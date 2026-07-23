from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from limen.models import DispatchLogEntry, Task
from limen.provider_selection import (
    ExecutionProfile,
    ModelCapability,
    catalog_hash,
    effective_profile,
    execution_profile_for,
    paid_service_block_reason,
    parse_opencode_catalog,
    parse_warp_catalog,
    select_opencode_model,
    validate_warp_override,
)


def profile(**overrides: object) -> ExecutionProfile:
    values: dict[str, object] = {
        "requested_hint": None,
        "reasoning_depth": 0.5,
        "cost_pressure": 0.5,
        "latency_pressure": 0.5,
        "min_context": 8192,
        "min_output": 2048,
        "tools_required": True,
        "attachments_required": False,
        "planning_only": False,
        "build_allowed": True,
        "verification_strength": 0.5,
    }
    values.update(overrides)
    return ExecutionProfile(**values)  # type: ignore[arg-type]


def model(model_id: str, **overrides: object) -> ModelCapability:
    values: dict[str, object] = {
        "model_id": model_id,
        "active": True,
        "text_input": True,
        "text_output": True,
        "toolcall": True,
        "reasoning": False,
        "attachment": False,
        "context_limit": 32768,
        "output_limit": 8192,
        "input_cost": 0.0,
        "output_cost": 0.0,
        "variant_count": 0,
        "release_ordinal": 700000,
    }
    values.update(overrides)
    return ModelCapability(**values)  # type: ignore[arg-type]


def test_profile_derives_from_live_task_shape_and_preserves_unknown_hint() -> None:
    task = Task(
        id="DYNAMIC",
        title="large dependency-aware task",
        description="x" * 3000,
        target_agent="opencode",
        priority="critical",
        budget_cost=3,
        labels=["tier:future-shape"],
        depends_on=["A", "B"],
        created=date(2026, 7, 10),
    )
    result = execution_profile_for(task)
    assert result.requested_hint == "future-shape"
    assert result.reasoning_depth > 0.5
    assert result.min_context >= 8192
    assert result.tools_required is True


def test_tier_hint_is_opaque_and_cannot_change_routing_profile() -> None:
    common = {
        "id": "OPAQUE",
        "title": "same task",
        "description": "same evidence",
        "target_agent": "opencode",
        "priority": "medium",
        "budget_cost": 2,
        "created": date(2026, 7, 10),
    }
    legacy = execution_profile_for(Task(**common, labels=["tier:economy"]))
    future = execution_profile_for(Task(**common, labels=["tier:any-future-word"]))
    legacy_shape = legacy.as_dict() | {"requested_hint": None}
    future_shape = future.as_dict() | {"requested_hint": None}
    assert legacy_shape == future_shape
    assert legacy.requested_hint == "economy"
    assert future.requested_hint == "any-future-word"


def test_numeric_profile_constraints_are_schema_driven() -> None:
    task = Task(
        id="PROFILE",
        title="numeric constraints",
        target_agent="opencode",
        labels=[
            "profile:reasoning-depth:0.91",
            "profile:cost-pressure:0.12",
            "profile:min-context:131072",
            "profile:runway-seconds:172800",
        ],
        created=date(2026, 7, 10),
    )
    result = execution_profile_for(task)
    assert result.reasoning_depth == 0.91
    assert result.cost_pressure == 0.12
    assert result.min_context == 131072
    assert result.runway_seconds == 172800


def test_execution_profile_rejects_unbounded_runway() -> None:
    task = Task(
        id="UNBOUNDED-RUNWAY",
        title="invalid workstream length",
        target_agent="opencode",
        labels=["profile:runway-seconds:999999999"],
        created=date(2026, 7, 10),
    )
    with pytest.raises(ValueError, match="runway_seconds"):
        execution_profile_for(task)
    with pytest.raises(ValueError, match="runway_seconds"):
        profile(runway_seconds="86400")


def test_model_acceptance_never_turns_a_plan_into_executable_authority() -> None:
    requested = profile(planning_only=True, build_allowed=False, reasoning_depth=0.6)
    result = effective_profile(requested, plan_accepted=False)
    assert result == requested
    assert result.planning_only is True
    assert result.build_allowed is False


