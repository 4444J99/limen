"""Focused contracts for scripts/private-vault.py."""

from __future__ import annotations

import importlib.util
import json
import shutil
import stat
import subprocess
import tempfile
import threading
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
    public_key = root / "docs" / "keys" / "synthetic-public-key.asc"
    public_key.parent.mkdir(parents=True)
    public_key.write_text("synthetic public key\n", encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "VAULT_DIR", vault_dir)
    monkeypatch.setattr(module, "MANIFEST", vault_dir / "manifest.jsonl")
    monkeypatch.setattr(module, "PUBKEY", public_key)
    monkeypatch.setattr(module, "BOOTSTRAP_ARTIFACT_IDS", frozenset({"artifact-001"}))
    module._real_tracked_files = module._tracked_files
    monkeypatch.setattr(module, "_tracked_files", lambda: set())
    module._real_index_entry_matches_worktree = module._index_entry_matches_worktree
    monkeypatch.setattr(module, "_index_entry_matches_worktree", lambda _relative: True)
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

    def copy_descriptor(source_fd: int, destination_fd: int) -> None:
        module.os.lseek(source_fd, 0, module.os.SEEK_SET)
        module.os.ftruncate(destination_fd, 0)
        module.os.lseek(destination_fd, 0, module.os.SEEK_SET)
        with (
            module.os.fdopen(module.os.dup(source_fd), "rb") as source_handle,
            module.os.fdopen(module.os.dup(destination_fd), "wb") as destination_handle,
        ):
            shutil.copyfileobj(source_handle, destination_handle)

    monkeypatch.setattr(module, "_decrypt_descriptors", copy_descriptor)
    monkeypatch.setattr(
        module,
        "_ciphertext_recipient_keyids",
        lambda _ciphertext: {module.ENCRYPTION_SUBKEY_ID},
    )
    monkeypatch.setattr(
        module,
        "_ciphertext_recipient_keyids_fd",
        lambda _ciphertext_fd: {module.ENCRYPTION_SUBKEY_ID},
    )
    monkeypatch.setattr(module, "_openpgp_packet_tags", lambda _ciphertext: [1, 20])
    monkeypatch.setattr(module, "_openpgp_packet_tags_fd", lambda _ciphertext_fd: [1, 20])
    return module


def _add(vault, source: Path, artifact_id: str = "artifact-001") -> int:
    return vault.cmd_add(SimpleNamespace(file=str(source), artifact_id=artifact_id, apply=True))


def _tracked_paths(vault, artifact_id: str = "artifact-001") -> set[str]:
    return {
        "docs/keys/synthetic-public-key.asc",
        "institutio/vault/manifest.jsonl",
        f"institutio/vault/{artifact_id}.gpg",
    }


def _read_descriptor(vault, file_descriptor: int) -> bytes:
    vault.os.lseek(file_descriptor, 0, vault.os.SEEK_SET)
    with vault.os.fdopen(vault.os.dup(file_descriptor), "rb") as handle:
        return handle.read()


def _write_descriptor(vault, file_descriptor: int, payload: bytes) -> None:
    vault.os.ftruncate(file_descriptor, 0)
    vault.os.lseek(file_descriptor, 0, vault.os.SEEK_SET)
    with vault.os.fdopen(vault.os.dup(file_descriptor), "wb") as handle:
        handle.write(payload)


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


