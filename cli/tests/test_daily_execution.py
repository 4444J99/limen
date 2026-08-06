from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

import limen.daily_execution as daily_execution
from limen.daily_execution import (
    DeliveryReceiptV1,
    InteractionEventV1,
    ObligationV1,
    _run_id,
    can_transition,
    run_daily_execution,
    transition_state,
)


def _runner_factory(calls: list[dict], *, followup_due: int = 2):
    def runner(*, name, args, env, cwd, timeout_seconds):
        calls.append(
            {
                "name": name,
                "args": list(args),
                "fire": env.get("LIMEN_APPLY_FIRE"),
                "outbound_env": {
                    key: env[key]
                    for key in (
                        "LIMEN_APPLY_FIRE",
                        "LIMEN_CORRESPONDENCE_FIRE",
                        "LIMEN_LINKEDIN_FIRE",
                        "LIMEN_MAIL_SEND",
                    )
                    if key in env
                },
            }
        )
        summaries = {
            "ingest": {},
            "opportunities": {"inbound": 0},
            "applications": {"qualified": 3, "staged": 3, "submitted": 3},
            "followups": {
                "reply_owed": followup_due,
                "by_disposition": {"held": followup_due} if followup_due else {},
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
    assert calls[0]["outbound_env"] == {}
    assert calls[1]["outbound_env"] == {}
    assert calls[2]["outbound_env"] == {"LIMEN_APPLY_FIRE": "1"}
    assert calls[3]["outbound_env"] == {
        "LIMEN_CORRESPONDENCE_FIRE": "1",
        "LIMEN_LINKEDIN_FIRE": "1",
        "LIMEN_MAIL_SEND": "1",
    }
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


def test_only_current_run_provider_evidence_counts_as_application_confirmation(tmp_path: Path, monkeypatch):
    # Pin the operator's local day while retaining the production parser for receipt
    # timestamps. A wall-clock fixture eventually stops being a current-run receipt.
    monkeypatch.setenv("LIMEN_DAILY_EXECUTION_TIMEZONE", "America/New_York")
    parsed_local_date = daily_execution._local_date
    fixture_date = parsed_local_date("2026-08-03T12:00:00Z")
    monkeypatch.setattr(
        daily_execution,
        "_local_date",
        lambda value=None: fixture_date if value is None else parsed_local_date(value),
    )
    confirmation_path = tmp_path / "delivery-receipts.json"
    run_id = _run_id(tmp_path)
    confirmation_path.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "exact_target": "role-1",
                        "attempted_action": "application submit",
                        "provider_response": "provider response",
                        "timestamp": "2026-08-03T12:00:00Z",
                        "confirmation_evidence": ["portal:1"],
                        "state": "confirmed",
                        "provider": "greenhouse",
                        "account": "candidate",
                        "run_id": run_id,
                        "obligation_id": "obligation-1",
                    },
                    {
                        "exact_target": "role-2",
                        "attempted_action": "application submit",
                        "provider_response": "provider response",
                        "timestamp": "2026-08-03T12:00:00Z",
                        "confirmation_evidence": ["mailbox:2"],
                        "state": "confirmed",
                        "provider": "lever",
                        "account": "candidate",
                        "run_id": run_id,
                        "obligation_id": "obligation-2",
                    },
                    {
                        "exact_target": "role-3",
                        "attempted_action": "application submit",
                        "provider_response": "accepted",
                        "timestamp": "2026-08-03T12:00:00Z",
                        "confirmation_evidence": [],
                        "state": "attempted",
                        "provider": "ashby",
                        "account": "candidate",
                        "run_id": run_id,
                        "obligation_id": "obligation-3",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_DELIVERY_RECEIPTS", str(confirmation_path))
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
    run_id = _run_id(tmp_path)
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
                        "provider": "uma",
                        "account": "candidate",
                        "run_id": run_id,
                        "obligation_id": "obligation-1",
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


def test_repeated_completed_run_returns_identical_persisted_state(tmp_path: Path, monkeypatch):
    receipt_path = tmp_path / "daily.json"
    delivery_path = tmp_path / "delivery-receipts.json"
    run_id = _run_id(tmp_path)
    delivery_path.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "exact_target": f"role-{index}",
                        "attempted_action": "application submit",
                        "provider_response": "provider response",
                        "timestamp": "2026-08-03T12:00:00Z",
                        "confirmation_evidence": [f"portal:{index}"],
                        "state": "confirmed",
                        "provider": "greenhouse",
                        "account": "candidate",
                        "run_id": run_id,
                        "obligation_id": f"obligation-{index}",
                    }
                    for index in range(3)
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_DAILY_EXECUTION_RECEIPT", str(receipt_path))
    monkeypatch.setenv("LIMEN_DELIVERY_RECEIPTS", str(delivery_path))
    # Force every clock read onto a distinct second so the replay cannot pass by
    # luckily landing inside the same wall-clock second as the first run.
    ticks = iter(range(60))
    monkeypatch.setattr(daily_execution, "_now", lambda: f"2026-08-03T12:00:{next(ticks):02d}Z")
    calls: list[dict] = []

    first = run_daily_execution(
        fire=False,
        root=tmp_path,
        step_runner=_runner_factory(calls, followup_due=0),
    )
    first_bytes = receipt_path.read_bytes()
    second = run_daily_execution(
        fire=False,
        root=tmp_path,
        step_runner=_runner_factory(calls, followup_due=0),
    )

    assert second == first
    assert receipt_path.read_bytes() == first_bytes
    assert len(calls) == 4


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


def test_unconfigured_delivery_ledger_reports_unmeasured_not_zero(monkeypatch):
    """An unwired ledger must not masquerade as a shortfall of work.

    ``LIMEN_DELIVERY_RECEIPTS`` is optional, but when unset the canonical ledger reads
    empty and ``confirmed`` counts zero — a measurement that was never taken. Emitting
    a shortage there produces an exit condition no retry can satisfy, which is exactly
    what burned 27 hours of agent quota on 2026-08-04/05.
    """
    monkeypatch.delenv("LIMEN_DELIVERY_RECEIPTS", raising=False)

    summary = daily_execution._application_summary(
        {"summary": {"qualified": 5, "staged": 4, "submitted": 4}},
        run_id="daily_test",
        delivery_rows=[],
    )

    assert summary["confirmation_measured"] is False
    assert summary["shortage"] == 0
    assert summary["shortage_reason"] is None
    assert any("not configured" in blocker for blocker in summary["blockers"])
    # The fabrication guard still fires — an engine claiming submissions it cannot
    # evidence is always a blocker. Only the reason differs: "there was nowhere to
    # look" must not be reported as "we looked and found none".
    assert any("confirmation receipt" in blocker for blocker in summary["blockers"])
    assert not any("no portal/mailbox confirmation receipt" in b for b in summary["blockers"])


def test_configured_ledger_still_reports_a_real_shortage(monkeypatch, tmp_path):
    """With the ledger wired, a genuine confirmation shortfall is still surfaced."""
    ledger = tmp_path / "delivery-receipts.json"
    ledger.write_text(json.dumps({"receipts": []}), encoding="utf-8")
    monkeypatch.setenv("LIMEN_DELIVERY_RECEIPTS", str(ledger))

    summary = daily_execution._application_summary(
        {"summary": {"qualified": 5, "staged": 4, "submitted": 4}},
        run_id="daily_test",
        delivery_rows=[],
    )

    assert summary["confirmation_measured"] is True
    assert summary["shortage"] == 3
    assert summary["shortage_reason"] == "provider confirmation evidence is below the daily target"
