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
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

ROOT = Path(__file__).resolve().parent.parent
PUBKEY = ROOT / "docs" / "keys" / "anthony-padavano-gpg.asc"
VAULT_DIR = ROOT / "institutio" / "vault"
MANIFEST = VAULT_DIR / "manifest.jsonl"
FINGERPRINT = "205A566A5FFE43D2E28E05A4C5B98FFAF8ED000E"
ENCRYPTION_SUBKEY_ID = "7C99B54C1ED4B555"

SCHEMA = "private-vault-manifest-v2"
MAGIC = b"LIMEN-PRIVATE-VAULT-V2\n"
MAX_HEADER_BYTES = 64 * 1024
ARTIFACT_ID_RE = re.compile(r"^artifact-[0-9]{3,55}$")
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
        "artifact-004",
    }
)
PRIVATE_TRACKING_PREFIXES = (".limen-private/", ".agent-runtime/", ".limen-workstream/")
PRIVATE_TRACKING_ROOTS = tuple(prefix.rstrip("/") for prefix in PRIVATE_TRACKING_PREFIXES)
COMMAND_TIMEOUT_SECONDS = 120
LOCK_TIMEOUT_SECONDS = 30
DIAGNOSTIC_LIMIT = 4096
RECOVERY_CANARY = b"LIMEN-PRIVATE-VAULT-RECOVERY-CANARY-V1\n"
PUBLIC_SAFE_HISTORY_ROOT = "eeaaa85b7e7270e1b9e9140b78f7ff2360e2524f"


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
            errors="surrogateescape",
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise VaultError(f"required executable is unavailable: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise VaultError(f"{args[0]} exceeded the {COMMAND_TIMEOUT_SECONDS}s command deadline") from exc


def _git_common_directory() -> Path | None:
    marker = ROOT / ".git"
    if marker.is_dir():
        git_directory = marker
    elif marker.is_file() and not marker.is_symlink():
        try:
            header = marker.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise VaultError("cannot establish authentic Git history") from exc
        if not header.startswith("gitdir: "):
            raise VaultError("cannot establish authentic Git history")
        git_directory = Path(header.removeprefix("gitdir: "))
        if not git_directory.is_absolute():
            git_directory = marker.parent / git_directory
        git_directory = git_directory.resolve()
    else:
        return None
    common_marker = git_directory / "commondir"
    if not common_marker.exists():
        return git_directory
    try:
        common_value = common_marker.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise VaultError("cannot establish authentic Git history") from exc
    if not common_value:
        raise VaultError("cannot establish authentic Git history")
    common_directory = Path(common_value)
    if not common_directory.is_absolute():
        common_directory = git_directory / common_directory
    return common_directory.resolve()


def _reject_legacy_grafts() -> None:
    common_directory = _git_common_directory()
    if common_directory is not None and os.path.lexists(common_directory / "info" / "grafts"):
        raise VaultError("refusing rewritten Git custody history")


def _git_command(*args: str) -> subprocess.CompletedProcess[str]:
    _reject_legacy_grafts()
    return _run_command(["git", "--no-replace-objects", "-C", str(ROOT), *args])


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
        raise VaultError("artifact id must use the neutral artifact-NNN form")
    return value


def _reject_duplicate_fields(pairs: list[tuple[str, object]]) -> dict:
    value: dict = {}
    for key, item in pairs:
        if key in value:
            raise VaultError("manifest object contains a duplicate field")
        value[key] = item
    return value


def _canonical_vaulted_at(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo == timezone.utc and value == parsed.isoformat(timespec="seconds")


def _contained_file(base: Path, name: str) -> Path:
    if not name or Path(name).name != name or Path(name).is_absolute():
        raise VaultError(f"unsafe vault filename: {name!r}")
    base_resolved = base.resolve()
    candidate = base / name
    if candidate.parent.resolve() != base_resolved:
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
            row = json.loads(raw, object_pairs_hook=_reject_duplicate_fields)
        except json.JSONDecodeError as exc:
            raise VaultError(f"manifest line {line_number} is invalid JSON: {exc.msg}") from exc
        except VaultError as exc:
            raise VaultError(f"manifest line {line_number} contains a duplicate field") from exc
        if not isinstance(row, dict):
            raise VaultError(f"manifest line {line_number} is not an object")
        rows.append(row)
    return rows


def _validate_public_row(row: dict, line_number: int) -> list[str]:
    errors: list[str] = []
    extra = sorted(set(row) - PUBLIC_FIELDS)
    missing = sorted(PUBLIC_FIELDS - set(row))
    if extra:
        errors.append(f"manifest line {line_number} exposes unsupported fields")
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
    if not _canonical_vaulted_at(row.get("vaulted_at")):
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
    run = _git_command("ls-files", "-z")
    if run.returncode != 0:
        raise VaultError(f"cannot inspect git custody: {_diagnostic(run)}")
    return {path for path in run.stdout.split("\0") if path}


def _index_entry_matches_worktree(relative: str) -> bool:
    staged = _git_command("ls-files", "--stage", "-z", "--", relative)
    if staged.returncode != 0:
        return False
    entries = [entry for entry in staged.stdout.split("\0") if entry]
    if len(entries) != 1 or "\t" not in entries[0]:
        return False
    metadata, staged_path = entries[0].split("\t", 1)
    fields = metadata.split()
    if len(fields) != 3 or fields[0] != "100644" or fields[2] != "0" or staged_path != relative:
        return False
    worktree = _git_command("hash-object", f"--path={relative}", "--", relative)
    return worktree.returncode == 0 and worktree.stdout.strip() == fields[1]


def _custody_metadata(row: dict) -> tuple[str, str, int, str, str]:
    ciphertext = row.get("ciphertext")
    ciphertext_sha256 = row.get("ciphertext_sha256")
    ciphertext_bytes = row.get("ciphertext_bytes")
    recipient_fpr = row.get("recipient_fpr")
    vaulted_at = row.get("vaulted_at")
    if (
        not isinstance(ciphertext, str)
        or not isinstance(ciphertext_sha256, str)
        or not SHA256_RE.fullmatch(ciphertext_sha256)
        or not isinstance(ciphertext_bytes, int)
        or ciphertext_bytes < 0
        or not isinstance(recipient_fpr, str)
        or not _canonical_vaulted_at(vaulted_at)
    ):
        raise VaultError("manifest contains invalid immutable custody metadata")
    return ciphertext, ciphertext_sha256, ciphertext_bytes, recipient_fpr, vaulted_at


def _historical_artifacts() -> dict[str, tuple[str, str, int, str, str]]:
    """Return immutable metadata for every neutral v2 artifact admitted to custody."""
    shallow = _git_command("rev-parse", "--is-shallow-repository")
    if shallow.returncode != 0:
        raise VaultError("cannot prove complete committed custody history")
    if shallow.stdout.strip() != "false":
        raise VaultError("committed custody history requires a non-shallow repository")
    manifest_relative = MANIFEST.relative_to(ROOT).as_posix()
    history = _git_command("rev-list", "--full-history", "HEAD", "--", manifest_relative)
    if history.returncode != 0:
        raise VaultError(f"cannot inspect manifest custody history: {_diagnostic(history)}")
    safe_root_object = _git_command("cat-file", "-e", f"{PUBLIC_SAFE_HISTORY_ROOT}^{{commit}}")
    safe_root_is_reachable = False
    if safe_root_object.returncode == 0:
        safe_root = _git_command("merge-base", "--is-ancestor", PUBLIC_SAFE_HISTORY_ROOT, "HEAD")
        if safe_root.returncode not in {0, 1}:
            raise VaultError("cannot inspect the public-safe manifest history boundary")
        safe_root_is_reachable = safe_root.returncode == 0

    artifacts: dict[str, tuple[str, str, int, str, str]] = {}
    for revision in history.stdout.splitlines():
        presence = _git_command("ls-tree", "--name-only", "-z", revision, "--", manifest_relative)
        if presence.returncode != 0:
            raise VaultError("cannot inspect a committed manifest history tree")
        historical_paths = [path for path in presence.stdout.split("\0") if path]
        if not historical_paths:
            # A deletion commit is part of the fixed-path history but has no file at that revision.
            continue
        if historical_paths != [manifest_relative]:
            raise VaultError("committed manifest history tree returned an unexpected path")
        snapshot = _git_command("show", f"{revision}:{manifest_relative}")
        if snapshot.returncode != 0:
            raise VaultError("cannot read a committed manifest history snapshot")
        require_public_safe = True
        if safe_root_is_reachable:
            before_safe_root = _git_command("merge-base", "--is-ancestor", revision, PUBLIC_SAFE_HISTORY_ROOT)
            if before_safe_root.returncode not in {0, 1}:
                raise VaultError("cannot classify a committed manifest history revision")
            require_public_safe = revision == PUBLIC_SAFE_HISTORY_ROOT or before_safe_root.returncode == 1
        for line_number, raw in enumerate(snapshot.stdout.splitlines(), 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw, object_pairs_hook=_reject_duplicate_fields)
            except json.JSONDecodeError as exc:
                raise VaultError(f"committed manifest history contains invalid JSON at line {line_number}") from exc
            except VaultError as exc:
                raise VaultError(
                    f"committed manifest history contains a duplicate field at line {line_number}"
                ) from exc
            if not isinstance(row, dict):
                if require_public_safe:
                    raise VaultError("committed manifest history contains a non-public-safe row")
                continue
            if require_public_safe and _validate_public_row(row, line_number):
                raise VaultError("committed manifest history contains a non-public-safe row")
            if row.get("schema") != SCHEMA:
                continue
            artifact_id = row.get("artifact_id")
            if not isinstance(artifact_id, str):
                raise VaultError("committed manifest history contains a non-string artifact id")
            if ARTIFACT_ID_RE.fullmatch(artifact_id):
                metadata = _custody_metadata(row)
                previous = artifacts.get(artifact_id)
                if previous is not None and previous != metadata:
                    raise VaultError("committed custody history changes immutable artifact metadata")
                artifacts[artifact_id] = metadata
    return artifacts


def _require_committed_custody(rows: list[dict]) -> None:
    historical_artifacts = _historical_artifacts()
    for row in rows:
        artifact_id_value = row.get("artifact_id")
        if not isinstance(artifact_id_value, str):
            raise VaultError("restore target has an invalid artifact id")
        artifact_id = _safe_artifact_id(artifact_id_value)
        expected_metadata = historical_artifacts.get(artifact_id)
        if expected_metadata is None:
            raise VaultError(f"restore target is not admitted to committed custody: {artifact_id}")
        if _custody_metadata(row) != expected_metadata:
            raise VaultError(f"restore target differs from committed custody history: {artifact_id}")


def _reject_tracked_plaintext(source: Path) -> tuple[int, int]:
    source_info = source.stat()
    source_identity = source_info.st_dev, source_info.st_ino
    tracked = _tracked_files()
    for tracked_path in tracked:
        try:
            tracked_info = (ROOT / tracked_path).stat(follow_symlinks=False)
        except (FileNotFoundError, NotADirectoryError, OSError):
            continue
        if stat.S_ISREG(tracked_info.st_mode) and (tracked_info.st_dev, tracked_info.st_ino) == source_identity:
            raise VaultError("refusing to vault plaintext whose file object is already git-tracked")
    try:
        relative = source.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return source_identity
    if relative in tracked:
        raise VaultError("refusing to vault plaintext that is already git-tracked")
    if not any(relative.startswith(prefix) for prefix in PRIVATE_TRACKING_PREFIXES):
        raise VaultError("repository-local plaintext must remain under a gitignored private namespace")
    return source_identity


def _require_untracked_source_identity(source: Path, expected_identity: tuple[int, int]) -> None:
    current_identity = _reject_tracked_plaintext(source)
    if current_identity != expected_identity:
        raise VaultError("private source changed during custody admission")


def _gpg_env(gnupghome: str) -> dict:
    env = dict(os.environ)
    env["GNUPGHOME"] = gnupghome
    return env


def _import_pubkey(gnupghome: str) -> None:
    if not PUBKEY.is_file() or PUBKEY.is_symlink():
        raise VaultError("committed public key must be a regular non-symlink file")
    run = _run_command(
        ["gpg", "--batch", "--import", str(PUBKEY)],
        env=_gpg_env(gnupghome),
    )
    if run.returncode != 0:
        raise VaultError(f"public-key import failed: {_diagnostic(run)}")
    exported = _run_command(
        ["gpg", "--batch", "--armor", "--export", FINGERPRINT],
        env=_gpg_env(gnupghome),
    )
    if exported.returncode != 0 or not exported.stdout:
        raise VaultError("canonical public-key export failed")
    try:
        committed_armor = PUBKEY.read_text(encoding="ascii")
    except (OSError, UnicodeDecodeError) as exc:
        raise VaultError("committed public-key file is not canonical ASCII armor") from exc
    if committed_armor != exported.stdout:
        raise VaultError("committed public-key file must contain only canonical public-key armor")
    secret_listing = _run_command(
        ["gpg", "--batch", "--with-colons", "--list-secret-keys"],
        env=_gpg_env(gnupghome),
    )
    if secret_listing.returncode != 0:
        raise VaultError(f"secret-key inspection failed: {_diagnostic(secret_listing)}")
    if any(line.startswith(("sec:", "ssb:")) for line in secret_listing.stdout.splitlines()):
        raise VaultError("committed public-key file contains secret-key material")


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


def _run_gpg_from_fd(
    args: list[str], source_fd: int, destination_fd: int | None = None
) -> subprocess.CompletedProcess[str]:
    os.lseek(source_fd, 0, os.SEEK_SET)
    if destination_fd is not None:
        os.ftruncate(destination_fd, 0)
        os.lseek(destination_fd, 0, os.SEEK_SET)
    with os.fdopen(os.dup(source_fd), "rb") as source_handle:
        destination_handle = os.fdopen(os.dup(destination_fd), "wb") if destination_fd is not None else None
        try:
            return subprocess.run(
                args,
                stdin=source_handle,
                stdout=destination_handle if destination_handle is not None else subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="surrogateescape",
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise VaultError("required executable is unavailable: gpg") from exc
        except subprocess.TimeoutExpired as exc:
            raise VaultError(f"gpg exceeded the {COMMAND_TIMEOUT_SECONDS}s command deadline") from exc
        finally:
            if destination_handle is not None:
                destination_handle.close()


def _decrypt_descriptors(source_fd: int, destination_fd: int) -> None:
    run = _run_gpg_from_fd(["gpg", "--batch", "--yes", "--decrypt"], source_fd, destination_fd)
    if run.returncode != 0:
        raise VaultError(f"decryption failed (private key required): {_diagnostic(run)}")
    os.fsync(destination_fd)


def _ciphertext_recipient_keyids_fd(ciphertext_fd: int) -> set[str]:
    run = _run_gpg_from_fd(
        ["gpg", "--batch", "--list-only", "--status-fd", "1", "--decrypt"],
        ciphertext_fd,
    )
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


def _openpgp_packet_tags_handle(handle: BinaryIO, size: int) -> list[int]:
    tags: list[int] = []

    def read_octet(handle) -> int:
        raw = handle.read(1)
        if len(raw) != 1:
            raise VaultError("ciphertext has truncated OpenPGP framing")
        return raw[0]

    def skip_body(handle, length: int) -> None:
        if length < 0 or handle.tell() + length > size:
            raise VaultError("ciphertext has invalid OpenPGP packet length")
        handle.seek(length, os.SEEK_CUR)

    def read_new_length(handle) -> tuple[int, bool]:
        first = read_octet(handle)
        if first < 192:
            return first, False
        if first < 224:
            second = read_octet(handle)
            return ((first - 192) << 8) + second + 192, False
        if first == 255:
            raw = handle.read(4)
            if len(raw) != 4:
                raise VaultError("ciphertext has truncated OpenPGP packet length")
            return int.from_bytes(raw, "big"), False
        return 1 << (first & 0x1F), True

    while handle.tell() < size:
        header = read_octet(handle)
        if not header & 0x80:
            raise VaultError("ciphertext contains bytes outside OpenPGP packet framing")
        if header & 0x40:
            tags.append(header & 0x3F)
            length, partial = read_new_length(handle)
            skip_body(handle, length)
            while partial:
                length, partial = read_new_length(handle)
                skip_body(handle, length)
            continue

        tags.append((header >> 2) & 0x0F)
        length_type = header & 0x03
        if length_type == 3:
            raise VaultError("ciphertext uses indeterminate OpenPGP packet framing")
        length_octets = (1, 2, 4)[length_type]
        raw_length = handle.read(length_octets)
        if len(raw_length) != length_octets:
            raise VaultError("ciphertext has truncated OpenPGP packet length")
        skip_body(handle, int.from_bytes(raw_length, "big"))

    if tags not in ([1, 18], [1, 20]):
        raise VaultError("ciphertext has an unexpected OpenPGP packet sequence")
    return tags


def _openpgp_packet_tags(ciphertext: Path) -> list[int]:
    """Parse complete OpenPGP packet framing without decrypting packet bodies."""
    with ciphertext.open("rb") as handle:
        return _openpgp_packet_tags_handle(handle, ciphertext.stat().st_size)


def _openpgp_packet_tags_fd(ciphertext_fd: int) -> list[int]:
    os.lseek(ciphertext_fd, 0, os.SEEK_SET)
    with os.fdopen(os.dup(ciphertext_fd), "rb") as handle:
        return _openpgp_packet_tags_handle(handle, os.fstat(ciphertext_fd).st_size)


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
            _openpgp_packet_tags(path)
            recipients = _ciphertext_recipient_keyids(path)
        except VaultError as exc:
            failures.append(f"ciphertext recipient inspection failed: {name}: {exc}")
        else:
            if recipients != {ENCRYPTION_SUBKEY_ID}:
                failures.append(f"ciphertext recipient mismatch: {name}")
    return failures


def _sha256_fd(file_descriptor: int) -> str:
    os.lseek(file_descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    with os.fdopen(os.dup(file_descriptor), "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ciphertext_failures_fd(row: dict, file_descriptor: int) -> list[str]:
    name = str(row.get("ciphertext") or "")
    failures: list[str] = []
    info = os.fstat(file_descriptor)
    if not stat.S_ISREG(info.st_mode):
        return [f"missing or unsafe ciphertext: {name}"]
    if _sha256_fd(file_descriptor) != row.get("ciphertext_sha256"):
        failures.append(f"ciphertext sha mismatch: {name}")
    if info.st_size != row.get("ciphertext_bytes"):
        failures.append(f"ciphertext byte count mismatch: {name}")
    if not failures:
        try:
            _openpgp_packet_tags_fd(file_descriptor)
            recipients = _ciphertext_recipient_keyids_fd(file_descriptor)
        except VaultError as exc:
            failures.append(f"ciphertext recipient inspection failed: {name}: {exc}")
        else:
            if recipients != {ENCRYPTION_SUBKEY_ID}:
                failures.append(f"ciphertext recipient mismatch: {name}")
    return failures


def _copy_file_and_hash(source: BinaryIO, destination: BinaryIO) -> tuple[str, int]:
    digest = hashlib.sha256()
    count = 0
    for chunk in iter(lambda: source.read(1 << 20), b""):
        destination.write(chunk)
        digest.update(chunk)
        count += len(chunk)
    return digest.hexdigest(), count


def _snapshot_source(source: Path, destination: Path, expected_identity: tuple[int, int]) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(source, flags)
    except OSError as exc:
        raise VaultError("cannot open a stable private source snapshot") from exc
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise VaultError("private snapshot source is not a regular file")
        if (before.st_dev, before.st_ino) != expected_identity:
            raise VaultError("private source changed before snapshot creation")
        with os.fdopen(source_fd, "rb", closefd=False) as input_handle, destination.open("wb") as output:
            result = _copy_file_and_hash(input_handle, output)
            output.flush()
            os.fsync(output.fileno())
        after = os.fstat(source_fd)
    finally:
        os.close(source_fd)
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    if before_identity != after_identity or result[1] != before.st_size:
        raise VaultError("private source changed while creating its snapshot")
    os.chmod(destination, 0o600)
    return result


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


def _extract_envelope_descriptors(envelope_fd: int, artifact_id: str, destination_fd: int) -> str:
    digest = hashlib.sha256()
    count = 0
    os.lseek(envelope_fd, 0, os.SEEK_SET)
    os.ftruncate(destination_fd, 0)
    os.lseek(destination_fd, 0, os.SEEK_SET)
    with (
        os.fdopen(os.dup(envelope_fd), "rb") as source,
        os.fdopen(os.dup(destination_fd), "wb") as output,
    ):
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
        for chunk in iter(lambda: source.read(1 << 20), b""):
            output.write(chunk)
            digest.update(chunk)
            count += len(chunk)
        output.flush()
        os.fsync(output.fileno())
    if digest.hexdigest() != expected_sha or count != expected_bytes:
        raise VaultError(f"restored plaintext integrity mismatch for {artifact_id}")
    return original_name


def cmd_add(args: argparse.Namespace) -> int:
    if not getattr(args, "apply", False):
        raise VaultError("add is mutating; rerun with --apply")
    artifact_id = _safe_artifact_id(args.artifact_id)
    if artifact_id not in BOOTSTRAP_ARTIFACT_IDS:
        raise VaultError("artifact id has no public recovery admission proof")
    source = Path(args.file).expanduser().resolve()
    if not source.is_file():
        raise VaultError("source is not a file")
    source_identity = _reject_tracked_plaintext(source)
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
        cipher_published = False
        try:
            try:
                temporary_context = tempfile.TemporaryDirectory(
                    prefix=".limen-vault-plaintext-",
                    dir=source.parent,
                )
            except OSError as exc:
                raise VaultError("cannot create a secure temporary directory on the source filesystem") from exc
            with temporary_context as temporary_directory:
                temporary_root = Path(temporary_directory)
                os.chmod(temporary_root, 0o700)
                snapshot = temporary_root / "snapshot"
                envelope = temporary_root / "envelope"
                plaintext_sha256, plaintext_bytes = _snapshot_source(source, snapshot, source_identity)
                _require_untracked_source_identity(source, source_identity)
                _write_envelope(
                    snapshot,
                    artifact_id,
                    source.name,
                    plaintext_sha256,
                    plaintext_bytes,
                    envelope,
                )
                _encrypt_file(envelope, temporary_cipher)
            _require_untracked_source_identity(source, source_identity)
            os.chmod(temporary_cipher, 0o644)
            os.replace(temporary_cipher, cipher_path)
            cipher_published = True
            row = {
                "schema": SCHEMA,
                "artifact_id": artifact_id,
                "ciphertext": cipher_name,
                "ciphertext_sha256": _sha256(cipher_path),
                "ciphertext_bytes": cipher_path.stat().st_size,
                "recipient_fpr": FINGERPRINT,
                "vaulted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            _write_manifest([*rows, row])
        except BaseException:
            if cipher_published:
                cipher_path.unlink(missing_ok=True)
            raise
        finally:
            temporary_cipher.unlink(missing_ok=True)
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
    elif not _index_entry_matches_worktree(manifest_relative):
        failures.append("manifest Git index content differs from the validated worktree file")
    pubkey_relative = PUBKEY.relative_to(ROOT).as_posix()
    if pubkey_relative not in tracked or not _index_entry_matches_worktree(pubkey_relative):
        failures.append("public-key Git index content differs from the validated worktree file")
    try:
        _validate_committed_pubkey()
    except VaultError as exc:
        failures.append(f"committed public-key validation failed: {exc}")
    for prefix in PRIVATE_TRACKING_PREFIXES:
        root = prefix.rstrip("/")
        if any(path == root or path.startswith(prefix) for path in tracked):
            failures.append(f"private plaintext namespace contains git-tracked content: {prefix}")
    seen_ids: set[str] = set()
    seen_ciphers: set[str] = set()
    digest_owners: dict[str, str] = {}
    expected_vault_files = {manifest_relative}
    current_artifacts: dict[str, tuple[str, str, int, str, str]] = {}
    for line_number, row in enumerate(rows, 1):
        failures.extend(_validate_public_row(row, line_number))
        artifact_id = str(row.get("artifact_id") or "")
        name = str(row.get("ciphertext") or "")
        if artifact_id in seen_ids:
            failures.append(f"duplicate artifact id: {artifact_id}")
        if name in seen_ciphers:
            failures.append(f"duplicate ciphertext: {name}")
        digest = row.get("ciphertext_sha256")
        if isinstance(digest, str) and SHA256_RE.fullmatch(digest):
            previous_owner = digest_owners.get(digest)
            if previous_owner is not None and previous_owner != artifact_id:
                failures.append("duplicate ciphertext digest across distinct artifact ids")
            else:
                digest_owners[digest] = artifact_id
        seen_ids.add(artifact_id)
        seen_ciphers.add(name)
        if ARTIFACT_ID_RE.fullmatch(artifact_id):
            try:
                current_artifacts[artifact_id] = _custody_metadata(row)
            except VaultError:
                pass
        try:
            path = _cipher_path(row)
        except VaultError:
            continue
        failures.extend(_ciphertext_failures(row, path))
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(ROOT).as_posix()
        expected_vault_files.add(relative)
        if relative not in tracked:
            failures.append(f"ciphertext not git-tracked (custody gap): {relative}")
        elif not _index_entry_matches_worktree(relative):
            failures.append(f"ciphertext Git index content differs from the validated worktree file: {name}")
    try:
        historical_artifacts = _historical_artifacts()
        custody_baseline = BOOTSTRAP_ARTIFACT_IDS | set(historical_artifacts)
    except VaultError as exc:
        failures.append(str(exc))
        historical_artifacts = {}
        custody_baseline = BOOTSTRAP_ARTIFACT_IDS
    missing_required = sorted(custody_baseline - seen_ids)
    if missing_required:
        failures.append(f"required custody baseline is missing neutral ids: {', '.join(missing_required)}")
    unattested_ids = sorted(seen_ids - BOOTSTRAP_ARTIFACT_IDS)
    if unattested_ids:
        failures.append("non-bootstrap ciphertext lacks a public recovery admission proof")
    for artifact_id, expected_metadata in historical_artifacts.items():
        current_metadata = current_artifacts.get(artifact_id)
        if current_metadata is not None and current_metadata != expected_metadata:
            failures.append(f"immutable custody metadata changed: {artifact_id}")
    if any(path.startswith("institutio/vault/") and path not in expected_vault_files for path in tracked):
        failures.append("Git index contains unmanifested vault content")
    for stray in VAULT_DIR.iterdir() if VAULT_DIR.exists() else []:
        if stray.is_symlink():
            failures.append(f"unsupported vault symlink: {stray.name}")
        elif stray.is_dir():
            failures.append(f"unsupported vault directory: {stray.name}")
        elif stray.suffix == ".gpg" and stray.name not in seen_ciphers:
            failures.append(f"unmanifested ciphertext: {stray.name}")
        elif stray.is_file() and stray != MANIFEST and stray.suffix != ".gpg":
            failures.append(f"unsupported vault file: {stray.name}")
        elif not stray.is_file():
            failures.append(f"unsupported vault entry: {stray.name}")
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


def _temporary_file_at(directory_fd: int, artifact_id: str, suffix: str) -> tuple[str, int]:
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    for _attempt in range(128):
        name = f".{artifact_id}.{secrets.token_hex(8)}{suffix}"
        try:
            file_descriptor = os.open(name, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError:
            continue
        os.fchmod(file_descriptor, 0o600)
        return name, file_descriptor
    raise VaultError("cannot allocate a private restore temporary")


def _restore_name(destination_fd: int, artifact_id: str, original_name: str) -> str:
    proposed = f"{artifact_id}--{original_name}"
    try:
        name_max = os.fpathconf(destination_fd, "PC_NAME_MAX")
    except (OSError, ValueError):
        name_max = 255
    if len(os.fsencode(proposed)) <= name_max:
        return proposed
    return f"{artifact_id}--restored"


def _snapshot_ciphertext(source: Path, destination_fd: int) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        source_fd = os.open(source, flags)
    except OSError as exc:
        raise VaultError("cannot open a stable ciphertext snapshot") from exc
    try:
        source_info = os.fstat(source_fd)
        if not stat.S_ISREG(source_info.st_mode):
            raise VaultError("ciphertext snapshot source is not a regular file")
        os.ftruncate(destination_fd, 0)
        os.lseek(destination_fd, 0, os.SEEK_SET)
        with (
            os.fdopen(source_fd, "rb", closefd=False) as input_handle,
            os.fdopen(destination_fd, "wb", closefd=False) as output_handle,
        ):
            shutil.copyfileobj(input_handle, output_handle, length=1 << 20)
            output_handle.flush()
            os.fsync(output_handle.fileno())
    finally:
        os.close(source_fd)
    os.fchmod(destination_fd, 0o600)


def _link_no_replace_at(directory_fd: int, source: str, destination: str) -> tuple[int, int]:
    source_info = os.stat(source, dir_fd=directory_fd, follow_symlinks=False)
    identity = source_info.st_dev, source_info.st_ino
    try:
        os.link(
            source,
            destination,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except FileExistsError as exc:
        raise VaultError(f"restore target already exists: {destination}") from exc
    return identity


def _rollback_link_at(directory_fd: int, destination: str, identity: tuple[int, int]) -> None:
    try:
        current = os.stat(destination, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (current.st_dev, current.st_ino) == identity:
        os.unlink(destination, dir_fd=directory_fd)


def _destination_identity(directory_fd: int) -> tuple[int, int]:
    info = os.fstat(directory_fd)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise VaultError("restore destination must be an owner-only directory")
    return info.st_dev, info.st_ino


def _is_private_repository_destination(relative: Path) -> bool:
    value = relative.as_posix()
    return any(
        value == root or value.startswith(prefix)
        for root, prefix in zip(PRIVATE_TRACKING_ROOTS, PRIVATE_TRACKING_PREFIXES, strict=True)
    )


def _require_destination_route(destination_root: Path, *, repository_local_requested: bool) -> None:
    try:
        resolved_destination = destination_root.resolve(strict=False)
        resolved_relative = resolved_destination.relative_to(ROOT.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        if repository_local_requested:
            raise VaultError("repository-local restore destination must remain in a private namespace") from exc
        return
    if not _is_private_repository_destination(resolved_relative):
        raise VaultError("repository-local restore destination must remain in a private namespace")


def _require_destination_identity(
    destination_root: Path,
    identity: tuple[int, int],
    *,
    repository_local_requested: bool,
) -> None:
    _require_destination_route(destination_root, repository_local_requested=repository_local_requested)
    try:
        current = destination_root.stat(follow_symlinks=False)
    except OSError as exc:
        raise VaultError("restore destination changed during operation") from exc
    if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != identity:
        raise VaultError("restore destination changed during operation")
    _require_destination_route(destination_root, repository_local_requested=repository_local_requested)


def _entry_exists_at(directory_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


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
    _require_committed_custody(targets)
    for row in targets:
        failures = _ciphertext_failures(row, _cipher_path(row))
        if failures:
            raise VaultError("; ".join(failures))
    if not getattr(args, "apply", False):
        raise VaultError("restore is mutating; rerun with --apply")
    destination_root = Path(os.path.abspath(os.fspath(Path(args.dest).expanduser())))
    try:
        repository_destination = destination_root.relative_to(ROOT.resolve())
    except ValueError:
        repository_destination = None
    repository_local_requested = repository_destination is not None
    if repository_destination is not None and not _is_private_repository_destination(repository_destination):
        raise VaultError("repository-local restore destination must use a private namespace")
    _require_destination_route(destination_root, repository_local_requested=repository_local_requested)
    try:
        destination_root.mkdir(parents=True, mode=0o700)
    except FileExistsError:
        created_destination = False
    else:
        created_destination = True
    try:
        initial_destination = destination_root.stat(follow_symlinks=False)
    except OSError as exc:
        raise VaultError("cannot establish the restore destination") from exc
    if not stat.S_ISDIR(initial_destination.st_mode):
        raise VaultError("restore destination must be an owner-only directory")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        destination_fd = os.open(destination_root, directory_flags)
    except OSError as exc:
        raise VaultError("cannot pin the restore destination directory") from exc
    try:
        if created_destination:
            os.fchmod(destination_fd, 0o700)
        destination_identity = _destination_identity(destination_fd)
    except Exception:
        os.close(destination_fd)
        raise
    if destination_identity != (initial_destination.st_dev, initial_destination.st_ino):
        os.close(destination_fd)
        raise VaultError("restore destination changed during operation")
    prepared: list[tuple[str, str, int, str, int, str, int, str]] = []
    temporaries: list[tuple[str, int]] = []
    final_names: set[str] = set()
    published: list[tuple[str, tuple[int, int]]] = []
    succeeded = False
    try:
        _require_destination_identity(
            destination_root,
            destination_identity,
            repository_local_requested=repository_local_requested,
        )
        for row in targets:
            artifact_id = _safe_artifact_id(str(row.get("artifact_id") or ""))
            cipher_path = _cipher_path(row)
            _require_destination_identity(
                destination_root,
                destination_identity,
                repository_local_requested=repository_local_requested,
            )
            cipher_name, cipher_fd = _temporary_file_at(destination_fd, artifact_id, ".ciphertext.gpg")
            temporaries.append((cipher_name, cipher_fd))
            _require_destination_identity(
                destination_root,
                destination_identity,
                repository_local_requested=repository_local_requested,
            )
            envelope_name, envelope_fd = _temporary_file_at(destination_fd, artifact_id, ".envelope")
            temporaries.append((envelope_name, envelope_fd))
            _require_destination_identity(
                destination_root,
                destination_identity,
                repository_local_requested=repository_local_requested,
            )
            plaintext_name, plaintext_fd = _temporary_file_at(destination_fd, artifact_id, ".plaintext")
            temporaries.append((plaintext_name, plaintext_fd))
            _snapshot_ciphertext(cipher_path, cipher_fd)
            failures = _ciphertext_failures_fd(row, cipher_fd)
            if failures:
                raise VaultError("; ".join(failures))
            _decrypt_descriptors(cipher_fd, envelope_fd)
            original_name = _extract_envelope_descriptors(envelope_fd, artifact_id, plaintext_fd)
            final_name = _restore_name(destination_fd, artifact_id, original_name)
            if _entry_exists_at(destination_fd, final_name) or final_name in final_names:
                raise VaultError(f"restore target already exists: {final_name}")
            final_names.add(final_name)
            prepared.append(
                (
                    artifact_id,
                    cipher_name,
                    cipher_fd,
                    envelope_name,
                    envelope_fd,
                    plaintext_name,
                    plaintext_fd,
                    final_name,
                )
            )

        _require_destination_identity(
            destination_root,
            destination_identity,
            repository_local_requested=repository_local_requested,
        )
        for (
            _artifact_id,
            _cipher_name,
            _cipher_fd,
            _envelope_name,
            _envelope_fd,
            plaintext,
            _plaintext_fd,
            final,
        ) in prepared:
            published.append((final, _link_no_replace_at(destination_fd, plaintext, final)))
        _require_destination_identity(
            destination_root,
            destination_identity,
            repository_local_requested=repository_local_requested,
        )
        for temporary_name, _file_descriptor in temporaries:
            os.unlink(temporary_name, dir_fd=destination_fd)
        succeeded = True
        for (
            artifact_id,
            _cipher_name,
            _cipher_fd,
            _envelope_name,
            _envelope_fd,
            _plaintext,
            _plaintext_fd,
            _final,
        ) in prepared:
            print(f"OK: restored {artifact_id} (pinned ciphertext and plaintext verified)")
    finally:
        if not succeeded:
            for final_name, identity in reversed(published):
                _rollback_link_at(destination_fd, final_name, identity)
        for temporary_name, file_descriptor in reversed(temporaries):
            try:
                os.unlink(temporary_name, dir_fd=destination_fd)
            except FileNotFoundError:
                pass
            finally:
                os.close(file_descriptor)
        if created_destination and not succeeded:
            try:
                _require_destination_identity(
                    destination_root,
                    destination_identity,
                    repository_local_requested=repository_local_requested,
                )
            except OSError:
                pass
            except VaultError:
                pass
            else:
                try:
                    destination_root.rmdir()
                except OSError:
                    pass
        os.close(destination_fd)
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