def test_add_rejects_unattested_id_before_any_write(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")

    with pytest.raises(vault.VaultError, match="recovery admission proof"):
        _add(vault, source, "artifact-002")
    assert list(vault.VAULT_DIR.iterdir()) == []


@pytest.mark.parametrize("failure", [OSError("synthetic hash failure"), KeyboardInterrupt()])
def test_add_rolls_back_published_ciphertext_when_metadata_construction_fails(
    vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure: BaseException
):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")

    def fail_metadata(_path: Path) -> str:
        raise failure

    monkeypatch.setattr(vault, "_sha256", fail_metadata)

    with pytest.raises(type(failure)):
        _add(vault, source)

    assert not (vault.VAULT_DIR / "artifact-001.gpg").exists()
    assert not vault.MANIFEST.exists()
    assert [path for path in vault.VAULT_DIR.iterdir() if path.name.startswith(".artifact-001.")] == []


@pytest.mark.parametrize("artifact_id", ["../escape", "nested/path", "/absolute", "Uppercase", "descriptive-name"])
def test_add_rejects_traversal_and_non_neutral_ids(vault, tmp_path: Path, artifact_id: str):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    with pytest.raises(vault.VaultError):
        _add(vault, source, artifact_id)
    assert list(vault.VAULT_DIR.iterdir()) == []


@pytest.mark.parametrize("private_root", [".limen-private", ".agent-runtime", ".limen-workstream", None])
def test_add_rejects_hardlink_to_tracked_plaintext_alias(
    vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, private_root: str | None
):
    tracked_alias = vault.ROOT / "tracked-alias"
    tracked_alias.write_text("synthetic", encoding="utf-8")
    if private_root is None:
        source = tmp_path / "outside-private"
    else:
        source = vault.ROOT / private_root / "private"
        source.parent.mkdir(parents=True)
    vault.os.link(tracked_alias, source)
    monkeypatch.setattr(vault, "_tracked_files", lambda: {"tracked-alias"})

    with pytest.raises(vault.VaultError, match="file object is already git-tracked"):
        _add(vault, source)

    assert not vault.MANIFEST.exists()


def test_add_rejects_tracked_hardlink_swapped_in_before_snapshot(
    vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    source = tmp_path / "private"
    source.write_text("initial", encoding="utf-8")
    tracked_alias = vault.ROOT / "tracked-alias"
    tracked_alias.write_text("tracked", encoding="utf-8")
    monkeypatch.setattr(vault, "_tracked_files", lambda: {"tracked-alias"})
    real_snapshot = vault._snapshot_source

    def swap_then_snapshot(source_path: Path, destination: Path, expected_identity: tuple[int, int]):
        source_path.unlink()
        vault.os.link(tracked_alias, source_path)
        return real_snapshot(source_path, destination, expected_identity)

    monkeypatch.setattr(vault, "_snapshot_source", swap_then_snapshot)

    with pytest.raises(vault.VaultError, match="changed before snapshot"):
        _add(vault, source)

    assert not vault.MANIFEST.exists()


def test_add_rechecks_tracked_aliases_after_snapshot(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private"
    source.write_text("private", encoding="utf-8")
    tracked_alias = vault.ROOT / "tracked-alias"
    tracked_alias.write_text("initial tracked object", encoding="utf-8")
    monkeypatch.setattr(vault, "_tracked_files", lambda: {"tracked-alias"})
    real_snapshot = vault._snapshot_source

    def relink_tracked_path_then_snapshot(source_path: Path, destination: Path, expected_identity: tuple[int, int]):
        tracked_alias.unlink()
        vault.os.link(source_path, tracked_alias)
        return real_snapshot(source_path, destination, expected_identity)

    monkeypatch.setattr(vault, "_snapshot_source", relink_tracked_path_then_snapshot)

    with pytest.raises(vault.VaultError, match="file object is already git-tracked"):
        _add(vault, source)

    assert not vault.MANIFEST.exists()
    assert not (vault.VAULT_DIR / "artifact-001.gpg").exists()


def test_verify_accepts_coherent_public_safe_custody(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault))
    assert vault.cmd_verify(SimpleNamespace()) == 0


@pytest.mark.parametrize(
    ("target", "relative", "expected"),
    [
        ("manifest", "institutio/vault/manifest.jsonl", "manifest Git index content differs"),
        ("public_key", "docs/keys/synthetic-public-key.asc", "public-key Git index content differs"),
        ("ciphertext", "institutio/vault/artifact-001.gpg", "ciphertext Git index content differs"),
    ],
)
def test_verify_rejects_staged_custody_file_that_differs_from_validated_worktree(
    vault,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    target: str,
    relative: str,
    expected: str,
):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "init", "-b", "main"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "add", "institutio/vault", "docs/keys/synthetic-public-key.asc"],
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
            "commit coherent custody",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    target_path = {
        "manifest": vault.MANIFEST,
        "public_key": vault.PUBKEY,
        "ciphertext": vault.VAULT_DIR / "artifact-001.gpg",
    }[target]
    validated_content = target_path.read_bytes()
    target_path.write_bytes(validated_content + b"synthetic staged content\n")
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "add", relative],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    target_path.write_bytes(validated_content)
    monkeypatch.setattr(vault, "_tracked_files", vault._real_tracked_files)
    monkeypatch.setattr(vault, "_index_entry_matches_worktree", vault._real_index_entry_matches_worktree)

    assert vault.cmd_verify(SimpleNamespace()) == 1
    assert expected in capsys.readouterr().out


