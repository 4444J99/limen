"""Tests for the event-sourced board fold (limen.materialize).

The thesis under test: the board is a materialized view — board = fold(events). Two invariants:
  A. round-trip: fold(seed_events_from_board(b)) reproduces b byte-for-byte (canonical serialize).
  B. history-replay: folding the concatenated diff_boards() deltas across a sequence of board
     versions reconstructs the final version exactly — including task order.
"""

from __future__ import annotations

import yaml
from limen.materialize import diff_boards, fold, seed_events_from_board
from limen.models import LimenFile


def _task(tid: str, **over):
    base = {
        "id": tid,
        "title": f"task {tid}",
        "target_agent": "jules",
        "created": "2026-07-01",
    }
    base.update(over)
    return base


def _board(tasks: list[dict], version: str = "1.0") -> LimenFile:
    return LimenFile.model_validate({"version": version, "tasks": tasks})


def _canonical(board: LimenFile) -> str:
    return yaml.dump(board.model_dump(mode="json", exclude_none=True), sort_keys=False, default_flow_style=False)


def test_roundtrip_reproduces_board_bytes():
    board = _board(
        [
            _task("A", status="open", labels=["x", "y"]),
            _task("B", status="done", description="did a thing", priority="high"),
            _task("C", status="in_progress", depends_on=["A"]),
        ]
    )
    rebuilt = fold(seed_events_from_board(board))
    assert _canonical(rebuilt) == _canonical(board)


def test_roundtrip_preserves_task_order():
    # first-seen fold order must equal board order (the append-stable property).
    board = _board([_task("Z"), _task("A"), _task("M")])
    rebuilt = fold(seed_events_from_board(board))
    assert [t.id for t in rebuilt.tasks] == ["Z", "A", "M"]


def test_history_replay_reconstructs_final_board():
    v1 = _board([_task("A", status="open"), _task("B", status="open")])
    v2 = _board([_task("A", status="dispatched"), _task("B", status="open"), _task("C", status="open")])
    v3 = _board([_task("A", status="done"), _task("C", status="open")])  # B removed, A advanced

    events = []
    prev = None
    for ver in (v1, v2, v3):
        events += diff_boards(prev, ver)
        prev = ver

    rebuilt = fold(events)
    assert _canonical(rebuilt) == _canonical(v3)


def test_history_replay_reconstructs_reordering():
    # order is state too: a pure reorder (no content change) must be captured and replayed.
    v1 = _board([_task("A"), _task("B"), _task("C")])
    v2 = _board([_task("C"), _task("A"), _task("B")])
    events = diff_boards(None, v1) + diff_boards(v1, v2)
    rebuilt = fold(events)
    assert [t.id for t in rebuilt.tasks] == ["C", "A", "B"]
    assert _canonical(rebuilt) == _canonical(v2)


def test_pure_append_needs_no_order_event():
    # appends alone must NOT emit a board.order event (that would be churn); first-seen fold handles it.
    v1 = _board([_task("A"), _task("B")])
    v2 = _board([_task("A"), _task("B"), _task("C")])
    deltas = diff_boards(v1, v2)
    assert all(e["type"] != "board.order" for e in deltas)
    assert [e["task_id"] for e in deltas] == ["C"]


def test_remove_drops_task():
    v1 = _board([_task("A"), _task("B")])
    v2 = _board([_task("A")])
    rebuilt = fold(diff_boards(None, v1) + diff_boards(v1, v2))
    assert [t.id for t in rebuilt.tasks] == ["A"]


def test_stale_order_event_never_drops_a_live_task():
    # a board.order that omits a live id must still keep that task (appended), never lose it.
    events = [
        {"type": "task.upsert", "task_id": "A", "data": _task("A")},
        {"type": "task.upsert", "task_id": "B", "data": _task("B")},
        {"type": "board.order", "data": {"ids": ["A"]}},  # forgets B
    ]
    rebuilt = fold(events)
    assert [t.id for t in rebuilt.tasks] == ["A", "B"]
