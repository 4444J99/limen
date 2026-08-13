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
from limen.conduct.broker import ConductBroker, ConductConflict, TaskAlreadyHomed
from limen.conduct.client import BrokerUnavailable
from limen.conduct.models import AgentIdentityV1, ConductorSessionV1
from limen.conduct.store import SQLiteStateStore
from limen.io import load_limen_file, queue_lock, save_limen_file
from limen.models import DispatchLogEntry, LimenFile
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
ROOT = Path(__file__).resolve().parents[2]


def _task(tid: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": tid,
        "title": f"task {tid}",
        "repo": "organvm/limen",
        "target_agent": "codex",
        "created": "2026-07-01",
        "predicate": f"pytest -q -k {tid}",
        "receipt_target": f"github:organvm/limen:pull-request:{tid}",
        "origin": "human_prompt",
        "horizon": "present",
        "value_case": f"Apply the bounded TABVLARIVS task {tid}",
        "owner_surface": "organvm/limen",
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
        bound_agent: str | None = None,
        bound_surface: str | None = None,
        conflict_on: set[str] | None = None,
    ):
        self.tasks = {str(task["id"]): dict(task) for task in tasks}
        self.fail_after = fail_after
        self.conflict_on = set(conflict_on or ())
        self.unavailable_on_register = unavailable_on_register
        self.bound_agent = bound_agent
        self.bound_surface = bound_surface
        self.registered: list[Any] = []
        self.packets: list[Any] = []

    def register(self, session):
        if self.unavailable_on_register:
            raise BrokerUnavailable("test broker unavailable")
        self.registered.append(session)
        registered = session.model_dump(mode="json")
        if self.bound_agent is not None:
            registered["identity"]["agent"] = self.bound_agent
        if self.bound_surface is not None:
            registered["identity"]["surface"] = self.bound_surface
        return {"session": registered}

    def submit(self, packet):
        if self.fail_after is not None and len(self.packets) >= self.fail_after:
            raise BrokerUnavailable("test broker interrupted")
        intent = dict(packet.intent)
        task_id = str(intent["task_id"])
        if task_id in self.conflict_on:
            # The deployed Worker's answer, verbatim: HTTP 409 whose detail is keeper prose.
            # Callers must classify on the status, never on the sentence.
            raise ConductConflict(
                f'conduct broker rejected request (409): {{"detail": "task {task_id} already exists"}}',
                status=409,
            )
        self.packets.append(packet)
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
    ununderwritten = _task("T-NEW", status="open")
    ununderwritten.pop("value_case")
    with pytest.raises(ValueError, match="task-not-underwritten:value_case"):
        submit_task_upsert(board, ununderwritten, agent="codex")
    with pytest.raises(ValueError, match="receipt credit requires an evidence-bound status transition"):
        submit_task_upsert(
            board,
            _task("T-CREDIT", status="done", receipt_verified=True),
            agent="codex",
        )
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


def test_pure_reducer_requires_and_preserves_completion_evidence():
    tasks: OrderedDict[str, dict[str, Any]] = OrderedDict([("T-CREDIT", _task("T-CREDIT", status="in_progress"))])
    meta: dict[str, Any] = {"version": "1.0", "portal": None}
    before = tasks.copy()
    missing = _ticket(
        INTENT_STATUS,
        task_id="T-CREDIT",
        patch={"status": "done", "receipt_verified": True},
        log={"status": "done"},
    )

    with pytest.raises(ValueError, match="completion-not-verified:predicate"):
        _apply(missing, tasks, meta)
    assert tasks == before

    digest = "a" * 64
    receipt_target = tasks["T-CREDIT"]["receipt_target"]
    completion = _ticket(
        INTENT_STATUS,
        task_id="T-CREDIT",
        patch={"status": "done", "receipt_verified": True},
        log={
            "status": "done",
            "predicate_exit_code": 0,
            "remote_receipt": receipt_target,
            "verification_context_digest": digest,
        },
    )

    _apply(completion, tasks, meta)

    assert tasks["T-CREDIT"]["receipt_verified"] is True
    assert tasks["T-CREDIT"]["dispatch_log"][-1]["predicate_exit_code"] == 0
    assert tasks["T-CREDIT"]["dispatch_log"][-1]["remote_receipt"] == receipt_target
    assert tasks["T-CREDIT"]["dispatch_log"][-1]["verification_context_digest"] == digest


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
    desired.tasks[1].dispatch_log.append(
        DispatchLogEntry(
            timestamp=_NOW,
            agent="codex",
            session_id="claim-session",
            status="dispatched",
        )
    )

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
    assert fake.packets[0].initiator.agent == "legacy-adapter"
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
    assert result.projected_tasks["T-1"]["status"] == "dispatched"
    assert result.projected_tasks["T-1"] == fake.tasks["T-1"]
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


