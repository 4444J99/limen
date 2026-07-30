from __future__ import annotations

from pathlib import Path

from limen.conduct import liveness
from limen.conduct.liveness import foreign_worktree_occupant


def test_own_lineage_is_not_a_foreign_occupant(monkeypatch, tmp_path) -> None:
    # The claimant registers from INSIDE the worktree it claims: its own boot chain must not
    # read as an occupant, or succession would always be refused.
    monkeypatch.setattr(liveness, "_ancestor_pids", lambda: {100, 200})
    monkeypatch.setattr(liveness, "_process_cwds", lambda: {tmp_path: 100, tmp_path / "sub": 200})
    assert foreign_worktree_occupant(tmp_path) is None


def test_foreign_process_in_worktree_blocks_succession(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(liveness, "_ancestor_pids", lambda: {100})
    monkeypatch.setattr(liveness, "_process_cwds", lambda: {tmp_path / "deep": 999})
    assert foreign_worktree_occupant(tmp_path) == 999


def test_process_outside_worktree_is_ignored(monkeypatch, tmp_path) -> None:
    elsewhere = tmp_path.parent
    monkeypatch.setattr(liveness, "_ancestor_pids", lambda: {100})
    monkeypatch.setattr(liveness, "_process_cwds", lambda: {elsewhere: 999})
    assert foreign_worktree_occupant(tmp_path) is None


def test_unavailable_probe_fails_closed(monkeypatch, tmp_path) -> None:
    # pid -1 is the probe's own unavailability sentinel: it must surface as "occupied" so a
    # broken probe can only refuse succession, never steal a live session's worktree.
    monkeypatch.setattr(liveness, "_ancestor_pids", lambda: {100})
    monkeypatch.setattr(liveness, "_process_cwds", lambda: {Path("/"): -1})
    assert foreign_worktree_occupant(tmp_path) == -1


def test_real_probe_sees_this_test_process_as_own_lineage(tmp_path) -> None:
    # Unmocked end-to-end shape check: the current process's cwd is NOT under tmp_path, and
    # nothing foreign lives there, so a fresh temporary directory reads unoccupied — unless the
    # host probe itself is unavailable, in which case fail-closed (-1) is the correct answer.
    assert foreign_worktree_occupant(tmp_path) in (None, -1)
