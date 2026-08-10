"""Focused contracts for scripts/private-vault.py."""

from __future__ import annotations

import importlib.util
import json
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "private-vault.py"


@pytest.fixture
def vault(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    spec = importlib.util.spec_from_file_location("private_vault_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    root = tmp_path / "repo"
    vault_dir = root / "institutio" / "vault"
    vault_dir.mkdir(parents=True)
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "VAULT_DIR", vault_dir)
    monkeypatch.setattr(module, "MANIFEST", vault_dir / "manifest.jsonl")
    monkeypatch.setattr(module, "REQUIRED_ARTIFACT_IDS", frozenset({"artifact-001"}))
    monkeypatch.setattr(module, "_tracked_files", lambda: set())
    module._real_encrypt_file = module._encrypt_file
    module._real_decrypt_file = module._decrypt_file
    module._real_ciphertext_recipient_keyids = module._ciphertext_recipient_keyids
    monkeypatch.setattr(module, "_encrypt_file", lambda source, destination: shutil.copyfile(source, destination))
    monkeypatch.setattr(module, "_decrypt_file", lambda source, destination: shutil.copyfile(source, destination))
    monkeypatch.setattr(
        module,
        "_ciphertext_recipient_keyids",
        lambda _ciphertext: {module.ENCRYPTION_SUBKEY_ID},
    )
    return module


def _add(vault, source: Path, artifact_id: str = "artifact-001") -> int:
    return vault.cmd_add(SimpleNamespace(file=str(source), artifact_id=artifact_id, apply=True))


def _tracked_paths(vault, artifact_id: str = "artifact-001") -> set[str]:
    return {
        "institutio/vault/manifest.jsonl",
        f"institutio/vault/{artifact_id}.gpg",
    }


def test_add_writes_public_safe_manifest_and_rejects_duplicate_id(vault, tmp_path: Path):
    source = tmp_path / "private-research.md"
    source.write_text("private evidence\n", encoding="utf-8")

    assert _add(vault, source) == 0
    with pytest.raises(vault.VaultError, match="already vaulted"):
        _add(vault, source)

    rows = vault._read_manifest()
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == vault.PUBLIC_FIELDS
    assert row["artifact_id"] == "artifact-001"
    assert row["ciphertext"] == "artifact-001.gpg"
    encoded = vault.MANIFEST.read_text(encoding="utf-8")
    assert str(source) not in encoded
    assert source.name not in encoded
    assert "plaintext_sha256" not in encoded
    assert "source_path" not in encoded


def test_add_requires_apply_before_any_write(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")

    with pytest.raises(vault.VaultError, match="--apply"):
        vault.cmd_add(SimpleNamespace(file=str(source), artifact_id="artifact-001", apply=False))
    assert list(vault.VAULT_DIR.iterdir()) == []


@pytest.mark.parametrize("artifact_id", ["../escape", "nested/path", "/absolute", "Uppercase"])
def test_add_rejects_traversal_and_non_neutral_ids(vault, tmp_path: Path, artifact_id: str):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    with pytest.raises(vault.VaultError):
        _add(vault, source, artifact_id)
    assert list(vault.VAULT_DIR.iterdir()) == []


def test_verify_accepts_coherent_public_safe_custody(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault))
    assert vault.cmd_verify(SimpleNamespace()) == 0


def test_verify_rejects_missing_required_manifest(vault):
    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_verify_rejects_tracked_private_namespace(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = vault.ROOT / ".limen-private" / "private.md"
    source.parent.mkdir(parents=True)
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    tracked = _tracked_paths(vault) | {".limen-private/private.md"}
    monkeypatch.setattr(vault, "_tracked_files", lambda: tracked)
    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_verify_rejects_nested_vault_content(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    nested = vault.VAULT_DIR / "import"
    nested.mkdir()
    (nested / "unmanifested.gpg").write_bytes(b"ciphertext")
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault))
    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_verify_rejects_wrong_recipient(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault))
    monkeypatch.setattr(vault, "_ciphertext_recipient_keyids", lambda _ciphertext: {"0" * 16})
    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_verify_rejects_manifest_ciphertext_traversal(vault, monkeypatch: pytest.MonkeyPatch):
    row = {
        "schema": vault.SCHEMA,
        "artifact_id": "artifact-001",
        "ciphertext": "../outside.gpg",
        "ciphertext_sha256": "0" * 64,
        "ciphertext_bytes": 1,
        "recipient_fpr": vault.FINGERPRINT,
        "vaulted_at": "2026-08-09T00:00:00+00:00",
    }
    vault.MANIFEST.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(vault, "_tracked_files", lambda: {"institutio/vault/manifest.jsonl"})
    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_failed_restore_removes_all_plaintext_temporaries(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    destination = tmp_path / "restore"

    def corrupt_decrypt(ciphertext: Path, envelope: Path) -> None:
        shutil.copyfile(ciphertext, envelope)
        with envelope.open("ab") as handle:
            handle.write(b"tamper")

    monkeypatch.setattr(vault, "_decrypt_file", corrupt_decrypt)
    with pytest.raises(vault.VaultError, match="integrity mismatch"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
    assert list(destination.iterdir()) == []


def test_failed_restore_cleans_up_after_decrypt_failure(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    destination = tmp_path / "restore"

    def reject_decrypt(_ciphertext: Path, _envelope: Path) -> None:
        raise vault.VaultError("decryption failed: no secret key")

    monkeypatch.setattr(vault, "_decrypt_file", reject_decrypt)
    with pytest.raises(vault.VaultError, match="no secret key"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
    assert list(destination.iterdir()) == []


def test_restore_rejects_unpinned_ciphertext_before_writing(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    (vault.VAULT_DIR / "artifact-001.gpg").write_bytes(b"substituted")
    destination = tmp_path / "restore"

    with pytest.raises(vault.VaultError, match="ciphertext"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
    assert not destination.exists()


def test_restore_requires_apply_before_plaintext_write(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    destination = tmp_path / "restore"

    with pytest.raises(vault.VaultError, match="--apply"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=False))
    assert not destination.exists()


def test_successful_restore_is_verified_atomic_and_owner_only(vault, tmp_path: Path):
    source = tmp_path / "private notes.md"
    payload = b"valuable private research\n"
    source.write_bytes(payload)
    _add(vault, source)
    destination = tmp_path / "restore"

    assert (
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
        == 0
    )
    restored = destination / "artifact-001--private notes.md"
    assert restored.read_bytes() == payload
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert stat.S_IMODE(restored.stat().st_mode) == 0o600
    assert [path for path in destination.iterdir() if path.name.startswith(".artifact-001.")] == []


def test_restore_bounds_output_name(vault, tmp_path: Path):
    source = tmp_path / ("n" * 240)
    source.write_text("secret", encoding="utf-8")
    artifact_id = "a" * 64
    _add(vault, source, artifact_id)
    destination = tmp_path / "restore"

    assert (
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id=artifact_id, dest=str(destination), apply=True)) == 0
    )
    assert (destination / f"{artifact_id}--restored").read_text(encoding="utf-8") == "secret"


def test_add_stages_ciphertext_on_vault_filesystem(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")

    def assert_vault_staging(envelope: Path, destination: Path) -> None:
        assert destination.parent == vault.VAULT_DIR
        shutil.copyfile(envelope, destination)

    monkeypatch.setattr(vault, "_encrypt_file", assert_vault_staging)
    assert _add(vault, source) == 0


def test_add_encrypts_one_immutable_snapshot(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("initial", encoding="utf-8")
    original_write_envelope = vault._write_envelope

    def mutate_source_after_snapshot(*args, **kwargs):
        source.write_text("changed-after-snapshot", encoding="utf-8")
        original_write_envelope(*args, **kwargs)

    monkeypatch.setattr(vault, "_write_envelope", mutate_source_after_snapshot)
    _add(vault, source)
    destination = tmp_path / "restore"
    vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
    assert (destination / "artifact-001--private.md").read_text(encoding="utf-8") == "initial"


def test_add_holds_lock_through_manifest_publication(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    events: list[str] = []
    original_write_manifest = vault._write_manifest

    @contextmanager
    def observed_lock():
        events.append("lock-enter")
        yield
        events.append("lock-exit")

    def observed_write_manifest(rows):
        events.append("manifest-write")
        original_write_manifest(rows)

    monkeypatch.setattr(vault, "_vault_lock", observed_lock)
    monkeypatch.setattr(vault, "_write_manifest", observed_write_manifest)
    _add(vault, source)
    assert events == ["lock-enter", "manifest-write", "lock-exit"]


def test_restore_selectors_are_mutually_exclusive(vault, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        vault.sys,
        "argv",
        ["private-vault.py", "restore", "--artifact-id", "artifact-001", "--all", "--apply"],
    )
    with pytest.raises(SystemExit) as exc_info:
        vault.main()
    assert exc_info.value.code == 2


def test_recovery_check_round_trips_only_synthetic_content(vault):
    assert vault.cmd_recovery_check(SimpleNamespace(apply=True)) == 0


def test_recovery_check_requires_apply(vault):
    with pytest.raises(vault.VaultError, match="--apply"):
        vault.cmd_recovery_check(SimpleNamespace(apply=False))


def test_real_gpg_round_trip_with_scratch_key(
    vault,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
    tmp_path: Path,
):
    gnupghome = Path(tempfile.mkdtemp(prefix="limen-vault-gpg-", dir="/tmp"))
    request.addfinalizer(lambda: shutil.rmtree(gnupghome, ignore_errors=True))
    gnupghome.chmod(0o700)
    identity = "Limen Vault Recovery Test <vault-recovery@example.invalid>"
    common = [
        "gpg",
        "--batch",
        "--homedir",
        str(gnupghome),
        "--pinentry-mode",
        "loopback",
        "--passphrase",
        "",
    ]
    subprocess.run(
        [*common, "--quick-generate-key", identity, "ed25519", "sign", "1d"],
        check=True,
        capture_output=True,
        text=True,
    )
    listing = subprocess.run(
        ["gpg", "--batch", "--homedir", str(gnupghome), "--with-colons", "--list-secret-keys"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    fingerprint = next(line.split(":")[9] for line in listing if line.startswith("fpr:"))
    subprocess.run(
        [*common, "--quick-add-key", fingerprint, "cv25519", "encrypt", "1d"],
        check=True,
        capture_output=True,
        text=True,
    )
    listing = subprocess.run(
        ["gpg", "--batch", "--homedir", str(gnupghome), "--with-colons", "--list-secret-keys"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    encryption_key_id = next(line.split(":")[4] for line in listing if line.startswith("ssb:"))
    public_key = tmp_path / "scratch-public-key.asc"
    public_key.write_text(
        subprocess.run(
            ["gpg", "--batch", "--homedir", str(gnupghome), "--armor", "--export", fingerprint],
            check=True,
            capture_output=True,
            text=True,
        ).stdout,
        encoding="utf-8",
    )
    monkeypatch.setattr(vault, "PUBKEY", public_key)
    monkeypatch.setattr(vault, "FINGERPRINT", fingerprint)
    monkeypatch.setattr(vault, "ENCRYPTION_SUBKEY_ID", encryption_key_id)
    monkeypatch.setenv("GNUPGHOME", str(gnupghome))
    source = tmp_path / "synthetic-source"
    ciphertext = tmp_path / "synthetic-source.gpg"
    restored = tmp_path / "synthetic-restored"
    source.write_bytes(vault.RECOVERY_CANARY)

    vault._real_encrypt_file(source, ciphertext)
    assert vault._real_ciphertext_recipient_keyids(ciphertext) == {encryption_key_id}
    vault._real_decrypt_file(ciphertext, restored)
    assert restored.read_bytes() == vault.RECOVERY_CANARY
