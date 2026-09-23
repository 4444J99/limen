from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from limen.storage_headroom import SCHEMA, StorageAdmissionError, require_storage_headroom


GIB = 1024**3


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