def test_remote_registration_identity_is_bound_into_compatibility_packet():
    fake = FakeConductClient(
        [],
        bound_agent="codex",
        bound_surface="credential-principal",
    )
    ticket = _ticket(
        INTENT_UPSERT,
        task_id="T-BOUND",
        patch=_task("T-BOUND", status="open"),
        ticket_id="principal-bound",
    )

    tabularius._relay_ticket(ticket, None, client=fake)

    assert fake.packets[0].conductor.agent == "codex"
    assert fake.packets[0].conductor.surface == "credential-principal"
    assert fake.packets[0].initiator == fake.packets[0].conductor


def test_the_healthy_path_keeps_the_stable_relay_literal():
    """The recorded ``session_id`` is an observable identifier — the keeper stamps it into every
    projection event, and harvest reads it. It must NOT change when nothing is wrong."""
    fake = FakeConductClient([])
    ticket = _ticket(
        INTENT_UPSERT,
        task_id="T-STABLE",
        patch=_task("T-STABLE", status="open"),
        ticket_id="stable-relay",
    )

    tabularius._relay_ticket(ticket, None, client=fake)

    assert fake.registered[0].session_id == f"{ticket.agent}-{ticket.session_id}"
    assert len(fake.registered) == 1


def test_a_frozen_relay_literal_falls_back_to_a_keyed_id_and_still_relays():
    """A FIXED relay session id is claimable exactly once, and the loser is refused forever.

    ``register()`` binds agent/surface/session_id from the principal and then rejects any
    re-registration whose whole identity object differs — so post-binding the only fields that can
    still differ are client-declared, and a drift in them is a permanent 409. That froze
    ``dispatch-serial-results`` from 2026-07-19: jules sessions launched, receipts were never
    recorded, and the throughput governor read 0 dispatches (#1995). A refused literal must fall
    back to an id this client can own, rather than killing the relay.
    """
    refused: list[str] = []
    ticket = _ticket(
        INTENT_UPSERT,
        task_id="T-FROZEN",
        patch=_task("T-FROZEN", status="open"),
        ticket_id="frozen-relay",
    )
    frozen_literal = f"{ticket.agent}-{ticket.session_id}"

    class FrozenLiteralClient(FakeConductClient):
        def register(self, session):
            if session.session_id == frozen_literal:
                refused.append(session.session_id)
                raise ConductConflict(
                    'conduct broker rejected request (409): {"detail": '
                    '"session_id is already registered to another identity"}',
                    status=409,
                )
            return super().register(session)

    fake = FrozenLiteralClient([])

    tabularius._relay_ticket(ticket, None, client=fake)

    literal = f"{ticket.agent}-{ticket.session_id}"
    assert refused == [literal]  # the literal was tried first, and only once
    assert fake.registered[0].session_id.startswith(f"{literal}-")
    assert fake.registered[0].identity.session_id == fake.registered[0].session_id
    assert fake.packets, "the ticket must still relay after the fallback"


def test_a_non_conflict_registration_failure_is_never_retried():
    """Only a conflict means "that literal is not mine". Anything else must surface unchanged."""

    class BrokenClient(FakeConductClient):
        def register(self, session):
            raise BrokerUnavailable("keeper down")

    fake = BrokenClient([])
    ticket = _ticket(
        INTENT_UPSERT,
        task_id="T-DOWN",
        patch=_task("T-DOWN", status="open"),
        ticket_id="down-relay",
    )

    with pytest.raises(BrokerUnavailable):
        tabularius._relay_ticket(ticket, None, client=fake)


def test_relay_identity_key_tracks_only_the_fields_register_leaves_unbound():
    """The key must cover exactly what the keeper compares verbatim — no more, no less.

    Principal-bound fields are normalized on both sides, so keying them would split one relay
    session into many for no reason; client-declared fields are compared as sent, so NOT keying
    them re-opens the freeze.
    """
    base = AgentIdentityV1(
        agent="dispatch",
        surface="tabularius-relay",
        session_id="dispatch-serial-results",
        provider_identity="limen-cli",
    )
    key = tabularius._relay_identity_key(base)

    assert tabularius._relay_identity_key(base.model_copy(update={"agent": "codex"})) == key
    assert tabularius._relay_identity_key(base.model_copy(update={"surface": "other-surface"})) == key
    assert tabularius._relay_identity_key(base.model_copy(update={"session_id": "other-session"})) == key

    assert tabularius._relay_identity_key(base.model_copy(update={"provider_identity": "limen-cli-2"})) != key
    assert tabularius._relay_identity_key(base.model_copy(update={"native_run_id": "run-7"})) != key


