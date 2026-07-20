"""Tests for the broker-backed TABVLARIVS compatibility relay.

The local ``tasks.yaml`` file is a read-only hot projection. Producers may
append immutable compatibility tickets locally, but a drain may archive a
ticket only after the authenticated conduct broker acknowledges the canonical
task projection. Broker outages leave unacknowledged tickets pending.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import limen.tabularius as tabularius
import pytest
from limen.conduct.client import BrokerUnavailable
from limen.io import load_limen_file, queue_lock, save_limen_file
from limen.models import LimenFile
from limen.tabularius import (
    INTENT_META,
    INTENT_REMOVE,
    INTENT_STATUS,
    INTENT_UPSERT,
    Ticket,
    _admit_exact_preconditions,
    _apply,
    _archive,
    _inbox,
    _rejected,
    apply_limen_file_sync,
    drain_once,
    new_ticket_id,
    pending_count,
    pending_task_ids,
    preserve_board_projection,
    submit_task_status,
    submit_task_upsert,
    submit_ticket,
    task_state_sha256,
)

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


def _task(tid: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": tid,
        "title": f"task {tid}",
        "repo": "organvm/limen",
        "target_agent": "codex",
        "created": "2026-07-01",
        "predicate": f"pytest -q -k {tid}",
        "receipt_target": f"github:organvm/limen:pull-request:{tid}",
    }
    base.update(over)
    return base


def _board(tasks: list[dict[str, Any]]) -> LimenFile:
    return LimenFile.model_validate({"version": "1.0", "tasks": tasks})


def _seed_board(tmp_path: Path, n: int = 6) -> Path:
    board = tmp_path / "tasks.yaml"
    save_limen_file(board, _board([_task(f"T-{i}", status="open") for i in range(n)]))
    return board


def _ticket(intent: str, task_id: str | None = None, ts: datetime = _NOW, **over: Any) -> Ticket:
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


class FakeConductClient:
    """Minimal owner-compatible conduct client with observable acknowledgements."""

    def __init__(
        self,
        tasks: list[dict[str, Any]],
        *,
        fail_after: int | None = None,
        unavailable_on_register: bool = False,
    ):
        self.tasks = {str(task["id"]): dict(task) for task in tasks}
        self.fail_after = fail_after
        self.unavailable_on_register = unavailable_on_register
        self.registered: list[Any] = []
        self.packets: list[Any] = []

    def register(self, session):
        if self.unavailable_on_register:
            raise BrokerUnavailable("test broker unavailable")
        self.registered.append(session)
        return {"session": session.model_dump(mode="json")}

    def submit(self, packet):
        if self.fail_after is not None and len(self.packets) >= self.fail_after:
            raise BrokerUnavailable("test broker interrupted")
        self.packets.append(packet)
        intent = dict(packet.intent)
        task_id = str(intent["task_id"])
        if intent["kind"] == "task.upsert":
            projected = dict(intent["task"])
        else:
            projected = {**self.tasks[task_id], **dict(intent.get("patch") or {})}
        projected["id"] = task_id
        self.tasks[task_id] = projected
        return {
            "status": "accepted",
            "projection_receipts": [{"task_id": task_id, "task": dict(projected)}],
        }


def _fake_for_board(board: Path, **kwargs: Any) -> FakeConductClient:
    tasks = [task.model_dump(mode="json", exclude_none=True) for task in load_limen_file(board).tasks]
    return FakeConductClient(tasks, **kwargs)


# Local ticket primitives remain durable and deterministic.
def test_ticket_ids_are_unique_and_time_sortable():
    first = new_ticket_id("session", _NOW)
    second = new_ticket_id("session", _NOW)
    assert first != second
    assert first.startswith("20260702T120000_000000Z-session-")
    assert second.startswith("20260702T120000_000000Z-session-")


def test_submit_ticket_is_exclusive_and_pending_ids_are_visible(tmp_path):
    board = _seed_board(tmp_path)
    ticket = _ticket(
        INTENT_UPSERT,
        task_id="T-new",
        patch=_task("T-new", status="open"),
        ticket_id="fixed-ticket",
    )

    submit_ticket(board, ticket)
    with pytest.raises(FileExistsError):
        submit_ticket(board, ticket)

    assert pending_count(board) == 1
    assert pending_task_ids(board) == {"T-new"}


def test_submit_helpers_validate_before_emitting(tmp_path):
    board = _seed_board(tmp_path)
    with pytest.raises(ValueError, match="status must be one of"):
        submit_task_status(board, "T-1", status="completed", agent="codex")
    with pytest.raises(ValueError, match="conflicts"):
        submit_task_status(
            board,
            "T-1",
            status="done",
            agent="codex",
            patch={"status": "failed"},
        )
    with pytest.raises(Exception):
        submit_task_upsert(board, {"title": "missing id"}, agent="codex")
    assert pending_count(board) == 0


# The pure reducer remains useful for validating legacy ticket syntax. It does
# not authorize a local projection write.
def test_pure_reducer_merges_fields_and_appends_status_receipt():
    tasks: OrderedDict[str, dict[str, Any]] = OrderedDict(
        [("T-1", _task("T-1", status="open", description="preserve me"))]
    )
    meta: dict[str, Any] = {"version": "1.0", "portal": None}
    ticket = _ticket(
        INTENT_STATUS,
        task_id="T-1",
        patch={"status": "dispatched", "priority": "high"},
        log={"status": "dispatched", "output": "claimed"},
    )

    _apply(ticket, tasks, meta)

    assert tasks["T-1"]["description"] == "preserve me"
    assert tasks["T-1"]["priority"] == "high"
    assert tasks["T-1"]["status"] == "dispatched"
    assert tasks["T-1"]["dispatch_log"][-1]["output"] == "claimed"


def test_batch_admission_rejects_stale_exact_state_ticket():
    base = _task("T-1", status="open")
    archive = _ticket(
        INTENT_UPSERT,
        task_id="T-1",
        patch={"status": "archived"},
        precondition={"status": "open", "task_sha256": task_state_sha256(base)},
        ticket_id="archive",
    )
    claim = _ticket(
        INTENT_STATUS,
        task_id="T-1",
        patch={"status": "dispatched"},
        log={"status": "dispatched"},
        ticket_id="claim",
    )

    admitted, rejected = _admit_exact_preconditions([(Path("archive.json"), archive), (Path("claim.json"), claim)])

    assert [ticket.ticket_id for _, ticket in admitted] == ["claim"]
    assert rejected[0][0] == Path("archive.json")
    assert "invalidated regardless of timestamp order" in rejected[0][1]


# Empty/no-op operations never need the broker and never touch the projection.
def test_empty_inbox_is_noop_and_projection_is_byte_untouched(tmp_path):
    board = _seed_board(tmp_path)
    before = board.read_bytes()

    result = drain_once(board)

    assert result.applied == 0
    assert result.wrote is False
    assert result.pending == 0
    assert board.read_bytes() == before


def test_sync_noop_neither_calls_broker_nor_touches_projection(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    before = board.read_bytes()

    def unexpected_client():
        raise AssertionError("no-op sync must not contact broker")

    monkeypatch.setattr(tabularius, "client_from_env", unexpected_client)
    result = apply_limen_file_sync(
        board,
        load_limen_file(board),
        agent="legacy-adapter",
        session_id="sync-noop",
    )

    assert result.wrote is False
    assert result.note == "no board change"
    assert board.read_bytes() == before


def test_sync_relays_claim_to_broker_without_writing_projection(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    before = board.read_bytes()
    fake = _fake_for_board(board)
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)
    desired = load_limen_file(board)
    desired.tasks[1].status = "dispatched"

    result = apply_limen_file_sync(
        board,
        desired,
        agent="legacy-adapter",
        session_id="sync-relay",
        now=_NOW,
    )

    assert result.applied == 1
    assert result.wrote is False
    assert result.note == "broker-committed"
    assert fake.packets[0].intent["kind"] == "task.claim"
    assert fake.tasks["T-1"]["status"] == "dispatched"
    assert board.read_bytes() == before
    assert not _archive(board).exists()


def test_sync_fails_closed_on_unsupported_remove_without_writing(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    before = board.read_bytes()
    fake = _fake_for_board(board)
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)
    desired = load_limen_file(board)
    desired.tasks = desired.tasks[1:]

    with pytest.raises(RuntimeError, match="no authenticated remote compatibility transition"):
        apply_limen_file_sync(
            board,
            desired,
            agent="legacy-adapter",
            session_id="sync-remove",
        )

    assert fake.packets == []
    assert board.read_bytes() == before


def test_drain_archives_only_broker_acknowledged_ticket(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    before = board.read_bytes()
    fake = _fake_for_board(board)
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)
    acknowledged = _ticket(
        INTENT_STATUS,
        task_id="T-1",
        patch={"status": "dispatched"},
        log={"status": "dispatched", "output": "claimed"},
        ticket_id="acknowledged",
    )
    unsupported = _ticket(
        INTENT_META,
        patch={"portal": {"budget": "invalid"}},
        ticket_id="unsupported",
    )
    submit_ticket(board, acknowledged)
    submit_ticket(board, unsupported)

    result = drain_once(board)

    assert (result.applied, result.rejected, result.wrote) == (1, 1, False)
    assert (_archive(board) / "acknowledged.json").exists()
    assert not (_archive(board) / "unsupported.json").exists()
    assert (_rejected(board) / "unsupported.json").exists()
    assert pending_count(board) == 0
    assert fake.tasks["T-1"]["status"] == "dispatched"
    assert board.read_bytes() == before


def test_equivalent_tickets_share_a_deterministic_remote_work_key(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    fake = _fake_for_board(board)
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)
    first = _ticket(
        INTENT_STATUS,
        task_id="T-1",
        patch={"status": "dispatched"},
        log={"status": "dispatched", "output": "claimed"},
        ticket_id="decomposition-a",
    )
    second = first.model_copy(update={"ticket_id": "decomposition-b"})
    base = dict(fake.tasks["T-1"])

    tabularius._relay_ticket(first, base, client=fake)
    tabularius._relay_ticket(second, base, client=fake)

    assert fake.packets[0].work_id != fake.packets[1].work_id
    assert fake.packets[0].work_key == fake.packets[1].work_key


def test_drain_defers_all_tickets_when_broker_is_unavailable(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    before = board.read_bytes()
    ticket = _ticket(
        INTENT_STATUS,
        task_id="T-1",
        patch={"status": "dispatched"},
        log={"status": "dispatched"},
        ticket_id="waiting",
    )
    submit_ticket(board, ticket)

    def unavailable():
        raise BrokerUnavailable("test broker unavailable")

    monkeypatch.setattr(tabularius, "client_from_env", unavailable)
    result = drain_once(board)

    assert result.deferred is True
    assert result.applied == 0
    assert result.rejected == 0
    assert result.wrote is False
    assert pending_count(board) == 1
    assert (_inbox(board) / "waiting.json").exists()
    assert not _archive(board).exists()
    assert not list(_rejected(board).glob("*.json"))
    assert board.read_bytes() == before


def test_local_retry_replays_committed_full_projection_after_cache_write_crash(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    ticket = _ticket(
        INTENT_STATUS,
        task_id="T-1",
        patch={"status": "dispatched"},
        log={"status": "dispatched", "output": "claimed once"},
        ticket_id="crash-retry",
    )
    submit_ticket(board, ticket)
    real_save = tabularius.save_local_conduct_projection
    attempts = 0

    def fail_first_cache_write(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("simulated post-commit cache crash")
        return real_save(*args, **kwargs)

    monkeypatch.setattr(tabularius, "save_local_conduct_projection", fail_first_cache_write)
    first = drain_once(board)

    assert first.deferred is True
    assert first.applied == 0
    assert pending_count(board) == 1
    assert load_limen_file(board).tasks[1].status == "open"

    second = drain_once(board)
    projected = load_limen_file(board)
    task = projected.tasks[1]

    assert second.deferred is False
    assert second.applied == 1
    assert pending_count(board) == 0
    assert task.status == "dispatched"
    assert projected.portal.budget.track.spent == task.budget_cost
    assert sum(bool(entry.conduct_event_id) for entry in task.dispatch_log) == 1
    assert attempts == 2


def test_mid_drain_outage_archives_acknowledged_prefix_and_leaves_rest_pending(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    before = board.read_bytes()
    fake = _fake_for_board(board, fail_after=1)
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)
    first = _ticket(
        INTENT_STATUS,
        task_id="T-1",
        patch={"status": "dispatched"},
        log={"status": "dispatched"},
        ticket_id="01-first",
    )
    second = _ticket(
        INTENT_STATUS,
        task_id="T-2",
        patch={"status": "dispatched"},
        log={"status": "dispatched"},
        ticket_id="02-second",
    )
    submit_ticket(board, first)
    submit_ticket(board, second)

    result = drain_once(board)

    assert result.deferred is True
    assert result.applied == 1
    assert result.rejected == 0
    assert (_archive(board) / "01-first.json").exists()
    assert (_inbox(board) / "02-second.json").exists()
    assert pending_count(board) == 1
    assert board.read_bytes() == before


def test_unparseable_ticket_is_quarantined_without_contacting_broker(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    before = board.read_bytes()
    inbox = _inbox(board)
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "garbage.json").write_text("{ this is not valid json ")
    fake = _fake_for_board(board)
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)

    result = drain_once(board)

    assert result.rejected == 1
    assert result.applied == 0
    assert fake.packets == []
    assert (_rejected(board) / "garbage.json").exists()
    assert board.read_bytes() == before


def test_held_queue_lock_defers_without_contacting_broker(tmp_path, monkeypatch):
    board = _seed_board(tmp_path)
    before = board.read_bytes()
    submit_ticket(
        board,
        _ticket(
            INTENT_STATUS,
            task_id="T-1",
            patch={"status": "dispatched"},
            log={"status": "dispatched"},
        ),
    )

    def unexpected_client():
        raise AssertionError("held-lock drain must not contact broker")

    monkeypatch.setattr(tabularius, "client_from_env", unexpected_client)
    with queue_lock(board) as locked:
        assert locked
        result = drain_once(board, lock_timeout=1)

    assert result.deferred is True
    assert result.wrote is False
    assert pending_count(board) == 1
    assert board.read_bytes() == before


def test_preserve_projection_is_retired_noop(tmp_path):
    board = _seed_board(tmp_path)
    before = board.read_bytes()

    result = preserve_board_projection(board)

    assert result.pushed is False
    assert result.changed is False
    assert result.skipped is True
    assert "remote" in result.reason or "retired" in result.reason
    assert board.read_bytes() == before


def test_reducer_preserves_successor_terminal_hold():
    held = _task(
        "T-held",
        status="failed",
        labels=["workstream:successor-required"],
    )
    tasks: OrderedDict[str, dict[str, Any]] = OrderedDict([("T-held", held)])
    meta: dict[str, Any] = {}

    forbidden = [
        _ticket(INTENT_STATUS, task_id="T-held", patch={"status": "open"}),
        _ticket(INTENT_UPSERT, task_id="T-held", patch={"status": "done", "labels": []}),
        _ticket(INTENT_REMOVE, task_id="T-held"),
    ]
    for ticket in forbidden:
        with pytest.raises(ValueError, match="successor-required"):
            _apply(ticket, tasks, meta)

    completion = _ticket(
        INTENT_STATUS,
        task_id="T-held",
        patch={"status": "done"},
        log={"status": "done", "output": "terminal receipt"},
    )
    _apply(completion, tasks, meta)

    assert tasks["T-held"]["status"] == "done"
    assert tasks["T-held"]["labels"] == ["workstream:successor-required"]
