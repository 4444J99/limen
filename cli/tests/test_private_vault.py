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
    monkeypatch.setattr(module, "BOOTSTRAP_ARTIFACT_IDS", frozenset({"artifact-001"}))
    module._real_tracked_files = module._tracked_files
    monkeypatch.setattr(module, "_tracked_files", lambda: set())
    module._real_historical_artifacts = module._historical_artifacts

    def synthetic_historical_artifacts():
        if not module.MANIFEST.is_file():
            return {}
        return {
            row["artifact_id"]: module._custody_metadata(row)
            for row in module._read_manifest()
            if row.get("schema") == module.SCHEMA and isinstance(row.get("artifact_id"), str)
        }

    monkeypatch.setattr(module, "_historical_artifacts", synthetic_historical_artifacts)
    module._real_validate_committed_pubkey = module._validate_committed_pubkey
    monkeypatch.setattr(module, "_validate_committed_pubkey", lambda: None)
    module._real_encrypt_file = module._encrypt_file
    module._real_decrypt_file = module._decrypt_file
    module._real_ciphertext_recipient_keyids = module._ciphertext_recipient_keyids
    module._real_openpgp_packet_tags = module._openpgp_packet_tags
    monkeypatch.setattr(module, "_encrypt_file", lambda source, destination: shutil.copyfile(source, destination))
    monkeypatch.setattr(module, "_decrypt_file", lambda source, destination: shutil.copyfile(source, destination))
    monkeypatch.setattr(
        module,
        "_ciphertext_recipient_keyids",
        lambda _ciphertext: {module.ENCRYPTION_SUBKEY_ID},
    )
    monkeypatch.setattr(module, "_openpgp_packet_tags", lambda _ciphertext: [1, 20])
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