def test_fixed_relay_session_id_freezes_on_provider_drift_but_a_keyed_one_does_not(tmp_path):
    """The regression, against the real broker: same principal, drifted provider identity."""
    broker = ConductBroker(store=SQLiteStateStore(tmp_path / "conduct.db"))
    now = datetime.now(timezone.utc)

    def session(session_id: str, provider: str) -> ConductorSessionV1:
        return ConductorSessionV1(
            session_id=session_id,
            identity=AgentIdentityV1(
                agent="dispatch",
                surface="tabularius-relay",
                session_id=session_id,
                provider_identity=provider,
            ),
            origin="relay",
            capabilities=frozenset({"task-submit"}),
            transport="ianva",
            harvest_method="receipt",
            registered_at=now,
            heartbeat_at=now,
        )

    broker.register(session("dispatch-serial-results", "limen-cli"))
    with pytest.raises(ConductConflict):
        broker.register(session("dispatch-serial-results", "limen-cli-2"))

    def keyed(provider: str) -> ConductorSessionV1:
        identity = session("dispatch-serial-results", provider).identity
        return session(f"dispatch-serial-results-{tabularius._relay_identity_key(identity)}", provider)

    broker.register(keyed("limen-cli"))
    broker.register(keyed("limen-cli-2"))
    broker.register(keyed("limen-cli"))


def test_canonical_task_projection_uses_rest_ref_and_sha_pinned_raw_blob(monkeypatch):
    head = "f" * 40
    document = tabularius.yaml.safe_dump(
        {
            "version": "1.0",
            "tasks": [
                _task("T-REMOTE", status="dispatched"),
                _task("T-AFTER", status="open"),
            ],
        },
        sort_keys=False,
    ).encode()
    requested = []

    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return self.body

    def fake_urlopen(request, *, timeout):
        requested.append((request.full_url, timeout))
        if tabularius.urllib.parse.urlsplit(request.full_url).hostname == "api.github.com":
            return Response(f'{{"object":{{"sha":"{head}"}}}}'.encode())
        return Response(document)

    monkeypatch.setattr(tabularius.urllib.request, "urlopen", fake_urlopen)

    projection = tabularius.fetch_canonical_task_projection("T-REMOTE", timeout=17)

    assert projection.repository == "organvm/limen"
    assert projection.branch == "tabularius/board-projection"
    assert projection.head_sha == head
    assert projection.task is not None
    assert projection.task.id == "T-REMOTE"
    assert projection.task.status == "dispatched"
    assert requested == [
        (
            "https://api.github.com/repos/organvm/limen/git/ref/heads/tabularius%2Fboard-projection",
            17,
        ),
        (f"https://raw.githubusercontent.com/organvm/limen/{head}/tasks.yaml", 17),
    ]


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
        agent="codex",
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


def test_canonical_revision_matches_worker_millisecond_canon() -> None:
    """Python renders revisions in the keeper's JS toISOString canon (#1408 family).

    canonicalRevision in projection.js always emits millisecond precision, so a
    microsecond render from a Python producer can never CAS-match the keeper —
    every status transition on a Python-stamped task 409s with
    "exact revision moved". Vectors below are `new Date(v).toISOString()` output.
    """
    canon = tabularius._canonical_revision
    assert canon({"updated": "2026-07-22T19:28:29.695237Z"}) == "2026-07-22T19:28:29.695Z"
    assert canon({"updated": "2026-07-22T19:28:29Z"}) == "2026-07-22T19:28:29.000Z"
    assert canon({"updated": "2026-07-22T19:28:29.695Z"}) == "2026-07-22T19:28:29.695Z"
    assert canon({"dispatch_log": [{"timestamp": "2026-07-23T10:30:04.446Z"}]}) == "2026-07-23T10:30:04.446Z"
    assert (
        canon({"updated": datetime(2026, 7, 22, 19, 28, 29, 695237, tzinfo=timezone.utc)}) == "2026-07-22T19:28:29.695Z"
    )
    # Non-datetime revisions pass through untouched, exactly like the worker.
    assert canon({"created": "2026-07-23"}) == "2026-07-23"
    assert canon({"status": "open"}) == "open"


