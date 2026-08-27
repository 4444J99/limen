#!/usr/bin/env python3
"""Preserve bounded tracked worktree debt as owner-blocker receipts.

This is a custody helper, not a cleanup helper. It captures a private,
content-addressed tracked patch plus a deterministic archive of untracked
content and bounded public metadata for dirty worktrees, then records an
owner-blocker receipt in docs/worktree-preservation-receipts.json.
Physical removal still belongs to the reclaim acceptance surface after an
owner decision.

The helper fails closed before writing any durable artifact when tracked or
untracked content exceeds its byte ceiling, changes during capture, cannot be
read back from the private archive, or the aggregate set exceeds the
invocation ceilings.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import selectors
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.worktree_debt import worktree_debt_report

PRESERVATION_RECEIPTS = ROOT / "docs" / "worktree-preservation-receipts.json"
PRIVATE_ROOT = ROOT / ".limen-private" / "session-corpus" / "lifecycle" / "worktree-preserve"
REMOTE_RE = re.compile(r"(?:github\.com[:/])([^/\s]+)/([^/\s]+?)(?:\.git)?$")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")

MAX_PATCH_BYTES = 64 * 1024 * 1024
MAX_TOTAL_PATCH_BYTES = 128 * 1024 * 1024
MAX_UNTRACKED_BYTES = 512 * 1024 * 1024
MAX_TOTAL_UNTRACKED_BYTES = 1024 * 1024 * 1024
MAX_METADATA_BYTES = 4 * 1024 * 1024
PATCH_CHUNK_BYTES = 1024 * 1024
MAX_STDERR_BYTES = 4096
PUBLIC_SAMPLE_LIMIT = 25
PUBLIC_REMOVED_FIELDS = {"dirty_paths", "untracked_paths", "worktree_status"}


class PreservationError(RuntimeError):
    """A fail-closed custody refusal."""


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(value: str) -> str:
    cleaned = SAFE_NAME_RE.sub("-", value.strip()).strip("-._")
    return cleaned[:80] or "worktree"


def run_git(path: Path, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))
    if len(proc.stdout.encode("utf-8", errors="replace")) > MAX_METADATA_BYTES:
        return subprocess.CompletedProcess(
            proc.args,
            1,
            "",
            f"git {' '.join(args)} exceeded the {MAX_METADATA_BYTES}-byte metadata ceiling",
        )
    if len(proc.stderr.encode("utf-8", errors="replace")) > MAX_METADATA_BYTES:
        return subprocess.CompletedProcess(
            proc.args,
            1,
            "",
            f"git {' '.join(args)} stderr exceeded the {MAX_METADATA_BYTES}-byte metadata ceiling",
        )
    return proc


def run_git_checked(path: Path, args: list[str], timeout: int = 60) -> str:
    proc = run_git(path, args, timeout=timeout)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or f"exit {proc.returncode}"
        raise PreservationError(f"{path}: git {' '.join(args)} failed: {detail}")
    return proc.stdout


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(PATCH_CHUNK_BYTES), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_slug(remote: str) -> str | None:
    match = REMOTE_RE.search(remote.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def git_z_paths(path: Path, args: list[str], timeout: int = 60) -> list[str]:
    output = run_git_checked(path, [*args, "-z"], timeout=timeout)
    return [value for value in output.split("\0") if value]


def load_receipts() -> dict[str, Any]:
    try:
        data = json.loads(PRESERVATION_RECEIPTS.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"generated_utc": utc_now(), "receipts": []}
    except (OSError, json.JSONDecodeError) as exc:
        raise PreservationError(f"cannot read preservation ledger {PRESERVATION_RECEIPTS}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("receipts"), list):
        raise PreservationError(f"invalid preservation ledger shape: {PRESERVATION_RECEIPTS}")
    return data


def rel_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except (OSError, ValueError):
        return str(path)


def stop_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except ProcessLookupError:
            return
        proc.wait(timeout=2)


def stream_git_patch(path: Path, destination: Path, max_bytes: int, timeout: int = 180) -> dict[str, Any]:
    """Stream ``git diff --binary HEAD`` without materializing it in memory."""

    if max_bytes <= 0 or max_bytes > MAX_PATCH_BYTES:
        raise PreservationError(f"patch byte ceiling must be between 1 and {MAX_PATCH_BYTES}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    proc: subprocess.Popen[bytes] | None = None
    selector = selectors.DefaultSelector()
    stderr = bytearray()
    digest = hashlib.sha256()
    total = 0
    deadline = time.monotonic() + timeout
    try:
        with destination.open("xb") as output:
            proc = subprocess.Popen(
                ["git", "-C", str(path), "diff", "--binary", "HEAD"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert proc.stdout is not None
            assert proc.stderr is not None
            selector.register(proc.stdout, selectors.EVENT_READ, "stdout")
            selector.register(proc.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PreservationError(f"{path}: git diff timed out after {timeout}s")
                events = selector.select(timeout=min(1.0, remaining))
                if not events:
                    continue
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), PATCH_CHUNK_BYTES)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "stderr":
                        available = MAX_STDERR_BYTES - len(stderr)
                        if available > 0:
                            stderr.extend(chunk[:available])
                        continue
                    if total + len(chunk) > max_bytes:
                        raise PreservationError(f"{path}: tracked patch exceeds the {max_bytes}-byte per-item ceiling")
                    output.write(chunk)
                    digest.update(chunk)
                    total += len(chunk)
            returncode = proc.wait(timeout=max(1.0, deadline - time.monotonic()))
            if returncode != 0:
                detail = stderr.decode("utf-8", errors="replace").strip() or f"exit {returncode}"
                raise PreservationError(f"{path}: git diff --binary HEAD failed: {detail}")
            output.flush()
            os.fsync(output.fileno())
        return {"bytes": total, "sha256": digest.hexdigest()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreservationError(f"{path}: cannot capture tracked patch: {exc}") from exc
    finally:
        selector.close()
        if proc is not None:
            stop_process(proc)
        if sys.exc_info()[0] is not None:
            destination.unlink(missing_ok=True)


def _safe_untracked_relative(value: str) -> Path:
    relative = Path(value)
    if not value or relative.is_absolute() or "\x00" in value or ".." in relative.parts:
        raise PreservationError(f"unsafe untracked path returned by Git: {value!r}")
    return relative


def _untracked_entries(worktree: Path, untracked_paths: list[str]) -> list[tuple[str, Path, os.stat_result]]:
    """Expand Git's untracked leaves without following symlinks or escaping the worktree."""

    root = worktree.resolve()
    entries: dict[str, tuple[Path, os.stat_result]] = {}

    def visit(relative: Path) -> None:
        source = worktree / relative
        try:
            source_parent = source.parent.resolve(strict=True)
            source_parent.relative_to(root)
            info = source.lstat()
        except (OSError, ValueError) as exc:
            raise PreservationError(f"{worktree}: cannot safely inspect untracked path {relative}: {exc}") from exc
        archive_name = relative.as_posix().rstrip("/")
        if not archive_name:
            raise PreservationError(f"{worktree}: untracked path resolved to the worktree root")
        entries[archive_name] = (source, info)
        if stat.S_ISDIR(info.st_mode):
            try:
                children = sorted(source.iterdir(), key=lambda item: os.fsencode(item.name))
            except OSError as exc:
                raise PreservationError(f"{worktree}: cannot enumerate untracked directory {relative}: {exc}") from exc
            for child in children:
                visit(relative / child.name)

    for value in sorted(set(untracked_paths), key=os.fsencode):
        relative = _safe_untracked_relative(value)
        if any(parent.as_posix() in entries for parent in relative.parents if parent != Path(".")):
            continue
        visit(relative)
    return [(name, *entries[name]) for name in sorted(entries, key=os.fsencode)]


