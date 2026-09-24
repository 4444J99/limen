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
    new_blobs = {oid for oid, row in zip(object_ids, check.stdout.decode().splitlines(), strict=True) if row.startswith("blob ")}

    entries: list[dict[str, object]] = []
    paths: list[Path] = []
    embedded_manifest: str | None = None
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
    catalog = {
        "schema": "arca-legacy-ciphertext-catalog-v1",
        "source_commit": head,
        "source_base": base,
        "entries": entries,
    }
    if embedded_manifest is not None:
        catalog["legacy_manifest_json_b64"] = embedded_manifest
    output = output.expanduser().resolve()
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arca-cipher-catalog-") as temp:
        os.chmod(temp, 0o700)
        plaintext = Path(temp) / "catalog.json"
        plaintext.write_text(json.dumps(catalog, ensure_ascii=True, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        os.chmod(plaintext, 0o600)
        partial = output.with_name(f".{output.name}.partial")
        PRIVATE._encrypt_file(plaintext, partial)
        if not partial.is_file() or partial.stat().st_size == 0:
            raise PreserveError("encrypted catalog could not be verified as a non-empty file")
        os.chmod(partial, 0o600)
        os.replace(partial, output)
    result: dict[str, object] = {
        "state": "catalog-ready",
        "commit": head,
        "files": len(paths),
        "bytes": sum(int(entry["bytes"]) for entry in entries),
        "catalog_sha256": _sha256(output)[0],
        "catalog_path": str(output),
    }
    if apply:
        expected = {root / str(entry["path"]): str(entry["sha256"]) for entry in entries}
        result["publication"] = PUBLISHER.publish(remote, output, paths, apply=True, expected_digests=expected)
    else:
        expected = {root / str(entry["path"]): str(entry["sha256"]) for entry in entries}
        result["publication"] = PUBLISHER.publish(remote, output, paths, apply=False, expected_digests=expected)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--repo", required=True, help="private GitHub owner/repository")
    parser.add_argument("--catalog-output", type=Path, required=True, help="local encrypted catalog destination")
    parser.add_argument("--apply", action="store_true", help="publish ciphertext assets and verify remote readback")
    args = parser.parse_args()
    try:
        print(json.dumps(preserve(args.checkout, args.repo, output=args.catalog_output, apply=args.apply), sort_keys=True))
    except (PreserveError, PRIVATE.VaultError, PUBLISHER.AssetError, OSError) as exc:
        print(f"arca-preserve-git-ciphertext: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
