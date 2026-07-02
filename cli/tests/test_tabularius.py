"""Tests for TABVLARIVS — the single-writer record-keeper (limen.tabularius).

What is under test: workers hand the keeper immutable tickets in a lock-free inbox, and the keeper
is the ONLY writer of tasks.yaml — it drains, folds each ticket onto the board in order, validates,
and seals through the collapse-guard. The invariants that make it safe to run every beat:
  * an empty inbox is a no-op that never touches the board;
  * a submitted ticket folds onto the board and is archived (the event log);
  * one bad ticket is quarantined and never takes the good ones (or the board) down;
  * a held queue lock defers the drain, never blocks;
  * a batch that would collapse the board is rejected whole, board intact.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from limen.io import load_limen_file, queue_lock, save_limen_file
from limen.models import LimenFile
from limen.tabularius import (
    INTENT_REMOVE,
    INTENT_STATUS,
    INTENT_UPSERT,
    Ticket,
    _archive,
    _inbox,
    _rejected,
    drain_once,
    new_ticket_id,
    pending_count,
    submit_ticket,
)

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


def _task(tid: str, **over) -> dict:
    base = {"id": tid, "title": f"task {tid}", "target_agent": "jules", "created": "2026-07-01"}
    base.update(over)
    return base


def _board(tasks: list[dict]) -> LimenFile:
    return LimenFile.model_validate({"version": "1.0", "tasks": tasks})


def _seed_board(tmp_path: Path, n: int = 6) -> Path:
    """A board with n tasks (above the collapse-guard floor of 5) at tmp_path/tasks.yaml."""
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, _board([_task(f"T-{i}", status="open") for i in range(n)]))
    return board


def _ticket(intent: str, task_id: str | None = None, ts: datetime = _NOW, **over) -> Ticket:
    return Ticket(
        ticket_id=over.pop("ticket_id", new_ticket_id("test", ts)),
        timestamp=ts,
        agent=over.pop("agent", "claude"),
        session_id=over.pop("session_id", "sess-1"),
        intent=intent,
        task_id=task_id,
        patch=over.pop("patch", None),
        log=over.pop("log", None),
    )


# --- the no-op contract (why it is safe every beat) ----------------------------------------------
def test_empty_inbox_is_noop(tmp_path):
    board = _seed_board(tmp_path)
    before = board.read_text()
    result = drain_once(board)
    assert result.applied == 0 and result.wrote is False and result.pending == 0
    assert board.read_text() == before  # board byte-untouched


def test_missing_inbox_is_noop(tmp_path):
    board = _seed_board(tmp_path)
    # no logs/tickets/inbox dir exists at all
    assert not _inbox(board).exists()
    result = drain_once(board)
    assert result.wrote is False and "empty" in result.note


# --- the core lifecycle: submit → drain → board updated → archived -------------------------------
def test_upsert_creates_new_task_and_archives_ticket(tmp_path):
    board = _seed_board(tmp_path)
    tk = _ticket(INTENT_UPSERT, task_id="T-new", patch=_task("T-new", status="open", priority="high"))
    submit_ticket(board, tk)
    assert pending_count(board) == 1

    result = drain_once(board)
    assert result.applied == 1 and result.wrote is True

    lf = load_limen_file(board)
    new = {t.id: t for t in lf.tasks}["T-new"]
    assert new.priority == "high" and len(lf.tasks) == 7
    # the ticket moved out of the inbox and into the archive (the event log)
    assert pending_count(board) == 0
    assert (_archive(board) / f"{tk.ticket_id}.json").exists()


def test_status_ticket_sets_status_and_appends_dispatch_log(tmp_path):
    board = _seed_board(tmp_path)
    tk = _ticket(INTENT_STATUS, task_id="T-1", log={"status": "done", "output": "shipped PR #999"})
    submit_ticket(board, tk)
    drain_once(board)

    t1 = {t.id: t for t in load_limen_file(board).tasks}["T-1"]
    assert t1.status == "done"
    assert len(t1.dispatch_log) == 1
    entry = t1.dispatch_log[0]
    assert entry.agent == "claude" and entry.status == "done" and entry.output == "shipped PR #999"


def test_partial_patch_preserves_other_fields(tmp_path):
    board = _seed_board(tmp_path)
    # seed T-2 with a description, then patch only its priority — description must survive
    save_limen_file(
        board,
        _board(
            [_task("T-2", status="open", description="keep me", priority="low")]
            + [_task(f"P-{i}", status="open") for i in range(5)]  # distinct filler ids (no T-2 collision)
        ),
    )
    submit_ticket(board, _ticket(INTENT_UPSERT, task_id="T-2", patch={"priority": "high"}))
    drain_once(board)

    t2 = {t.id: t for t in load_limen_file(board).tasks}["T-2"]
    assert t2.priority == "high" and t2.description == "keep me"


def test_remove_ticket_drops_task(tmp_path):
    board = _seed_board(tmp_path, n=6)  # 6 → 5 does not trip the guard (floor 5)
    submit_ticket(board, _ticket(INTENT_REMOVE, task_id="T-0"))
    drain_once(board)
    ids = {t.id for t in load_limen_file(board).tasks}
    assert "T-0" not in ids and len(ids) == 5


# --- ordering: concurrent tickets replay in one deterministic total order ------------------------
def test_tickets_apply_in_timestamp_order(tmp_path):
    board = _seed_board(tmp_path)
    early = datetime(2026, 7, 2, 10, 0, 0, tzinfo=timezone.utc)
    late = datetime(2026, 7, 2, 11, 0, 0, tzinfo=timezone.utc)
    # submit the LATER one first on disk; the keeper must still apply early→late
    submit_ticket(board, _ticket(INTENT_STATUS, task_id="T-1", ts=late, log={"status": "done"}))
    submit_ticket(board, _ticket(INTENT_STATUS, task_id="T-1", ts=early, log={"status": "in_progress"}))
    drain_once(board)

    t1 = {t.id: t for t in load_limen_file(board).tasks}["T-1"]
    assert [e.status for e in t1.dispatch_log] == ["in_progress", "done"]
    assert t1.status == "done"  # latest ticket wins the final status


# --- one bad ticket never breaks the batch or the board -----------------------------------------
def test_bad_ticket_quarantined_good_ticket_survives(tmp_path):
    board = _seed_board(tmp_path)
    good = _ticket(INTENT_UPSERT, task_id="T-ok", patch=_task("T-ok", status="open"))
    # a status ticket for a task that does not exist AND lacks the required created field → invalid
    bad = _ticket(INTENT_STATUS, task_id="T-ghost", log={"status": "done"})
    submit_ticket(board, good)
    submit_ticket(board, bad)

    result = drain_once(board)
    assert result.applied == 1 and result.rejected == 1

    ids = {t.id for t in load_limen_file(board).tasks}
    assert "T-ok" in ids and "T-ghost" not in ids
    # the bad ticket landed in rejected/ with a reason sidecar, board still valid
    assert (_rejected(board) / f"{bad.ticket_id}.json").exists()
    assert (_rejected(board) / f"{bad.ticket_id}.json.reason.txt").exists()


def test_unparseable_ticket_is_quarantined(tmp_path):
    board = _seed_board(tmp_path)
    inbox = _inbox(board)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "garbage.json").write_text("{ this is not valid json ")
    result = drain_once(board)
    assert result.rejected == 1 and result.applied == 0
    assert (_rejected(board) / "garbage.json").exists()


# --- never dead-stop: a held lock defers, and the collapse-guard fences a bad batch --------------
def test_held_lock_defers_without_touching_board(tmp_path):
    board = _seed_board(tmp_path)
    submit_ticket(board, _ticket(INTENT_UPSERT, task_id="T-x", patch=_task("T-x", status="open")))
    before = board.read_text()
    # simulate a legacy writer holding the queue lock
    with queue_lock(board) as locked:
        assert locked
        result = drain_once(board, lock_timeout=1)
    assert result.deferred is True and result.wrote is False
    assert board.read_text() == before  # board untouched
    assert pending_count(board) == 1  # ticket still waiting

    # once the lock is free, the same ticket lands
    assert drain_once(board).applied == 1
    assert "T-x" in {t.id for t in load_limen_file(board).tasks}


def test_collapse_guard_rejects_a_shrinking_batch(tmp_path):
    board = _seed_board(tmp_path, n=6)
    # remove 5 of 6 tasks in one batch: 6 → 1 trips the collapse-guard (< floor 5)
    for i in range(5):
        submit_ticket(
            board, _ticket(INTENT_REMOVE, task_id=f"T-{i}", ts=datetime(2026, 7, 2, 12, i, tzinfo=timezone.utc))
        )
    result = drain_once(board)

    assert result.wrote is False  # board never shrunk
    assert len(load_limen_file(board).tasks) == 6  # good board intact
    assert result.rejected == 5  # the whole batch quarantined
