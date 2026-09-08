"""A canonical reservation's debit and refund must use the same immutable cost."""

import pytest

from limen.tabularius import _project_local_task_event
from test_canonical_inventory_identity import event
from test_tabularius import _board, _task


def funded_board(cost=2):
    board = _board([_task("FIXTURE", status="open", budget_cost=cost)])
    board.portal.budget.daily = 2000
    board.portal.budget.per_agent = {"codex": 2000, "jules": 2000}
    board.portal.budget.track.date = "2026-09-08"
    board.portal.budget.track.spent = 9
    board.portal.budget.track.per_agent = {"codex": 4, "jules": 5}
    return board


def claim(board):
    request = event("task.claim", {"status": "dispatched"}, event_id="claim")
    request["intent"]["log"].update(session_id="d" * 64, execution_contract_hash="e" * 64)
    return _project_local_task_event(board, request)[0]


def assert_track(board, spent, codex):
    assert board.portal.budget.track.spent == spent
    assert board.portal.budget.track.per_agent == {"codex": codex, "jules": 5}


def assert_rejected_unchanged(board, request):
    before = board.model_dump(mode="json")
    with pytest.raises(ValueError, match="reservation_budget_cost_immutable"):
        _project_local_task_event(board, request)
    assert board.model_dump(mode="json") == before


def test_claim_cannot_inflate_cost_after_debit_before_refund():
    # Review 5144025944: the old projection debited 1, persisted 1000, then
    # refunded 1000 and erased spend belonging to other reservations.
    board = funded_board(1)
    assert_rejected_unchanged(board, event("task.claim", {"status": "dispatched", "budget_cost": 1000}))
    assert_track(board, 9, 4)


@pytest.mark.parametrize("status", ["dispatched", "in_progress"])
@pytest.mark.parametrize("kind", ["task.mutate", "task.status", "task.upsert"])
@pytest.mark.parametrize("cost", [1, 1000])
def test_active_reservation_cannot_change_cost_in_metadata_or_upsert(status, kind, cost):
    board = claim(funded_board())
    if status == "in_progress":
        board, _ = _project_local_task_event(
            board, event("task.status", {"status": status}, status="dispatched", event_id="started")
        )
    request = event(kind, {"status": status, "budget_cost": cost}, status=status, event_id="cost-change")
    if kind == "task.upsert":
        request["intent"]["task"] = {**board.tasks[0].model_dump(mode="json"), "budget_cost": cost}
    assert_rejected_unchanged(board, request)
    assert_track(board, 11, 6)


@pytest.mark.parametrize("status", ["open", "failed"])
def test_settlement_cannot_change_reserved_cost(status):
    board = claim(funded_board())
    request = event("task.status", {"status": status, "budget_cost": 1000}, status="dispatched", event_id="settle")
    if status == "failed":
        request["intent"]["log"].update(
            lifecycle_repair="provider-terminal",
            execution_started=True,
            execution_result_kind="failed",
            execution_reservation_id="d" * 64,
            execution_contract_hash="e" * 64,
        )
    assert_rejected_unchanged(board, request)
    assert_track(board, 11, 6)
    if status == "failed":
        del request["intent"]["patch"]["budget_cost"]
        settled, _ = _project_local_task_event(board, request)
        assert settled.tasks[0].status == "failed"
        assert_track(settled, 11, 6)


@pytest.mark.parametrize("kind", ["task.mutate", "task.upsert"])
def test_open_cost_update_then_claim_and_refund_preserve_other_reservations(kind):
    board = funded_board()
    update = event(kind, {"budget_cost": 3}, event_id="open-cost")
    if kind == "task.upsert":
        update["intent"]["task"] = {**board.tasks[0].model_dump(mode="json"), "budget_cost": 3}
    board, _ = _project_local_task_event(board, update)
    assert_track(board, 9, 4)
    board = claim(board)
    assert_track(board, 12, 7)
    board, _ = _project_local_task_event(
        board,
        event(
            "task.mutate", {"title": "Unrelated metadata", "budget_cost": 3}, status="dispatched", event_id="metadata"
        ),
    )
    board, _ = _project_local_task_event(
        board, event("task.status", {"status": "open"}, status="dispatched", event_id="refund")
    )
    assert_track(board, 9, 4)


def test_postlaunch_reroute_retains_each_attempt_debit_and_immutable_cost():
    board = claim(funded_board())
    request = event("task.status", {"status": "open", "budget_cost": 1000}, status="dispatched", event_id="reroute")
    request["intent"]["log"].update(
        lifecycle_repair="provider-reroute",
        execution_started=True,
        execution_reservation_id="d" * 64,
        execution_contract_hash="e" * 64,
    )
    assert_rejected_unchanged(board, request)
    del request["intent"]["patch"]["budget_cost"]
    board, _ = _project_local_task_event(board, request)
    assert_track(board, 11, 6)
    board, _ = _project_local_task_event(board, event("task.mutate", {"budget_cost": 3}, event_id="next-cost"))
    second_claim = event("task.claim", {"status": "dispatched"}, event_id="second-claim")
    board, _ = _project_local_task_event(board, second_claim)
    assert_track(board, 14, 9)
    board, _ = _project_local_task_event(
        board, event("task.status", {"status": "open"}, status="dispatched", event_id="second-refund")
    )
    assert_track(board, 11, 6)
