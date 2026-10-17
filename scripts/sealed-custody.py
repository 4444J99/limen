#!/usr/bin/env python3
"""Sealed custody: arca-sealed private bundles on two physical devices, proven without the key.

WHY: private media derivatives need encrypted second-device custody, and the only existing
two-device proof (scripts/check-group02-independent-custody.py) is hardcoded to Group 02 ids and
one domus release. This tool is the reusable form. It reuses, never reinvents:

  * the cipher + key      -> `scripts/arca.sh seal|unseal` (AES-256-CBC, pbkdf2 x200000, tar payload),
                             so L-ARCA-KEY-ESCROW stays the single escrow liability;
  * physical device ids   -> limen.agent_state.custody._device_identity (diskutil/ioreg whole disk);
  * the portable receipt  -> limen.prima_materia.CustodyReceiptV1 (>=2 independent restored devices).

VERBS
  seal     --source DIR --replica-root DIR --run RUN_ID [--label TEXT]
           Seal DIR into <replica-root>/<RUN_ID>/bundle.tar.enc (0600) beside a private manifest.json
           (per-member sha256 computed from the SOURCE before sealing). arca's plaintext tar is
           confined to a fresh 0700 dir under $LIMEN_CUSTODY_STAGING_ROOT, never /var/folders.
  verify   --replica DIR
           KEY-LESS: recompute ciphertext sha256/bytes against the manifest. Exit 0 match, 1 mismatch.
  restore  --replica DIR [--key-source keychain|op]
           Unseal into a fresh 0700 scratch dir, check every member sha256 (and that no extra files
           appeared), stamp restore_verified_at/restore_key_source into the manifest, delete the
           plaintext. `--key-source op` proves the credential-organ escrow copy restores the bundle
           with no Keychain involvement. Exit 0 only if every member matches.
  receipt  --replica DIR [--replica DIR ...] --out PRIVATE_JSON --tracked-out TRACKED_JSON
           [--plaintext-retained] [--retirement-lever ID]
           Build and validate a CustodyReceiptV1 from >=2 replicas on DISTINCT devices, each
           restore-verified. The private receipt carries device ids; the tracked receipt is redacted
           (no device ids, no absolute paths, no member digests).

The key is never printed, logged, or placed in argv: arca.sh holds it only in a shell variable and
hands it to openssl through the environment of that one child; this tool never sees it.

ENVIRONMENT
  LIMEN_CUSTODY_STAGING_ROOT  plaintext scratch root (default $HOME/Workspace/limen/.limen-private/custody-staging)
  LIMEN_SEALED_CUSTODY_TEST=1 together with LIMEN_SEALED_CUSTODY_DEVICE_ID_OVERRIDE=<opaque id> replaces
                              the diskutil device probe so the hermetic test can simulate two devices.
                              The override is ignored unless LIMEN_SEALED_CUSTODY_TEST=1.

Run it under an interpreter that can import limen's dependencies (rfc8785, pydantic), e.g. the
cli venv: `cli/.venv/bin/python -I scripts/sealed-custody.py ...`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli/src"))

import rfc8785
from limen.agent_state.crypto import encryption_profile_digest
from limen.agent_state.models import ReceiptError
from limen.prima_materia import CustodyReceiptV1, RestorationProofV1

ARCA = ROOT / "scripts" / "arca.sh"
BUNDLE = "bundle.tar.enc"
MANIFEST = "manifest.json"
MANIFEST_SCHEMA = "limen.sealed_custody_manifest.v1"
TRACKED_SCHEMA = "limen.sealed_custody_receipt.tracked.v1"
SOURCE_KIND = "arca-sealed-tar"
RUN_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
ARCA_TIMEOUT_SECONDS = 3600


class SealedCustodyError(RuntimeError):
    """A sealed-custody invariant failed; the message never contains key material."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _device_id(path: Path) -> str:
    if os.environ.get("LIMEN_SEALED_CUSTODY_TEST") == "1":
        override = os.environ.get("LIMEN_SEALED_CUSTODY_DEVICE_ID_OVERRIDE")
        if override:
            return override
    from limen.agent_state.custody import _device_identity

    return _device_identity(path)


