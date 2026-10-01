#!/usr/bin/env python3
"""Admit restored Group 02 ignored payload to the ordinary worktree lifecycle.

No worktree, branch, tracked file, or Git store is removed by this adapter.
The receipt is pinned to a merged diagnostics commit; private manifests remain
inside the encrypted release. Apply rechecks bytes and process ownership through
the existing descriptor-safe custody purge before removing ignored directories.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli/src"))
sys.path.insert(0, str(ROOT / "scripts"))
import importlib.util

from limen.protected_exclusions import ProtectedExclusionRegistry
from limen.worktree_abandonment import CustodyPathIdentity, purge_custody_proven_path

RECEIPT_REF = "b97e9eabd50881fbe2ad1dd47a2d65fbb4309be3"
RECEIPT_PATH = "assessments/2026-10-01-group02-custody-receipt.json"


def run(*args: str) -> bytes:
    return subprocess.run(args, check=True, capture_output=True, timeout=120).stdout


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def path_digest(path: Path) -> str:
    return hashlib.sha256(str(path).encode()).hexdigest()


def inventory(root: Path) -> dict:
    entries = {}

    def visit(path: Path) -> None:
        raw = path.lstat()
        key = path.relative_to(root).as_posix() if path != root else "."
        item = {"mode": stat.S_IMODE(raw.st_mode)}
        if stat.S_ISLNK(raw.st_mode):
            item.update(kind="symlink", target=os.readlink(path))
        elif stat.S_ISDIR(raw.st_mode):
            item["kind"] = "dir"
        elif stat.S_ISREG(raw.st_mode):
            item.update(kind="file", sha256=digest(path), bytes=raw.st_size)
        else:
            raise ValueError("unsupported-filesystem-entry")
        entries[key] = item
        if item["kind"] == "dir":
            for child in sorted(path.iterdir()):
                visit(child)

    visit(root)
    return entries


def verify_tree(root: Path, entries: dict) -> None:
    if inventory(root) != entries:
        raise ValueError("custody-content-or-mode-drift")


def restore(snapshot: Path, destination: Path, entries: dict) -> None:
    # Reject links and special members: current cohort contains only regular
    # files/directories. No extraction may cross the temporary restore boundary.
    with tarfile.open(snapshot) as archive:
        members = archive.getmembers()
        for member in members:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or name.parts[0] != "source":
                raise ValueError("archive-path-escape")
            if not (member.isdir() or member.isfile()):
                raise ValueError("archive-link-or-special-entry")
        archive.extractall(destination, filter="data")
    restored = destination / "source"
    for key, item in entries.items():
        name = PurePosixPath(key)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError("manifest-path-escape")
        os.chmod(restored / key, item["mode"])
    verify_tree(restored, entries)


def ignored_directories(root: Path) -> list[Path]:
    ignored = {
        Path(os.fsdecode(value))
        for value in run(
            "git",
            "-C",
            str(root),
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "-z",
        ).split(b"\0")
        if value
    }
    selected = set()
    for relative in ignored:
        parent = relative.parent
        if parent == Path("."):
            raise ValueError("ignored-root-file-retained")
        while parent.parent != Path("."):
            candidate = parent.parent
            files = {p.relative_to(root) for p in (root / candidate).rglob("*") if not p.is_dir() or p.is_symlink()}
            if not files <= ignored:
                break
            parent = candidate
        selected.add(root / parent)
    # Deduplicate overlapping subtrees, then prove every entry is ignored.
    result = sorted(p for p in selected if not any(q in p.parents for q in selected))
    for directory in result:
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("ignored-directory-unavailable")
        files = {p.relative_to(root) for p in directory.rglob("*") if not p.is_dir() or p.is_symlink()}
        if not files <= ignored or run("git", "-C", str(root), "ls-files", "--", str(directory)):
            raise ValueError("payload-not-exclusively-ignored")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--id", required=True, choices=("G02-05", "G02-09"))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    # Reuse the installed policy's protection, process, lock and age gates.
    spec = importlib.util.spec_from_file_location("group02_reclaimer", ROOT / "scripts/reclaim-worktrees.py")
    reclaimer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reclaimer
    spec.loader.exec_module(reclaimer)
    common = Path(os.fsdecode(run("git", "-C", str(root), "rev-parse", "--git-common-dir")).strip())
    if not common.is_absolute():
        common = root / common
    registry = ProtectedExclusionRegistry.load(
        common.resolve(strict=True).parent, reclaimer.PROTECTED_EXCLUSION_REGISTRY
    )
    reclaimer._ACTIVE_PROCESS_CWDS = reclaimer.active_process_cwds()
    action, reason = reclaimer.classify(root, __import__("time").time(), 24, protected_registry=registry)
    if (action, reason) != ("skip", "ignored-payload-custody-unproven"):
        raise ValueError(f"ordinary-lifecycle-retained:{reason}")
    if not (root / ".git").is_file():
        raise ValueError("not-linked-worktree")
    envelope = json.loads(run("gh", "api", f"repos/4444J99/_diagnostics/contents/{RECEIPT_PATH}?ref={RECEIPT_REF}"))
    receipt_bytes = base64.b64decode(envelope["content"])
    receipt = json.loads(receipt_bytes)
    if receipt["schema"] != "group02.remote-custody-receipt.v1" or receipt["repository_id"] != 1124448005:
        raise ValueError("custody-receipt-identity-mismatch")
    entry = next(e for e in receipt["entries"] if e["id"] == args.id)
    if entry["source_path_sha256"] != path_digest(root) or entry["excluded_nested_count"]:
        raise ValueError("custody-root-coverage-mismatch")
    release = json.loads(run("gh", "api", f"repos/4444J99/domus-genoma/releases/{receipt['release_id']}"))
    if release["draft"] or release["tag_name"] != receipt["release_tag"]:
        raise ValueError("custody-release-mismatch")
    with tempfile.TemporaryDirectory(prefix="group02-restored-") as scratch:
        temporary = Path(scratch)
        run(
            "gh",
            "release",
            "download",
            receipt["release_tag"],
            "--repo",
            "4444J99/domus-genoma",
            "--pattern",
            entry["asset"],
            "--dir",
            str(temporary),
        )
        ciphertext = temporary / entry["asset"]
        if digest(ciphertext) != entry["ciphertext_sha256"] or ciphertext.stat().st_size != entry["ciphertext_bytes"]:
            raise ValueError("ciphertext-mismatch")
        run(str(ROOT / "scripts/arca.sh"), "unseal", str(ciphertext), str(temporary / "unsealed"))
        bundle = temporary / "unsealed" / args.id
        manifest = json.loads((bundle / "manifest.json").read_bytes())
        if manifest["source_path_sha256"] != path_digest(root) or manifest["excluded_nested_roots"]:
            raise ValueError("private-manifest-root-mismatch")
        snapshot = bundle / "snapshot.tar.gz"
        if digest(snapshot) != manifest["snapshot_sha256"]:
            raise ValueError("snapshot-mismatch")
        entries = manifest["entries"]
        restore(snapshot, temporary / "restored", entries)
        verify_tree(root, entries)
        directories = ignored_directories(root)
        report = {
            "schema": "limen.restored_ignored_retirement.v1",
            "id": args.id,
            "path_sha256": path_digest(root),
            "receipt_ref": RECEIPT_REF,
            "restore_verified": True,
            "ignored_directories": len(directories),
            "applied": args.apply,
            "purge_receipts": [],
        }
        if args.apply:
            for directory in directories:
                prefix = directory.relative_to(root).as_posix()
                expected_entries = {
                    ("." if key == prefix else key[len(prefix) + 1 :]): item
                    for key, item in entries.items()
                    if key == prefix or key.startswith(prefix + "/")
                }
                raw = directory.lstat()
                identity = CustodyPathIdentity(
                    str(directory), path_digest(directory), raw.st_dev, raw.st_ino, raw.st_mtime_ns
                )

                def owner_probe(_path):
                    reclaimer._ACTIVE_PROCESS_CWDS = reclaimer.active_process_cwds()
                    return reclaimer.active_process_owner(root)

                result = purge_custody_proven_path(
                    directory,
                    identity,
                    reason="custody-restored+idle",
                    custody_plan_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
                    custody_content_sha256=manifest["snapshot_sha256"],
                    receipt_root=Path.home() / ".local/state/limen/abandonment-receipts",
                    owner_probe=owner_probe,
                    content_probe=lambda path, expected=expected_entries: verify_tree(path, expected),
                )
                report["purge_receipts"].append(result["receipt_path"])
        print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "retained", "reason": str(exc)[:200]}))
        raise SystemExit(2)
