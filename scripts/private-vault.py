#!/usr/bin/env python3
"""PRIVATE-VAULT — git-tracked ciphertext custody for private artifacts.

Ciphertext and a deliberately minimal manifest are tracked. Plaintext names, source paths,
content hashes, sizes, and descriptions live only inside the encrypted envelope. The public
manifest contains only a neutral artifact id plus ciphertext custody metadata.

  add      encrypt a file into a v2 envelope and append a public-safe manifest row
  verify   validate manifest schema, containment, ciphertext integrity, and git custody
  restore  decrypt, verify, and atomically publish one artifact (or --all)
  list     list neutral artifact ids, newest first

The committed public key is the encryption source of truth. Decryption uses the operator's
normal GPG keyring and therefore still requires the private key.
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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBKEY = ROOT / "docs" / "keys" / "anthony-padavano-gpg.asc"
VAULT_DIR = ROOT / "institutio" / "vault"
MANIFEST = VAULT_DIR / "manifest.jsonl"
FINGERPRINT = "205A566A5FFE43D2E28E05A4C5B98FFAF8ED000E"

SCHEMA = "private-vault-manifest-v2"
MAGIC = b"LIMEN-PRIVATE-VAULT-V2\n"
MAX_HEADER_BYTES = 64 * 1024
ARTIFACT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PUBLIC_FIELDS = {
    "schema",
    "artifact_id",
    "ciphertext",
    "ciphertext_sha256",
    "ciphertext_bytes",
    "recipient_fpr",
    "vaulted_at",
}


class VaultError(RuntimeError):
    """A user-facing vault contract failure."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_artifact_id(value: str) -> str:
    if not ARTIFACT_ID_RE.fullmatch(value or ""):
        raise VaultError("artifact id must match [a-z0-9][a-z0-9-]{0,63}")
    return value


def _contained_file(base: Path, name: str) -> Path:
    if not name or Path(name).name != name or Path(name).is_absolute():
        raise VaultError(f"unsafe vault filename: {name!r}")
    base_resolved = base.resolve()
    candidate = (base / name).resolve()
    if candidate.parent != base_resolved:
        raise VaultError(f"vault filename escapes custody root: {name!r}")
    return candidate


def _cipher_path(row: dict) -> Path:
    artifact_id = _safe_artifact_id(str(row.get("artifact_id") or ""))
    expected = f"{artifact_id}.gpg"
    name = str(row.get("ciphertext") or "")
    if name != expected:
        raise VaultError(f"ciphertext for {artifact_id} must be named {expected}")
    return _contained_file(VAULT_DIR, name)


def _read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    rows: list[dict] = []
    for line_number, raw in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VaultError(f"manifest line {line_number} is invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise VaultError(f"manifest line {line_number} is not an object")
        rows.append(row)
    return rows


def _validate_public_row(row: dict, line_number: int) -> list[str]:
    errors: list[str] = []
    extra = sorted(set(row) - PUBLIC_FIELDS)
    missing = sorted(PUBLIC_FIELDS - set(row))
    if extra:
        errors.append(f"manifest line {line_number} exposes unsupported fields: {', '.join(extra)}")
    if missing:
        errors.append(f"manifest line {line_number} misses fields: {', '.join(missing)}")
    if row.get("schema") != SCHEMA:
        errors.append(f"manifest line {line_number} has unsupported schema")
    try:
        _cipher_path(row)
    except VaultError as exc:
        errors.append(f"manifest line {line_number}: {exc}")
    cipher_sha = str(row.get("ciphertext_sha256") or "")
    if not SHA256_RE.fullmatch(cipher_sha):
        errors.append(f"manifest line {line_number} has invalid ciphertext sha256")
    if not isinstance(row.get("ciphertext_bytes"), int) or row.get("ciphertext_bytes", -1) < 0:
        errors.append(f"manifest line {line_number} has invalid ciphertext byte count")
    if row.get("recipient_fpr") != FINGERPRINT:
        errors.append(f"manifest line {line_number} has unexpected recipient fingerprint")
    if not isinstance(row.get("vaulted_at"), str) or not row.get("vaulted_at"):
        errors.append(f"manifest line {line_number} has invalid vaulted_at")
    return errors


def _write_manifest(rows: list[dict]) -> None:
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=".manifest.", dir=VAULT_DIR)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, MANIFEST)
    finally:
        temporary.unlink(missing_ok=True)


