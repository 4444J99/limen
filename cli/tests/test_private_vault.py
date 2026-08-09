"""Focused contracts for scripts/private-vault.py."""

from __future__ import annotations

import importlib.util
import json
import shutil
import stat
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
    monkeypatch.setattr(module, "_tracked_files", lambda: set())
    monkeypatch.setattr(module, "_encrypt_file", lambda source, destination: shutil.copyfile(source, destination))
    monkeypatch.setattr(module, "_decrypt_file", lambda source, destination: shutil.copyfile(source, destination))
    return module


def _add(vault, source: Path, artifact_id: str = "artifact-001") -> int:
    return vault.cmd_add(SimpleNamespace(file=str(source), artifact_id=artifact_id))


def _tracked_paths(vault, artifact_id: str = "artifact-001") -> set[str]:
    return {
        "institutio/vault/manifest.jsonl",
        f"institutio/vault/{artifact_id}.gpg",
    }


def test_add_writes_public_safe_manifest_and_detects_duplicate_id(vault, tmp_path: Path):
    source = tmp_path / "private-research.md"
    source.write_text("private evidence\n", encoding="utf-8")

    assert _add(vault, source) == 0
    assert _add(vault, source) == 0

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
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination)))
    assert list(destination.iterdir()) == []


def test_successful_restore_is_verified_atomic_and_owner_only(vault, tmp_path: Path):
    source = tmp_path / "private notes.md"
    payload = b"valuable private research\n"
    source.write_bytes(payload)
    _add(vault, source)
    destination = tmp_path / "restore"

    assert vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination))) == 0
    restored = destination / "artifact-001--private notes.md"
    assert restored.read_bytes() == payload
    assert stat.S_IMODE(restored.stat().st_mode) == 0o600
    assert [path for path in destination.iterdir() if path.name.startswith(".artifact-001.")] == []