def test_verify_rejects_copied_ciphertext_under_distinct_ids(
    vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(vault, "BOOTSTRAP_ARTIFACT_IDS", frozenset({"artifact-001", "artifact-002"}))
    _add(vault, source)
    first_row = vault._read_manifest()[0]
    second_cipher = vault.VAULT_DIR / "artifact-002.gpg"
    shutil.copyfile(vault.VAULT_DIR / "artifact-001.gpg", second_cipher)
    second_row = dict(first_row, artifact_id="artifact-002", ciphertext="artifact-002.gpg")
    vault._write_manifest([first_row, second_row])
    monkeypatch.setattr(
        vault,
        "_tracked_files",
        lambda: _tracked_paths(vault) | {"institutio/vault/artifact-002.gpg"},
    )

    assert vault.cmd_verify(SimpleNamespace()) == 1
    assert "duplicate ciphertext digest across distinct artifact ids" in capsys.readouterr().out


def test_verify_allows_independently_encrypted_equal_plaintext(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("equal plaintext", encoding="utf-8")
    second.write_text("equal plaintext", encoding="utf-8")
    monkeypatch.setattr(vault, "BOOTSTRAP_ARTIFACT_IDS", frozenset({"artifact-001", "artifact-002"}))

    def distinct_encryption(envelope: Path, destination: Path) -> None:
        destination.write_bytes(destination.name.encode("utf-8") + envelope.read_bytes())

    monkeypatch.setattr(vault, "_encrypt_file", distinct_encryption)
    _add(vault, first, "artifact-001")
    _add(vault, second, "artifact-002")
    monkeypatch.setattr(
        vault,
        "_tracked_files",
        lambda: _tracked_paths(vault) | {"institutio/vault/artifact-002.gpg"},
    )

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


def test_historical_manifest_ignores_git_replace_objects(vault, monkeypatch: pytest.MonkeyPatch):
    def run_git(*args: str, input_text: str | None = None) -> str:
        return subprocess.run(
            ["git", "-C", str(vault.ROOT), *args],
            input=input_text,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        ).stdout.strip()

    run_git("init", "-b", "main")
    run_git("config", "user.email", "vault-test@example.invalid")
    run_git("config", "user.name", "Vault Test")
    row = {
        "schema": vault.SCHEMA,
        "artifact_id": "artifact-001",
        "ciphertext": "artifact-001.gpg",
        "ciphertext_sha256": "1" * 64,
        "ciphertext_bytes": 1,
        "recipient_fpr": vault.FINGERPRINT,
        "vaulted_at": "2026-08-09T00:00:00+00:00",
    }
    vault.MANIFEST.write_text(json.dumps(row) + "\n", encoding="utf-8")
    run_git("add", "institutio/vault/manifest.jsonl")
    run_git("-c", "commit.gpgsign=false", "commit", "-m", "admit custody")
    admitted = run_git("rev-parse", "HEAD")
    empty_tree = run_git("mktree", input_text="")
    replacement = run_git("-c", "commit.gpgsign=false", "commit-tree", empty_tree, input_text="synthetic\n")
    run_git("replace", admitted, replacement)
    monkeypatch.setattr(vault, "PUBLIC_SAFE_HISTORY_ROOT", admitted)

    assert set(vault._real_historical_artifacts()) == {"artifact-001"}


def test_historical_manifest_rejects_legacy_grafts(vault):
    subprocess.run(
        ["git", "-C", str(vault.ROOT), "init", "-b", "main"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    grafts = vault.ROOT / ".git" / "info" / "grafts"
    grafts.write_text("synthetic\n", encoding="utf-8")

    with pytest.raises(vault.VaultError, match="rewritten Git custody history"):
        vault._real_historical_artifacts()


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
        if "--is-shallow-repository" in args:
            return subprocess.CompletedProcess(args, 0, stdout="false\n", stderr="")
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


def test_historical_manifest_rejects_shallow_repository(vault, monkeypatch: pytest.MonkeyPatch):
    def shallow_repository(args, *, env=None):
        del env
        assert "--is-shallow-repository" in args
        return subprocess.CompletedProcess(args, 0, stdout="true\n", stderr="")

    monkeypatch.setattr(vault, "_run_command", shallow_repository)

    with pytest.raises(vault.VaultError, match="non-shallow repository"):
        vault._real_historical_artifacts()


def test_historical_manifest_rejects_unprovable_repository_depth(vault, monkeypatch: pytest.MonkeyPatch):
    def unavailable_depth(args, *, env=None):
        del env
        assert "--is-shallow-repository" in args
        return subprocess.CompletedProcess(args, 128, stdout="", stderr="unavailable")

    monkeypatch.setattr(vault, "_run_command", unavailable_depth)

    with pytest.raises(vault.VaultError, match="cannot prove complete"):
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


@pytest.mark.parametrize("schema", [None, "unsupported-schema"])
def test_historical_manifest_rejects_non_v2_post_boundary_rows(
    vault, monkeypatch: pytest.MonkeyPatch, schema: str | None
):
    manifest_relative = "institutio/vault/manifest.jsonl"
    row = {"artifact_id": "artifact-001"}
    if schema is not None:
        row["schema"] = schema

    def non_v2_snapshot(args, *, env=None):
        del env
        if "--is-shallow-repository" in args:
            return subprocess.CompletedProcess(args, 0, stdout="false\n", stderr="")
        if "rev-list" in args:
            return subprocess.CompletedProcess(args, 0, stdout="a" * 40 + "\n", stderr="")
        if "cat-file" in args:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        if "ls-tree" in args:
            return subprocess.CompletedProcess(args, 0, stdout=manifest_relative + "\0", stderr="")
        if "show" in args:
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(row) + "\n", stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(vault, "_run_command", non_v2_snapshot)

    with pytest.raises(vault.VaultError, match="non-public-safe"):
        vault._real_historical_artifacts()


def test_historical_manifest_validates_side_branches_incomparable_with_boundary(vault, monkeypatch: pytest.MonkeyPatch):
    manifest_relative = "institutio/vault/manifest.jsonl"
    safe_root = "a" * 40
    side_revision = "b" * 40
    monkeypatch.setattr(vault, "PUBLIC_SAFE_HISTORY_ROOT", safe_root)
    row = {
        "schema": vault.SCHEMA,
        "artifact_id": "artifact-001",
        "ciphertext": "artifact-001.gpg",
        "ciphertext_sha256": "1" * 64,
        "ciphertext_bytes": 1,
        "recipient_fpr": vault.FINGERPRINT,
        "vaulted_at": "2026-08-09T00:00:00+00:00",
        "private_field": "synthetic",
    }

    def side_branch_snapshot(args, *, env=None):
        del env
        if "--is-shallow-repository" in args:
            return subprocess.CompletedProcess(args, 0, stdout="false\n", stderr="")
        if "rev-list" in args:
            return subprocess.CompletedProcess(args, 0, stdout=side_revision + "\n", stderr="")
        if "cat-file" in args:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if "merge-base" in args and args[-2:] == [safe_root, "HEAD"]:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if "merge-base" in args and args[-2:] == [side_revision, safe_root]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="")
        if "ls-tree" in args:
            return subprocess.CompletedProcess(args, 0, stdout=manifest_relative + "\0", stderr="")
        if "show" in args:
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(row) + "\n", stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(vault, "_run_command", side_branch_snapshot)

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
    # .agent-runtime/ and .limen-workstream/ remain gitignored local scratch.
    # .limen-private/ is encrypted and git-tracked via institutio/vault/ (not gitignored).
    for prefix in (".agent-runtime/", ".limen-workstream/"):
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


@pytest.mark.parametrize("private_root", [".limen-private", ".agent-runtime", ".limen-workstream"])
def test_verify_rejects_tracked_private_namespace_root(
    vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, private_root: str
):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault) | {private_root})

    assert vault.cmd_verify(SimpleNamespace()) == 1


def test_verify_rejects_non_bootstrap_artifact_without_recovery_proof(
    vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    with monkeypatch.context() as allow_synthetic_admission:
        allow_synthetic_admission.setattr(vault, "BOOTSTRAP_ARTIFACT_IDS", frozenset({"artifact-001", "artifact-002"}))
        _add(vault, source, "artifact-002")
    monkeypatch.setattr(vault, "_tracked_files", lambda: _tracked_paths(vault, "artifact-002"))

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

    def corrupt_decrypt(ciphertext_fd: int, envelope_fd: int) -> None:
        _write_descriptor(vault, envelope_fd, _read_descriptor(vault, ciphertext_fd) + b"tamper")

    monkeypatch.setattr(vault, "_decrypt_descriptors", corrupt_decrypt)
    with pytest.raises(vault.VaultError, match="integrity mismatch"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
    assert not destination.exists()


def test_failed_restore_cleans_up_after_decrypt_failure(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    destination = tmp_path / "restore"

    def reject_decrypt(_ciphertext_fd: int, _envelope_fd: int) -> None:
        raise vault.VaultError("decryption failed: no secret key")

    monkeypatch.setattr(vault, "_decrypt_descriptors", reject_decrypt)
    with pytest.raises(vault.VaultError, match="no secret key"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
    assert not destination.exists()


def test_restore_rejects_unpinned_ciphertext_before_writing(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("secret", encoding="utf-8")
    _add(vault, source)
    (vault.VAULT_DIR / "artifact-001.gpg").write_bytes(b"substituted")
    destination = tmp_path / "restore"

    with pytest.raises(vault.VaultError, match="ciphertext"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
    assert not destination.exists()


def test_restore_rejects_ciphertext_replaced_before_snapshot(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("trusted", encoding="utf-8")
    _add(vault, source)
    ciphertext = vault.VAULT_DIR / "artifact-001.gpg"
    destination = tmp_path / "restore"
    real_snapshot = vault._snapshot_ciphertext

    def replace_before_snapshot(source_path: Path, snapshot_fd: int) -> None:
        source_path.write_bytes(b"replacement")
        real_snapshot(source_path, snapshot_fd)

    monkeypatch.setattr(vault, "_snapshot_ciphertext", replace_before_snapshot)

    with pytest.raises(vault.VaultError, match="ciphertext"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))

    assert ciphertext.read_bytes() == b"replacement"
    assert not destination.exists()


def test_restore_decrypts_the_validated_ciphertext_snapshot(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("trusted", encoding="utf-8")
    _add(vault, source)
    ciphertext = vault.VAULT_DIR / "artifact-001.gpg"
    expected_ciphertext = ciphertext.read_bytes()
    destination = tmp_path / "restore"

    def replace_original_then_decrypt(snapshot_fd: int, envelope_fd: int) -> None:
        assert _read_descriptor(vault, snapshot_fd) == expected_ciphertext
        ciphertext.write_bytes(b"replacement")
        _write_descriptor(vault, envelope_fd, _read_descriptor(vault, snapshot_fd))

    monkeypatch.setattr(vault, "_decrypt_descriptors", replace_original_then_decrypt)

    assert (
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
        == 0
    )
    assert (destination / "artifact-001--private.md").read_text(encoding="utf-8") == "trusted"
    assert ciphertext.read_bytes() == b"replacement"


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


def test_restore_rejects_unprotected_repository_destination(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    destination = vault.ROOT / "restored"

    with pytest.raises(vault.VaultError, match="private namespace"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))

    assert not destination.exists()


@pytest.mark.parametrize("private_root", [".limen-private", ".agent-runtime", ".limen-workstream"])
def test_restore_allows_each_repository_private_destination(vault, tmp_path: Path, private_root: str):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    destination = vault.ROOT / private_root / "restore"

    assert (
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))
        == 0
    )
    assert (destination / "artifact-001--private.md").read_text(encoding="utf-8") == "synthetic"


def test_restore_rejects_private_destination_redirected_into_public_repository_path(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    private_root = vault.ROOT / ".limen-private"
    private_root.mkdir()
    public_root = vault.ROOT / "public"
    public_root.mkdir()
    (private_root / "redirect").symlink_to(public_root, target_is_directory=True)
    destination = private_root / "redirect" / "nested"

    with pytest.raises(vault.VaultError, match="remain in a private namespace"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))

    assert not (public_root / "nested").exists()
    assert list(public_root.iterdir()) == []


def test_restore_rejects_external_alias_into_public_repository_path(vault, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("synthetic", encoding="utf-8")
    _add(vault, source)
    public_root = vault.ROOT / "public"
    public_root.mkdir()
    external_alias = tmp_path / "external-alias"
    external_alias.symlink_to(public_root, target_is_directory=True)
    destination = external_alias / "nested"

    with pytest.raises(vault.VaultError, match="remain in a private namespace"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))

    assert not (public_root / "nested").exists()
    assert list(public_root.iterdir()) == []


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


def test_restore_rejects_destination_swap_before_temp_creation(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("trusted", encoding="utf-8")
    _add(vault, source)
    destination = tmp_path / "restore"
    destination.mkdir(mode=0o700)
    original_destination = tmp_path / "restore-original"
    redirect = tmp_path / "redirect"
    redirect.mkdir(mode=0o700)
    real_temporary_file_at = vault._temporary_file_at
    swapped = False

    def swap_then_create(directory_fd: int, artifact_id: str, suffix: str):
        nonlocal swapped
        if not swapped:
            swapped = True
            destination.rename(original_destination)
            destination.symlink_to(redirect, target_is_directory=True)
        return real_temporary_file_at(directory_fd, artifact_id, suffix)

    monkeypatch.setattr(vault, "_temporary_file_at", swap_then_create)

    with pytest.raises(vault.VaultError, match="destination changed"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))

    assert destination.is_symlink()
    assert list(redirect.iterdir()) == []
    assert list(original_destination.iterdir()) == []


def test_restore_rejects_destination_swap_during_publication(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    source.write_text("trusted", encoding="utf-8")
    _add(vault, source)
    destination = tmp_path / "restore"
    destination.mkdir(mode=0o700)
    original_destination = tmp_path / "restore-original"
    redirect = tmp_path / "redirect"
    redirect.mkdir(mode=0o700)
    real_link = vault._link_no_replace_at
    swapped = False

    def swap_then_link(directory_fd: int, source_name: str, destination_name: str):
        nonlocal swapped
        if not swapped:
            swapped = True
            destination.rename(original_destination)
            destination.symlink_to(redirect, target_is_directory=True)
        return real_link(directory_fd, source_name, destination_name)

    monkeypatch.setattr(vault, "_link_no_replace_at", swap_then_link)

    with pytest.raises(vault.VaultError, match="destination changed"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))

    assert destination.is_symlink()
    assert list(redirect.iterdir()) == []
    assert list(original_destination.iterdir()) == []


def test_restore_atomic_publish_does_not_replace_concurrent_target(
    vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    source = tmp_path / "private.md"
    source.write_text("trusted", encoding="utf-8")
    _add(vault, source)
    destination = tmp_path / "restore"
    destination.mkdir(mode=0o700)
    final_path = destination / "artifact-001--private.md"
    real_link = vault.os.link

    def concurrent_link(
        source_path,
        destination_path,
        *,
        src_dir_fd=None,
        dst_dir_fd=None,
        follow_symlinks=True,
    ):
        concurrent_fd = vault.os.open(
            destination_path,
            vault.os.O_WRONLY | vault.os.O_CREAT | vault.os.O_EXCL,
            0o600,
            dir_fd=dst_dir_fd,
        )
        try:
            vault.os.write(concurrent_fd, b"concurrent")
        finally:
            vault.os.close(concurrent_fd)
        return real_link(
            source_path,
            destination_path,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(vault.os, "link", concurrent_link)

    with pytest.raises(vault.VaultError, match="already exists"):
        vault.cmd_restore(SimpleNamespace(all=False, artifact_id="artifact-001", dest=str(destination), apply=True))

    assert final_path.read_text(encoding="utf-8") == "concurrent"
    assert [path for path in destination.iterdir() if path.name.startswith(".artifact-001.")] == []


def test_restore_all_rolls_back_earlier_links_on_late_concurrent_target(
    vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    first = tmp_path / "first.md"
    first.write_text("first", encoding="utf-8")
    second = tmp_path / "second.md"
    second.write_text("second", encoding="utf-8")
    monkeypatch.setattr(vault, "BOOTSTRAP_ARTIFACT_IDS", frozenset({"artifact-001", "artifact-002"}))
    _add(vault, first, "artifact-001")
    _add(vault, second, "artifact-002")
    destination = tmp_path / "restore"
    destination.mkdir(mode=0o700)
    first_path = destination / "artifact-001--first.md"
    second_path = destination / "artifact-002--second.md"
    real_link = vault.os.link
    links = 0

    def race_second_link(
        source_path,
        destination_path,
        *,
        src_dir_fd=None,
        dst_dir_fd=None,
        follow_symlinks=True,
    ):
        nonlocal links
        links += 1
        if links == 2:
            concurrent_fd = vault.os.open(
                destination_path,
                vault.os.O_WRONLY | vault.os.O_CREAT | vault.os.O_EXCL,
                0o600,
                dir_fd=dst_dir_fd,
            )
            try:
                vault.os.write(concurrent_fd, b"concurrent")
            finally:
                vault.os.close(concurrent_fd)
        return real_link(
            source_path,
            destination_path,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(vault.os, "link", race_second_link)

    with pytest.raises(vault.VaultError, match="already exists"):
        vault.cmd_restore(SimpleNamespace(all=True, artifact_id=None, dest=str(destination), apply=True))

    assert not first_path.exists()
    assert second_path.read_text(encoding="utf-8") == "concurrent"
    assert [path for path in destination.iterdir() if path.name.startswith(".artifact-")] == []


def test_restore_all_preflights_every_target_before_publish(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    first = tmp_path / "first.md"
    first.write_text("first", encoding="utf-8")
    second = tmp_path / "second.md"
    second.write_text("second", encoding="utf-8")
    monkeypatch.setattr(vault, "BOOTSTRAP_ARTIFACT_IDS", frozenset({"artifact-001", "artifact-002"}))
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


def test_restore_bounds_output_name(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / ("n" * 240)
    source.write_text("secret", encoding="utf-8")
    artifact_id = "artifact-" + "1" * 55
    monkeypatch.setattr(vault, "BOOTSTRAP_ARTIFACT_IDS", frozenset({artifact_id}))
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


def test_add_rejects_source_mutation_during_snapshot(vault, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    source = tmp_path / "private.md"
    original = b"a" * (2 << 20)
    replacement = b"b" * len(original)
    source.write_bytes(original)
    begin_write = threading.Event()
    write_finished = threading.Event()

    def writer() -> None:
        assert begin_write.wait(5)
        with source.open("r+b") as handle:
            handle.write(replacement)
            handle.flush()
            vault.os.fsync(handle.fileno())
        write_finished.set()

    writer_thread = threading.Thread(target=writer)
    writer_thread.start()

    def hybrid_copy(input_handle, output_handle):
        digest = vault.hashlib.sha256()
        first = input_handle.read(1)
        output_handle.write(first)
        digest.update(first)
        begin_write.set()
        assert write_finished.wait(5)
        count = len(first)
        for chunk in iter(lambda: input_handle.read(1 << 20), b""):
            output_handle.write(chunk)
            digest.update(chunk)
            count += len(chunk)
        return digest.hexdigest(), count

    monkeypatch.setattr(vault, "_copy_file_and_hash", hybrid_copy)
    try:
        with pytest.raises(vault.VaultError, match="source changed while creating its snapshot"):
            _add(vault, source)
    finally:
        writer_thread.join(timeout=5)

    assert not writer_thread.is_alive()
    assert not vault.MANIFEST.exists()


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
