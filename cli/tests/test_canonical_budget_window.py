"""Refunds cannot spend credit from a different canonical UTC budget window."""

import pytest

from limen.tabularius import _local_budget_refund, _project_local_task_event
from test_canonical_inventory_identity import event
from test_tabularius import _board, _task


def request(task_id, kind, prior_status, timestamp, event_id, agent="codex", **patch):
    result = event(kind, patch, task_id=task_id, agent=agent, status=prior_status, event_id=event_id)
    result["timestamp"] = timestamp
    return result


def apply(board, *args, **kwargs):
    return _project_local_task_event(board, request(*args, **kwargs))[0]


@pytest.mark.parametrize("new_agent", ["codex", "jules"])
@pytest.mark.parametrize("metadata", [False, True])
def test_old_window_refund_preserves_current_window_claim(new_agent, metadata):
    board = _board(
        [
            _task("OLD", status="open", budget_cost=2),
            _task("NEW", status="open", budget_cost=5, target_agent=new_agent),
        ]
    )
    board.portal.budget.daily = 100
    board.portal.budget.per_agent = {"codex": 100, "jules": 100}
    board = apply(board, "OLD", "task.claim", "open", "2026-09-08T23:59:00Z", "old-claim", status="dispatched")
    board = apply(
        board, "NEW", "task.claim", "open", "2026-09-09T00:01:00Z", "new-claim", agent=new_agent, status="dispatched"
    )
    if metadata:
        board = apply(
            board, "OLD", "task.mutate", "dispatched", "2026-09-09T00:02:00Z", "metadata", title="Unrelated update"
        )
    expected = board.portal.budget.track.model_dump()
    board = apply(board, "OLD", "task.status", "dispatched", "2026-09-09T00:03:00Z", "old-refund", status="open")
    assert board.tasks[0].status == "open"
    assert board.portal.budget.track.model_dump() == expected
    assert board.portal.budget.track.spent == 5
    assert board.portal.budget.track.per_agent[new_agent] == 5
    board = apply(
        board, "NEW", "task.status", "dispatched", "2026-09-09T00:04:00Z", "new-refund", agent=new_agent, status="open"
    )
    assert board.portal.budget.track.spent == 0
    assert board.portal.budget.track.per_agent[new_agent] == 0


@pytest.mark.parametrize("refund_time", ["2026-09-08T23:59:59Z", "2026-09-09T00:00:00Z"])
def test_same_window_refund_and_first_rollover_leave_no_spend(refund_time):
    board = _board([_task("OLD", status="open", budget_cost=2)])
    board = apply(board, "OLD", "task.claim", "open", "2026-09-08T23:59:00Z", "claim", status="dispatched")
    board = apply(board, "OLD", "task.status", "dispatched", refund_time, "refund", status="open")
    assert board.portal.budget.track.date == refund_time[:10]
    assert board.portal.budget.track.spent == 0
    assert board.portal.budget.track.per_agent.get("codex", 0) == 0


@pytest.mark.parametrize("timestamp", [None, "unknown", "2026-09-08T12:00:00", "2026-02-30T12:00:00Z"])
def test_unknown_canonical_claim_window_fails_closed(timestamp):
    board = _board([_task("OLD", status="open", budget_cost=2)])
    board = apply(board, "OLD", "task.claim", "open", "2026-09-08T23:59:00Z", "claim", status="dispatched")
    raw = board.model_dump(mode="json")
    raw["tasks"][0]["dispatch_log"][0]["timestamp"] = timestamp
    before = board.portal.budget.track.model_dump()
    with pytest.raises(ValueError, match="canonical budget refund window"):
        _local_budget_refund(raw, raw["tasks"][0], {"timestamp": "2026-09-08T23:59:59Z"})
    assert raw["portal"]["budget"]["track"] == before


def test_postlaunch_reroute_then_new_day_claim_refunds_only_new_attempt():
    board = _board([_task("OLD", status="open", budget_cost=2)])
    first = request("OLD", "task.claim", "open", "2026-09-08T23:58:00Z", "first", status="dispatched")
    first["intent"]["log"].update(session_id="d" * 64, execution_contract_hash="e" * 64)
    board, _ = _project_local_task_event(board, first)
    reroute = request("OLD", "task.status", "dispatched", "2026-09-08T23:59:00Z", "reroute", status="open")
    reroute["intent"]["log"].update(
        lifecycle_repair="provider-reroute",
        execution_started=True,
        execution_reservation_id="d" * 64,
        execution_contract_hash="e" * 64,
    )
    board, _ = _project_local_task_event(board, reroute)
    assert board.portal.budget.track.spent == 2
    board = apply(board, "OLD", "task.claim", "open", "2026-09-09T00:01:00Z", "second", status="dispatched")
    assert board.portal.budget.track.spent == 2
    board = apply(board, "OLD", "task.status", "dispatched", "2026-09-09T00:02:00Z", "refund", status="open")
    assert board.portal.budget.track.spent == 0
    assert board.portal.budget.track.per_agent["codex"] == 0
