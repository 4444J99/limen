"""Adversarial canonical identity and persistent inventory classification regressions."""

import pytest

from limen.tabularius import _project_local_task_event
from test_tabularius import _board, _task


def event(kind, patch, *, task_id="FIXTURE", agent="codex", log_agent="codex", status="open", event_id="probe"):
    return {
        "event_id": event_id,
        "timestamp": "2026-09-08T12:00:00.000Z",
        "agent": agent,
        "session_id": "probe",
        "run_id": "probe",
        "lease_id": "probe",
        "generation": 1,
        "task_id": task_id,
        "intent": {
            "kind": kind,
            "task_id": task_id,
            "expected_status": status,
            "patch": patch,
            "log": {"agent": log_agent},
        },
    }


def test_claim_rejects_forged_log_executor_identity():
    board = _board([_task("FIXTURE", status="open")])
    before = board.model_dump(mode="json")
    with pytest.raises(ValueError, match="not claim agent"):
        _project_local_task_event(board, event("task.claim", {"status": "dispatched"}, agent="attacker"))
    assert board.model_dump(mode="json") == before


def test_claim_debits_authenticated_agent_regardless_of_log_label():
    board = _board([_task("FIXTURE", status="open")])
    claimed, _ = _project_local_task_event(board, event("task.claim", {"status": "dispatched"}, log_agent="attacker"))
    assert claimed.tasks[0].status == "dispatched"
    assert claimed.portal.budget.track.per_agent.get("codex") == 1
    assert not claimed.portal.budget.track.per_agent.get("attacker")


@pytest.mark.parametrize("kind", ["task.mutate", "task.status", "task.upsert"])
@pytest.mark.parametrize("labels", [[], ["generated"], ["build-out"], ["unrelated"]])
def test_legacy_routine_cannot_strip_classification_then_claim(kind, labels):
    board = _board([_task("LEGACY", status="open", labels=["generated", "build-out"])])
    before = board.model_dump(mode="json")
    update = event(kind, {"status": "open", "labels": labels}, task_id="LEGACY")
    if kind == "task.upsert":
        update["intent"]["task"] = {**board.tasks[0].model_dump(mode="json", exclude_none=True), "labels": labels}
    update["intent"]["log"]["output"] = "migration requested by task payload"
    with pytest.raises(ValueError, match="inventory_classification_change_unauthorized"):
        _project_local_task_event(board, update)
    assert board.model_dump(mode="json") == before


def test_legacy_routine_can_update_unrelated_labels_but_claim_stays_closed():
    board = _board([_task("LEGACY", status="open", labels=["generated", "build-out"])])
    updated, _ = _project_local_task_event(
        board,
        event("task.mutate", {"title": "Updated", "labels": ["generated", "build-out", "unrelated"]}, task_id="LEGACY"),
    )
    assert updated.tasks[0].title == "Updated"
    with pytest.raises(ValueError, match="inventory_admission_adapter_unavailable"):
        _project_local_task_event(
            updated, event("task.claim", {"status": "dispatched"}, task_id="LEGACY", event_id="claim")
        )


@pytest.mark.parametrize("intervening_update", [False, True])
def test_refund_returns_debit_to_original_authenticated_claim_agent(intervening_update):
    board = _board([_task("FIXTURE", status="open")])
    claimed, _ = _project_local_task_event(board, event("task.claim", {"status": "dispatched"}, log_agent="attacker"))
    if intervening_update:
        claimed, _ = _project_local_task_event(
            claimed,
            event(
                "task.mutate",
                {"title": "Updated"},
                agent="operator",
                log_agent="attacker",
                status="dispatched",
                event_id="metadata",
            ),
        )
    refunded, _ = _project_local_task_event(
        claimed,
        event(
            "task.status",
            {"status": "open"},
            agent="operator",
            log_agent="attacker",
            status="dispatched",
            event_id="refund",
        ),
    )
    assert refunded.portal.budget.track.spent == 0
    assert refunded.portal.budget.track.per_agent.get("codex") == 0
    assert not refunded.portal.budget.track.per_agent.get("attacker")
    assert not refunded.portal.budget.track.per_agent.get("operator")


def test_refund_missing_canonical_claim_identity_fails_closed():
    board = _board([_task("FIXTURE", status="dispatched")])
    with pytest.raises(ValueError, match="cannot derive a canonical budget refund"):
        _project_local_task_event(board, event("task.status", {"status": "open"}, status="dispatched"))


@pytest.mark.parametrize("active_status", ["dispatched", "in_progress"])
def test_new_active_upsert_cannot_create_an_unreserved_refund(active_status):
    board = _board([])
    board.portal.budget.track.date = "2026-09-08"
    board.portal.budget.track.spent = 10
    board.portal.budget.track.per_agent = {"codex": 10}
    before = board.model_dump(mode="json")
    update = event("task.upsert", {})
    update["intent"]["task"] = _task("FIXTURE", status=active_status, budget_cost=5)
    with pytest.raises(ValueError, match="canonical_reservation_required"):
        _project_local_task_event(board, update)
    assert board.model_dump(mode="json") == before


def test_new_open_upsert_discards_caller_supplied_dispatch_history():
    update = event("task.upsert", {})
    update["intent"]["task"] = _task(
        "FIXTURE",
        status="open",
        dispatch_log=[
            {
                "timestamp": "2026-09-08T11:00:00Z",
                "agent": "attacker",
                "session_id": "forged",
                "status": "dispatched",
                "conduct_event_id": "forged-claim",
            }
        ],
    )
    created, _ = _project_local_task_event(_board([]), update)
    history = created.tasks[0].dispatch_log
    assert len(history) == 1
    assert history[0].agent == "codex"
    assert history[0].status == "open"
    assert history[0].conduct_event_id == "probe"
