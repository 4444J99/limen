#!/usr/bin/env python3
"""Preserve unpublished legacy ARCA ciphertext as encrypted-catalog release assets.

This copies no plaintext and writes no Git objects. It describes ciphertext blobs unique to
the local ARCA branch in a GPG-encrypted catalog, then delegates neutral asset upload and
readback to arca-release-assets.py. Source commit and files remain untouched.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_VAULT = ROOT / "scripts" / "private-vault.py"
ASSET_PUBLISHER = ROOT / "scripts" / "arca-release-assets.py"


class PreserveError(RuntimeError):
    pass


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise PreserveError(f"required ARCA component unavailable: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRIVATE = _module("arca_private_vault", PRIVATE_VAULT)
PUBLISHER = _module("arca_release_assets", ASSET_PUBLISHER)


def _git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise PreserveError("local ARCA Git inspection failed; source remains untouched") from exc
    if result.returncode:
        raise PreserveError("local ARCA Git inspection failed; source remains untouched")
    return result.stdout


def _sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return digest.hexdigest(), size


def _git_object_oid(kind: str, payload: bytes, object_format: str) -> str:
    if object_format not in {"sha1", "sha256"}:
        raise PreserveError("unsupported Git object format; source retained")
    digest = hashlib.new(object_format)
    digest.update(f"{kind} {len(payload)}\0".encode("ascii"))
    digest.update(payload)
    return digest.hexdigest()


def _write_object(repo: Path, kind: str, source: Path | bytes) -> str:
    command = ["git", "-C", str(repo), "hash-object", "-w", "-t", kind, "--stdin"]
    try:
        if isinstance(source, Path):
            with source.open("rb") as stream:
                result = subprocess.run(command, stdin=stream, capture_output=True, check=False, timeout=900)
        else:
            result = subprocess.run(command, input=source, capture_output=True, check=False, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PreserveError("isolated Git object reconstruction failed") from exc
    if result.returncode:
        raise PreserveError("isolated Git object reconstruction failed")
    return result.stdout.decode("ascii").strip()


def preserve(root: Path, remote: str, *, output: Path, apply: bool = False) -> dict[str, object]:
    root = root.resolve()
    if not (root / ".git").exists():
        raise PreserveError("source must be a Git checkout")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all").strip():
        raise PreserveError("ARCA checkout is dirty; refusing an ambiguous source snapshot")
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    base = _git(root, "rev-parse", "refs/remotes/origin/main").decode().strip()
    merge = _git(root, "merge-base", "HEAD", "refs/remotes/origin/main").decode().strip()
    if head == base or not merge or not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise PreserveError("no unpublished local ARCA commit is present")
    object_rows = _git(root, "rev-list", "--objects", "refs/remotes/origin/main..HEAD").splitlines()
    object_ids = [line.split(b" ", 1)[0].decode("ascii") for line in object_rows]
    if not object_ids:
        raise PreserveError("local ARCA branch contains no unpublished objects")
    check = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch-check=%(objecttype) %(objectsize)"],
        input=("\n".join(object_ids) + "\n").encode(),
        capture_output=True,
        check=False,
        timeout=120,
    )
    if check.returncode:
        raise PreserveError("cannot classify unpublished Git objects")
    object_format = _git(root, "rev-parse", "--show-object-format").decode().strip()
    if object_format not in {"sha1", "sha256"}:
        raise PreserveError("unsupported Git object format; source retained")
    new_blobs: set[str] = set()
    metadata_objects: list[dict[str, object]] = []
    metadata_bytes = 0
    for oid, row in zip(object_ids, check.stdout.decode().splitlines(), strict=True):
        kind, separator, size_text = row.partition(" ")
        if not separator or kind not in {"blob", "commit", "tree", "tag"} or not size_text.isdecimal():
            raise PreserveError("unclassified unpublished Git object; source retained")
        if kind == "blob":
            new_blobs.add(oid)
            continue
        size = int(size_text)
        metadata_bytes += size
        if metadata_bytes > 16 * 1024 * 1024:
            raise PreserveError("Git metadata closure exceeds encrypted catalog bound")
        payload = _git(root, "cat-file", kind, oid)
        if len(payload) != size or _git_object_oid(kind, payload, object_format) != oid:
            raise PreserveError("Git metadata object failed exact identity verification")
        metadata_objects.append(
            {
                "oid": oid,
                "type": kind,
                "bytes": size,
                "raw_b64": base64.b64encode(payload).decode("ascii"),
            }
        )

    entries: list[dict[str, object]] = []
    paths: list[Path] = []
    embedded_manifest: str | None = None
    embedded_manifest_oid: str | None = None
    rows = _git(root, "ls-tree", "-r", "-z", "HEAD").split(b"\0")
    matched: set[str] = set()
    for row in filter(None, rows):
        metadata, raw_path = row.split(b"\t", 1)
        mode, kind, oid_b = metadata.split()
        oid = oid_b.decode("ascii")
        if kind != b"blob" or oid not in new_blobs:
            continue
        rel = raw_path.decode("utf-8", "surrogateescape")
        path = root / rel
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise PreserveError("ciphertext source is not a regular file; refusing partial preservation")
        actual_git_oid = _git(root, "hash-object", "--no-filters", "--", rel).decode().strip()
        if actual_git_oid != oid:
            raise PreserveError("working ciphertext differs from its committed blob; source remains untouched")
        sha256, size = _sha256(path)
        if size == 0:
            raise PreserveError("empty ciphertext blob found; refusing partial preservation")
        if rel == "manifest.json":
            if embedded_manifest is not None or size > 1024 * 1024:
                raise PreserveError("legacy manifest is duplicated or exceeds the bounded catalog metadata limit")
            embedded_manifest = base64.b64encode(path.read_bytes()).decode("ascii")
            embedded_manifest_oid = oid
            matched.add(oid)
            continue
        if not (rel.endswith(".tar.enc") or re.search(r"\.tar\.enc\.part\.[a-z]+$", rel)):
            raise PreserveError("unpublished ARCA commit contains an unsupported non-ciphertext blob")
        entries.append({"path": rel, "git_blob": oid, "sha256": sha256, "bytes": size, "mode": int(mode, 8)})
        paths.append(path)
        matched.add(oid)
    if matched != new_blobs or not entries:
        raise PreserveError("not every unpublished blob is represented by an encrypted payload path")
    entries.sort(key=lambda entry: str(entry["path"]))
    # Wrap every legacy byte stream, including split AES segments, in the same
    # independently inspectable pinned-recipient envelope as native file objects.
    # The inner Git identity is retained; reconstruction removes only this layer.
    output = output.expanduser().resolve()
    if output.exists() or output.is_symlink():
        raise PreserveError("catalog already exists; retain it for explicit resume")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    transport = output.parent / f"{output.name}.objects"
    if transport.is_symlink() or transport.exists():
        raise PreserveError("transport capture already exists; retain it for explicit resume")
    transport.mkdir(mode=0o700)
    wrapped_paths: list[Path] = []
    for index, entry in enumerate(entries):
        source = root / str(entry["path"])
        target = transport / f"{index:08d}.gpg"
        PRIVATE._encrypt_file(source, target)
        os.chmod(target, 0o600)
        if _sha256(source) != (entry["sha256"], entry["bytes"]):
            raise PreserveError("source changed during envelope creation; capture retained")
        digest, size = _sha256(target)
        entry["transport"] = {"encryption": "openpgp", "sha256": digest, "bytes": size}
        wrapped_paths.append(target)
    paths = wrapped_paths
    catalog = {
        "schema": "arca-legacy-ciphertext-catalog-v1",
        "source_commit": head,
        "source_base": base,
        "git_object_format": object_format,
        "git_metadata_objects": metadata_objects,
        "git_closure_scope": "origin-main-excluded-to-head",
        "entries": entries,
    }
    if embedded_manifest is not None:
        catalog["legacy_manifest_json_b64"] = embedded_manifest
        catalog["legacy_manifest_git_blob"] = embedded_manifest_oid
    with tempfile.TemporaryDirectory(prefix="arca-cipher-catalog-") as temp:
        os.chmod(temp, 0o700)
        plaintext = Path(temp) / "catalog.json"
        plaintext.write_text(
            json.dumps(catalog, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(plaintext, 0o600)
        partial = output.with_name(f".{output.name}.partial")
        PRIVATE._encrypt_file(plaintext, partial)
        if not partial.is_file() or partial.stat().st_size == 0:
            raise PreserveError("encrypted catalog could not be verified as a non-empty file")
        os.chmod(partial, 0o600)
        os.replace(partial, output)
    result: dict[str, object] = {
        "state": "catalog-ready",
        "git_identity_verified": True,
        "files": len(paths),
        "bytes": sum(int(entry["bytes"]) for entry in entries),
        "catalog_sha256": _sha256(output)[0],
    }
    if apply:
        expected = {path: str(entry["transport"]["sha256"]) for path, entry in zip(paths, entries, strict=True)}
        result["publication"] = PUBLISHER.publish(remote, output, paths, apply=True, expected_digests=expected)
    else:
        expected = {path: str(entry["transport"]["sha256"]) for path, entry in zip(paths, entries, strict=True)}
        result["publication"] = PUBLISHER.publish(remote, output, paths, apply=False, expected_digests=expected)
    return result


def resume_existing(
    root: Path,
    remote: str,
    *,
    catalog: Path,
    expected_head: str,
    expected_catalog_sha256: str,
    expected_files: int,
    expected_bytes: int,
    apply: bool = False,
    verify_existing_by_server_digest: bool = False,
    batch_deadline_seconds: int = PUBLISHER.BATCH_DEADLINE_SECONDS,
) -> dict[str, object]:
    """Resume a fixed encrypted catalog without generating a new release tag."""
    root = root.resolve()
    if not re.fullmatch(r"[0-9a-f]{40,64}", expected_head):
        raise PreserveError("expected source commit is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_catalog_sha256):
        raise PreserveError("expected encrypted catalog digest is invalid")
    if expected_files <= 0 or expected_bytes <= 0:
        raise PreserveError("expected ciphertext extent is invalid")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all").strip():
        raise PreserveError("ARCA checkout is dirty; source retained")
    if _git(root, "rev-parse", "HEAD").decode().strip() != expected_head:
        raise PreserveError("ARCA source commit changed; source retained")
    if _sha256(catalog)[0] != expected_catalog_sha256:
        raise PreserveError("encrypted catalog changed; source retained")
    names = _git(
        root,
        "diff",
        "--name-only",
        "--diff-filter=AMR",
        "-z",
        "refs/remotes/origin/main",
        "HEAD",
    ).split(b"\0")
    paths: list[Path] = []
    expected: dict[Path, str] = {}
    total = 0
    for raw in filter(None, names):
        rel = raw.decode("utf-8", "surrogateescape")
        if rel == "manifest.json":
            continue
        if not (rel.endswith(".tar.enc") or re.search(r"\.tar\.enc\.part\.[a-z]+$", rel)):
            raise PreserveError("source delta contains unsupported material")
        path = root / rel
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise PreserveError("ciphertext source is not a regular file")
        oid = _git(root, "rev-parse", f"HEAD:{rel}").decode().strip()
        if _git(root, "hash-object", "--no-filters", "--", rel).decode().strip() != oid:
            raise PreserveError("ciphertext differs from committed source")
        digest, size = _sha256(path)
        paths.append(path)
        expected[path] = digest
        total += size
    if len(paths) != expected_files or total != expected_bytes:
        raise PreserveError("ciphertext extent differs from fixed catalog receipt")
    transport = catalog.parent / f"{catalog.name}.objects"
    if transport.exists() or transport.is_symlink():
        if transport.is_symlink() or not transport.is_dir():
            raise PreserveError("transport capture is unsafe")
        with tempfile.TemporaryDirectory(prefix="arca-resume-catalog-") as temp:
            plaintext = Path(temp) / "catalog.json"
            PRIVATE._decrypt_file(catalog, plaintext)
            try:
                captured = json.loads(plaintext.read_text())
                rows = captured["entries"]
                if captured["source_commit"] != expected_head or len(rows) != len(paths):
                    raise ValueError("identity mismatch")
                wrapped: list[Path] = []
                wrapped_digests: dict[Path, str] = {}
                for index, row in enumerate(rows):
                    source = root / row["path"]
                    if source not in expected or expected[source] != row["sha256"]:
                        raise ValueError("source mismatch")
                    envelope = row["transport"]
                    target = transport / f"{index:08d}.gpg"
                    if (
                        envelope["encryption"] != "openpgp"
                        or target.is_symlink()
                        or _sha256(target) != (envelope["sha256"], envelope["bytes"])
                    ):
                        raise ValueError("envelope mismatch")
                    wrapped.append(target)
                    wrapped_digests[target] = envelope["sha256"]
                if len({row["path"] for row in rows}) != len(paths):
                    raise ValueError("duplicate source")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                raise PreserveError("transport capture differs from the encrypted catalog") from exc
        paths, expected = wrapped, wrapped_digests
    return PUBLISHER.publish(
        remote,
        catalog,
        paths,
        apply=apply,
        expected_digests=expected,
        verify_existing_by_server_digest=verify_existing_by_server_digest,
        batch_deadline_seconds=batch_deadline_seconds,
    )


def reconstruct(catalog_path: Path, assets: Path, base_repo: str, destination: Path) -> dict[str, object]:
    """Restore the original Git object IDs into an isolated new bare repository."""
    if destination.exists() or destination.is_symlink():
        raise PreserveError("reconstruction destination already exists")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arca-git-reconstruct-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "repository.git"
        plaintext = Path(temporary) / "catalog.json"
        PRIVATE._decrypt_file(catalog_path, plaintext)
        try:
            catalog = json.loads(plaintext.read_text(encoding="utf-8"))
            head = str(catalog["source_commit"])
            base = str(catalog["source_base"])
            object_format = str(catalog["git_object_format"])
            rows = catalog["entries"]
            metadata = catalog["git_metadata_objects"]
        except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
            raise PreserveError("encrypted Git reconstruction catalog is invalid") from exc
        if (
            catalog.get("schema") != "arca-legacy-ciphertext-catalog-v1"
            or object_format not in {"sha1", "sha256"}
            or not isinstance(rows, list)
            or not isinstance(metadata, list)
            or not re.fullmatch(r"[0-9a-f]{40}" if object_format == "sha1" else r"[0-9a-f]{64}", head)
            or not re.fullmatch(r"[0-9a-f]{40}" if object_format == "sha1" else r"[0-9a-f]{64}", base)
        ):
            raise PreserveError("encrypted Git reconstruction catalog has invalid identity")
        init = subprocess.run(
            ["git", "init", "--bare", f"--object-format={object_format}", str(staging)],
            capture_output=True,
            check=False,
            timeout=30,
        )
        if init.returncode:
            raise PreserveError("isolated bare repository could not be initialized")
        fetch = subprocess.run(
            ["git", "-C", str(staging), "fetch", "--no-tags", base_repo, "+refs/heads/main:refs/remotes/base/main"],
            capture_output=True,
            check=False,
            timeout=900,
        )
        if fetch.returncode:
            raise PreserveError("exact base commit is unavailable; reconstruction retained")
        _git(staging, "cat-file", "-e", f"{base}^{{commit}}")
        for row in rows:
            if not isinstance(row, dict):
                raise PreserveError("encrypted catalog contains an invalid blob entry")
            rel = row.get("path")
            digest = row.get("sha256")
            oid = row.get("git_blob")
            if (
                not isinstance(rel, str)
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or not isinstance(oid, str)
                or not re.fullmatch(r"[0-9a-f]{40}" if object_format == "sha1" else r"[0-9a-f]{64}", oid)
            ):
                raise PreserveError("encrypted catalog contains an invalid blob identity")
            transport = row.get("transport")
            asset_digest, asset_bytes = digest, row.get("bytes")
            if transport is not None:
                if (
                    not isinstance(transport, dict)
                    or transport.get("encryption") != "openpgp"
                    or not isinstance(transport.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", transport["sha256"])
                    or not isinstance(transport.get("bytes"), int)
                    or transport["bytes"] <= 0
                ):
                    raise PreserveError("encrypted catalog contains invalid transport envelope")
                asset_digest, asset_bytes = transport["sha256"], transport["bytes"]
            asset = assets / f"object-{asset_digest}.enc"
            if asset.is_symlink() or not asset.is_file() or _sha256(asset) != (asset_digest, asset_bytes):
                raise PreserveError("ciphertext asset is unavailable or differs from catalog")
            if transport is not None:
                inner = Path(temporary) / "inner-ciphertext"
                PRIVATE._decrypt_file(asset, inner)
                if _sha256(inner) != (digest, row.get("bytes")):
                    raise PreserveError("unwrapped ciphertext differs from original Git bytes")
                asset = inner
            if _write_object(staging, "blob", asset) != oid:
                raise PreserveError("ciphertext Git blob ID differs from original")
        if "legacy_manifest_json_b64" in catalog:
            try:
                manifest = base64.b64decode(catalog["legacy_manifest_json_b64"], validate=True)
            except (ValueError, TypeError) as exc:
                raise PreserveError("embedded legacy manifest is invalid") from exc
            if _write_object(staging, "blob", manifest) != catalog.get("legacy_manifest_git_blob"):
                raise PreserveError("embedded legacy manifest Git blob ID differs")
        for row in metadata:
            if not isinstance(row, dict) or row.get("type") not in {"commit", "tree", "tag"}:
                raise PreserveError("encrypted catalog contains invalid Git metadata")
            try:
                payload = base64.b64decode(row["raw_b64"], validate=True)
            except (KeyError, ValueError, TypeError) as exc:
                raise PreserveError("encrypted Git metadata bytes are invalid") from exc
            if len(payload) != row.get("bytes") or _write_object(staging, row["type"], payload) != row.get("oid"):
                raise PreserveError("Git metadata failed exact object-ID reconstruction")
        _git(staging, "update-ref", "refs/heads/recovered", head)
        _git(staging, "fsck", "--strict", "--full", "--no-reflogs", "--no-dangling")
        if _git(staging, "rev-parse", "refs/heads/recovered").decode().strip() != head:
            raise PreserveError("isolated reconstructed HEAD differs from source")
        os.replace(staging, destination)
    return {"state": "reconstructed", "git_identity_verified": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path, nargs="?")
    parser.add_argument("--repo", help="private GitHub owner/repository")
    parser.add_argument("--catalog-output", type=Path, help="local encrypted catalog destination")
    parser.add_argument("--apply", action="store_true", help="publish ciphertext assets and verify remote readback")
    parser.add_argument("--resume-existing-catalog", action="store_true", help="reuse a fixed encrypted catalog")
    parser.add_argument("--expected-head")
    parser.add_argument("--expected-catalog-sha256")
    parser.add_argument("--expected-files", type=int)
    parser.add_argument("--expected-bytes", type=int)
    parser.add_argument("--verify-existing-by-server-digest", action="store_true")
    parser.add_argument("--batch-deadline-seconds", type=int, default=PUBLISHER.BATCH_DEADLINE_SECONDS)
    parser.add_argument("--reconstruct-catalog", type=Path)
    parser.add_argument("--assets", type=Path)
    parser.add_argument("--base-repo")
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    try:
        if args.reconstruct_catalog:
            if (
                args.checkout
                or args.repo
                or args.catalog_output
                or args.apply
                or args.resume_existing_catalog
                or args.expected_head
                or args.expected_catalog_sha256
                or args.expected_files
                or args.expected_bytes
                or args.verify_existing_by_server_digest
                or args.batch_deadline_seconds != PUBLISHER.BATCH_DEADLINE_SECONDS
                or not args.assets
                or not args.base_repo
                or not args.destination
            ):
                raise PreserveError("reconstruction requires catalog, assets, base repo and destination only")
            result = reconstruct(args.reconstruct_catalog, args.assets, args.base_repo, args.destination)
        elif args.resume_existing_catalog:
            if (
                not args.checkout
                or not args.repo
                or not args.catalog_output
                or not args.expected_head
                or not args.expected_catalog_sha256
                or args.expected_files is None
                or args.expected_bytes is None
                or args.assets
                or args.base_repo
                or args.destination
            ):
                raise PreserveError("resume requires checkout, repository, catalog and fixed source receipt")
            result = resume_existing(
                args.checkout,
                args.repo,
                catalog=args.catalog_output,
                expected_head=args.expected_head,
                expected_catalog_sha256=args.expected_catalog_sha256,
                expected_files=args.expected_files,
                expected_bytes=args.expected_bytes,
                apply=args.apply,
                verify_existing_by_server_digest=args.verify_existing_by_server_digest,
                batch_deadline_seconds=args.batch_deadline_seconds,
            )
        else:
            if (
                not args.checkout
                or not args.repo
                or not args.catalog_output
                or args.expected_head
                or args.expected_catalog_sha256
                or args.expected_files is not None
                or args.expected_bytes is not None
                or args.verify_existing_by_server_digest
                or args.batch_deadline_seconds != PUBLISHER.BATCH_DEADLINE_SECONDS
                or args.assets
                or args.base_repo
                or args.destination
            ):
                raise PreserveError("preservation requires checkout, repo and catalog output only")
            result = preserve(args.checkout, args.repo, output=args.catalog_output, apply=args.apply)
        print(json.dumps(result, sort_keys=True))
    except (PreserveError, PRIVATE.VaultError, PUBLISHER.AssetError, OSError) as exc:
        print(f"arca-preserve-git-ciphertext: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
