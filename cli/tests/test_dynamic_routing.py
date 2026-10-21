import json

from limen.provider_selection import (
    execution_profile_for,
    parse_opencode_catalog,
    select_opencode_model,
)


def entry(**changes):
    value = {
        "id": "arbitrary",
        "providerID": "fixture",
        "enabled": True,
        "capabilities": {
            "tools": True,
            "reasoning": True,
            "input": {"text": True},
            "output": {"text": True},
        },
        "limit": {"context": 65536, "output": 8192},
        "cost": [{"input": 1, "output": 2}],
    }
    return value | changes


def test_v2_registry_cost_tiers_and_tools_are_understood():
    models = parse_opencode_catalog(json.dumps([entry()]))
    assert len(models) == 1
    assert models[0].model_id == "fixture/arbitrary"
    assert models[0].toolcall
    assert models[0].input_cost == 1
    assert select_opencode_model(models, execution_profile_for(None)) == models[0]


def test_missing_cost_is_unknown_and_never_free_or_eligible():
    model = parse_opencode_catalog(json.dumps(entry(cost={})))[0]
    assert model.input_cost is None
    assert not model.zero_cost
    assert select_opencode_model([model], execution_profile_for(None)) is None


def test_missing_text_capabilities_are_not_assumed():
    model = parse_opencode_catalog(json.dumps(entry(capabilities={"tools": True})))[0]
    assert not model.text_input
    assert not model.satisfies(execution_profile_for(None))


def test_disabled_registry_model_stays_unavailable():
    model = parse_opencode_catalog(json.dumps(entry(enabled=False)))[0]
    assert not model.active


def test_cost_tiers_use_conservative_upper_bound():
    model = parse_opencode_catalog(
        json.dumps(
            entry(
                cost=[
                    {"input": 1, "output": 2},
                    {"input": 10, "output": 20},
                ]
            )
        )
    )[0]
    assert (model.input_cost, model.output_cost) == (10, 20)


def test_negative_nan_or_partial_prices_are_unknown():
    for cost in ({"input": -1, "output": 0}, {"input": "nan", "output": 1}, [{"input": 1, "output": 2}, {"input": 3}]):
        model = parse_opencode_catalog(json.dumps(entry(cost=cost)))[0]
        assert not model.cost_known
        assert not model.satisfies(execution_profile_for(None))


def test_catalog_change_and_phase_change_reselect_without_default_model():
    from limen.delegation_policy import select_delegation

    request = {
        "phase": "delegation",
        "catalog_source": "fixture-registry",
        "catalog_observed_at": 1000,
        "models": [entry()],
    }
    receipt = select_delegation(request, now=1001)
    assert receipt["selected_model"] == "fixture/arbitrary"
    assert receipt["observed_child_model"] is None
    assert receipt["execution_profile"] == execution_profile_for(None).as_dict()
    assert select_delegation(request | {"catalog_observed_at": 1}, now=1001)["decision"] == "deny"
    assert select_delegation(request | {"models": []}, now=1001)["decision"] == "deny"
    assert select_delegation(request | {"phase": "plan-to-build"}, now=1001)["phase"] == "plan-to-build"


def test_bounded_retry_and_reserved_models_are_enforced():
    from limen.delegation_policy import select_delegation

    request = {
        "phase": "delegation",
        "catalog_source": "fixture-registry",
        "catalog_observed_at": 1000,
        "models": [entry(reserved=True)],
    }
    assert select_delegation(request, now=1001)["decision"] == "deny"
    assert select_delegation(request | {"attempt": 3}, now=1001)["decision"] == "deny"


def test_real_v2_modalities_and_wrapped_registry():
    raw = entry(capabilities={"tools": True, "input": ["text"], "output": ["text"]})
    model = parse_opencode_catalog(json.dumps({"location": {}, "data": [raw]}))[0]
    assert model.text_input and model.text_output
    assert model.satisfies(execution_profile_for(None))


def test_complex_requirement_never_assumes_unknown_reasoning():
    from dataclasses import replace

    model = parse_opencode_catalog(
        json.dumps(
            entry(
                capabilities={
                    "tools": True,
                    "input": ["text"],
                    "output": ["text"],
                }
            )
        )
    )[0]
    assert not model.satisfies(replace(execution_profile_for(None), reasoning_depth=0.9))


def test_unknown_availability_is_not_eligible():
    raw = entry()
    raw.pop("enabled")
    model = parse_opencode_catalog(json.dumps(raw))[0]
    assert not model.active
    assert select_opencode_model([model], execution_profile_for(None)) is None