def test_manifest_rejects_duplicate_json_fields(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    encoded = vault.MANIFEST.read_text(encoding="utf-8")
    vault.MANIFEST.write_text(
        encoded.replace(
            '"artifact_id":"artifact-001"',
            '"artifact_id":"artifact-999","artifact_id":"artifact-001"',
        ),
        encoding="utf-8",
    )

    with pytest.raises(vault.VaultError, match="duplicate field"):
        vault._read_manifest()


def test_manifest_rejects_noncanonical_vaulted_at(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    row = vault._read_manifest()[0]
    row["vaulted_at"] = "not-a-canonical-timestamp"

    assert any("invalid vaulted_at" in error for error in vault._validate_public_row(row, 1))
    with pytest.raises(vault.VaultError, match="immutable custody metadata"):
        vault._custody_metadata(row)


def test_add_requires_apply_before_any_write(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")

    with pytest.raises(vault.VaultError, match="--apply"):
        vault.cmd_add(SimpleNamespace(file=str(source), artifact_id="artifact-001", apply=False))
    assert list(vault.VAULT_DIR.iterdir()) == []


@pytest.mark.parametrize("artifact_id", ["../escape", "nested/path", "/absolute", "Uppercase", "descriptive-name"])
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


def test_verify_rejects_deletion_from_committed_custody(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault))
    monkeypatch.setattr(
        vault,
        "_historical_artifacts",
        lambda: {
            "artifact-002": (
                "artifact-002.gpg",
                "0" * 64,
                1,
                vault.FINGERPRINT,
                "2026-08-09T00:00:00+00:00",
            )
        },
    )

    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_historical_baseline_is_monotonic_across_commits(vault, monkeypatch: pytest.MonkeyPatch):
    def run_git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(vault.ROOT), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

    run_git("init", "-b", "main")
    run_git("config", "user.email", "vault-test@example.invalid")
    run_git("config", "user.name", "Vault Test")

    def history_row(artifact_id: str, digest: str) -> dict:
        return {
            "schema": vault.SCHEMA,
            "artifact_id": artifact_id,
            "ciphertext": f"{artifact_id}.gpg",
            "ciphertext_sha256": digest,
            "ciphertext_bytes": 1,
            "recipient_fpr": vault.FINGERPRINT,
            "vaulted_at": "2026-08-09T00:00:00+00:00",
        }

    first_rows = [
        history_row("artifact-001", "1" * 64),
        history_row("artifact-002", "2" * 64),
        {"schema": vault.SCHEMA, "artifact_id": "descriptive-name"},
    ]
    vault.MANIFEST.write_text("".join(json.dumps(row) + "\n" for row in first_rows), encoding="utf-8")
    run_git("add", "institutio/vault/manifest.jsonl")
    run_git("-c", "commit.gpgsign=false", "commit", "-m", "admit custody")
    vault.MANIFEST.write_text(json.dumps(history_row("artifact-001", "1" * 64)) + "\n", encoding="utf-8")
    run_git("add", "institutio/vault/manifest.jsonl")
    run_git("-c", "commit.gpgsign=false", "commit", "-m", "attempt deletion")
    safe_root = subprocess.run(
        ["git", "-C", str(vault.ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()
    monkeypatch.setattr(vault, "PUBLIC_SAFE_HISTORY_ROOT", safe_root)

    assert set(vault._real_historical_artifacts()) == {"artifact-001", "artifact-002"}


def test_historical_baseline_survives_fixed_path_replacement(vault):
    def run_git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(vault.ROOT), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def history_row(artifact_id: str, digest: str) -> dict:
        return {
            "schema": vault.SCHEMA,
            "artifact_id": artifact_id,
            "ciphertext": f"{artifact_id}.gpg",
            "ciphertext_sha256": digest,
            "ciphertext_bytes": 1,
            "recipient_fpr": vault.FINGERPRINT,
            "vaulted_at": "2026-08-09T00:00:00+00:00",
        }

    run_git("init", "-b", "main")
    run_git("config", "user.email", "vault-test@example.invalid")
    run_git("config", "user.name", "Vault Test")
    vault.MANIFEST.write_text(json.dumps(history_row("artifact-001", "1" * 64)) + "\n", encoding="utf-8")
    run_git("add", "institutio/vault/manifest.jsonl")
    run_git("-c", "commit.gpgsign=false", "commit", "-m", "admit original custody")
    run_git("mv", "institutio/vault/manifest.jsonl", "institutio/vault/original.jsonl")
    run_git("-c", "commit.gpgsign=false", "commit", "-m", "rename fixed manifest away")
    replacement = vault.ROOT / "replacement" / "manifest.jsonl"
    replacement.parent.mkdir()
    replacement.write_text(json.dumps(history_row("artifact-002", "2" * 64)) + "\n", encoding="utf-8")
    run_git("add", "replacement/manifest.jsonl")
    run_git("-c", "commit.gpgsign=false", "commit", "-m", "add replacement elsewhere")
    run_git("mv", "replacement/manifest.jsonl", "institutio/vault/manifest.jsonl")
    run_git("-c", "commit.gpgsign=false", "commit", "-m", "restore fixed manifest path")

    assert set(vault._real_historical_artifacts()) == {"artifact-001", "artifact-002"}


def test_historical_manifest_rejects_duplicate_json_fields(vault):
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "init", "-b", "main"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    row = {
        "schema": vault.SCHEMA,
        "artifact_id": "artifact-001",
        "ciphertext": "artifact-001.gpg",
        "ciphertext_sha256": "1" * 64,
        "ciphertext_bytes": 1,
        "recipient_fpr": vault.FINGERPRINT,
        "vaulted_at": "2026-08-09T00:00:00+00:00",
    }
    encoded = json.dumps(row, separators=(",", ":")).replace(
        '"artifact_id":"artifact-001"',
        '"artifact_id":"artifact-999","artifact_id":"artifact-001"',
    )
    vault.MANIFEST.write_text(encoded + "\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "add", "institutio/vault/manifest.jsonl"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(vault.ROOT),
            "-c",
            "user.email=vault-test@example.invalid",
            "-c",
            "user.name=Vault Test",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "commit duplicate manifest field",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    with pytest.raises(vault.VaultError, match="duplicate field"):
        vault._real_historical_artifacts()


def test_historical_manifest_fails_when_present_snapshot_is_unreadable(vault, monkeypatch: pytest.MonkeyPatch):
    manifest_relative = "institutio/vault/manifest.jsonl"

    def missing_snapshot(args, *, env=None):
        del env
        if "rev-list" in args:
            return subprocess.CompletedProcess(args, 0, stdout="a" * 40 + "\n", stderr="")
        if "cat-file" in args:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        if "ls-tree" in args:
            return subprocess.CompletedProcess(args, 0, stdout=manifest_relative + "\0", stderr="")
        if "show" in args:
            return subprocess.CompletedProcess(args, 128, stdout="", stderr="missing blob")
        raise AssertionError(args)

    monkeypatch.setattr(vault, "_run_command", missing_snapshot)

    with pytest.raises(vault.VaultError, match="cannot read a committed manifest history snapshot"):
        vault._real_historical_artifacts()


def test_historical_manifest_rejects_non_public_safe_rows(vault):
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "init", "-b", "main"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    row = {
        "schema": vault.SCHEMA,
        "artifact_id": "artifact-001",
        "ciphertext": "artifact-001.gpg",
        "ciphertext_sha256": "1" * 64,
        "ciphertext_bytes": 1,
        "recipient_fpr": vault.FINGERPRINT,
        "vaulted_at": "2026-08-09T00:00:00+00:00",
        "unsupported": "synthetic",
    }
    vault.MANIFEST.write_text(json.dumps(row) + "\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "add", "institutio/vault/manifest.jsonl"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(vault.ROOT),
            "-c",
            "user.email=vault-test@example.invalid",
            "-c",
            "user.name=Vault Test",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "commit unsupported public field",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    with pytest.raises(vault.VaultError, match="non-public-safe"):
        vault._real_historical_artifacts()


def test_tracked_files_preserve_non_ascii_private_paths(vault):
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "init", "-b", "main"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    private_path = vault.ROOT / ".limen-private" / "résumé.md"
    private_path.parent.mkdir()
    private_path.write_text("synthetic", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "add", "-f", ".limen-private/résumé.md"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert ".limen-private/résumé.md" in vault._real_tracked_files()


def test_accepted_repository_private_namespaces_are_gitignored(vault, tmp_path: Path):
    repository = tmp_path / "ignore-repository"
    repository.mkdir()
    shutil.copyfile(SCRIPT.parents[1] / ".gitignore", repository / ".gitignore")
    subprocess.run(
        ["git", "-C", str(repository), "init", "-b", "main"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "core.excludesFile", "/dev/null"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    for prefix in vault.PRIVATE_TRACKING_PREFIXES:
        probe = f"{prefix}vault-ignore-probe"
        ignored = subprocess.run(
            ["git", "-C", str(repository), "check-ignore", "--no-index", "--quiet", probe],
            check=False,
            timeout=60,
        )
        assert ignored.returncode == 0, probe


def test_verify_rejects_changed_historical_ciphertext_metadata(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault))
    current = vault._custody_metadata(vault._read_manifest()[0])
    historical = (current[0], "0" * 64, current[2], current[3], current[4])
    monkeypatch.setattr(vault, "_historical_artifacts", lambda: {"artifact-001": historical})

    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_verify_rejects_non_string_artifact_id(vault):
    row = {
        "schema": vault.SCHEMA,
        "artifact_id": 123,
        "ciphertext": "123.gpg",
        "ciphertext_sha256": "0" * 64,
        "ciphertext_bytes": 1,
        "recipient_fpr": vault.FINGERPRINT,
        "vaulted_at": "2026-08-09T00:00:00+00:00",
    }

    errors = vault._validate_public_row(row, 1)

    assert any("artifact id must be a string" in error for error in errors)


def test_verify_rejects_symlinked_manifest(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "manifest-target.jsonl"
    target.write_text("{}\n", encoding="utf-8")
    vault.MANIFEST.symlink_to(target)
    monkeypatch.setattr(vault, "_tracked_files", lambda: {"institutio/vault/manifest.jsonl"})

    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_verify_rejects_invalid_committed_public_key(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault))

    def reject_key() -> None:
        raise vault.VaultError("pinned identity mismatch")

    monkeypatch.setattr(vault, "_validate_committed_pubkey", reject_key)

    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_import_rejects_symlinked_public_key(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "public-key.asc"
    target.write_text("synthetic public key", encoding="utf-8")
    symlink = tmp_path / "committed-key.asc"
    symlink.symlink_to(target)
    monkeypatch.setattr(vault, "PUBKEY", symlink)

    with pytest.raises(vault.VaultError, match="non-symlink"):
        vault._import_pubkey(str(tmp_path / "gnupg"))


def test_import_rejects_secret_key_material(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    public_key = tmp_path / "committed-key.asc"
    canonical_armor = "synthetic canonical public-key armor\n"
    public_key.write_text(canonical_armor, encoding="utf-8")
    monkeypatch.setattr(vault, "PUBKEY", public_key)

    def expose_secret(args, *, env=None):
        del env
        if "--import" in args:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if "--export" in args:
            return subprocess.CompletedProcess(args, 0, stdout=canonical_armor, stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="sec:u:255:22:SECRET\n", stderr="")

    monkeypatch.setattr(vault, "_run_command", expose_secret)

    with pytest.raises(vault.VaultError, match="secret-key material"):
        vault._import_pubkey(str(tmp_path / "gnupg"))


def test_import_rejects_non_key_bytes(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    canonical_armor = "synthetic canonical public-key armor\n"
    public_key = tmp_path / "committed-key.asc"
    public_key.write_text(canonical_armor + "synthetic trailing bytes\n", encoding="utf-8")
    monkeypatch.setattr(vault, "PUBKEY", public_key)

    def canonical_export(args, *, env=None):
        del env
        if "--import" in args:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if "--export" in args:
            return subprocess.CompletedProcess(args, 0, stdout=canonical_armor, stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(vault, "_run_command", canonical_export)

    with pytest.raises(vault.VaultError, match="only canonical public-key armor"):
        vault._import_pubkey(str(tmp_path / "gnupg"))


def test_committed_public_key_validation_rejects_unusable_subkey(vault, monkeypatch: pytest.MonkeyPatch):
    primary = [""] * 12
    primary[0] = "pub"
    primary[4] = vault.FINGERPRINT[-16:]
    primary[11] = "scESC"
    primary_fingerprint = [""] * 10
    primary_fingerprint[0] = "fpr"
    primary_fingerprint[9] = vault.FINGERPRINT
    subkey = [""] * 12
    subkey[0] = "sub"
    subkey[4] = vault.ENCRYPTION_SUBKEY_ID
    subkey[11] = "e"
    subkey_fingerprint = [""] * 10
    subkey_fingerprint[0] = "fpr"
    subkey_fingerprint[9] = "0" * 24 + vault.ENCRYPTION_SUBKEY_ID
    listing = "\n".join(":".join(fields) for fields in (primary, primary_fingerprint, subkey, subkey_fingerprint))

    monkeypatch.setattr(vault, "_import_pubkey", lambda _gnupghome: None)

    def reject_probe(args, *, env=None):
        del env
        if "--list-keys" in args:
            return subprocess.CompletedProcess(args, 0, stdout=listing, stderr="")
        return subprocess.CompletedProcess(args, 2, stdout="", stderr="Unusable public key")

    monkeypatch.setattr(vault, "_run_command", reject_probe)

    with pytest.raises(vault.VaultError, match="unusable"):
        vault._real_validate_committed_pubkey()


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


def test_openpgp_framing_rejects_appended_bytes(vault, tmp_path: Path):
    ciphertext = tmp_path / "synthetic.gpg"
    ciphertext.write_bytes(bytes([0xC1, 0x01]) + b"x" + bytes([0xD4, 0x02]) + b"yz")

    assert vault._real_openpgp_packet_tags(ciphertext) == [1, 20]

    with ciphertext.open("ab") as handle:
        handle.write(b"synthetic trailing bytes")

    with pytest.raises(vault.VaultError, match="outside OpenPGP packet framing"):
        vault._real_openpgp_packet_tags(ciphertext)


def test_verify_rejects_symlinked_ciphertext(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    ciphertext = vault.VAULT_DIR / "artifact-001.gpg"
    outside = tmp_path / "outside.gpg"
    outside.write_bytes(ciphertext.read_bytes())
    ciphertext.unlink()
    ciphertext.symlink_to(outside)
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault))

    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_verify_rejects_dangling_vault_symlink(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    (vault.VAULT_DIR / "alias").symlink_to(tmp_path / "missing")
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault) | {"institutio/vault/alias"})

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


def test_restore_rejects_substitution_against_committed_custody(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    original_row = vault._read_manifest()[0]
    expected_metadata = vault._custody_metadata(original_row)
    ciphertext = vault.VAULT_DIR / "artifact-001.gpg"
    ciphertext.write_bytes(b"synthetic replacement ciphertext")
    substituted_row = dict(original_row)
    substituted_row["ciphertext_sha256"] = vault._sha256(ciphertext)
    substituted_row["ciphertext_bytes"] = ciphertext.stat().st_size
    vault._write_manifest([substituted_row])
    monkeypatch.setattr(vault, "_historical_artifacts", lambda: {"artifact-001": expected_metadata})
    destination = tmp_path / "restore"

    with pytest.raises(vault.VaultError, match="committed custody history"):
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


def test_restore_preserves_existing_directory_permissions(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    destination = tmp_path / "restore"
    destination.mkdir(mode=0o750)
    destination.chmod(0o750)

    with pytest.raises(vault.VaultError, match="owner-only"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))

    assert stat.S_IMODE(destination.stat().st_mode) == 0o750


def test_restore_refuses_dangling_target(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    destination = tmp_path / "restore"
    destination.mkdir(mode=0o700)
    final_path = destination / "artifact-001--private.md"
    final_path.symlink_to(destination / "missing")

    with pytest.raises(vault.VaultError, match="already exists"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))

    assert final_path.is_symlink()


def test_restore_all_preflights_every_target_before_publish(vault, tmp_path: Path):
    first = tmp_path / "first.md"
    first.write_text("first", encoding="utf-8")
    second = tmp_path / "second.md"
    second.write_text("second", encoding="utf-8")
    _add(vault, first, "artifact-001")
    _add(vault, second, "artifact-002")
    destination = tmp_path / "restore"
    destination.mkdir(mode=0o700)
    existing = destination / "artifact-002--second.md"
    existing.write_text("existing", encoding="utf-8")

    with pytest.raises(vault.VaultError, match="already exists"):
        vault.cmd_restore(SimpleNamespace(all=True, artifact_id=None, dest=str(destination), apply=True))

    assert not (destination / "artifact-001--first.md").exists()
    assert existing.read_text(encoding="utf-8") == "existing"


def test_restore_bounds_output_name(vault, tmp_path: Path):
    source = tmp_path / ("n" * 240)
    source.write_text("secret", encoding="utf-8")
    artifact_id = "artifact-" + "1" * 55
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


def test_add_stages_plaintext_on_source_filesystem(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "source-custody" / "private.md"
    source.parent.mkdir()
    source.write_text("synthetic", encoding="utf-8")
    real_temporary_directory = tempfile.TemporaryDirectory
    observed_directories: list[Path] = []

    def custody_temporary_directory(*args, **kwargs):
        observed_directories.append(Path(kwargs["dir"]))
        return real_temporary_directory(*args, **kwargs)

    monkeypatch.setattr(vault.tempfile, "TemporaryDirectory", custody_temporary_directory)

    _add(vault, source)

    assert observed_directories == [source.parent]


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
    if shutil.which("gpg") is None:
        pytest.skip("gpg is unavailable on this host")
    # Keep the GnuPG agent socket path short while respecting the configured temp directory.
    gnupghome = Path(tempfile.mkdtemp(prefix="limen-vault-gpg-"))
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
