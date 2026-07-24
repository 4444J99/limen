from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from limen.provider_health import (
    ProviderHealthPolicy,
    ProviderOutcome,
    append_provider_outcome,
    classify_provider_terminal,
    execution_profile_hash,
    load_provider_outcomes,
    project_provider_health,
)
from limen.provider_selection import ExecutionProfile, ModelCapability, select_opencode_model
from limen.models import Task


NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)
HASH = "a" * 64
PROFILE_HASH = execution_profile_hash({"tools_required": True})


def policy(**overrides: int) -> ProviderHealthPolicy:
    values = {
        "failure_window_seconds": 86_400,
        "cooldown_seconds": 3_600,
        "terminal_attempts": 2,
        "same_model_retries": 1,
        "smoke_timeout_seconds": 120,
    }
    values.update(overrides)
    return ProviderHealthPolicy(**values)


def outcome(
    model_id: str,
    terminal_class: str,
    *,
    finished_at: datetime,
    retry_count: int = 0,
) -> ProviderOutcome:
    return ProviderOutcome(
        provider=model_id.split("/", 1)[0],
        runtime_model=model_id,
        catalog_hash=HASH,
        execution_profile_hash=PROFILE_HASH,
        terminal_class=terminal_class,
        started_at=finished_at - timedelta(seconds=5),
        finished_at=finished_at,
        retry_count=retry_count,
        receipt_reference="issue:928",
    )


def profile() -> ExecutionProfile:
    return ExecutionProfile(
        requested_hint=None,
        reasoning_depth=0.5,
        cost_pressure=1.0,
        latency_pressure=0.5,
        min_context=8192,
        min_output=2048,
        tools_required=True,
        attachments_required=False,
        planning_only=False,
        build_allowed=True,
        verification_strength=0.5,
    )


def model(model_id: str, *, zero_cost: bool = True) -> ModelCapability:
    return ModelCapability(
        model_id=model_id,
        active=True,
        text_input=True,
        text_output=True,
        toolcall=True,
        reasoning=False,
        attachment=False,
        context_limit=32768,
        output_limit=8192,
        input_cost=0 if zero_cost else 2,
        output_cost=0 if zero_cost else 2,
        variant_count=0,
        release_ordinal=700000,
    )


