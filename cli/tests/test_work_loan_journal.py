from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import limen.dispatch as dispatch
from limen.models import Task
from limen.work_loan_journal import (
    WorkLoanJournalError,
    WorkLoanJournalStore,
    build_work_loan_source,
    journal_snapshots,
    reconcile_terminal_tasks,
)


NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
DIGEST = "a" * 64


def task_row(task_id: str = "WORK-LOAN-1", **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": task_id,
        "title": "Account for one bounded run",
        "repo": "organvm/limen",
        "target_agent": "jules",
        "priority": "high",
        "budget_cost": 2,
        "status": "open",
        "labels": [],
        "origin": "human_prompt",
        "horizon": "present",
        "value_case": "Turn scarce capacity into one verified durable receipt",
        "owner_surface": "organvm/limen",
        "predicate": "python3 -m pytest cli/tests/test_work_loan_journal.py -q",
        "receipt_target": f"github:organvm/limen:pull-request:{task_id}",
        "created": date(2026, 7, 21),
        "dispatch_log": [],
    }
    row.update(overrides)
    return row


def store(tmp_path: Path) -> WorkLoanJournalStore:
    return WorkLoanJournalStore(tmp_path / "work-loan-journal.jsonl")


def test_journal_keeps_requested_reserved_and_actual_capacity_distinct(tmp_path: Path) -> None:
    journal = store(tmp_path)
    task = task_row()

    journal.record_reservation(task, agent="jules", reservation_id="reservation-1", now=NOW)
    journal.record_actual(
        task,
        agent="jules",
        reservation_id="reservation-1",
        elapsed_seconds=3.5,
        local_host=False,
        metrics={"input_tokens": 13, "output_tokens": 8, "dollars_usd": 0},
        now=NOW,
    )

    [snapshot] = journal_snapshots(journal.read())
    assert snapshot["requested"]["runs"] == 2
    assert snapshot["requested"]["input_tokens"] is None
    assert snapshot["reserved"]["runs"] == 2
    assert snapshot["actual"]["runs"] == 1
    assert snapshot["actual"]["input_tokens"] == 13
    assert snapshot["actual"]["output_tokens"] == 8
    assert snapshot["actual"]["dollars_usd"] == 0
    assert snapshot["actual"]["elapsed_seconds"] == 3.5
    assert snapshot["actual"]["host_local_seconds"] is None
    assert snapshot["unrepaid_debt"] is True
    assert journal.path.stat().st_mode & 0o777 == 0o600


def test_journal_is_hash_chained_and_rejects_tampering(tmp_path: Path) -> None:
    journal = store(tmp_path)
    task = task_row()
    journal.record_reservation(task, agent="jules", reservation_id="reservation-1", now=NOW)
    rows = journal.path.read_text(encoding="utf-8").splitlines()
    first = json.loads(rows[0])
    first["subject_id"] = "TAMPERED"
    rows[0] = json.dumps(first, sort_keys=True)
    journal.path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(WorkLoanJournalError, match="line 1 is invalid"):
        journal.read()


def test_correlation_retries_are_idempotent_but_conflicts_fail(tmp_path: Path) -> None:
    journal = store(tmp_path)
    task = task_row()
    journal.record_reservation(task, agent="jules", reservation_id="reservation-1", now=NOW)
    first = journal.path.read_bytes()

    journal.record_reservation(task, agent="jules", reservation_id="reservation-1", now=NOW)
    assert journal.path.read_bytes() == first

    with pytest.raises(WorkLoanJournalError, match="different accounting"):
        journal.record_reservation(task, agent="codex", reservation_id="reservation-1", now=NOW)


@pytest.mark.parametrize(
    ("outcome", "receipt_verified", "predicate_passed", "earned"),
    [
        ("done", True, True, True),
        ("done", False, True, False),
        ("failed", True, True, False),
    ],
)
def test_settlement_earns_credit_only_from_verified_done(
    tmp_path: Path,
    outcome: str,
    receipt_verified: bool,
    predicate_passed: bool,
    earned: bool,
) -> None:
    journal = store(tmp_path)
    task = task_row(task_id=f"WORK-LOAN-{outcome}-{receipt_verified}")
    journal.record_reservation(task, agent="jules", reservation_id="reservation-1", now=NOW)
    journal.record_settlement(
        task,
        outcome=outcome,
        receipt_verified=receipt_verified,
        predicate_passed=predicate_passed,
        verification_digest=DIGEST,
        correlation_id="settlement-1",
        now=NOW,
    )

    [snapshot] = journal_snapshots(journal.read())
    assert snapshot["earned_credit"] is earned
    assert snapshot["unrepaid_debt"] is not earned