def _tracked_files() -> set[str]:
    run = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        raise VaultError(f"cannot inspect git custody: {run.stderr.strip()}")
    return set(run.stdout.splitlines())


def _reject_tracked_plaintext(source: Path) -> None:
    try:
        relative = source.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return
    if relative in _tracked_files():
        raise VaultError("refusing to vault plaintext that is already git-tracked")


def _gpg_env(gnupghome: str) -> dict:
    env = dict(os.environ)
    env["GNUPGHOME"] = gnupghome
    return env


def _import_pubkey(gnupghome: str) -> None:
    if not PUBKEY.exists():
        raise VaultError("committed public key is missing")
    run = subprocess.run(
        ["gpg", "--batch", "--import", str(PUBKEY)],
        env=_gpg_env(gnupghome),
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        raise VaultError(f"public-key import failed: {run.stderr.strip()}")


def _encrypt_file(source: Path, destination: Path) -> None:
    with tempfile.TemporaryDirectory() as gnupghome:
        os.chmod(gnupghome, 0o700)
        _import_pubkey(gnupghome)
        run = subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--trust-model",
                "always",
                "--recipient",
                FINGERPRINT,
                "--output",
                str(destination),
                "--encrypt",
                str(source),
            ],
            env=_gpg_env(gnupghome),
            capture_output=True,
            text=True,
        )
    if run.returncode != 0 or not destination.is_file():
        raise VaultError(f"encryption failed: {run.stderr.strip()}")


def _decrypt_file(source: Path, destination: Path) -> None:
    run = subprocess.run(
        ["gpg", "--batch", "--yes", "--output", str(destination), "--decrypt", str(source)],
        capture_output=True,
        text=True,
    )
    if run.returncode != 0 or not destination.is_file():
        raise VaultError(f"decryption failed (private key required): {run.stderr.strip()}")


def _write_envelope(source: Path, artifact_id: str, destination: Path) -> None:
    header = {
        "artifact_id": artifact_id,
        "original_name": source.name,
        "plaintext_sha256": _sha256(source),
        "plaintext_bytes": source.stat().st_size,
    }
    encoded_header = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded_header) > MAX_HEADER_BYTES:
        raise VaultError("encrypted envelope header is too large")
    with destination.open("wb") as output, source.open("rb") as input_handle:
        output.write(MAGIC)
        output.write(encoded_header + b"\n")
        shutil.copyfileobj(input_handle, output, length=1 << 20)


def _extract_envelope(envelope: Path, artifact_id: str, destination: Path) -> str:
    digest = hashlib.sha256()
    count = 0
    with envelope.open("rb") as source:
        if source.readline(len(MAGIC) + 1) != MAGIC:
            raise VaultError(f"decrypted envelope for {artifact_id} has invalid magic")
        raw_header = source.readline(MAX_HEADER_BYTES + 1)
        if not raw_header.endswith(b"\n") or len(raw_header) > MAX_HEADER_BYTES:
            raise VaultError(f"decrypted envelope for {artifact_id} has invalid header")
        try:
            header = json.loads(raw_header)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VaultError(f"decrypted envelope for {artifact_id} has invalid metadata") from exc
        if header.get("artifact_id") != artifact_id:
            raise VaultError(f"decrypted envelope identity mismatch for {artifact_id}")
        original_name = str(header.get("original_name") or "")
        if not original_name or Path(original_name).name != original_name:
            raise VaultError(f"decrypted envelope for {artifact_id} has unsafe output name")
        expected_sha = str(header.get("plaintext_sha256") or "")
        expected_bytes = header.get("plaintext_bytes")
        if not SHA256_RE.fullmatch(expected_sha):
            raise VaultError(f"decrypted envelope for {artifact_id} has invalid plaintext hash")
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise VaultError(f"decrypted envelope for {artifact_id} has invalid plaintext size")
        with destination.open("wb") as output:
            for chunk in iter(lambda: source.read(1 << 20), b""):
                output.write(chunk)
                digest.update(chunk)
                count += len(chunk)
    if digest.hexdigest() != expected_sha or count != expected_bytes:
        raise VaultError(f"restored plaintext integrity mismatch for {artifact_id}")
    return original_name