def test_append_only_ledger_round_trips_and_skips_malformed_rows(tmp_path) -> None:
    path = tmp_path / "outcomes.jsonl"
    row = outcome("provider-z/arbitrary-renamed", "success", finished_at=NOW)
    append_provider_outcome(path, row)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{malformed\n")
        malformed_type = {**row.as_dict(), "retry_count": {"not": "an integer"}}
        handle.write(json.dumps(malformed_type) + "\n")

    loaded = load_provider_outcomes(path)

    assert loaded == [row]
    assert json.loads(path.read_text().splitlines()[0])["runtime_model"] == "provider-z/arbitrary-renamed"
    assert path.stat().st_mode & 0o077 == 0


def test_secret_shaped_receipt_is_rejected() -> None:
    with pytest.raises(ValueError, match="secret-shaped"):
        ProviderOutcome(
            provider="p",
            runtime_model="p/m",
            catalog_hash=HASH,
            execution_profile_hash=PROFILE_HASH,
            terminal_class="success",
            started_at=NOW,
            finished_at=NOW,
            retry_count=0,
            receipt_reference="token=do-not-store",
        )


def test_two_model_failures_cool_then_require_post_cooldown_smoke() -> None:
    model_id = "provider-a/shape-random"
    events = [
        outcome(model_id, "stream_failure", finished_at=NOW - timedelta(minutes=10)),
        outcome(model_id, "timeout", finished_at=NOW),
    ]

    cooling = project_provider_health(events, policy(), now=NOW + timedelta(minutes=30))
    awaiting_smoke = project_provider_health(events, policy(), now=NOW + timedelta(minutes=61))
    recovered = project_provider_health(
        events + [outcome(model_id, "smoke_success", finished_at=NOW + timedelta(minutes=62))],
        policy(),
        now=NOW + timedelta(minutes=63),
    )

    assert cooling.allows(model_id, now=NOW + timedelta(minutes=30)) is False
    assert awaiting_smoke.models[model_id].requires_smoke is True
    assert awaiting_smoke.allows(model_id, now=NOW + timedelta(minutes=61)) is False
    assert recovered.allows(model_id, now=NOW + timedelta(minutes=63)) is True


def test_auth_and_rate_failures_cool_the_provider_not_only_one_model() -> None:
    events = [
        outcome("provider-q/first", "auth_failure", finished_at=NOW - timedelta(seconds=5)),
        outcome("provider-q/second", "rate_limit", finished_at=NOW),
    ]
    health = project_provider_health(events, policy(), now=NOW + timedelta(minutes=1))

    assert health.allows("provider-q/unseen", now=NOW + timedelta(minutes=1)) is False
    assert health.allows("provider-r/unseen", now=NOW + timedelta(minutes=1)) is True


def test_healthy_fallback_and_all_unhealthy_are_name_and_order_independent() -> None:
    first = "provider-a/random-17"
    second = "provider-b/random-03"
    events = [
        outcome(first, "transport_failure", finished_at=NOW - timedelta(seconds=5)),
        outcome(first, "stream_failure", finished_at=NOW),
    ]
    health = project_provider_health(events, policy(), now=NOW + timedelta(minutes=1))

    assert select_opencode_model(
        [model(first), model(second)],
        profile(),
        health,
        now=NOW + timedelta(minutes=1),
    ) == model(second)

    both = project_provider_health(
        events
        + [
            outcome(second, "timeout", finished_at=NOW - timedelta(seconds=5)),
            outcome(second, "no_output", finished_at=NOW),
        ],
        policy(),
        now=NOW + timedelta(minutes=1),
    )
    assert (
        select_opencode_model(
            [model(second), model(first)],
            profile(),
            both,
            now=NOW + timedelta(minutes=1),
        )
        is None
    )


def test_outcome_fitness_outranks_zero_cost() -> None:
    proven = "provider-p/paid-random"
    unknown = "provider-z/free-random"
    health = project_provider_health(
        [outcome(proven, "success", finished_at=NOW)],
        policy(),
        now=NOW + timedelta(seconds=1),
    )

    selected = select_opencode_model(
        [model(unknown, zero_cost=True), model(proven, zero_cost=False)],
        profile(),
        health,
        now=NOW + timedelta(seconds=1),
    )

    assert selected == model(proven, zero_cost=False)


def test_terminal_classifier_and_retry_policy_are_bounded() -> None:
    assert classify_provider_terminal(timed_out=True) == "timeout"
    assert classify_provider_terminal(returncode=1, output="stream ended with unexpected EOF") == "stream_failure"
    assert classify_provider_terminal(returncode=1, output="OAuth session expired") == "auth_failure"
    assert classify_provider_terminal(returncode=0) == "success"
    assert policy().same_model_retries == 1
    assert policy().smoke_timeout_seconds == 120


def test_opencode_run_retries_one_transient_attempt_and_appends_outcome(tmp_path, monkeypatch) -> None:
    from limen import dispatch

    task = Task(id="HEALTH-RETRY", title="retry", target_agent="opencode", created=NOW.date())
    ledger = tmp_path / "provider-outcomes.jsonl"
    monkeypatch.setenv("LIMEN_PROVIDER_OUTCOME_LEDGER", str(ledger))
    monkeypatch.setenv("LIMEN_PROVIDER_SAME_MODEL_RETRIES", "1")
    dispatch._MODEL_SELECTION_RECEIPTS[task.id] = {
        "execution_profile": profile().as_dict(),
        "selected_model": "provider-z/arbitrary-model",
        "selection_source": "test",
        "catalog_hash": HASH,
    }
    calls: list[int] = []

    def run(*_args, **_kwargs):
        calls.append(1)
        if len(calls) == 1:
            return subprocess.CompletedProcess([], 1, "", "stream ended with unexpected EOF")
        return subprocess.CompletedProcess([], 0, "ok", "")

    monkeypatch.setattr(dispatch, "_run_capture", run)
    monkeypatch.setattr(dispatch, "_show_opencode_clock_after_run", lambda _task: None)

    result = dispatch._run_isolated_agent("opencode", task, tmp_path, ["opencode", "prompt"], 30)

    assert result is True
    assert len(calls) == 2
    rows = load_provider_outcomes(ledger)
    assert [row.terminal_class for row in rows] == ["stream_failure"]
    assert rows[0].retry_count == 0
    assert dispatch._MODEL_SELECTION_RECEIPTS[task.id]["_provider_retry_count"] == 1
    dispatch._MODEL_SELECTION_RECEIPTS.pop(task.id, None)


def test_dispatch_selector_blocks_cooled_model_and_records_health_hash(tmp_path, monkeypatch) -> None:
    from limen import dispatch

    ledger = tmp_path / "provider-outcomes.jsonl"
    current = datetime.now(timezone.utc)
    cooled = "provider-a/runtime-random"
    fallback = "provider-b/runtime-random"
    append_provider_outcome(ledger, outcome(cooled, "stream_failure", finished_at=current - timedelta(seconds=5)))
    append_provider_outcome(ledger, outcome(cooled, "timeout", finished_at=current))
    monkeypatch.setenv("LIMEN_PROVIDER_OUTCOME_LEDGER", str(ledger))
    monkeypatch.setattr(
        dispatch, "discover_opencode_models", lambda *_args, **_kwargs: [model(cooled), model(fallback)]
    )
    task = Task(id="HEALTH-SELECT", title="select", target_agent="opencode", created=current.date())

    selected = dispatch._opencode_model(task)

    receipt = dispatch._MODEL_SELECTION_RECEIPTS.pop(task.id)
    assert selected == fallback
    assert receipt["selection_source"] == "opencode_live_catalog_health"
    assert len(receipt["health_snapshot_hash"]) == 64


def test_down_lanes_consumes_provider_level_health_as_fourth_source(tmp_path, monkeypatch) -> None:
    from limen import dispatch

    ledger = tmp_path / "provider-outcomes.jsonl"
    current = datetime.now(timezone.utc)
    append_provider_outcome(
        ledger,
        outcome("provider-z/runtime-one", "auth_failure", finished_at=current - timedelta(seconds=5)),
    )
    append_provider_outcome(
        ledger,
        outcome("provider-z/runtime-two", "rate_limit", finished_at=current),
    )
    monkeypatch.setenv("LIMEN_PROVIDER_OUTCOME_LEDGER", str(ledger))
    monkeypatch.setattr(dispatch, "_usage_dead_lanes", lambda: set())
    monkeypatch.setattr(dispatch, "_oauth_unreachable_lanes", lambda: set())

    assert "opencode" in dispatch._down_lanes()
