from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "positioning-c10-readiness.py"
RECEIPT = ROOT / "docs" / "receipts" / "positioning" / "preflights" / "2026-08-10-psp-c10-readiness-synthetic.json"


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
    assert state["leaf_dependencies"] == {
        "PSP-P12-W01": ["PSP-P09-W08", "PSP-P10-W01", "PSP-P11-W02"],
        "PSP-P12-W02": ["PSP-P12-W01", "PSP-P10-W05", "PSP-P11-W07"],
        "PSP-P12-W03": ["PSP-P12-W02", "PSP-P11-W04"],
        "PSP-P12-W04": ["PSP-P12-W02", "PSP-P11-W08"],
        "PSP-P12-W05": ["PSP-P12-W02"],
        "PSP-P12-W06": ["PSP-P12-W02", "PSP-P12-W04", "PSP-P12-W05", "PSP-P02-W08"],
        "PSP-P10-W08": ["PSP-P09-W08", "PSP-P10-W07", "PSP-P12-W02"],
    }
    for key in (
        "synthetic_counts_as_conversion",
        "synthetic_counts_as_revenue",
        "synthetic_counts_as_testimonial_or_reference",
        "prepared_dependency_counts_as_closed",
        "agent_or_synthetic_testimonial_counts_as_real",
    ):
        assert contract["truth_boundary"][key] is False


def test_synthetic_run_exercises_all_decisions_without_creating_proof() -> None:
    receipt = MODULE.build_receipt()

    decisions = {row["hypothetical_decision"] for row in receipt["scenario_results"].values()}
    assert decisions == {"keep", "narrow", "pivot", "insufficient_evidence"}
    assert receipt["operational_readiness"]["status"] == "synthetic_dry_run_pass"
    assert receipt["commercial_proof"]["established"] is False
    assert all(value == 0 for key, value in receipt["commercial_proof"].items() if key != "established")
    assert receipt["program_completion"]["leaf_predicates_satisfied"] == []
    assert receipt["program_completion"]["phase_predicate_satisfied"] is False
    assert receipt["program_completion"]["chunk_exit_gate_satisfied"] is False
    assert receipt["external_effects"] == []
    assert receipt["scenario_results"]["SYN-SCENARIO-BOUNDED-PILOT"]["hypothetical_decision"] == "insufficient_evidence"
    assert receipt["commercial_proof"]["real_conversions"] == 0
    assert receipt["commercial_proof"]["real_paid_audits"] == 0
    assert receipt["commercial_proof"]["real_bounded_pilots"] == 0
    assert receipt["commercial_proof"]["real_revenue_receipts"] == 0
    assert receipt["commercial_proof"]["real_testimonials_or_references"] == 0


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
    assert fixture["testimonial_objects"] == []


def test_paid_audit_requires_payment_and_bounded_pilot_cannot_prove_demand() -> None:
    _contract, fixture, state = _validated_inputs()
    bounded = next(row for row in fixture["outcomes"] if row["outcome_type"] == "explicitly_bounded_pilot")
    assert (
        MODULE.hypothetical_decision([bounded], state["qualified_threshold"], revision_recorded=False)
        == "insufficient_evidence"
    )

    paid = copy.deepcopy(next(row for row in fixture["outcomes"] if row["outcome_type"] == "paid_audit"))
    paid["payment_receipt_present"] = False
    assert (
        MODULE.hypothetical_decision([paid], state["qualified_threshold"], revision_recorded=False)
        == "insufficient_evidence"
    )

    bad_fixture = copy.deepcopy(fixture)
    next(row for row in bad_fixture["outcomes"] if row["outcome_type"] == "paid_audit")["payment_receipt_present"] = (
        False
    )
    with pytest.raises(MODULE.ReadinessError, match="paid audit lacks payment evidence"):
        MODULE.validate_fixture(bad_fixture, state)


def test_five_no_outcomes_require_a_recorded_revision() -> None:
    _contract, fixture, state = _validated_inputs()
    pivot = next(row for row in fixture["scenarios"] if row["scenario_id"] == "SYN-SCENARIO-PIVOT")
    outcomes = {row["outcome_id"]: row for row in fixture["outcomes"]}
    rows = [outcomes[outcome_id] for outcome_id in pivot["outcome_ids"]]
    assert (
        MODULE.hypothetical_decision(rows, state["qualified_threshold"], revision_recorded=False)
        == "insufficient_evidence"
    )
    assert MODULE.hypothetical_decision(rows, state["qualified_threshold"], revision_recorded=True) == "pivot"


def test_synthetic_testimonial_objects_fail_closed() -> None:
    _contract, fixture, state = _validated_inputs()
    drifted = copy.deepcopy(fixture)
    drifted["testimonial_objects"] = [{"author": "agent", "attributed_as_real": True}]
    with pytest.raises(MODULE.ReadinessError, match="testimonials may not be real objects"):
        MODULE.validate_fixture(drifted, state)


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

    drifted = copy.deepcopy(contract)
    drifted["leaf_dependency_matrix"]["PSP-P12-W06"] = ["PSP-P12-W02"]
    with pytest.raises(MODULE.ReadinessError, match="PSP-P12-W06 dependencies drifted"):
        MODULE.validate_contract(drifted, program, graph)


def test_receipt_binds_only_the_c10_registry_projection() -> None:
    contract, _fixture, program, graph = MODULE.load_inputs()
    original = MODULE.validate_contract(contract, program, graph)["registry_projection_sha256"]
    unrelated = copy.deepcopy(graph)
    unrelated["program"]["unrelated_test_note"] = "does not affect C10"
    assert MODULE.validate_contract(contract, program, unrelated)["registry_projection_sha256"] == original


def test_committed_receipt_is_the_deterministic_synthetic_run() -> None:
    result = MODULE.verify_receipt(RECEIPT)

    assert result["status"] == "ok"
    assert result["commercial_proof"] is False
    assert result["external_effects"] == []