def test_terminal_reconciliation_uses_keeper_receipt_evidence(tmp_path: Path) -> None:
    journal = store(tmp_path)
    initial = task_row()
    journal.record_reservation(initial, agent="jules", reservation_id="reservation-1", now=NOW)
    terminal = task_row(
        status="done",
        receipt_verified=True,
        dispatch_log=[
            {
                "timestamp": NOW.isoformat(),
                "agent": "tabularius",
                "session_id": "keeper",
                "status": "done",
                "predicate_exit_code": 0,
                "verification_context_digest": DIGEST,
                "remote_receipt": initial["receipt_target"],
            }
        ],
    )

    assert reconcile_terminal_tasks([terminal], journal, now=NOW) == 1
    assert reconcile_terminal_tasks([terminal], journal, now=NOW) == 0
    [snapshot] = journal_snapshots(journal.read())
    assert snapshot["earned_credit"] is True
    assert snapshot["receipt_verified"] is True


def test_source_report_is_bounded_and_keeps_unknowns_explicit(tmp_path: Path) -> None:
    journal = store(tmp_path)
    for number in range(3):
        task = task_row(f"WORK-LOAN-{number}")
        journal.record_reservation(task, agent="jules", reservation_id=f"reservation-{number}", now=NOW)

    full, tracked = build_work_loan_source(journal.read(), generated_at=NOW, public_limit=2)

    assert full["source_report"]["exhaustive"] is True
    assert full["source_report"]["normalized_leaf_count"] == 3
    assert full["summary"]["unrepaid_debt_count"] == 3
    assert tracked["tracked_loan_count"] == 2
    assert tracked["tracked_loan_truncated_count"] == 1
    assert "subject_id" not in tracked["loans"][0]
    assert tracked["loans"][0]["actual"]["input_tokens"] is None


def test_value_selection_uses_underwriting_only_inside_existing_buckets(monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_VALUE_GATE", "0")
    ordinary = Task.model_validate(task_row("ORDINARY"))
    deadline = Task.model_validate(
        task_row(
            "DEADLINE",
            external_deadline=True,
            due_at="2026-07-22T12:00:00Z",
        )
    )

    ordered = dispatch.sort_value_gate_candidates([ordinary, deadline], set())

    assert [task.id for task in ordered] == ["DEADLINE", "ORDINARY"]


def test_dispatch_refuses_provider_launch_when_reservation_cannot_land(monkeypatch) -> None:
    class BrokenStore:
        def record_reservation(self, *_args, **_kwargs) -> None:
            raise WorkLoanJournalError("journal unavailable")

    launched = False

    def launch(*_args, **_kwargs) -> bool:
        nonlocal launched
        launched = True
        return True

    monkeypatch.setattr(dispatch, "default_work_loan_journal_store", lambda: BrokenStore())
    monkeypatch.setattr(dispatch, "call_agent_dispatch", launch)

    result = dispatch._journaled_agent_dispatch(
        "jules",
        Task.model_validate(task_row()),
        False,
        "reservation-1",
    )

    assert dispatch._is_blocked_result(result)
    assert "work-loan reservation failed" in str(result)
    assert launched is False


def test_dispatch_records_actual_usage_after_launch(monkeypatch, tmp_path: Path) -> None:
    journal = store(tmp_path)
    ticks = iter((10.0, 12.25))
    monkeypatch.setattr(dispatch, "default_work_loan_journal_store", lambda: journal)
    monkeypatch.setattr(dispatch, "call_agent_dispatch", lambda *_args, **_kwargs: "provider-run")
    monkeypatch.setattr(dispatch.time, "monotonic", lambda: next(ticks))

    result = dispatch._journaled_agent_dispatch(
        "jules",
        Task.model_validate(task_row()),
        False,
        "reservation-1",
    )

    assert result == "provider-run"
    [snapshot] = journal_snapshots(journal.read())
    assert snapshot["actual"]["elapsed_seconds"] == 2.25
    assert snapshot["actual"]["host_local_seconds"] is None
