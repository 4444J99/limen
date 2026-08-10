from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "positioning-c10-readiness.py"
RECEIPT = (
    ROOT
    / "docs"
    / "receipts"
    / "positioning"
    / "preflights"
    / "2026-08-10-psp-c10-readiness-synthetic.json"
)


def _load_module():
    loader = importlib.machinery.SourceFileLoader("positioning_c10_readiness", str(SCRIPT))
    spec = importlib.util.spec_from_loader("positioning_c10_readiness", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


MODULE = _load_module()


def _validated_inputs():
    contract, fixture, program, graph = MODULE.load_inputs()
    state = MODULE.validate_contract(contract, program, graph)
    return contract, fixture, state


def test_contract_preserves_exact_registry_scope_assignments_and_gates() -> None:
    contract, _fixture, state = _validated_inputs()

    assert state["leaf_ids"] == [
        "PSP-P12-W01",
        "PSP-P12-W02",
        "PSP-P12-W03",
        "PSP-P12-W04",
        "PSP-P12-W05",
        "PSP-P12-W06",
        "PSP-P10-W08",
    ]
    assert state["conductor_assignment"] == {"slug": "gpt-5.6-sol", "effort": "max"}
    assert state["leaf_assignments"]["PSP-P12-W05"] == {
        "slug": "gpt-5.6-luna",
        "effort": "medium",
    }
    assert state["leaf_assignments"]["PSP-P10-W08"] == {
        "slug": "gpt-5.6-sol",
        "effort": "max",
    }
    assert set(state["gate_ids"]) == {"HG-PUBLICATION-SEND", "HG-CONTRACT", "HG-PUBLIC-IDENTITY"}
    assert contract["truth_boundary"]["synthetic_closes_leaf"] is False


def test_synthetic_run_exercises_all_decisions_without_creating_proof() -> None:
    receipt = MODULE.build_receipt()

    decisions = {
        row["hypothetical_decision"] for row in receipt["scenario_results"].values()
    }
    assert decisions == {"keep", "narrow", "pivot", "insufficient_evidence"}
    assert receipt["operational_readiness"]["status"] == "synthetic_dry_run_pass"
    assert receipt["commercial_proof"]["established"] is False
    assert all(value == 0 for key, value in receipt["commercial_proof"].items() if key != "established")
    assert receipt["program_completion"]["leaf_predicates_satisfied"] == []
    assert receipt["program_completion"]["phase_predicate_satisfied"] is False
    assert receipt["program_completion"]["chunk_exit_gate_satisfied"] is False
    assert receipt["external_effects"] == []


def test_preflight_rejects_real_mode_or_effect_authority() -> None:
    _contract, fixture, state = _validated_inputs()
    real_mode = copy.deepcopy(fixture)
    real_mode["mode"] = "real"
    with pytest.raises(MODULE.ReadinessError, match="synthetic fixtures only"):
        MODULE.validate_fixture(real_mode, state)

    effectful = copy.deepcopy(fixture)
    effectful["authority_receipts"][0]["usable_for_real_effect"] = True
    with pytest.raises(MODULE.ReadinessError, match="cannot authorize a real effect"):
        MODULE.validate_fixture(effectful, state)


def test_synthetic_claim_refresh_is_never_applied_or_publishable() -> None:
    _contract, fixture, state = _validated_inputs()
    fixture_state = MODULE.validate_fixture(fixture, state)

    assert fixture_state["claim_proposal_count"] == 3
    assert {row["disposition"] for row in fixture["claim_refresh_proposals"]} == {
        "strengthen",
        "narrow",
        "invalidate",
    }
    assert all(row["apply"] is False for row in fixture["claim_refresh_proposals"])
    assert all(row["publishable"] is False for row in fixture["claim_refresh_proposals"])
    assert all(row["prominence"] == "nowhere" for row in fixture["claim_refresh_proposals"])


def test_registry_or_gate_drift_fails_closed() -> None:
    contract, _fixture, program, graph = MODULE.load_inputs()
    drifted = copy.deepcopy(contract)
    drifted["model_routing"]["leaves"]["PSP-P12-W05"]["effort"] = "high"
    with pytest.raises(MODULE.ReadinessError, match="PSP-P12-W05 model assignment drifted"):
        MODULE.validate_contract(drifted, program, graph)

    drifted = copy.deepcopy(contract)
    drifted["leaf_gate_matrix"]["PSP-P12-W04"] = ["HG-CONTRACT"]
    with pytest.raises(MODULE.ReadinessError, match="PSP-P12-W04 human gates drifted"):
        MODULE.validate_contract(drifted, program, graph)


def test_committed_receipt_is_the_deterministic_synthetic_run() -> None:
    result = MODULE.verify_receipt(RECEIPT)

    assert result["status"] == "ok"
    assert result["commercial_proof"] is False
    assert result["external_effects"] == []