# ── already-homed tolerance (the local projection LAGS the keeper) ────────────
#
# A caller derives "this task is absent" from tasks.yaml, which republishes on its own
# cadence. When the keeper already holds the task, the create is refused — benignly. Three
# keepers word that refusal three ways (the Worker's 409 "already exists", the in-process
# compat path's "already exists", the ticket path's "is no longer absent"), so tolerance is
# keyed on the STATUS/marker and attributed to the in-flight ticket, never parsed out of
# the sentence.


def test_sync_tolerates_an_opted_in_already_homed_create_and_keeps_relaying(tmp_path, monkeypatch):
    board = _seed_board(tmp_path, n=1)
    fake = _fake_for_board(board, conflict_on={"T-homed"})
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)
    desired = load_limen_file(board)
    desired.tasks.append(_board([_task("T-homed", status="open")]).tasks[0])
    desired.tasks.append(_board([_task("T-fresh", status="open")]).tasks[0])

    result = apply_limen_file_sync(
        board,
        desired,
        agent="legacy-adapter",
        session_id="sync-relay",
        tolerate_already_homed={"T-homed", "T-fresh"},
    )

    assert result.already_homed == ["T-homed"]
    # The conflict did not hold the genuinely-new task hostage.
    assert "T-fresh" in fake.tasks
    assert result.applied == 1


def test_sync_refuses_a_conflict_for_a_task_the_caller_did_not_opt_in(tmp_path, monkeypatch):
    board = _seed_board(tmp_path, n=1)
    fake = _fake_for_board(board, conflict_on={"T-homed"})
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)
    desired = load_limen_file(board)
    desired.tasks.append(_board([_task("T-homed", status="open")]).tasks[0])

    with pytest.raises(ConductConflict):
        apply_limen_file_sync(
            board,
            desired,
            agent="legacy-adapter",
            session_id="sync-relay",
            tolerate_already_homed={"T-something-else"},
        )


def test_sync_without_the_opt_in_still_fails_closed_on_a_conflict(tmp_path, monkeypatch):
    board = _seed_board(tmp_path, n=1)
    fake = _fake_for_board(board, conflict_on={"T-homed"})
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)
    desired = load_limen_file(board)
    desired.tasks.append(_board([_task("T-homed", status="open")]).tasks[0])

    with pytest.raises(ConductConflict):
        apply_limen_file_sync(board, desired, agent="legacy-adapter", session_id="sync-relay")


def test_already_homed_tolerance_is_keyed_on_status_not_on_keeper_prose(tmp_path, monkeypatch):
    """Reword every keeper's detail text: tolerance must survive, because it reads the code."""
    board = _seed_board(tmp_path, n=1)
    fake = _fake_for_board(board)
    reworded = []

    def submit(packet):
        task_id = str(dict(packet.intent)["task_id"])
        if task_id == "T-homed":
            reworded.append(task_id)
            raise ConductConflict("HTTP 409 Conflict", status=409)
        return FakeConductClient.submit(fake, packet)

    fake.submit = submit
    monkeypatch.setattr(tabularius, "client_from_env", lambda: fake)
    desired = load_limen_file(board)
    desired.tasks.append(_board([_task("T-homed", status="open")]).tasks[0])

    result = apply_limen_file_sync(
        board,
        desired,
        agent="legacy-adapter",
        session_id="sync-relay",
        tolerate_already_homed={"T-homed"},
    )

    assert reworded == ["T-homed"]
    assert result.already_homed == ["T-homed"]


def test_local_keepers_own_wording_is_tolerated_too(tmp_path):
    """The in-tree LocalConductClient says 'is no longer absent', not 'already exists'.

    Regression: keying on the remote keeper's sentence made this path fatal, and the
    genuinely-new atom in the same batch was lost with it.
    """
    board = _seed_board(tmp_path, n=1)
    desired = load_limen_file(board)
    desired.tasks.append(_board([_task("T-homed", status="open")]).tasks[0])
    # First pass homes T-homed on the real local keeper.
    apply_limen_file_sync(board, desired, agent="legacy-adapter", session_id="first")

    # Now rewind the local projection so it LAGS the keeper — exactly what the beat sees.
    save_limen_file(board, _board([_task("T-0", status="open")]))
    lagging = load_limen_file(board)
    lagging.tasks.append(_board([_task("T-homed", status="open")]).tasks[0])
    lagging.tasks.append(_board([_task("T-fresh", status="open")]).tasks[0])

    result = apply_limen_file_sync(
        board,
        lagging,
        agent="legacy-adapter",
        session_id="second",
        tolerate_already_homed={"T-homed", "T-fresh"},
    )

    assert result.already_homed == ["T-homed"]
    assert "T-fresh" in result.projected_tasks


