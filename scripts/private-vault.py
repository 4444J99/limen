#!/usr/bin/env python3
"""PRIVATE-VAULT — git-tracked ciphertext custody for private artifacts.

Ciphertext and a deliberately minimal manifest are tracked. Plaintext names, source paths,
content hashes, sizes, and descriptions live only inside the encrypted envelope. The public
manifest contains only a neutral artifact id plus ciphertext custody metadata.

  add      encrypt a file into a v2 envelope and append a public-safe manifest row
  verify   validate manifest schema, containment, ciphertext integrity, and git custody
  restore  decrypt, verify, and atomically publish one artifact (or --all)
  recovery-check  prove the real private key can round-trip a synthetic canary
  list     list neutral artifact ids, newest first

The committed public key is the encryption source of truth. Decryption uses the operator's
normal GPG keyring and therefore still requires the private key.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent.parent
PUBKEY = ROOT / "docs" / "keys" / "anthony-padavano-gpg.asc"
VAULT_DIR = ROOT / "institutio" / "vault"
MANIFEST = VAULT_DIR / "manifest.jsonl"
FINGERPRINT = "205A566A5FFE43D2E28E05A4C5B98FFAF8ED000E"
ENCRYPTION_SUBKEY_ID = "7C99B54C1ED4B555"

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
BOOTSTRAP_ARTIFACT_IDS = frozenset(
    {
        "artifact-001",
        "artifact-002",
        "artifact-003",
        "styx-effort-brief-20260809",
    }
)
PRIVATE_TRACKING_PREFIXES = (".limen-private/", ".agent-runtime/", ".limen-workstream/")
COMMAND_TIMEOUT_SECONDS = 120
LOCK_TIMEOUT_SECONDS = 30
DIAGNOSTIC_LIMIT = 4096
RECOVERY_CANARY = b"LIMEN-PRIVATE-VAULT-RECOVERY-CANARY-V1\n"


class VaultError(RuntimeError):
    """A user-facing vault contract failure."""


def _diagnostic(run: subprocess.CompletedProcess[str]) -> str:
    value = (run.stderr or run.stdout or "").strip()
    if len(value) > DIAGNOSTIC_LIMIT:
        return value[:DIAGNOSTIC_LIMIT] + "... [truncated]"
    return value


def _run_command(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            env=env,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise VaultError(f"required executable is unavailable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise VaultError(f"{args[0]} exceeded the {COMMAND_TIMEOUT_SECONDS}s command deadline") from exc


@contextmanager
def _vault_lock() -> Iterator[None]:
    identity = hashlib.sha256(str(ROOT.resolve()).encode("utf-8")).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"limen-private-vault-{os.getuid()}-{identity}.lock"
    flags = os.O_CREAT | os.O_RDWR | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as exc:
        raise VaultError(f"cannot open the bounded vault lock ({exc.errno})") from exc
    lock_info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(lock_info.st_mode)
        or lock_info.st_uid != os.getuid()
        or stat.S_IMODE(lock_info.st_mode) != 0o600
    ):
        os.close(descriptor)
        raise VaultError("vault lock must be an owner-only regular file")
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    try:
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise VaultError(f"vault lock exceeded the {LOCK_TIMEOUT_SECONDS}s deadline")
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


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
    artifact_id_value = row.get("artifact_id")
    if not isinstance(artifact_id_value, str):
        raise VaultError("artifact id must be a string")
    artifact_id = _safe_artifact_id(artifact_id_value)
    expected = f"{artifact_id}.gpg"
    name = str(row.get("ciphertext") or "")
    if name != expected:
        raise VaultError(f"ciphertext for {artifact_id} must be named {expected}")
    return _contained_file(VAULT_DIR, name)


def _read_manifest() -> list[dict]:
    if MANIFEST.is_symlink():
        raise VaultError("manifest must be a regular non-symlink file")
    if not MANIFEST.exists():
        return []
    if not MANIFEST.is_file():
        raise VaultError("manifest must be a regular non-symlink file")
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
    fd, temporary_name = tempfile.mkstemp(prefix=".private-vault-manifest.", dir=ROOT)
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
    run = _run_command(["git", "-C", str(ROOT), "ls-files"])
    if run.returncode != 0:
        raise VaultError(f"cannot inspect git custody: {_diagnostic(run)}")
    return set(run.stdout.splitlines())


def _historical_artifact_ids() -> set[str]:
    """Return every neutral v2 artifact id ever admitted to committed custody."""
    manifest_relative = MANIFEST.relative_to(ROOT).as_posix()
    history = _run_command(["git", "-C", str(ROOT), "log", "--format=%H", "--follow", "--", manifest_relative])
    if history.returncode != 0:
        raise VaultError(f"cannot inspect manifest custody history: {_diagnostic(history)}")

    artifact_ids: set[str] = set()
    for revision in history.stdout.splitlines():
        snapshot = _run_command(["git", "-C", str(ROOT), "show", f"{revision}:{manifest_relative}"])
        # A deletion commit is part of the path history but has no file at that revision.
        if snapshot.returncode != 0:
            continue
        for line_number, raw in enumerate(snapshot.stdout.splitlines(), 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise VaultError(f"committed manifest history contains invalid JSON at line {line_number}") from exc
            if not isinstance(row, dict) or row.get("schema") != SCHEMA:
                continue
            artifact_id = row.get("artifact_id")
            if not isinstance(artifact_id, str):
                raise VaultError("committed manifest history contains a non-string artifact id")
            artifact_ids.add(_safe_artifact_id(artifact_id))
    return artifact_ids


def _reject_tracked_plaintext(source: Path) -> None:
    try:
        relative = source.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return
    if relative in _tracked_files():
        raise VaultError("refusing to vault plaintext that is already git-tracked")
    if not any(relative.startswith(prefix) for prefix in PRIVATE_TRACKING_PREFIXES):
        raise VaultError("repository-local plaintext must remain under a gitignored private namespace")


def _gpg_env(gnupghome: str) -> dict:
    env = dict(os.environ)
    env["GNUPGHOME"] = gnupghome
    return env


def _import_pubkey(gnupghome: str) -> None:
    if not PUBKEY.exists():
        raise VaultError("committed public key is missing")
    run = _run_command(
        ["gpg", "--batch", "--import", str(PUBKEY)],
        env=_gpg_env(gnupghome),
    )
    if run.returncode != 0:
        raise VaultError(f"public-key import failed: {_diagnostic(run)}")


def _validate_committed_pubkey() -> None:
    with tempfile.TemporaryDirectory() as gnupghome:
        os.chmod(gnupghome, 0o700)
        _import_pubkey(gnupghome)
        listing = _run_command(
            ["gpg", "--batch", "--with-colons", "--fingerprint", "--fingerprint", "--list-keys"],
            env=_gpg_env(gnupghome),
        )
        if listing.returncode != 0:
            raise VaultError(f"committed public-key inspection failed: {_diagnostic(listing)}")

        primary_fingerprints: set[str] = set()
        encryption_subkeys: set[str] = set()
        pending_key: tuple[str, str, str] | None = None
        for line in listing.stdout.splitlines():
            fields = line.split(":")
            record_type = fields[0] if fields else ""
            if record_type in {"pub", "sub"} and len(fields) > 11:
                pending_key = (record_type, fields[4].upper(), fields[11].lower())
            elif record_type == "fpr" and len(fields) > 9 and pending_key is not None:
                key_type, key_id, capabilities = pending_key
                if key_type == "pub":
                    primary_fingerprints.add(fields[9].upper())
                elif "e" in capabilities:
                    encryption_subkeys.add(key_id)
                pending_key = None

        if primary_fingerprints != {FINGERPRINT}:
            raise VaultError("committed public key does not match the pinned primary fingerprint")
        if ENCRYPTION_SUBKEY_ID not in encryption_subkeys:
            raise VaultError("committed public key lacks the pinned encryption subkey")

        canary = Path(gnupghome) / "synthetic-canary"
        ciphertext = Path(gnupghome) / "synthetic-canary.gpg"
        canary.write_bytes(RECOVERY_CANARY)
        os.chmod(canary, 0o600)
        probe = _run_command(
            [
                "gpg",
                "--batch",
                "--yes",
                "--trust-model",
                "always",
                "--recipient",
                f"{ENCRYPTION_SUBKEY_ID}!",
                "--output",
                str(ciphertext),
                "--encrypt",
                str(canary),
            ],
            env=_gpg_env(gnupghome),
        )
        if probe.returncode != 0 or not ciphertext.is_file():
            raise VaultError("pinned encryption subkey is unusable")


def _encrypt_file(source: Path, destination: Path) -> None:
    with tempfile.TemporaryDirectory() as gnupghome:
        os.chmod(gnupghome, 0o700)
        _import_pubkey(gnupghome)
        run = _run_command(
            [
                "gpg",
                "--batch",
                "--yes",
                "--trust-model",
                "always",
                "--recipient",
                f"{ENCRYPTION_SUBKEY_ID}!",
                "--output",
                str(destination),
                "--encrypt",
                str(source),
            ],
            env=_gpg_env(gnupghome),
        )
    if run.returncode != 0 or not destination.is_file():
        raise VaultError(f"encryption failed: {_diagnostic(run)}")


def _decrypt_file(source: Path, destination: Path) -> None:
    run = _run_command(["gpg", "--batch", "--yes", "--output", str(destination), "--decrypt", str(source)])
    if run.returncode != 0 or not destination.is_file():
        raise VaultError(f"decryption failed (private key required): {_diagnostic(run)}")


def _ciphertext_recipient_keyids(ciphertext: Path) -> set[str]:
    run = _run_command(["gpg", "--batch", "--list-only", "--status-fd", "1", "--decrypt", str(ciphertext)])
    if run.returncode != 0:
        raise VaultError(f"cannot inspect ciphertext recipient: {_diagnostic(run)}")
    recipients = {
        fields[2].upper()
        for line in run.stdout.splitlines()
        if line.startswith("[GNUPG:] ENC_TO ") and len(fields := line.split()) >= 3
    }
    if not recipients:
        raise VaultError("ciphertext has no inspectable OpenPGP recipient")
    return recipients


def _ciphertext_failures(row: dict, path: Path) -> list[str]:
    name = str(row.get("ciphertext") or "")
    failures: list[str] = []
    if not path.is_file() or path.is_symlink():
        return [f"missing or unsafe ciphertext: {name}"]
    if _sha256(path) != row.get("ciphertext_sha256"):
        failures.append(f"ciphertext sha mismatch: {name}")
    if path.stat().st_size != row.get("ciphertext_bytes"):
        failures.append(f"ciphertext byte count mismatch: {name}")
    if not failures:
        try:
            recipients = _ciphertext_recipient_keyids(path)
        except VaultError as exc:
            failures.append(f"ciphertext recipient inspection failed: {name}: {exc}")
        else:
            if recipients != {ENCRYPTION_SUBKEY_ID}:
                failures.append(f"ciphertext recipient mismatch: {name}")
    return failures


def _snapshot_source(source: Path, destination: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    with source.open("rb") as input_handle, destination.open("wb") as output:
        for chunk in iter(lambda: input_handle.read(1 << 20), b""):
            output.write(chunk)
            digest.update(chunk)
            count += len(chunk)
    os.chmod(destination, 0o600)
    return digest.hexdigest(), count


def _write_envelope(
    snapshot: Path,
    artifact_id: str,
    original_name: str,
    plaintext_sha256: str,
    plaintext_bytes: int,
    destination: Path,
) -> None:
    header = {
        "artifact_id": artifact_id,
        "original_name": original_name,
        "plaintext_sha256": plaintext_sha256,
        "plaintext_bytes": plaintext_bytes,
    }
    encoded_header = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded_header) > MAX_HEADER_BYTES:
        raise VaultError("encrypted envelope header is too large")
    with destination.open("wb") as output, snapshot.open("rb") as input_handle:
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
    if not getattr(args, "apply", False):
        raise VaultError("add is mutating; rerun with --apply")
    artifact_id = _safe_artifact_id(args.artifact_id)
    source = Path(args.file).expanduser().resolve()
    if not source.is_file():
        raise VaultError("source is not a file")
    _reject_tracked_plaintext(source)
    with _vault_lock():
        rows = _read_manifest()
        for line_number, row in enumerate(rows, 1):
            errors = _validate_public_row(row, line_number)
            if errors:
                raise VaultError("; ".join(errors))
            if row["artifact_id"] == artifact_id:
                raise VaultError(f"artifact id is already vaulted: {artifact_id}")

        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        cipher_name = f"{artifact_id}.gpg"
        cipher_path = _contained_file(VAULT_DIR, cipher_name)
        if cipher_path.exists():
            raise VaultError(f"ciphertext already exists without a matching manifest row: {cipher_name}")

        temporary_cipher = _temporary_file(VAULT_DIR, artifact_id, ".ciphertext.gpg")
        try:
            with tempfile.TemporaryDirectory() as temporary_directory:
                temporary_root = Path(temporary_directory)
                snapshot = temporary_root / "snapshot"
                envelope = temporary_root / "envelope"
                plaintext_sha256, plaintext_bytes = _snapshot_source(source, snapshot)
                _write_envelope(
                    snapshot,
                    artifact_id,
                    source.name,
                    plaintext_sha256,
                    plaintext_bytes,
                    envelope,
                )
                _encrypt_file(envelope, temporary_cipher)
            os.chmod(temporary_cipher, 0o644)
            os.replace(temporary_cipher, cipher_path)
        finally:
            temporary_cipher.unlink(missing_ok=True)

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
    tracked = _tracked_files()
    failures: list[str] = []
    manifest_relative = MANIFEST.relative_to(ROOT).as_posix()
    manifest_is_safe = MANIFEST.is_file() and not MANIFEST.is_symlink()
    if not manifest_is_safe:
        failures.append(f"required manifest is missing: {manifest_relative}")
        rows: list[dict] = []
    else:
        rows = _read_manifest()
    if manifest_relative not in tracked:
        failures.append(f"manifest not git-tracked (custody gap): {manifest_relative}")
    try:
        _validate_committed_pubkey()
    except VaultError as exc:
        failures.append(f"committed public-key validation failed: {exc}")
    for prefix in PRIVATE_TRACKING_PREFIXES:
        if any(path.startswith(prefix) for path in tracked):
            failures.append(f"private plaintext namespace contains git-tracked content: {prefix}")
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
        failures.extend(_ciphertext_failures(row, path))
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative not in tracked:
            failures.append(f"ciphertext not git-tracked (custody gap): {relative}")
    try:
        custody_baseline = BOOTSTRAP_ARTIFACT_IDS | _historical_artifact_ids()
    except VaultError as exc:
        failures.append(str(exc))
        custody_baseline = BOOTSTRAP_ARTIFACT_IDS
    missing_required = sorted(custody_baseline - seen_ids)
    if missing_required:
        failures.append(f"required custody baseline is missing neutral ids: {', '.join(missing_required)}")
    for stray in VAULT_DIR.iterdir() if VAULT_DIR.exists() else []:
        if stray.is_dir():
            failures.append(f"unsupported vault directory: {stray.name}")
        elif stray.suffix == ".gpg" and stray.name not in seen_ciphers:
            failures.append(f"unmanifested ciphertext: {stray.name}")
        elif stray.is_file() and stray != MANIFEST and stray.suffix != ".gpg":
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


def _restore_name(destination_root: Path, artifact_id: str, original_name: str) -> str:
    proposed = f"{artifact_id}--{original_name}"
    try:
        name_max = os.pathconf(destination_root, "PC_NAME_MAX")
    except (OSError, ValueError):
        name_max = 255
    if len(os.fsencode(proposed)) <= name_max:
        return proposed
    return f"{artifact_id}--restored"


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
    for row in targets:
        failures = _ciphertext_failures(row, _cipher_path(row))
        if failures:
            raise VaultError("; ".join(failures))
    if not getattr(args, "apply", False):
        raise VaultError("restore is mutating; rerun with --apply")
    destination_root = Path(args.dest).expanduser().resolve()
    try:
        destination_root.mkdir(parents=True, mode=0o700)
    except FileExistsError:
        created_destination = False
    else:
        created_destination = True
    if created_destination:
        os.chmod(destination_root, 0o700)
    elif not destination_root.is_dir() or stat.S_IMODE(destination_root.stat().st_mode) & 0o077:
        raise VaultError("restore destination must be an owner-only directory")
    for row in targets:
        artifact_id = _safe_artifact_id(str(row.get("artifact_id") or ""))
        cipher_path = _cipher_path(row)
        envelope = _temporary_file(destination_root, artifact_id, ".envelope")
        plaintext = _temporary_file(destination_root, artifact_id, ".plaintext")
        try:
            _decrypt_file(cipher_path, envelope)
            original_name = _extract_envelope(envelope, artifact_id, plaintext)
            final_name = _restore_name(destination_root, artifact_id, original_name)
            final_path = _contained_file(destination_root, final_name)
            if final_path.exists():
                raise VaultError(f"restore target already exists: {final_name}")
            os.replace(plaintext, final_path)
            os.chmod(final_path, 0o600)
            print(f"OK: restored {artifact_id} (pinned ciphertext and plaintext verified)")
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


def cmd_recovery_check(args: argparse.Namespace) -> int:
    if not getattr(args, "apply", False):
        raise VaultError("recovery-check writes a temporary plaintext canary; rerun with --apply")
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        source = temporary_root / "synthetic-canary"
        ciphertext = temporary_root / "synthetic-canary.gpg"
        restored = temporary_root / "synthetic-canary.restored"
        source.write_bytes(RECOVERY_CANARY)
        os.chmod(source, 0o600)
        _encrypt_file(source, ciphertext)
        if _ciphertext_recipient_keyids(ciphertext) != {ENCRYPTION_SUBKEY_ID}:
            raise VaultError("synthetic recovery canary has the wrong recipient")
        _decrypt_file(ciphertext, restored)
        if restored.read_bytes() != RECOVERY_CANARY:
            raise VaultError("synthetic recovery canary content mismatch")
        os.chmod(restored, 0o600)
    print("OK: real-key recovery canary passed (synthetic content only)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    add = sub.add_parser("add", help="encrypt a file into the vault")
    add.add_argument("file")
    add.add_argument("--artifact-id", required=True, help="neutral public id (lowercase letters, digits, hyphens)")
    add.add_argument("--apply", action="store_true", help="authorize ciphertext and manifest writes")
    add.set_defaults(fn=cmd_add)

    verify = sub.add_parser("verify", help="validate public-safe ciphertext custody")
    verify.set_defaults(fn=cmd_verify)

    restore = sub.add_parser("restore", help="decrypt entries (requires private key)")
    selectors = restore.add_mutually_exclusive_group(required=True)
    selectors.add_argument("--artifact-id", help="neutral id to restore")
    selectors.add_argument("--all", action="store_true")
    restore.add_argument("--dest", default=str(Path.home() / ".limen-restore"))
    restore.add_argument("--apply", action="store_true", help="authorize plaintext restoration")
    restore.set_defaults(fn=cmd_restore)

    recovery = sub.add_parser("recovery-check", help="round-trip a synthetic canary with the real private key")
    recovery.add_argument("--apply", action="store_true", help="authorize temporary plaintext canary writes")
    recovery.set_defaults(fn=cmd_recovery_check)

    listing = sub.add_parser("list", help="list neutral artifact ids, newest first")
    listing.set_defaults(fn=cmd_list)

    args = parser.parse_args()
    try:
        return args.fn(args)
    except VaultError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"FAIL: filesystem operation failed ({exc.errno})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