def test_catalog_parser_uses_metadata_not_reported_name_tokens() -> None:
    payload = {
        "id": "shape-a",
        "providerID": "provider-z",
        "status": "active",
        "cost": {"input": 0, "output": 0},
        "limit": {"context": 65536, "output": 8192},
        "capabilities": {
            "reasoning": True,
            "toolcall": True,
            "attachment": False,
            "input": {"text": True},
            "output": {"text": True},
        },
        "variants": {"one": {}},
        "release_date": "2026-01-01",
    }
    parsed = parse_opencode_catalog("provider-z/renamed-anything\n" + json.dumps(payload))
    assert len(parsed) == 1
    assert parsed[0].model_id == "provider-z/renamed-anything"
    assert parsed[0].reasoning is True
    assert parsed[0].zero_cost is True


def test_selection_changes_with_capabilities_and_pressure_not_names_or_order() -> None:
    cheap = model("p/alpha", reasoning=False)
    capable = model(
        "q/beta",
        reasoning=True,
        context_limit=131072,
        output_limit=32768,
        input_cost=2,
        output_cost=2,
        variant_count=4,
    )
    economical = select_opencode_model([capable, cheap], profile(reasoning_depth=0.1, cost_pressure=1.0))
    deep = select_opencode_model([cheap, capable], profile(reasoning_depth=1.0, cost_pressure=0.0))
    assert economical == cheap
    assert deep == capable


def test_unreachable_or_incapable_models_are_never_synthesized() -> None:
    unavailable = model("p/unavailable", active=False)
    no_tools = model("p/no-tools", toolcall=False)
    too_small = model("p/too-small", context_limit=4096)
    assert select_opencode_model([unavailable, no_tools, too_small], profile()) is None


def test_attachment_requirement_filters_live_catalog() -> None:
    text_only = model("p/text")
    multimodal = model("p/multi", attachment=True)
    assert select_opencode_model([text_only, multimodal], profile(attachments_required=True)) == multimodal


def test_catalog_hash_is_order_independent_and_changes_with_capability() -> None:
    first = model("p/a")
    second = model("p/b")
    assert catalog_hash([first, second]) == catalog_hash([second, first])
    assert catalog_hash([first]) != catalog_hash([model("p/a", reasoning=True)])


def test_warp_defaults_to_provider_auto_and_only_validates_explicit_override() -> None:
    catalog = parse_warp_catalog('[{"id":"router-one"},{"id":"model-two"}]')
    assert validate_warp_override(catalog, None) is None
    assert validate_warp_override(catalog, "model-two") == "model-two"
    assert validate_warp_override(catalog, "missing") is None


def test_paid_service_safety_gate_uses_task_risk_not_model_catalog() -> None:
    safe = Task(id="SAFE", title="repair parser", target_agent="warp", created=date(2026, 7, 10))
    risky = Task(id="RISK", title="delete personal data", target_agent="warp", created=date(2026, 7, 10))
    assert paid_service_block_reason(safe) is None
    assert "safety gate" in str(paid_service_block_reason(risky))


def test_provider_selector_source_contains_no_literal_provider_model_id() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "limen" / "provider_selection.py").read_text()
    # A quoted provider/model value would be a catalog pin. Runtime composition (f-strings) is fine.
    assert not __import__("re").search(r"(['\"])[a-z0-9_.-]+/[a-z0-9_.-]+\1", source, __import__("re").I)


def test_dispatch_contains_no_codex_or_gemini_fallback_catalog() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "limen" / "dispatch.py").read_text()

    assert "_CODEX_TIER_MODELS_DEFAULT" not in source
    assert "_GEMINI_TIER_MODELS_DEFAULT" not in source
    assert "LIMEN_CODEX_TIER_SELECT" not in source
    assert "LIMEN_GEMINI_TIER_SELECT" not in source


def test_legacy_composite_event_remains_loadable_for_append_only_healing() -> None:
    entry = DispatchLogEntry(
        timestamp="2026-07-10T00:00:00Z",  # type: ignore[arg-type]
        agent="codex",
        session_id="legacy",
        status="timeout->jules",
    )
    assert entry.status == "timeout->jules"
    assert entry.route_to is None