def test_already_homed_marker_carries_its_task_identity():
    """The signal a caller needs is structural: which task, and 'this is the benign one'."""
    exc = TaskAlreadyHomed("task T-1 already exists", task_id="T-1")
    assert exc.task_id == "T-1"
    assert exc.already_homed is True
    assert exc.status == 409
    # Still a ValueError: every raise site it replaced was one, and callers catch that type.
    assert isinstance(exc, ValueError)


def test_a_non_absent_precondition_failure_is_never_tolerated():
    """Tolerance covers creates only. A failed update precondition means state moved."""
    ticket = _ticket(INTENT_UPSERT, task_id="T-1", precondition={"task_sha256": "deadbeef"})
    exc = TaskAlreadyHomed("task precondition failed: T-1 is no longer absent", task_id="T-1")
    assert tabularius._is_tolerated_already_homed(exc, ticket, {"T-1"}) is False

    create = _ticket(INTENT_UPSERT, task_id="T-1", precondition={"absent": True})
    assert tabularius._is_tolerated_already_homed(exc, create, {"T-1"}) is True
    assert tabularius._is_tolerated_already_homed(exc, create, set()) is False
    assert tabularius._is_tolerated_already_homed(RuntimeError("boom"), create, {"T-1"}) is False


def test_every_local_refusal_of_a_settled_create_reaches_the_classifier():
    """Completeness, not behaviour: are there only three sites, and do all three answer alike?

    The earlier tests prove the sites we know about behave. This one exists because the bug
    being guarded was a site nobody had enumerated — the local adapter's own wording, which
    the previous prose regex did not match, so a genuinely-new atom was dropped on the floor.

    Each of the three in-process paths is DRIVEN here (not asserted about), and the exception
    it actually raises is fed to the real classifier. A fourth path added later that refuses a
    settled create with a bare ``ValueError`` fails this test, because the classifier will
    reject it — which is the whole point.
    """
    create = _ticket(INTENT_UPSERT, task_id="T-1", precondition={"absent": True})
    settled = _task("T-1", status="open")
    raised: list[Exception] = []

    # Site 1 — the compatibility intent builder, before anything crosses the wire.
    with pytest.raises(TaskAlreadyHomed) as one:
        tabularius._compatibility_intent(create, settled)
    raised.append(one.value)

    # Site 2 — the local projection of a keeper task event, over a board that already holds it.
    event = {
        "task_id": "T-1",
        "intent": {"kind": "task.upsert", "task_id": "T-1", "expected_absent": True, "task": settled},
        "event_id": "conduct:already-homed:local:1",
    }
    with pytest.raises(TaskAlreadyHomed) as two:
        tabularius._project_local_task_event(_board([settled]), event)
    raised.append(two.value)

    # Site 3 — the ticket applier over an in-memory board that already holds the task.
    tasks: OrderedDict[str, dict[str, Any]] = OrderedDict({"T-1": dict(settled)})
    with pytest.raises(TaskAlreadyHomed) as three:
        _apply(create, tasks, {})
    raised.append(three.value)

    assert len(raised) == 3
    for exc in raised:
        assert exc.task_id == "T-1"
        assert exc.status == 409
        assert tabularius._is_tolerated_already_homed(exc, create, {"T-1"}) is True

    # Three sites, three different sentences — which is exactly why nobody reads the sentence.
    assert len({str(exc) for exc in raised}) > 1


def test_the_worker_and_the_python_keepers_agree_on_the_already_homed_status():
    """Cross-language parity: one condition, three keepers, one number.

    The whole tolerance path rests on 409 being what a keeper answers when a create loses to
    an already-homed task — and the production keeper is JavaScript, so no Python test touches
    it. This reads the Worker's own source and holds it to the number Python declares.

    It deliberately asserts on the STATUS ARGUMENT, not on the message: the two implementations
    are free to word the refusal differently (they do), and must not be free to number it
    differently.
    """
    projection = ROOT / "web" / "worker" / "src" / "conduct" / "projection.js"
    source = projection.read_text()
    absent_branch = source.split("if (intent.expected_absent && existing)", 1)
    assert len(absent_branch) == 2, (
        f"{projection} no longer refuses an expected_absent create over an existing task; "
        "the Python already-homed tolerance has nothing to key on"
    )
    # End at the call's own `);` — a `}` boundary would land inside the `${taskId}` literal.
    throw = absent_branch[1].split(");", 1)[0]
    assert f", {TaskAlreadyHomed.status}" in throw, (
        f"the Worker's already-homed refusal must carry {TaskAlreadyHomed.status}, "
        f"matching TaskAlreadyHomed.status; found: {throw.strip()}"
    )
