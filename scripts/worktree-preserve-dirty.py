#!/usr/bin/env python3
"""Preserve bounded tracked worktree debt as owner-blocker receipts.

This is a custody helper, not a cleanup helper. It captures a private,
content-addressed patch and bounded public metadata for dirty worktrees, then
records an owner-blocker receipt in docs/worktree-preservation-receipts.json.
Physical removal still belongs to the reclaim acceptance surface after an
owner decision.

The helper fails closed before writing any durable artifact when a worktree
contains untracked paths, a patch exceeds the per-item byte ceiling, or the
aggregate patch set exceeds the invocation ceiling.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import selectors
import shutil
import subprocess
import sys
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


def prepare_item(
    item: dict[str, Any],
    staging_root: Path,
    max_patch_bytes: int,
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
    if untracked_paths:
        raise PreservationError(
            f"{path}: {len(untracked_paths)} untracked path(s) are not representable by "
            "git diff --binary HEAD; no custody receipt was written"
        )

    path_digest = sha256_text(str(path.resolve()))
    staged_patch = staging_root / f"{safe_name(root)}-{path_digest[:12]}.patch"
    capture = stream_git_patch(path, staged_patch, max_patch_bytes)
    if capture["bytes"] <= 0:
        raise PreservationError(f"{path}: tracked dirty classification produced an empty patch")
    verification_patch = staged_patch.with_suffix(".verify.patch")
    try:
        verification_capture = stream_git_patch(path, verification_patch, max_patch_bytes)
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
            or post_untracked_paths
            or capture != verification_capture
        ):
            raise PreservationError(
                f"{path}: worktree identity or content changed during capture; retry from fresh state"
            )
    except (OSError, PreservationError):
        staged_patch.unlink(missing_ok=True)
        raise
    finally:
        verification_patch.unlink(missing_ok=True)

    private_dir_name = f"{safe_name(root)}-{path_digest[:8]}-{capture['sha256'][:16]}"
    private_dir = PRIVATE_ROOT / private_dir_name
    private_patch = private_dir / "dirty.patch"
    private_receipt = private_dir / "receipt.json"
    receipt = {
        "branch": branch,
        "classification": "bounded tracked worktree patch privately preserved; owner decision required",
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
            "A bounded private tracked patch/status receipt exists; create a narrow owner packet to "
            "review, push, supersede, or retire this preserved dirty state."
        ),
        "private_patch": rel_to_root(private_patch),
        "private_patch_sha256": capture["sha256"],
        "private_receipt": rel_to_root(private_receipt),
        "repo": repo_slug(remote) or remote,
        "root": root,
        "status": "private_patch_preserved",
        "untracked_paths_count": 0,
        "untracked_paths_sha256": sha256_text(""),
        "untracked_paths_sample": [],
        "worktree": str(path),
        "worktree_status_count": len(status_lines),
        "worktree_status_sample": status_lines[:PUBLIC_SAMPLE_LIMIT],
        "worktree_status_sha256": sha256_text("\n".join(status_lines)),
    }
    return {
        "dirty_paths": dirty_paths,
        "receipt": receipt,
        "staged_patch": staged_patch,
        "status_branch": status_branch,
        "untracked_paths": untracked_paths,
    }


def candidate_receipt(existing: dict[str, Any] | None, prepared: dict[str, Any]) -> dict[str, Any]:
    candidate = dict(existing or {})
    for field in PUBLIC_REMOVED_FIELDS:
        candidate.pop(field, None)
    candidate.update(prepared["receipt"])
    candidate["evidence_updated_utc"] = str((existing or {}).get("evidence_updated_utc") or utc_now())
    return candidate


def private_paths(receipt: dict[str, Any]) -> tuple[Path, Path]:
    patch = ROOT / str(receipt["private_patch"])
    private_receipt = ROOT / str(receipt["private_receipt"])
    return patch, private_receipt


def private_artifacts_valid(receipt: dict[str, Any]) -> bool:
    patch, private_receipt = private_paths(receipt)
    required = {
        patch,
        private_receipt,
        patch.parent / "status-branch.txt",
        patch.parent / "dirty-paths.txt",
        patch.parent / "untracked-paths.txt",
    }
    if not all(path.is_file() for path in required):
        return False
    try:
        private_payload = json.loads(private_receipt.read_text(encoding="utf-8"))
        return file_sha256(patch) == receipt.get("private_patch_sha256") and private_payload == receipt
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
    private_patch, private_receipt = private_paths(receipt)
    private_dir = private_patch.parent
    if private_dir.exists():
        if private_artifacts_valid(receipt):
            return None
        raise PreservationError(
            f"content-addressed private directory exists but is incomplete or mismatched: {private_dir}"
        )

    private_dir.mkdir(parents=True)
    created = private_dir
    try:
        temporary_patch = private_dir / ".dirty.patch.tmp"
        shutil.copyfile(prepared["staged_patch"], temporary_patch)
        if file_sha256(temporary_patch) != receipt["private_patch_sha256"]:
            raise PreservationError(f"private patch copy digest mismatch: {private_dir}")
        os.replace(temporary_patch, private_patch)
        atomic_write_text(private_dir / "status-branch.txt", prepared["status_branch"])
        atomic_write_text(private_dir / "dirty-paths.txt", "\n".join(prepared["dirty_paths"]) + "\n")
        atomic_write_text(private_dir / "untracked-paths.txt", "")
        atomic_write_text(private_receipt, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
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
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be non-negative")
    if not 1 <= args.max_patch_bytes <= MAX_PATCH_BYTES:
        parser.error(f"--max-patch-bytes must be between 1 and {MAX_PATCH_BYTES}")
    if not 1 <= args.max_total_patch_bytes <= MAX_TOTAL_PATCH_BYTES:
        parser.error(f"--max-total-patch-bytes must be between 1 and {MAX_TOTAL_PATCH_BYTES}")
    if args.max_patch_bytes > args.max_total_patch_bytes:
        parser.error("--max-patch-bytes cannot exceed --max-total-patch-bytes")
    return args


def main() -> int:
    args = parse_args()
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
        "prepared": 0,
        "requested": len(dirty),
        "roots": [],
        "total_patch_bytes": 0,
        "updated": 0,
        "would_update": 0,
    }
    try:
        with tempfile.TemporaryDirectory(prefix="limen-worktree-preserve-") as temporary:
            staging_root = Path(temporary)
            prepared_items: list[dict[str, Any]] = []
            for item in dirty:
                prepared = prepare_item(item, staging_root, args.max_patch_bytes)
                total = payload["total_patch_bytes"] + int(prepared["receipt"]["dirty_patch_bytes"])
                if total > args.max_total_patch_bytes:
                    raise PreservationError(
                        f"aggregate tracked patches exceed the {args.max_total_patch_bytes}-byte "
                        "invocation ceiling; no custody receipt was written"
                    )
                payload["total_patch_bytes"] = total
                prepared_items.append(prepared)

            data = load_receipts()
            receipt_rows = data["receipts"]
            by_root = {
                str(row.get("root")): (index, row)
                for index, row in enumerate(receipt_rows)
                if isinstance(row, dict) and row.get("root")
            }
            candidates: list[tuple[int | None, dict[str, Any], dict[str, Any]]] = []
            for prepared in prepared_items:
                root = str(prepared["receipt"]["root"])
                index, existing = by_root.get(root, (None, None))
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
