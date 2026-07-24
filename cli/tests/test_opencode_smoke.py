from __future__ import annotations

import json
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from limen import opencode_smoke
from limen.provider_health import (
    ProviderHealthPolicy,
    ProviderOutcome,
    append_provider_outcome,
    execution_profile_hash,
    load_provider_outcomes,
    project_provider_health,
    provider_for_model,
)
from limen.provider_selection import ModelCapability, catalog_hash, execution_profile_for

NOW = datetime(2026, 7, 24, 4, 0, tzinfo=UTC)
POLICY = ProviderHealthPolicy(86_400, 3_600, 2, 1, 120)


def model(model_id: str, *, cost: float = 1.0) -> ModelCapability:
    return ModelCapability(
        model_id=model_id,
        active=True,
        text_input=True,
        text_output=True,
        toolcall=True,
        reasoning=True,
        attachment=False,
        context_limit=131_072,
        output_limit=32_768,
        input_cost=cost,
        output_cost=cost,
        variant_count=2,
        release_ordinal=739_000,
    )


def outcome(item: ModelCapability, terminal: str, finished_at: datetime) -> ProviderOutcome:
    return ProviderOutcome(
        provider=provider_for_model(item.model_id),
        runtime_model=item.model_id,
        catalog_hash=catalog_hash([item]),
        execution_profile_hash=execution_profile_hash(execution_profile_for(None).as_dict()),
        terminal_class=terminal,
        started_at=finished_at - timedelta(seconds=5),
        finished_at=finished_at,
        retry_count=0,
        receipt_reference="test:receipt",
    )


@contextmanager
def admitted(*args, **kwargs):
    del args, kwargs
    yield {"allowed": True}


def test_candidate_prefers_arbitrarily_named_model_awaiting_smoke() -> None:
    waiting = model("provider-z/renamed-44")
    healthy = model("provider-q/renamed-11", cost=0)
    events = [
        outcome(waiting, "stream_failure", NOW - timedelta(minutes=62)),
        outcome(waiting, "timeout", NOW - timedelta(minutes=61)),
    ]
    health = project_provider_health(events, POLICY, now=NOW)

    selected = opencode_smoke.select_opencode_smoke_candidate(
        [healthy, waiting], execution_profile_for(None), health, now=NOW
    )

    assert selected == waiting


def test_success_requires_json_tool_read_and_marker_and_reenters(tmp_path, monkeypatch) -> None:
    waiting = model("provider-x/runtime-renamed")
    ledger = tmp_path / "outcomes.jsonl"
    append_provider_outcome(ledger, outcome(waiting, "stream_failure", NOW - timedelta(minutes=62)))
    append_provider_outcome(ledger, outcome(waiting, "timeout", NOW - timedelta(minutes=61)))
    seen = {}

    def runner(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs["env"]
        marker = (Path(kwargs["cwd"]) / "SMOKE.txt").read_text().strip()
        rows = [
            {"type": "tool", "part": {"tool": "read", "input": {"filePath": "SMOKE.txt"}}},
            {"type": "tool_result", "part": {"output": marker}},
        ]
        return subprocess.CompletedProcess(argv, 0, "\n".join(json.dumps(row) for row in rows), "")

    monkeypatch.setattr(opencode_smoke, "hold_lease", admitted)
    monkeypatch.setattr(opencode_smoke, "provider_health_policy", lambda: POLICY)
    result = opencode_smoke.run_opencode_smoke(ledger_path=ledger, models=[waiting], runner=runner, clock=lambda: NOW)

    assert result.succeeded is True
    assert result.terminal_class == "smoke_success"
    assert seen["env"]["OPENCODE_PERMISSION"] == opencode_smoke._SMOKE_PERMISSION
    assert "--auto" not in seen["argv"]
    assert result.receipt_reference and result.receipt_reference.startswith("opencode-smoke:")
    health = project_provider_health(load_provider_outcomes(ledger), POLICY, now=NOW)
    assert health.allows(waiting.model_id, now=NOW) is True


def test_plain_text_marker_without_json_tool_evidence_fails(tmp_path, monkeypatch) -> None:
    item = model("provider-y/runtime-random")

    def runner(argv, **kwargs):
        marker = (Path(kwargs["cwd"]) / "SMOKE.txt").read_text().strip()
        return subprocess.CompletedProcess(argv, 0, marker, "")

    monkeypatch.setattr(opencode_smoke, "hold_lease", admitted)
    monkeypatch.setattr(opencode_smoke, "provider_health_policy", lambda: POLICY)
    ledger = tmp_path / "outcomes.jsonl"
    result = opencode_smoke.run_opencode_smoke(ledger_path=ledger, models=[item], runner=runner, clock=lambda: NOW)

    assert result.succeeded is False
    assert result.tool_read_observed is False
    assert load_provider_outcomes(ledger)[-1].terminal_class == "no_output"


def test_timeout_is_bounded_and_recorded(tmp_path, monkeypatch) -> None:
    item = model("provider-t/runtime-timeout")

    def runner(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(opencode_smoke, "hold_lease", admitted)
    monkeypatch.setattr(opencode_smoke, "provider_health_policy", lambda: POLICY)
    ledger = tmp_path / "outcomes.jsonl"
    result = opencode_smoke.run_opencode_smoke(ledger_path=ledger, models=[item], runner=runner, clock=lambda: NOW)

    assert result.terminal_class == "timeout"
    assert load_provider_outcomes(ledger)[-1].terminal_class == "timeout"


def test_require_reentry_blocks_when_only_healthy_model_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(opencode_smoke, "provider_health_policy", lambda: POLICY)
    result = opencode_smoke.run_opencode_smoke(
        ledger_path=tmp_path / "outcomes.jsonl",
        models=[model("provider-n/runtime-healthy")],
        allow_healthy=False,
        clock=lambda: NOW,
    )

    assert result.status == "blocked"
    assert result.runtime_model is None
    assert not (tmp_path / "outcomes.jsonl").exists()


def test_secret_shaped_failure_output_is_not_persisted(tmp_path, monkeypatch) -> None:
    item = model("provider-s/runtime-secret")

    def runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, "", "api_key=do-not-persist")

    monkeypatch.setattr(opencode_smoke, "hold_lease", admitted)
    monkeypatch.setattr(opencode_smoke, "provider_health_policy", lambda: POLICY)
    ledger = tmp_path / "outcomes.jsonl"
    result = opencode_smoke.run_opencode_smoke(ledger_path=ledger, models=[item], runner=runner, clock=lambda: NOW)

    assert "do-not-persist" not in ledger.read_text()
    assert result.receipt_reference and "do-not-persist" not in result.receipt_reference
