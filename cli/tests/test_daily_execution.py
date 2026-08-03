from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from limen.daily_execution import (
    DeliveryReceiptV1,
    InteractionEventV1,
    ObligationV1,
    can_transition,
    run_daily_execution,
    transition_state,
)


def _runner_factory(calls: list[dict]):
    def runner(*, name, args, env, cwd, timeout_seconds):
        calls.append({"name": name, "args": list(args), "fire": env["LIMEN_APPLY_FIRE"]})
        summaries = {
            "ingest": {},
            "opportunities": {"inbound": 0},
            "applications": {"qualified": 3, "staged": 3, "submitted": 3},
            "followups": {
                "reply_owed": 2,
                "by_disposition": {"held": 2},
                "fixed_point": True,
                "uma_available": True,
            },
        }
        return {"name": name, "status": "completed", "returncode": 0, "summary": summaries[name]}

    return runner


def test_shared_records_reject_skipped_delivery_states():
    event = InteractionEventV1(
        source="mail",
        account="account-1",
        thread="thread-1",
        participants=["participant-1"],
        timestamp="2026-08-03T12:00:00Z",
        content_ref="private:mail/thread-1",
        observation_receipt="mail-receipt-1",
    )
    obligation = ObligationV1(
        evidence_links=["private:mail/thread-1"],
        required_action="reply",
        recipient_target="recipient-1",
        due_at="2026-08-04T12:00:00Z",
        risk_class="professional",
        owner="operator",
    )
    assert event.as_dict()["state"] == "observed"
    assert obligation.as_dict()["schema"] == "limen.obligation.v1"
    assert can_transition("attempted", "delivered")
    assert not can_transition("prepared", "confirmed")
    assert transition_state("delivered", "confirmed") == "confirmed"

    with pytest.raises(ValueError, match="confirmation_evidence"):
        DeliveryReceiptV1(
            exact_target="recipient-1",
            attempted_action="reply",
            provider_response="accepted",
            timestamp="2026-08-03T12:00:00Z",
            confirmation_evidence=[],
            state="confirmed",
        )


def test_daily_loop_passes_one_fire_valve_to_all_existing_owners(tmp_path: Path, monkeypatch):
    receipt_path = tmp_path / "daily.json"
    monkeypatch.setenv("LIMEN_DAILY_EXECUTION_RECEIPT", str(receipt_path))
    calls: list[dict] = []

    result = run_daily_execution(
        fire=True,
        root=tmp_path,
        step_runner=_runner_factory(calls),
    )

    assert [call["name"] for call in calls] == ["ingest", "opportunities", "applications", "followups"]
    assert {call["fire"] for call in calls} == {"1"}
    assert result["fire"] is True
    assert result["applications"]["submitted"] == 3
    assert result["follow_ups"]["blocked"] == 2
    assert json.loads(receipt_path.read_text())["schema"] == "limen.daily_execution.v1"


def test_submitted_or_generated_templates_never_become_confirmed(tmp_path: Path, monkeypatch):
    receipt_path = tmp_path / "daily.json"
    monkeypatch.setenv("LIMEN_DAILY_EXECUTION_RECEIPT", str(receipt_path))
    monkeypatch.delenv("LIMEN_APPLICATION_CONFIRMATION_RECEIPT", raising=False)
    monkeypatch.delenv("LIMEN_APPLICATION_RECEIPTS", raising=False)

    result = run_daily_execution(
        fire=True,
        root=tmp_path,
        step_runner=_runner_factory([]),
    )

    assert result["applications"]["submitted"] == 3
    assert result["applications"]["confirmed"] == 0
    assert any("confirmation receipt" in blocker for blocker in result["applications"]["blockers"])


def test_only_explicit_provider_evidence_counts_as_application_confirmation(tmp_path: Path, monkeypatch):
    confirmation_path = tmp_path / "application-confirmations.json"
    confirmation_path.write_text(
        json.dumps(
            {
                "receipts": [
                    {"state": "confirmed", "confirmation_evidence": ["portal:1"]},
                    {"state": "confirmed", "confirmation_evidence": ["mailbox:2"]},
                    {"state": "staged", "confirmation_evidence": []},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_APPLICATION_CONFIRMATION_RECEIPT", str(confirmation_path))
    result = run_daily_execution(
        fire=True,
        root=tmp_path,
        step_runner=_runner_factory([]),
        write_receipt=False,
    )

    assert result["applications"]["confirmed"] == 2
    assert result["applications"]["shortage"] == 1


def test_pipeline_submitted_label_and_filled_form_are_not_confirmation(tmp_path: Path, monkeypatch):
    pipeline = tmp_path / "application-pipeline"
    submitted = pipeline / "pipeline" / "submitted"
    submitted.mkdir(parents=True)
    (submitted / "role.yaml").write_text(
        "status: submitted\nsubmission:\n  portal_state: fully_filled_except_required_resume_upload\n  receipt: generated-template\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("APPLICATION_PIPELINE", str(pipeline))
    result = run_daily_execution(
        fire=True,
        root=tmp_path,
        step_runner=_runner_factory([]),
        write_receipt=False,
    )

    reconciliation = result["applications"]["historical_reconciliation"]
    assert reconciliation["claimed_submitted"] == 1
    assert reconciliation["unconfirmed_claims"] == 1
    assert reconciliation["confirmed"] == 0


def test_daily_receipt_keeps_only_valid_exact_target_provider_receipts(tmp_path: Path, monkeypatch):
    provider_path = tmp_path / "provider-receipts.json"
    provider_path.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "schema": "limen.delivery_receipt.v1",
                        "exact_target": "provider-target-1",
                        "attempted_action": "email follow-up",
                        "provider_response": "accepted",
                        "timestamp": "2026-08-03T12:00:00Z",
                        "confirmation_evidence": ["sent-mail:message-1"],
                        "state": "confirmed",
                    },
                    {"state": "confirmed", "exact_target": "missing evidence"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_DELIVERY_RECEIPTS", str(provider_path))
    result = run_daily_execution(
        fire=True,
        root=tmp_path,
        step_runner=_runner_factory([]),
        write_receipt=False,
    )

    assert len(result["delivery_receipts"]) == 1
    assert result["delivery_receipts"][0]["exact_target"] == "provider-target-1"


def test_cli_daily_execute_uses_the_same_coordinator(monkeypatch):
    from limen import cli

    expected = {
        "status": "confirmed",
        "applications": {"confirmed": 3, "target": 3},
        "follow_ups": {"confirmed": 1},
        "blockers": [],
    }
    monkeypatch.setattr("limen.daily_execution.run_daily_execution", lambda **_: expected)
    result = CliRunner().invoke(cli.main, ["daily-execute", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == expected
