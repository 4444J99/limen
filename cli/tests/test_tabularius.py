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
import subprocess

import limen.tabularius as tabularius
import pytest
from limen.io import load_limen_file, queue_lock, save_limen_file
from limen.models import LimenFile, Task
from limen.tabularius import (
    INTENT_META,
    INTENT_ORDER,
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
    preserve_board_projection,
    submit_ticket,
    task_state_sha256,
)

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


def _task(tid: str, **over) -> dict:
    base = {
        "id": tid,
        "title": f"task {tid}",
        "repo": "organvm/limen",
        "target_agent": "jules",
        "created": "2026-07-01",
        "predicate": f"pytest -q -k {tid}",
        "receipt_target": f"github:organvm/limen:pull-request:{tid}",
    }
    base.update(over)
    return base


def _board(tasks: list[dict]) -> LimenFile:
    return LimenFile.model_validate({"version": "1.0", "tasks": tasks})


def _seed_board(tmp_path: Path, n: int = 6) -> Path:
    """A board with n tasks (above the collapse-guard floor of 5) at tmp_path/tasks.yaml."""
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, _board([_task(f"T-{i}", status="open") for i in range(n)]))
    return board


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _commit_all(repo: Path, msg: str) -> None:
    _git(repo, "add", ".")
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=test", "commit", "-qm", msg],
        cwd=repo,
        check=True,
    )


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
        precondition=over.pop("precondition", None),
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