def _staging_root() -> Path:
    configured = os.environ.get("LIMEN_CUSTODY_STAGING_ROOT")
    root = Path(configured) if configured else Path.home() / "Workspace/limen/.limen-private/custody-staging"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root


def _scratch(prefix: str) -> Path:
    path = Path(tempfile.mkdtemp(prefix=prefix, dir=_staging_root()))
    path.chmod(0o700)
    return path


def _run_arca(args: list[str], scratch: Path, extra_env: dict[str, str]) -> None:
    tmpdir = scratch / "tmp"
    tmpdir.mkdir(mode=0o700)
    env = {**os.environ, **extra_env, "TMPDIR": str(tmpdir)}
    previous_umask = os.umask(0o077)
    try:
        result = subprocess.run(
            ["bash", str(ARCA), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=ARCA_TIMEOUT_SECONDS,
        )
    finally:
        os.umask(previous_umask)
    if result.returncode:
        tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-5:])
        raise SealedCustodyError(f"arca.sh {args[0]} failed (exit {result.returncode}): {tail}")


def _write_private_json(path: Path, value: dict[str, Any], *, exclusive: bool) -> None:
    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    if exclusive:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        return
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temporary = Path(raw)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _members(source: Path) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    for current, directories, files in os.walk(source, followlinks=False):
        directories.sort()
        for name in sorted(files):
            path = Path(current) / name
            if path.is_symlink() or not path.is_file():
                raise SealedCustodyError("source contains a symlink or special file; refusing to seal it")
            members.append(
                {
                    "path": path.relative_to(source).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                }
            )
    if not members:
        raise SealedCustodyError("source contains no regular files")
    members.sort(key=lambda member: member["path"])
    return members