def capture_untracked_archive(
    worktree: Path,
    untracked_paths: list[str],
    destination: Path,
    max_bytes: int,
) -> dict[str, Any]:
    """Write a deterministic tar archive and return its private manifest."""

    if max_bytes <= 0 or max_bytes > MAX_UNTRACKED_BYTES:
        raise PreservationError(f"untracked byte ceiling must be between 1 and {MAX_UNTRACKED_BYTES}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    payload_bytes = 0
    try:
        entries = _untracked_entries(worktree, untracked_paths)
        with tarfile.open(destination, mode="x", format=tarfile.PAX_FORMAT) as archive:
            for name, source, info in entries:
                member = tarfile.TarInfo(name=name)
                member.uid = 0
                member.gid = 0
                member.uname = ""
                member.gname = ""
                member.mtime = 0
                member.mode = stat.S_IMODE(info.st_mode)
                row: dict[str, Any] = {"mode": member.mode, "path": name}
                if stat.S_ISREG(info.st_mode):
                    size = int(info.st_size)
                    if payload_bytes + size > max_bytes:
                        raise PreservationError(
                            f"{worktree}: untracked payload exceeds the {max_bytes}-byte per-item ceiling"
                        )
                    with source.open("rb") as handle:
                        body = handle.read(max_bytes + 1)
                    if len(body) != size:
                        raise PreservationError(f"{worktree}: untracked file changed while reading: {name}")
                    payload_bytes += size
                    member.size = size
                    archive.addfile(member, io.BytesIO(body))
                    row.update({"sha256": sha256_bytes(body), "size": size, "type": "file"})
                elif stat.S_ISLNK(info.st_mode):
                    target = os.readlink(source)
                    encoded_target = os.fsencode(target)
                    if payload_bytes + len(encoded_target) > max_bytes:
                        raise PreservationError(
                            f"{worktree}: untracked payload exceeds the {max_bytes}-byte per-item ceiling"
                        )
                    payload_bytes += len(encoded_target)
                    member.type = tarfile.SYMTYPE
                    member.linkname = target
                    archive.addfile(member)
                    row.update(
                        {
                            "sha256": sha256_bytes(encoded_target),
                            "size": len(encoded_target),
                            "target": target,
                            "type": "symlink",
                        }
                    )
                elif stat.S_ISDIR(info.st_mode):
                    member.type = tarfile.DIRTYPE
                    archive.addfile(member)
                    row.update({"sha256": sha256_bytes(b""), "size": 0, "type": "directory"})
                else:
                    raise PreservationError(f"{worktree}: unsupported untracked file type: {name}")
                manifest.append(row)
        return {
            "archive_bytes": destination.stat().st_size,
            "archive_sha256": file_sha256(destination),
            "entry_count": len(manifest),
            "manifest": manifest,
            "manifest_sha256": sha256_text(json.dumps(manifest, sort_keys=True, separators=(",", ":"))),
            "payload_bytes": payload_bytes,
        }
    except (OSError, tarfile.TarError, PreservationError) as exc:
        destination.unlink(missing_ok=True)
        if isinstance(exc, PreservationError):
            raise
        raise PreservationError(f"{worktree}: cannot capture untracked archive: {exc}") from exc


def verify_untracked_archive(archive_path: Path, manifest: list[dict[str, Any]]) -> bool:
    """Read every archived entry and verify its path, type, mode, size, and digest."""

    expected = {str(row.get("path")): row for row in manifest}
    if len(expected) != len(manifest) or any(not name for name in expected):
        return False
    try:
        with tarfile.open(archive_path, mode="r:") as archive:
            members = archive.getmembers()
            if len(members) != len(expected) or {member.name for member in members} != set(expected):
                return False
            for member in members:
                row = expected[member.name]
                if member.mode != row.get("mode"):
                    return False
                row_type = row.get("type")
                if row_type == "file" and member.isfile():
                    handle = archive.extractfile(member)
                    if handle is None:
                        return False
                    digest = hashlib.sha256()
                    size = 0
                    for chunk in iter(lambda: handle.read(PATCH_CHUNK_BYTES), b""):
                        digest.update(chunk)
                        size += len(chunk)
                    if size != row.get("size") or digest.hexdigest() != row.get("sha256"):
                        return False
                elif row_type == "symlink" and member.issym():
                    target = member.linkname
                    if target != row.get("target") or sha256_bytes(os.fsencode(target)) != row.get("sha256"):
                        return False
                elif row_type == "directory" and member.isdir():
                    if row.get("size") != 0 or row.get("sha256") != sha256_bytes(b""):
                        return False
                else:
                    return False
    except (OSError, tarfile.TarError, KeyError, TypeError):
        return False
    return True


def prepare_item(
    item: dict[str, Any],
    staging_root: Path,
    max_patch_bytes: int,
    max_untracked_bytes: int = MAX_UNTRACKED_BYTES,
) -> dict[str, Any]:
    path = Path(str(item["path"]))
    root = str(item.get("name") or path.name)
    if not path.is_dir():
        raise PreservationError(f"{path}: worktree directory is missing")
    branch = run_git_checked(path, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    head = run_git_checked(path, ["rev-parse", "HEAD"]).strip()
    remote = run_git_checked(path, ["remote", "get-url", "origin"]).strip()
    status_branch = run_git_checked(
        path,
        ["status", "--short", "--branch", "--untracked-files=no"],
        timeout=120,
    )
    status_lines = [line for line in status_branch.splitlines() if line]
    dirty_paths = git_z_paths(path, ["diff", "--name-only", "HEAD"], timeout=120)
    untracked_paths = git_z_paths(path, ["ls-files", "--others", "--exclude-standard"], timeout=120)

    path_digest = sha256_text(str(path.resolve()))
    staged_patch = staging_root / f"{safe_name(root)}-{path_digest[:12]}.patch"
    capture = stream_git_patch(path, staged_patch, max_patch_bytes)
    staged_archive: Path | None = None
    untracked_capture: dict[str, Any] = {
        "archive_bytes": 0,
        "archive_sha256": sha256_bytes(b""),
        "entry_count": 0,
        "manifest": [],
        "manifest_sha256": sha256_text("[]"),
        "payload_bytes": 0,
    }
    if untracked_paths:
        staged_archive = staging_root / f"{safe_name(root)}-{path_digest[:12]}.untracked.tar"
        untracked_capture = capture_untracked_archive(path, untracked_paths, staged_archive, max_untracked_bytes)
    if capture["bytes"] <= 0 and not untracked_paths:
        raise PreservationError(f"{path}: dirty classification produced no tracked or untracked content")
    verification_patch = staged_patch.with_suffix(".verify.patch")
    verification_archive = (
        staged_archive.with_suffix(".verify.tar") if staged_archive is not None else None
    )
    try:
        verification_capture = stream_git_patch(path, verification_patch, max_patch_bytes)
        verification_untracked_capture = (
            capture_untracked_archive(path, untracked_paths, verification_archive, max_untracked_bytes)
            if verification_archive is not None
            else untracked_capture
        )
        post_branch = run_git_checked(path, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()
        post_head = run_git_checked(path, ["rev-parse", "HEAD"]).strip()
        post_remote = run_git_checked(path, ["remote", "get-url", "origin"]).strip()
        post_status_branch = run_git_checked(
            path,
            ["status", "--short", "--branch", "--untracked-files=no"],
            timeout=120,
        )
        post_dirty_paths = git_z_paths(path, ["diff", "--name-only", "HEAD"], timeout=120)
        post_untracked_paths = git_z_paths(path, ["ls-files", "--others", "--exclude-standard"], timeout=120)
        if (
            branch != post_branch
            or head != post_head
            or remote != post_remote
            or status_branch != post_status_branch
            or dirty_paths != post_dirty_paths
            or untracked_paths != post_untracked_paths
            or capture != verification_capture
            or untracked_capture != verification_untracked_capture
        ):
            raise PreservationError(
                f"{path}: worktree identity or content changed during capture; retry from fresh state"
            )
        if staged_archive is not None and not verify_untracked_archive(
            staged_archive, untracked_capture["manifest"]
        ):
            raise PreservationError(f"{path}: untracked archive failed readback verification")
    except (OSError, PreservationError):
        staged_patch.unlink(missing_ok=True)
        if staged_archive is not None:
            staged_archive.unlink(missing_ok=True)
        raise
    finally:
        verification_patch.unlink(missing_ok=True)
        if verification_archive is not None:
            verification_archive.unlink(missing_ok=True)

    bundle_digest = sha256_text(f"{capture['sha256']}\n{untracked_capture['archive_sha256']}\n")
    private_dir_name = f"{safe_name(root)}-{path_digest[:8]}-{bundle_digest[:16]}"
    private_dir = PRIVATE_ROOT / private_dir_name
    private_patch = private_dir / "dirty.patch"
    private_untracked_archive = private_dir / "untracked.tar" if untracked_paths else None
    private_untracked_manifest = private_dir / "untracked-manifest.json" if untracked_paths else None
    private_receipt = private_dir / "receipt.json"
    receipt = {
        "branch": branch,
        "classification": (
            "bounded tracked patch and untracked archive privately preserved; owner decision required"
        ),
        "custody_bundle_sha256": bundle_digest,
        "dirty_patch_bytes": capture["bytes"],
        "dirty_patch_command": "git diff --binary HEAD",
        "dirty_patch_max_bytes": max_patch_bytes,
        "dirty_patch_sha256": capture["sha256"],
        "dirty_paths_count": len(dirty_paths),
        "dirty_paths_sha256": sha256_text("\n".join(sorted(dirty_paths))),
        "dirty_paths_sample": dirty_paths[:PUBLIC_SAMPLE_LIMIT],
        "head": head,
        "lane": "owner-blocker",
        "next_action": (
            "Do not delete, reclaim, force-push, or auto-port this worktree from lifecycle cleanup. "
            "A bounded private tracked patch/untracked archive receipt exists; create a narrow owner packet to "
            "review, push, supersede, or retire this preserved dirty state."
        ),
        "private_patch": rel_to_root(private_patch),
        "private_patch_sha256": capture["sha256"],
        "private_receipt": rel_to_root(private_receipt),
        "private_untracked_archive": (
            rel_to_root(private_untracked_archive) if private_untracked_archive is not None else None
        ),
        "private_untracked_manifest": (
            rel_to_root(private_untracked_manifest) if private_untracked_manifest is not None else None
        ),
        "repo": repo_slug(remote) or remote,
        "root": root,
        "status": "private_bundle_preserved",
        "untracked_archive_bytes": untracked_capture["archive_bytes"],
        "untracked_archive_sha256": untracked_capture["archive_sha256"],
        "untracked_entries_count": untracked_capture["entry_count"],
        "untracked_manifest_sha256": untracked_capture["manifest_sha256"],
        "untracked_paths_count": len(untracked_paths),
        "untracked_paths_sha256": sha256_text("\n".join(sorted(untracked_paths))),
        "untracked_paths_sample": [],
        "untracked_payload_bytes": untracked_capture["payload_bytes"],
        "worktree": str(path),
        "worktree_key": path_digest,
        "worktree_status_count": len(status_lines),
        "worktree_status_sample": status_lines[:PUBLIC_SAMPLE_LIMIT],
        "worktree_status_sha256": sha256_text("\n".join(status_lines)),
    }
    return {
        "dirty_paths": dirty_paths,
        "receipt": receipt,
        "staged_archive": staged_archive,
        "staged_patch": staged_patch,
        "status_branch": status_branch,
        "untracked_manifest": untracked_capture["manifest"],
        "untracked_paths": untracked_paths,
    }


def candidate_receipt(existing: dict[str, Any] | None, prepared: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(existing or {})
    for field in PUBLIC_REMOVED_FIELDS:
        candidate.pop(field, None)
    candidate.update(prepared["receipt"])
    candidate["evidence_updated_utc"] = str((existing or {}).get("evidence_updated_utc") or utc_now())
    return candidate


def private_paths(receipt: dict[str, Any]) -> tuple[Path, Path, Path | None, Path | None]:
    patch = ROOT / str(receipt["private_patch"])
    private_receipt = ROOT / str(receipt["private_receipt"])
    archive_value = receipt.get("private_untracked_archive")
    manifest_value = receipt.get("private_untracked_manifest")
    archive = ROOT / str(archive_value) if archive_value else None
    manifest = ROOT / str(manifest_value) if manifest_value else None
    return patch, private_receipt, archive, manifest


def private_artifacts_valid(receipt: dict[str, Any]) -> bool:
    patch, private_receipt, archive, manifest_path = private_paths(receipt)
    required = {
        patch,
        private_receipt,
        patch.parent / "status-branch.txt",
        patch.parent / "dirty-paths.txt",
        patch.parent / "untracked-paths.txt",
    }
    if receipt.get("untracked_paths_count"):
        if archive is None or manifest_path is None:
            return False
        required.update({archive, manifest_path})
    if not all(path.is_file() for path in required):
        return False
    try:
        private_payload = json.loads(private_receipt.read_text(encoding="utf-8"))
        if file_sha256(patch) != receipt.get("private_patch_sha256") or private_payload != receipt:
            return False
        if archive is None or manifest_path is None:
            return not receipt.get("untracked_paths_count")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return bool(
            isinstance(manifest, list)
            and file_sha256(archive) == receipt.get("untracked_archive_sha256")
            and sha256_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
            == receipt.get("untracked_manifest_sha256")
            and verify_untracked_archive(archive, manifest)
        )
    except (OSError, json.JSONDecodeError):
        return False


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        assert temporary is not None
        os.replace(temporary, path)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def write_private_artifacts(prepared: dict[str, Any], receipt: dict[str, Any]) -> Path | None:
    private_patch, private_receipt, private_archive, private_manifest = private_paths(receipt)
    private_dir = private_patch.parent
    if private_dir.exists():
        if private_artifacts_valid(receipt):
            return None
        raise PreservationError(
            f"content-addressed private directory exists but is incomplete or mismatched: {private_dir}"
        )

    private_dir.mkdir(parents=True, mode=0o700)
    private_dir.chmod(0o700)
    created = private_dir
    try:
        temporary_patch = private_dir / ".dirty.patch.tmp"
        shutil.copyfile(prepared["staged_patch"], temporary_patch)
        if file_sha256(temporary_patch) != receipt["private_patch_sha256"]:
            raise PreservationError(f"private patch copy digest mismatch: {private_dir}")
        os.replace(temporary_patch, private_patch)
        private_patch.chmod(0o600)
        atomic_write_text(private_dir / "status-branch.txt", prepared["status_branch"])
        atomic_write_text(private_dir / "dirty-paths.txt", "\n".join(prepared["dirty_paths"]) + "\n")
        atomic_write_text(
            private_dir / "untracked-paths.txt",
            "\n".join(prepared["untracked_paths"]) + ("\n" if prepared["untracked_paths"] else ""),
        )
        if prepared["staged_archive"] is not None:
            if private_archive is None or private_manifest is None:
                raise PreservationError(f"private untracked paths are absent from receipt: {private_dir}")
            temporary_archive = private_dir / ".untracked.tar.tmp"
            shutil.copyfile(prepared["staged_archive"], temporary_archive)
            if file_sha256(temporary_archive) != receipt["untracked_archive_sha256"]:
                raise PreservationError(f"private untracked archive copy digest mismatch: {private_dir}")
            os.replace(temporary_archive, private_archive)
            private_archive.chmod(0o600)
            atomic_write_text(
                private_manifest,
                json.dumps(prepared["untracked_manifest"], indent=2, sort_keys=True) + "\n",
            )
        atomic_write_text(private_receipt, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        if not private_artifacts_valid(receipt):
            raise PreservationError(f"private custody bundle failed readback verification: {private_dir}")
        return created
    except Exception:
        shutil.rmtree(created)
        raise


def remove_created_private_dirs(paths: list[Path]) -> None:
    private_root = PRIVATE_ROOT.resolve()
    for path in reversed(paths):
        try:
            path.resolve().relative_to(private_root)
        except (OSError, ValueError):
            continue
        if path.is_dir():
            shutil.rmtree(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write private receipts and update preservation ledger")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--limit", type=int, default=0, help="maximum dirty roots to preserve; 0 means all")
    parser.add_argument(
        "--worktree",
        action="append",
        type=Path,
        default=[],
        help="preserve this exact worktree instead of selecting dirty debt roots; repeatable",
    )
    parser.add_argument(
        "--max-patch-bytes",
        type=int,
        default=MAX_PATCH_BYTES,
        help=f"per-root tracked patch ceiling; cannot exceed {MAX_PATCH_BYTES}",
    )
    parser.add_argument(
        "--max-total-patch-bytes",
        type=int,
        default=MAX_TOTAL_PATCH_BYTES,
        help=f"aggregate invocation ceiling; cannot exceed {MAX_TOTAL_PATCH_BYTES}",
    )
    parser.add_argument(
        "--max-untracked-bytes",
        type=int,
        default=MAX_UNTRACKED_BYTES,
        help=f"per-root untracked payload ceiling; cannot exceed {MAX_UNTRACKED_BYTES}",
    )
    parser.add_argument(
        "--max-total-untracked-bytes",
        type=int,
        default=MAX_TOTAL_UNTRACKED_BYTES,
        help=f"aggregate untracked payload ceiling; cannot exceed {MAX_TOTAL_UNTRACKED_BYTES}",
    )
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    if not 1 <= args.max_patch_bytes <= MAX_PATCH_BYTES:
        parser.error(f"--max-patch-bytes must be between 1 and {MAX_PATCH_BYTES}")
    if not 1 <= args.max_total_patch_bytes <= MAX_TOTAL_PATCH_BYTES:
        parser.error(f"--max-total-patch-bytes must be between 1 and {MAX_TOTAL_PATCH_BYTES}")
    if args.max_patch_bytes > args.max_total_patch_bytes:
        parser.error("--max-patch-bytes cannot exceed --max-total-patch-bytes")
    if not 1 <= args.max_untracked_bytes <= MAX_UNTRACKED_BYTES:
        parser.error(f"--max-untracked-bytes must be between 1 and {MAX_UNTRACKED_BYTES}")
    if not 1 <= args.max_total_untracked_bytes <= MAX_TOTAL_UNTRACKED_BYTES:
        parser.error(
            f"--max-total-untracked-bytes must be between 1 and {MAX_TOTAL_UNTRACKED_BYTES}"
        )
    if args.max_untracked_bytes > args.max_total_untracked_bytes:
        parser.error("--max-untracked-bytes cannot exceed --max-total-untracked-bytes")
    return args


def main() -> int:
    args = parse_args()
    if args.worktree:
        resolved = [path.expanduser().resolve() for path in args.worktree]
        if len(resolved) != len(set(resolved)):
            print("duplicate --worktree target", file=sys.stderr)
            return 2
        dirty = [
            {"debt": True, "name": path.name, "path": str(path), "reason": "dirty"}
            for path in resolved
        ]
    else:
        report = worktree_debt_report(ROOT)
        dirty = [item for item in report.get("items", []) if item.get("reason") == "dirty" and item.get("debt")]
    if args.limit > 0:
        dirty = dirty[: args.limit]

    payload: dict[str, Any] = {
        "apply": bool(args.apply),
        "failed": 0,
        "failures": [],
        "max_patch_bytes": args.max_patch_bytes,
        "max_total_patch_bytes": args.max_total_patch_bytes,
        "max_total_untracked_bytes": args.max_total_untracked_bytes,
        "max_untracked_bytes": args.max_untracked_bytes,
        "prepared": 0,
        "requested": len(dirty),
        "roots": [],
        "total_patch_bytes": 0,
        "total_untracked_bytes": 0,
        "updated": 0,
        "would_update": 0,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="limen-worktree-preserve-") as temporary:
            staging_root = Path(temporary)
            prepared_items: list[dict[str, Any]] = []
            for item in dirty:
                prepared = prepare_item(
                    item,
                    staging_root,
                    args.max_patch_bytes,
                    args.max_untracked_bytes,
                )
                total_patch = payload["total_patch_bytes"] + int(prepared["receipt"]["dirty_patch_bytes"])
                if total_patch > args.max_total_patch_bytes:
                    raise PreservationError(
                        f"aggregate tracked patches exceed the {args.max_total_patch_bytes}-byte "
                        "invocation ceiling; no custody receipt was written"
                    )
                total_untracked = payload["total_untracked_bytes"] + int(
                    prepared["receipt"]["untracked_payload_bytes"]
                )
                if total_untracked > args.max_total_untracked_bytes:
                    raise PreservationError(
                        f"aggregate untracked payload exceeds the {args.max_total_untracked_bytes}-byte "
                        "invocation ceiling; no custody receipt was written"
                    )
                payload["total_patch_bytes"] = total_patch
                payload["total_untracked_bytes"] = total_untracked
                prepared_items.append(prepared)

            data = load_receipts()
            receipt_rows = data["receipts"]
            by_worktree_key: dict[str, tuple[int, dict[str, Any]]] = {}
            by_legacy_worktree: dict[str, tuple[int, dict[str, Any]]] = {}
            for index, row in enumerate(receipt_rows):
                if not isinstance(row, dict):
                    continue
                worktree_key = row.get("worktree_key")
                worktree = row.get("worktree")
                if isinstance(worktree_key, str) and worktree_key:
                    if worktree_key in by_worktree_key:
                        raise PreservationError(
                            f"duplicate worktree preservation identity in tracked ledger: {worktree_key}"
                        )
                    by_worktree_key[worktree_key] = (index, row)
                elif isinstance(worktree, str) and worktree:
                    resolved_worktree = str(Path(worktree).expanduser().resolve(strict=False))
                    if resolved_worktree in by_legacy_worktree:
                        raise PreservationError(
                            "duplicate legacy worktree path in tracked preservation ledger"
                        )
                    by_legacy_worktree[resolved_worktree] = (index, row)
            candidates: list[tuple[int | None, dict[str, Any], dict[str, Any]]] = []
            for prepared in prepared_items:
                receipt = prepared["receipt"]
                worktree_key = str(receipt["worktree_key"])
                worktree = str(Path(str(receipt["worktree"])).resolve(strict=False))
                index, existing = by_worktree_key.get(
                    worktree_key,
                    by_legacy_worktree.get(worktree, (None, None)),
                )
                candidate = candidate_receipt(existing, prepared)
                artifacts_valid = private_artifacts_valid(candidate)
                if existing != candidate or not artifacts_valid:
                    candidate["evidence_updated_utc"] = utc_now()
                    payload["would_update"] += 1
                candidates.append((index, prepared, candidate))

            payload["prepared"] = len(prepared_items)
            payload["roots"] = [item["receipt"]["root"] for item in prepared_items]
            if args.apply and candidates:
                created_dirs: list[Path] = []
                try:
                    for _, prepared, candidate in candidates:
                        created = write_private_artifacts(prepared, candidate)
                        if created is not None:
                            created_dirs.append(created)
                    changed = 0
                    for index, _, candidate in candidates:
                        if index is None:
                            receipt_rows.append(candidate)
                            changed += 1
                        elif receipt_rows[index] != candidate:
                            receipt_rows[index] = candidate
                            changed += 1
                    if changed:
                        data["generated_utc"] = utc_now()
                        atomic_write_text(
                            PRESERVATION_RECEIPTS,
                            json.dumps(data, indent=2, sort_keys=True) + "\n",
                        )
                    payload["updated"] = max(changed, len(created_dirs))
                except Exception:
                    remove_created_private_dirs(created_dirs)
                    raise
    except (OSError, PreservationError) as exc:
        payload["failed"] = 1
        payload["failures"] = [str(exc)]

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "APPLY" if args.apply else "dry-run"
        print(
            f"worktree dirty preserve [{mode}]: {payload['prepared']}/{payload['requested']} "
            f"root(s), updated {payload['updated']}, failed {payload['failed']}"
        )
        for root in payload["roots"][:40]:
            print(f"  {root}")
        for failure in payload["failures"]:
            print(f"  FAIL: {failure}", file=sys.stderr)
    return 1 if payload["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
