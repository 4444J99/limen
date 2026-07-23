"""Regression tests for the BOARD-INTEGRITY guard (the 2026-06-26 institutional halt).

Incident: a writer atomically replaced the live 1449-task queue with ONE freshly-built task
that lacked the required `created` field. Two failures compounded into a multi-hour halt:
  1. the save REPLACED the whole board with a tiny one (no collapse-guard), and
  2. the lone task was invalid, so `load_limen_file` raised on the WHOLE board every beat —
     one partial task froze the entire institution (queue empty → fleet idle).

These tests pin both fixes in `limen.io`:
  • save_limen_file refuses a catastrophic shrink (preserving the rejected payload), and
  • load_limen_file backfills a missing `created` instead of rejecting the board.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from limen.io import BoardCollapseError, load_limen_file, save_limen_file
from limen.models import LimenFile


def _task(i: int, *, created: str | None = "2026-06-01") -> dict:
    t = {"id": f"T-{i}", "title": f"task {i}", "target_agent": "claude", "status": "open"}
    if created is not None:
        t["created"] = created
    return t


def _board(n: int) -> LimenFile:
    return LimenFile.model_validate({"version": "1.0", "tasks": [_task(i) for i in range(n)]})


def _save_raw(path: Path, n: int) -> None:
    """Seed the on-disk board directly (bypassing the guard) so a test can set up a prior state."""
    path.write_text(yaml.dump({"version": "1.0", "tasks": [_task(i) for i in range(n)]}, sort_keys=False))


# ---- collapse-guard on save -------------------------------------------------------------


def test_guard_refuses_catastrophic_shrink(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    _save_raw(board, 100)
    before = board.read_text()
    with pytest.raises(BoardCollapseError):
        save_limen_file(board, _board(1))
    # the good board is left INTACT...
    assert board.read_text() == before
    # ...and the rejected payload is preserved to a sidecar (never lost)
    sidecars = list(tmp_path.glob("tasks.yaml.rejected-*"))
    assert len(sidecars) == 1, f"expected one rejected sidecar, got {sidecars}"
    assert "T-0" in sidecars[0].read_text()


def test_guard_allows_growth(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    _save_raw(board, 100)
    save_limen_file(board, _board(101))  # an append must never trip the guard
    assert len(load_limen_file(board).tasks) == 101


def test_guard_allows_steady_state(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    _save_raw(board, 100)
    save_limen_file(board, _board(100))  # a status-update keeps the count
    assert len(load_limen_file(board).tasks) == 100


def test_guard_skips_small_boards(tmp_path: Path) -> None:
    """A prior board at/below the floor (tests, fresh bootstrap) is never guarded."""
    board = tmp_path / "tasks.yaml"
    _save_raw(board, 3)  # ≤ default floor (5)
    save_limen_file(board, _board(1))
    assert len(load_limen_file(board).tasks) == 1


def test_allow_shrink_bypasses_guard(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    _save_raw(board, 100)
    save_limen_file(board, _board(1), allow_shrink=True)  # explicit intentional archive
    assert len(load_limen_file(board).tasks) == 1


def test_env_disables_guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIMEN_BOARD_GUARD", "0")
    board = tmp_path / "tasks.yaml"
    _save_raw(board, 100)
    save_limen_file(board, _board(1))
    assert len(load_limen_file(board).tasks) == 1


def test_first_write_is_never_guarded(tmp_path: Path) -> None:
    """No prior file on disk ⇒ nothing to collapse ⇒ a fresh bootstrap write proceeds."""
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, _board(1))
    assert board.exists()


# ---- loader tolerance: one partial task must never reject the whole board ----------------


def test_load_backfills_missing_created(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    raw = {
        "version": "1.0",
        "tasks": [
            _task(0),  # valid
            _task(1, created=None),  # missing `created` — the incident's killer
            {
                "id": "T-2",
                "title": "t2",
                "target_agent": "claude",
                "status": "dispatched",
                "updated": "2026-06-20T10:00:00Z",
            },  # missing created, has updated
        ],
    }
    board.write_text(yaml.dump(raw, sort_keys=False))
    lf = load_limen_file(board)  # must NOT raise
    assert len(lf.tasks) == 3
    by_id = {t.id: t for t in lf.tasks}
    assert by_id["T-1"].created is not None
    # derived from `updated`'s date-part when present
    assert str(by_id["T-2"].created) == "2026-06-20"