def _load_manifest(replica: Path) -> dict[str, Any]:
    try:
        manifest = json.loads((replica / MANIFEST).read_text())
    except (OSError, ValueError) as exc:
        raise SealedCustodyError("replica manifest is missing or invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise SealedCustodyError("replica manifest has an unexpected schema")
    return manifest


def _ciphertext_state(replica: Path, manifest: dict[str, Any]) -> tuple[bool, int, str]:
    bundle = replica / BUNDLE
    if not bundle.is_file() or bundle.is_symlink():
        return False, 0, ""
    actual_bytes = bundle.stat().st_size
    actual_sha = _sha256_file(bundle)
    ok = actual_bytes == manifest.get("ciphertext_bytes") and actual_sha == manifest.get("ciphertext_sha256")
    return ok, actual_bytes, actual_sha


def cmd_seal(args: argparse.Namespace) -> int:
    source = Path(args.source).resolve(strict=True)
    if not source.is_dir():
        raise SealedCustodyError("--source must be a directory")
    if not RUN_ID_RE.fullmatch(args.run):
        raise SealedCustodyError("--run must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    replica_root = Path(args.replica_root).resolve(strict=True)
    members = _members(source)
    device_id = _device_id(replica_root)
    run_dir = replica_root / args.run
    run_dir.mkdir(mode=0o700)
    run_dir.chmod(0o700)
    bundle = run_dir / BUNDLE
    scratch = _scratch(".sealed-custody-seal-")
    try:
        _run_arca(["seal", str(source), str(bundle)], scratch, {})
        bundle.chmod(0o600)
        manifest = {
            "schema": MANIFEST_SCHEMA,
            "run_id": args.run,
            "label": args.label,
            "sealed_at": datetime.now(UTC).isoformat(),
            "source_name": source.name,
            "ciphertext_sha256": _sha256_file(bundle),
            "ciphertext_bytes": bundle.stat().st_size,
            "encryption_profile_digest": encryption_profile_digest(SOURCE_KIND),
            "device_id": device_id,
            "members": members,
        }
        _write_private_json(run_dir / MANIFEST, manifest, exclusive=True)
    except BaseException:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(
        f"sealed run={args.run} members={len(members)} ciphertext_bytes={manifest['ciphertext_bytes']} "
        f"ciphertext_sha256={manifest['ciphertext_sha256']}"
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    replica = Path(args.replica).resolve(strict=True)
    manifest = _load_manifest(replica)
    ok, actual_bytes, actual_sha = _ciphertext_state(replica, manifest)
    if ok:
        print(f"ok bytes={actual_bytes} sha256={actual_sha} path={replica / BUNDLE}")
        return 0
    print(
        f"MISMATCH expected bytes={manifest.get('ciphertext_bytes')} sha256={manifest.get('ciphertext_sha256')}; "
        f"actual bytes={actual_bytes} sha256={actual_sha or 'absent'} path={replica / BUNDLE}"
    )
    return 1


def cmd_restore(args: argparse.Namespace) -> int:
    replica = Path(args.replica).resolve(strict=True)
    manifest = _load_manifest(replica)
    ok, _, _ = _ciphertext_state(replica, manifest)
    if not ok:
        raise SealedCustodyError("ciphertext does not match the manifest; refusing to restore")
    scratch = _scratch(".sealed-custody-restore-")
    try:
        output = scratch / "out"
        _run_arca(["unseal", str(replica / BUNDLE), str(output)], scratch, {"ARCA_KEY_SOURCE": args.key_source})
        root = output / manifest["source_name"]
        expected = {member["path"]: member for member in manifest["members"]}
        mismatched = 0
        seen: set[str] = set()
        if root.is_dir():
            for current, _directories, files in os.walk(root, followlinks=False):
                for name in files:
                    path = Path(current) / name
                    relative = path.relative_to(root).as_posix()
                    seen.add(relative)
                    member = expected.get(relative)
                    if (
                        member is None
                        or path.is_symlink()
                        or path.stat().st_size != member["bytes"]
                        or _sha256_file(path) != member["sha256"]
                    ):
                        mismatched += 1
        mismatched += len(set(expected) - seen)
        result = {
            "schema": "limen.sealed_custody_restore.v1",
            "members": len(expected),
            "mismatched": mismatched,
            "key_source": args.key_source,
            "verified": mismatched == 0,
        }
        if mismatched == 0:
            manifest["restore_verified_at"] = datetime.now(UTC).isoformat()
            manifest["restore_key_source"] = args.key_source
            _write_private_json(replica / MANIFEST, manifest, exclusive=False)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verified"] else 1


def cmd_receipt(args: argparse.Namespace) -> int:
    if len(args.replica) < 2:
        raise SealedCustodyError("a custody receipt needs at least two --replica")
    manifests: list[dict[str, Any]] = []
    for raw in args.replica:
        replica = Path(raw).resolve(strict=True)
        manifest = _load_manifest(replica)
        ok, _, _ = _ciphertext_state(replica, manifest)
        if not ok:
            raise SealedCustodyError("a replica ciphertext does not match its manifest")
        if not manifest.get("restore_verified_at") or manifest.get("restore_key_source") not in {"keychain", "op"}:
            raise SealedCustodyError("every replica needs a passing restore before a receipt")
        manifests.append(manifest)
    first = manifests[0]
    for manifest in manifests[1:]:
        # Each replica is its own seal (fresh salt), so ciphertext bytes legitimately differ;
        # what must agree is the logical content and the cipher profile.
        for field in ("run_id", "encryption_profile_digest", "members"):
            if manifest[field] != first[field]:
                raise SealedCustodyError(f"replicas disagree on {field}")
    device_ids = [manifest["device_id"] for manifest in manifests]
    if len(set(device_ids)) != len(device_ids):
        raise SealedCustodyError("replicas must sit on distinct physical devices")

    logical_digest = _canonical_digest(first["members"])
    custody_id = (
        "custody_"
        + _canonical_digest(
            {
                "run_id": first["run_id"],
                "logical_sha256": logical_digest,
                "ciphertext_sha256": sorted(manifest["ciphertext_sha256"] for manifest in manifests),
                "encryption_profile_digest": first["encryption_profile_digest"],
                "device_ids": sorted(device_ids),
            }
        )[:32]
    )
    proofs = tuple(
        RestorationProofV1(
            custody_target_ref=f"sealed-replica-{index}",
            device_id=manifest["device_id"],
            restored_at=datetime.fromisoformat(manifest["restore_verified_at"]),
            restored_output_digest=logical_digest,
            predicate_digest=_canonical_digest(
                {
                    "schema": MANIFEST_SCHEMA,
                    "ciphertext_sha256": manifest["ciphertext_sha256"],
                    "restore_key_source": manifest["restore_key_source"],
                    "restore_verified_at": manifest["restore_verified_at"],
                }
            ),
        )
        for index, manifest in enumerate(manifests, start=1)
    )
    receipt = CustodyReceiptV1.model_validate(
        {
            "custody_id": custody_id,
            "encryption_profile_digest": first["encryption_profile_digest"],
            "chunk_manifest_digests": [manifest["ciphertext_sha256"] for manifest in manifests],
            "independent_device_ids": device_ids,
            "restoration_proofs": [proof.model_dump(mode="json") for proof in proofs],
        }
    )

    from limen.agent_state.custody import write_custody_receipt

    out = Path(args.out)
    tracked_out = Path(args.tracked_out)
    if out.resolve(strict=False) == tracked_out.resolve(strict=False):
        raise SealedCustodyError("private and tracked receipt paths must differ")
    write_custody_receipt(out, receipt)
    tracked = {
        "schema": TRACKED_SCHEMA,
        "run_id": first["run_id"],
        "label": first["label"],
        "ciphertext_sha256": first["ciphertext_sha256"],
        "ciphertext_bytes": first["ciphertext_bytes"],
        "replica_ciphertext_sha256": [manifest["ciphertext_sha256"] for manifest in manifests],
        "member_count": len(first["members"]),
        "independent_device_count": len(set(device_ids)),
        "restore_verified": [bool(manifest.get("restore_verified_at")) for manifest in manifests],
        "key_sources": [manifest["restore_key_source"] for manifest in manifests],
        "encryption_profile_digest": first["encryption_profile_digest"],
        "custody_receipt_sha256": _sha256_file(out),
        "plaintext_retained": bool(args.plaintext_retained),
        "retirement_lever": args.retirement_lever,
    }
    tracked_out.parent.mkdir(parents=True, exist_ok=True)
    tracked_out.write_text(json.dumps(tracked, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"schema": TRACKED_SCHEMA, "custody_receipt_sha256": tracked["custody_receipt_sha256"]}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    verbs = parser.add_subparsers(dest="verb", required=True)

    seal = verbs.add_parser("seal", help="seal a directory into one replica")
    seal.add_argument("--source", required=True)
    seal.add_argument("--replica-root", required=True)
    seal.add_argument("--run", required=True)
    seal.add_argument("--label", default="")
    seal.set_defaults(func=cmd_seal)

    verify = verbs.add_parser("verify", help="key-less ciphertext check against the manifest")
    verify.add_argument("--replica", required=True)
    verify.set_defaults(func=cmd_verify)

    restore = verbs.add_parser("restore", help="unseal into scratch and verify every member")
    restore.add_argument("--replica", required=True)
    restore.add_argument("--key-source", choices=("keychain", "op"), default="keychain")
    restore.set_defaults(func=cmd_restore)

    receipt = verbs.add_parser("receipt", help="build private + redacted tracked custody receipts")
    receipt.add_argument("--replica", action="append", required=True)
    receipt.add_argument("--out", required=True)
    receipt.add_argument("--tracked-out", required=True)
    receipt.add_argument("--plaintext-retained", action="store_true")
    receipt.add_argument("--retirement-lever")
    receipt.set_defaults(func=cmd_receipt)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (SealedCustodyError, ReceiptError, OSError, ValueError, subprocess.SubprocessError) as exc:
        # ValueError covers pydantic.ValidationError. No branch ever formats key material.
        print(f"sealed-custody: {args.verb} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