def test_tabularius_preserves_board_projection_without_stranding_local_commit(tmp_path):
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True)
    _git(repo, "switch", "-c", "main")
    board = repo / "tasks.yaml"
    save_limen_file(board, _board([_task(f"T-{i}", status="open") for i in range(6)]))
    _commit_all(repo, "base")
    _git(repo, "push", "-u", "origin", "main")

    submit_ticket(board, _ticket(INTENT_STATUS, task_id="T-1", log={"status": "done", "output": "ok"}))
    assert drain_once(board).wrote is True
    result = preserve_board_projection(board)

    assert result.pushed is True
    assert _git(repo, "status", "--porcelain", "--", "tasks.yaml") == ""
    remote_board = subprocess.run(
        ["git", "--git-dir", str(origin), "show", "main:tasks.yaml"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "status: done" in remote_board


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


def test_exact_task_precondition_rejects_archive_after_concurrent_claim(tmp_path):
    board = _seed_board(tmp_path)
    original = {task.id: task for task in load_limen_file(board).tasks}["T-1"]
    original_state = original.model_dump(mode="json", exclude_none=True)
    claim = _ticket(
        INTENT_STATUS,
        task_id="T-1",
        ts=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        log={"status": "dispatched", "output": "concurrent claim"},
    )
    archive = _ticket(
        INTENT_UPSERT,
        task_id="T-1",
        ts=datetime(2026, 7, 2, 12, 1, tzinfo=timezone.utc),
        patch={"status": "archived"},
        log={"status": "archived", "output": "stale migration"},
        precondition={"status": "open", "task_sha256": task_state_sha256(original_state)},
    )
    submit_ticket(board, claim)
    submit_ticket(board, archive)

    result = drain_once(board)

    assert (result.applied, result.rejected) == (1, 1)
    current = {task.id: task for task in load_limen_file(board).tasks}["T-1"]
    assert current.status == "dispatched"
    reason = (_rejected(board) / f"{archive.ticket_id}.json.reason.txt").read_text()
    assert "invalidated regardless of timestamp order" in reason


@pytest.mark.parametrize("claim_status", ["dispatched", "in_progress"])
def test_batch_admission_rejects_archive_before_later_active_claim(tmp_path, claim_status):
    board = _seed_board(tmp_path)
    original = {task.id: task for task in load_limen_file(board).tasks}["T-1"]
    original_state = original.model_dump(mode="json", exclude_none=True)
    archive = _ticket(
        INTENT_UPSERT,
        task_id="T-1",
        ts=datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        patch={"status": "archived"},
        log={"status": "archived", "output": "migration archive"},
        precondition={"status": "open", "task_sha256": task_state_sha256(original_state)},
    )
    later_claim = _ticket(
        INTENT_STATUS,
        task_id="T-1",
        ts=datetime(2026, 7, 2, 12, 1, tzinfo=timezone.utc),
        log={"status": claim_status, "output": "later concurrent claim"},
    )
    submit_ticket(board, archive)
    submit_ticket(board, later_claim)

    preview = drain_once(board, dry_run=True)
    assert (preview.applied, preview.rejected, preview.pending) == (1, 1, 2)
    result = drain_once(board)

    assert (result.applied, result.rejected) == (1, 1)
    current = {task.id: task for task in load_limen_file(board).tasks}["T-1"]
    assert current.status == claim_status
    assert [entry.status for entry in current.dispatch_log] == [claim_status]
    reason = (_rejected(board) / f"{archive.ticket_id}.json.reason.txt").read_text()
    assert "invalidated regardless of timestamp order" in reason


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


def test_bypassed_untyped_new_ticket_is_quarantined_without_blocking_typed_sibling(tmp_path):
    board = _seed_board(tmp_path)
    good = _ticket(INTENT_UPSERT, task_id="T-typed", patch=_task("T-typed", status="open"))
    bad_patch = _task("T-untyped", status="open")
    bad_patch.pop("predicate")
    bad_patch.pop("receipt_target")
    bad = _ticket(INTENT_UPSERT, task_id="T-untyped", patch=bad_patch)
    submit_ticket(board, bad)
    submit_ticket(board, good)

    result = drain_once(board)

    assert result.applied == 1 and result.rejected == 1
    assert "T-typed" in {task.id for task in load_limen_file(board).tasks}
    assert "T-untyped" not in {task.id for task in load_limen_file(board).tasks}
    reason = (_rejected(board) / f"{bad.ticket_id}.json.reason.txt").read_text()
    assert "predicate must be one executable command" in reason


def test_bypassed_legacy_active_transition_is_quarantined_without_blocking_sibling(tmp_path):
    board = _seed_board(tmp_path)
    current = load_limen_file(board)
    legacy = next(task for task in current.tasks if task.id == "T-0")
    legacy.status = "needs_human"
    legacy.predicate = None
    legacy.receipt_target = None
    save_limen_file(board, current)

    bad = _ticket(INTENT_STATUS, task_id="T-0", log={"status": "dispatched"})
    good = _ticket(INTENT_STATUS, task_id="T-1", log={"status": "done"})
    submit_ticket(board, bad)
    submit_ticket(board, good)

    result = drain_once(board)

    assert result.applied == 1 and result.rejected == 1
    tasks = {task.id: task for task in load_limen_file(board).tasks}
    assert tasks["T-0"].status == "needs_human"
    assert tasks["T-1"].status == "done"
    assert (
        "predicate must be one executable command"
        in (_rejected(board) / f"{bad.ticket_id}.json.reason.txt").read_text()
    )


def test_bad_meta_ticket_quarantined_good_ticket_survives(tmp_path):
    board = _seed_board(tmp_path)
    good = _ticket(INTENT_UPSERT, task_id="T-ok", patch=_task("T-ok", status="open"))
    bad = _ticket(INTENT_META, patch={"portal": {"budget": "not-a-mapping"}})
    submit_ticket(board, good)
    submit_ticket(board, bad)

    result = drain_once(board)

    assert result.applied == 1 and result.rejected == 1
    ids = {t.id for t in load_limen_file(board).tasks}
    assert "T-ok" in ids
    assert (_rejected(board) / f"{bad.ticket_id}.json").exists()


def test_bad_order_ticket_quarantined_good_ticket_survives(tmp_path):
    board = _seed_board(tmp_path)
    good = _ticket(INTENT_UPSERT, task_id="T-ok", patch=_task("T-ok", status="open"))
    bad = _ticket(INTENT_ORDER, patch={"ids": "T-2"})
    submit_ticket(board, good)
    submit_ticket(board, bad)

    result = drain_once(board)

    assert result.applied == 1 and result.rejected == 1
    ids = {t.id for t in load_limen_file(board).tasks}
    assert "T-ok" in ids
    assert (_rejected(board) / f"{bad.ticket_id}.json").exists()


def test_unparseable_ticket_is_quarantined(tmp_path):
    board = _seed_board(tmp_path)
    inbox = _inbox(board)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "garbage.json").write_text("{ this is not valid json ")
    result = drain_once(board)
    assert result.rejected == 1 and result.applied == 0
    assert (_rejected(board) / "garbage.json").exists()


# --- never dead-stop: a held lock defers, and the collapse-guard fences a bad batch --------------
def test_held_lock_defers_without_touching_board(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    submit_ticket(board, _ticket(INTENT_UPSERT, task_id="T-x", patch=_task("T-x", status="open")))
    before = board.read_text()
    real_parse = tabularius._parse_pending
    parse_calls = 0

    def counted_parse(inbox):
        nonlocal parse_calls
        parse_calls += 1
        return real_parse(inbox)

    monkeypatch.setattr(tabularius, "_parse_pending", counted_parse)
    # simulate a legacy writer holding the queue lock
    with queue_lock(board) as locked:
        assert locked
        result = drain_once(board, lock_timeout=1)
    assert result.deferred is True and result.wrote is False
    assert parse_calls == 0  # publisher's locked phase was never observed as a prefix
    assert board.read_text() == before  # board untouched
    assert pending_count(board) == 1  # ticket still waiting

    # once the lock is free, the same ticket lands
    assert drain_once(board).applied == 1
    assert parse_calls == 1
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


# --- the Step-2 migration safety invariant: producer path ≡ legacy direct write -----------------
def test_producer_path_matches_legacy_direct_write(tmp_path):
    """The conversion contract for every writer: swapping `load → extend → save_limen_file` for
    `submit_task_upsert(...) + drain` yields the SAME board — identical existing tasks, identical
    new-task fields, identical order — save only for the keeper's added `updated` provenance stamp.
    This is what turns each generator conversion into a mechanical, provable change, not surgery."""
    from limen.tabularius import submit_task_upsert

    existing = [_task(f"T-{i}", status="open") for i in range(6)]
    new_tasks = [
        Task.model_validate(_task("N-1", status="open", priority="high", repo="organvm/limen")),
        Task.model_validate(_task("N-2", status="open", priority="medium", labels=["mined"])),
        Task.model_validate(_task("N-3", status="open", type="content")),
    ]

    # Path A — legacy direct write: load → extend → save
    board_a = tmp_path / "a" / "tasks.yaml"
    board_a.parent.mkdir(parents=True)
    lf = _board(existing)
    lf.tasks.extend(new_tasks)
    save_limen_file(board_a, lf)

    # Path B — producer tickets drained by the keeper (monotonic ts pins the append order)
    board_b = tmp_path / "b" / "tasks.yaml"
    board_b.parent.mkdir(parents=True)
    save_limen_file(board_b, _board(existing))
    for i, t in enumerate(new_tasks):
        submit_task_upsert(
            board_b, t, agent="gen", session_id="s", now=datetime(2026, 7, 2, 12, i, tzinfo=timezone.utc)
        )
    result = drain_once(board_b)
    assert result.applied == 3 and result.wrote is True

    a_tasks = load_limen_file(board_a).tasks
    b_tasks = load_limen_file(board_b).tasks
    assert [t.id for t in a_tasks] == [t.id for t in b_tasks]  # same set AND order
    da = {t.id: t.model_dump(mode="json", exclude_none=True) for t in a_tasks}
    db = {t.id: t.model_dump(mode="json", exclude_none=True) for t in b_tasks}
    for tid in da:
        a, b = dict(da[tid]), dict(db[tid])
        # the keeper additionally stamps `updated` provenance on each folded task — a strict add,
        # not a divergence; every other field must match the legacy write byte-for-byte.
        a.pop("updated", None)
        b.pop("updated", None)
        assert a == b, f"field divergence on {tid}: {a} vs {b}"


def test_submit_task_upsert_validates_before_emitting(tmp_path):
    """The producer validates the task up front (fail-fast, like the legacy `Task(**t)`), so an
    invalid task never reaches the inbox as a silently-quarantined ticket."""
    import pytest

    from limen.tabularius import submit_task_upsert

    board = _seed_board(tmp_path)
    # a dict missing the required `id` — must raise at submit, not land a ticket
    with pytest.raises((ValueError, Exception)):
        submit_task_upsert(board, {"title": "no id"}, agent="gen")
    untyped = _task("NEW-UNTYPED", status="open")
    untyped.pop("predicate")
    untyped.pop("receipt_target")
    with pytest.raises(ValueError, match="predicate"):
        submit_task_upsert(board, untyped, agent="gen")
    assert pending_count(board) == 0  # nothing entered the inbox
