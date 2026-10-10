from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from limen.storage_headroom import SCHEMA, StorageAdmissionError, require_storage_headroom
from limen.storage_headroom import storage_identity as actual_storage_identity


GIB = 1024**3


@pytest.fixture(autouse=True)
def identity(monkeypatch):
    monkeypatch.setattr("limen.storage_headroom.storage_identity", lambda path: "internal")


def _free_bytes(monkeypatch: pytest.MonkeyPatch, value: int) -> None:
    monkeypatch.setattr(
        "limen.storage_headroom.os.statvfs",
        lambda _path: SimpleNamespace(f_bavail=value, f_frsize=1),
    )


def _state(tmp_path: Path) -> Path:
    return tmp_path / "state" / "limen" / "storage-headroom.json"


def test_low_space_latches_until_200_gib(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    target = tmp_path / "worktrees" / "new"

    _free_bytes(monkeypatch, 49 * GIB)
    with pytest.raises(StorageAdmissionError, match="storage-headroom-latched-until-200-gib-free"):
        require_storage_headroom(target)
    assert json.loads(_state(tmp_path).read_text())["blocked"] is True

    _free_bytes(monkeypatch, 100 * GIB)
    with pytest.raises(StorageAdmissionError, match="storage-headroom-latched-until-200-gib-free"):
        require_storage_headroom(target)

    _free_bytes(monkeypatch, 200 * GIB)
    require_storage_headroom(target)
    assert json.loads(_state(tmp_path).read_text())["blocked"] is False


def test_mid_band_allows_when_no_low_space_latch_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    _free_bytes(monkeypatch, 100 * GIB)

    require_storage_headroom(tmp_path / "worktrees" / "new")


def test_external_observation_cannot_clear_internal_legacy_latch(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    _free_bytes(monkeypatch, 49 * GIB)
    with pytest.raises(StorageAdmissionError):
        require_storage_headroom(tmp_path)
    monkeypatch.setattr(
        "limen.storage_headroom.storage_identity", lambda path: "internal" if path == Path.home() else "external"
    )
    _free_bytes(monkeypatch, 220 * GIB)
    require_storage_headroom(tmp_path)
    assert json.loads(_state(tmp_path).read_text())["blocked"] is True
    monkeypatch.setattr("limen.storage_headroom.storage_identity", lambda path: "internal")
    _free_bytes(monkeypatch, 100 * GIB)
    with pytest.raises(StorageAdmissionError):
        require_storage_headroom(tmp_path)


def test_shared_pool_latches_across_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(
        "limen.storage_headroom.storage_identity", lambda path: "internal" if path == Path.home() else "shared-apfs"
    )
    _free_bytes(monkeypatch, 49 * GIB)
    with pytest.raises(StorageAdmissionError):
        require_storage_headroom(tmp_path / "one")
    _free_bytes(monkeypatch, 100 * GIB)
    with pytest.raises(StorageAdmissionError):
        require_storage_headroom(tmp_path / "two")


def test_missing_mount_does_not_fall_back_to_parent(monkeypatch):
    monkeypatch.setattr(Path, "is_mount", lambda path: False)
    with pytest.raises(StorageAdmissionError, match="mount-unavailable"):
        require_storage_headroom("/Volumes/Absent/worktrees/new")


def test_apfs_volumes_use_persistent_container_uuid(tmp_path, monkeypatch):
    import plistlib

    monkeypatch.setattr("limen.storage_headroom.sys.platform", "darwin")

    def run(args, **kwargs):
        if args[0] == "df":
            return SimpleNamespace(stdout=b"Filesystem\n/dev/disk4s1 1 1 1 1% /mount\n")
        value = (
            {"DiskUUID": "12345678-1234-1234-1234-123456789012"}
            if args[-1] == "disk4"
            else {"FilesystemType": "apfs", "APFSContainerReference": "disk4"}
        )
        return SimpleNamespace(stdout=plistlib.dumps(value))

    monkeypatch.setattr("limen.storage_headroom.subprocess.run", run)
    assert actual_storage_identity(tmp_path) == "apfs:12345678-1234-1234-1234-123456789012"


def test_invalid_state_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    state = _state(tmp_path)
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"schema": SCHEMA, "blocked": "unknown", "observed_free_bytes": 0}))
    _free_bytes(monkeypatch, 220 * GIB)

    with pytest.raises(StorageAdmissionError, match="storage-admission-state-invalid"):
        require_storage_headroom(tmp_path / "worktrees" / "new")


def test_missing_unrelated_registration_does_not_block_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from limen.worktree_abandonment import _registered_worktree_paths

    existing = tmp_path / "existing"
    existing.mkdir()
    missing = tmp_path / "missing-registration"
    output = f"worktree {existing}\nHEAD {'a' * 40}\n\nworktree {missing}\nHEAD {'b' * 40}\n"
    monkeypatch.setattr(
        "limen.worktree_abandonment._run_git",
        lambda *_args: SimpleNamespace(returncode=0, stdout=output, stderr=""),
    )

    paths = _registered_worktree_paths(tmp_path)

    assert existing.resolve(strict=True) in paths
    assert missing.resolve(strict=False) in paths
