#!/usr/bin/env python3
"""Restore pinned Group 02 custody with credential-organ escrow, never Keychain.

Private manifests and plaintext remain in a bounded temporary native scratch root.
Only counts, hashes, and cohort IDs appear in the public result. Large cohorts
require the existing machine-wide heavy-work admission before downloading.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli/src"))
from limen.host_admission import AdmissionController

SPEC = importlib.util.spec_from_file_location("group02_restore", ROOT / "scripts/retire-restored-ignored-payload.py")
RESTORE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESTORE)
SMALL_CIPHER_LIMIT = 4 * 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024


def run(*args: str, **kwargs: object) -> bytes:
    return subprocess.run(args, check=True, capture_output=True, timeout=120, **kwargs).stdout


def safe_members(archive: tarfile.TarFile, prefix: str) -> list[tarfile.TarInfo]:
    # ARCA tar bundles include a harmless '.' directory header. It is not
    # restored: the temporary boundary's own permissions remain authoritative.
    members = [m for m in archive.getmembers() if not (m.name == "." and m.isdir())]
    if len(members) > 100000 or sum(m.size for m in members) > MAX_ARCHIVE_BYTES:
        raise ValueError("archive-bound")
    for member in members:
        name = PurePosixPath(member.name)
        if not name.parts or name.is_absolute() or ".." in name.parts or name.parts[0] != prefix:
            raise ValueError("archive-path")
        if not (member.isfile() or member.isdir() or member.issym()):
            raise ValueError("archive-special-entry")
    return members


def verify(entry: dict, release: dict, receipt: dict) -> dict:
    cohort = entry["id"]
    asset = next(a for a in release["assets"] if a["name"] == entry["asset"])
    if asset["size"] != entry["ciphertext_bytes"]:
        raise ValueError("asset-size")
    controller = AdmissionController()
    owner = f"group02-independent-restore:{cohort}"
    lease = None
    if asset["size"] > SMALL_CIPHER_LIMIT:
        decision = controller.acquire(
            "heavy", owner=owner, surface="group02-custody-restore", pid=os.getpid(), ttl_seconds=600
        )
        if not decision["allowed"]:
            return {"id": cohort, "accepted": False, "status": "admission-denied", "reasons": decision["reasons"]}
        lease = decision["lease"]
    try:
        scratch_root = Path.home() / ".local/share/limen"
        with tempfile.TemporaryDirectory(prefix="group02-independent-", dir=scratch_root) as scratch:
            temporary = Path(scratch)
            cipher = temporary / "cipher.enc"
            run(
                "gh",
                "release",
                "download",
                receipt["release_tag"],
                "--repo",
                "4444J99/domus-genoma",
                "--pattern",
                entry["asset"],
                "--output",
                str(cipher),
            )
            if (
                cipher.stat().st_size != entry["ciphertext_bytes"]
                or RESTORE.digest(cipher) != entry["ciphertext_sha256"]
            ):
                raise ValueError("ciphertext-mismatch")
            env = dict(os.environ)
            env.pop("OP_SERVICE_ACCOUNT_TOKEN", None)
            key = run("op", "read", "op://Private/limen-arca-vault/password", env=env).strip()
            if not re.fullmatch(rb"[0-9a-fA-F]{64}", key):
                raise ValueError("escrow-key-shape")
            read_fd, write_fd = os.pipe()
            try:
                os.write(write_fd, key + b"\n")
                os.close(write_fd)
                write_fd = -1
                run(
                    "openssl",
                    "enc",
                    "-d",
                    "-aes-256-cbc",
                    "-pbkdf2",
                    "-iter",
                    "200000",
                    "-pass",
                    f"fd:{read_fd}",
                    "-in",
                    str(cipher),
                    "-out",
                    str(temporary / "bundle.tar"),
                    pass_fds=(read_fd,),
                )
            finally:
                os.close(read_fd)
                if write_fd != -1:
                    os.close(write_fd)
            with tarfile.open(temporary / "bundle.tar") as archive:
                bundle = temporary / "bundle"
                bundle.mkdir()
                # ARCA also stores its protocol metadata outside the cohort.
                # Restore only these two exact regular members, never metadata
                # paths supplied by the outer archive.
                for filename in ("manifest.json", "snapshot.tar.gz"):
                    member = archive.getmember(f"{cohort}/{filename}")
                    if not member.isfile() or not 0 < member.size <= MAX_ARCHIVE_BYTES:
                        raise ValueError("bundle-member")
                    stream = archive.extractfile(member)
                    with (bundle / filename).open("wb") as output:
                        while block := stream.read(1024 * 1024):
                            output.write(block)
            manifest = json.loads((bundle / "manifest.json").read_bytes())
            if (
                manifest["source_path_sha256"] != entry["source_path_sha256"]
                or len(manifest["excluded_nested_roots"]) != entry["excluded_nested_count"]
            ):
                raise ValueError("manifest-coverage")
            snapshot = bundle / "snapshot.tar.gz"
            if RESTORE.digest(snapshot) != manifest["snapshot_sha256"]:
                raise ValueError("snapshot-mismatch")
            with tarfile.open(snapshot) as archive:
                members = safe_members(archive, "source")
                links = [m for m in members if m.issym()]
                for member in members:
                    if any(PurePosixPath(link.name) in PurePosixPath(member.name).parents for link in links):
                        raise ValueError("archive-entry-under-link")
                # Captured absolute symlinks are preserved as inert metadata,
                # after all regular extraction and chmod operations complete.
                archive.extractall(temporary / "restored", members=[m for m in members if not m.issym()], filter="data")
            restored = temporary / "restored/source"
            for name, item in manifest["entries"].items():
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("manifest-path")
                if item["kind"] != "symlink":
                    os.chmod(restored / name, item["mode"])
            for member in links:
                os.symlink(member.linkname, temporary / "restored" / member.name)
            RESTORE.verify_tree(restored, manifest["entries"])
            if len(manifest["entries"]) != entry["verified_entries"]:
                raise ValueError("manifest-count")
            fsck = None
            if entry["restored_git_fsck_exit"] is not None:
                run("git", "-C", str(restored), "fsck", "--full")
                fsck = 0
            result = {
                "id": cohort,
                "accepted": True,
                "verified_entries": len(manifest["entries"]),
                "snapshot_sha256": manifest["snapshot_sha256"],
                "restored_git_fsck_exit": fsck,
                "excluded_nested_count": entry["excluded_nested_count"],
            }
        return {**result, "plaintext_scratch_removed": True}
    finally:
        if lease:
            controller.release(lease_id=lease["lease_id"], owner=owner, pid=os.getpid())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", action="append", choices=[f"G02-{i:02}" for i in range(1, 12)])
    args = parser.parse_args()
    envelope = json.loads(
        run("gh", "api", f"repos/4444J99/_diagnostics/contents/{RESTORE.RECEIPT_PATH}?ref={RESTORE.RECEIPT_REF}")
    )
    receipt = json.loads(base64.b64decode(envelope["content"]))
    if receipt["schema"] != "group02.remote-custody-receipt.v1" or receipt["repository_id"] != 1124448005:
        raise ValueError("receipt-identity")
    release = json.loads(run("gh", "api", f"repos/4444J99/domus-genoma/releases/{receipt['release_id']}"))
    if release["draft"] or release["tag_name"] != receipt["release_tag"]:
        raise ValueError("release-identity")
    entries = [e for e in receipt["entries"] if args.id is None or e["id"] in args.id]
    results = []
    for entry in entries:
        try:
            result = verify(entry, release, receipt)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError) as error:
            result = {
                "id": entry["id"],
                "accepted": False,
                "status": "verification-failed",
                "failure_class": type(error).__name__,
            }
        results.append(result)
        print(
            json.dumps(
                {
                    "schema": "group02.independent-restore.v1",
                    "key_source": "canonical-credential-organ",
                    "mac_keychain_consulted": False,
                    **result,
                }
            ),
            flush=True,
        )
        if result.get("status") == "admission-denied":
            break
    return 0 if len(results) == len(entries) and all(r["accepted"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