def cmd_add(args: argparse.Namespace) -> int:
    artifact_id = _safe_artifact_id(args.artifact_id)
    source = Path(args.file).expanduser().resolve()
    if not source.is_file():
        raise VaultError("source is not a file")
    _reject_tracked_plaintext(source)
    rows = _read_manifest()
    for line_number, row in enumerate(rows, 1):
        errors = _validate_public_row(row, line_number)
        if errors:
            raise VaultError("; ".join(errors))
        if row["artifact_id"] == artifact_id:
            print(f"OK: {artifact_id} is already vaulted as {row['ciphertext']}")
            return 0

    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    cipher_name = f"{artifact_id}.gpg"
    cipher_path = _contained_file(VAULT_DIR, cipher_name)
    if cipher_path.exists():
        raise VaultError(f"ciphertext already exists without a matching manifest row: {cipher_name}")

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        envelope = temporary_root / "envelope"
        temporary_cipher = temporary_root / "ciphertext.gpg"
        envelope.touch(mode=0o600)
        _write_envelope(source, artifact_id, envelope)
        _encrypt_file(envelope, temporary_cipher)
        os.chmod(temporary_cipher, 0o644)
        os.replace(temporary_cipher, cipher_path)

    row = {
        "schema": SCHEMA,
        "artifact_id": artifact_id,
        "ciphertext": cipher_name,
        "ciphertext_sha256": _sha256(cipher_path),
        "ciphertext_bytes": cipher_path.stat().st_size,
        "recipient_fpr": FINGERPRINT,
        "vaulted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        _write_manifest([*rows, row])
    except Exception:
        cipher_path.unlink(missing_ok=True)
        raise
    print(f"OK: vaulted {artifact_id} -> institutio/vault/{cipher_name}")
    print("    next: git add the ciphertext and public-safe manifest")
    return 0


def cmd_verify(_args: argparse.Namespace) -> int:
    rows = _read_manifest()
    tracked = _tracked_files()
    failures: list[str] = []
    manifest_relative = MANIFEST.relative_to(ROOT).as_posix()
    if rows and manifest_relative not in tracked:
        failures.append(f"manifest not git-tracked (custody gap): {manifest_relative}")
    seen_ids: set[str] = set()
    seen_ciphers: set[str] = set()
    for line_number, row in enumerate(rows, 1):
        failures.extend(_validate_public_row(row, line_number))
        artifact_id = str(row.get("artifact_id") or "")
        name = str(row.get("ciphertext") or "")
        if artifact_id in seen_ids:
            failures.append(f"duplicate artifact id: {artifact_id}")
        if name in seen_ciphers:
            failures.append(f"duplicate ciphertext: {name}")
        seen_ids.add(artifact_id)
        seen_ciphers.add(name)
        try:
            path = _cipher_path(row)
        except VaultError:
            continue
        if not path.is_file() or path.is_symlink():
            failures.append(f"missing or unsafe ciphertext: {name}")
            continue
        if _sha256(path) != row.get("ciphertext_sha256"):
            failures.append(f"ciphertext sha mismatch: {name}")
        if path.stat().st_size != row.get("ciphertext_bytes"):
            failures.append(f"ciphertext byte count mismatch: {name}")
        relative = path.relative_to(ROOT).as_posix()
        if relative not in tracked:
            failures.append(f"ciphertext not git-tracked (custody gap): {relative}")
    for stray in VAULT_DIR.glob("*.gpg"):
        if stray.name not in seen_ciphers:
            failures.append(f"unmanifested ciphertext: {stray.name}")
    for stray in VAULT_DIR.iterdir() if VAULT_DIR.exists() else []:
        if stray.is_file() and stray != MANIFEST and stray.suffix != ".gpg":
            failures.append(f"unsupported vault file: {stray.name}")
    if failures:
        print("FAIL: private-vault custody:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"OK: private-vault custody ({len(rows)} row(s); ciphertext tracked; manifest public-safe)")
    return 0


def _temporary_file(directory: Path, artifact_id: str, suffix: str) -> Path:
    fd, name = tempfile.mkstemp(prefix=f".{artifact_id}.", suffix=suffix, dir=directory)
    os.close(fd)
    path = Path(name)
    os.chmod(path, 0o600)
    return path


def cmd_restore(args: argparse.Namespace) -> int:
    rows = _read_manifest()
    for line_number, row in enumerate(rows, 1):
        errors = _validate_public_row(row, line_number)
        if errors:
            raise VaultError("; ".join(errors))
    if args.all:
        targets = rows
    else:
        artifact_id = _safe_artifact_id(args.artifact_id or "")
        targets = [row for row in rows if row.get("artifact_id") == artifact_id]
    if not targets:
        raise VaultError("no matching vault entry (use list)")
    destination_root = Path(args.dest).expanduser().resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    for row in targets:
        artifact_id = _safe_artifact_id(str(row.get("artifact_id") or ""))
        cipher_path = _cipher_path(row)
        envelope = _temporary_file(destination_root, artifact_id, ".envelope")
        plaintext = _temporary_file(destination_root, artifact_id, ".plaintext")
        try:
            _decrypt_file(cipher_path, envelope)
            original_name = _extract_envelope(envelope, artifact_id, plaintext)
            final_name = f"{artifact_id}--{original_name}"
            final_path = _contained_file(destination_root, final_name)
            if final_path.exists():
                raise VaultError(f"restore target already exists: {final_name}")
            os.replace(plaintext, final_path)
            os.chmod(final_path, 0o600)
            print(f"OK: restored {artifact_id} (encrypted hash verified)")
        finally:
            envelope.unlink(missing_ok=True)
            plaintext.unlink(missing_ok=True)
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    rows = _read_manifest()
    if not rows:
        print("(vault empty)")
        return 0
    for row in sorted(rows, key=lambda item: item.get("vaulted_at", ""), reverse=True):
        print(f"{row.get('vaulted_at', '?')}  {row.get('artifact_id', '?'):24s}  {row.get('ciphertext', '?')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="encrypt a file into the vault")
    add.add_argument("file")
    add.add_argument("--artifact-id", required=True, help="neutral public id (lowercase letters, digits, hyphens)")
    add.set_defaults(fn=cmd_add)

    verify = sub.add_parser("verify", help="validate public-safe ciphertext custody")
    verify.set_defaults(fn=cmd_verify)

    restore = sub.add_parser("restore", help="decrypt entries (requires private key)")
    restore.add_argument("--artifact-id", help="neutral id to restore")
    restore.add_argument("--all", action="store_true")
    restore.add_argument("--dest", default=str(Path.home() / ".limen-restore"))
    restore.set_defaults(fn=cmd_restore)

    listing = sub.add_parser("list", help="list neutral artifact ids, newest first")
    listing.set_defaults(fn=cmd_list)

    args = parser.parse_args()
    if args.cmd == "restore" and not args.all and not args.artifact_id:
        parser.error("restore requires --artifact-id or --all")
    try:
        return args.fn(args)
    except VaultError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
