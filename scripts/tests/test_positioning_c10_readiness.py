from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import json
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
    assert state["conductor_assignment_requirement"]["effort"] == "max"
    assert state["conductor_assignment_requirement"]["selection"] == "runtime_catalog"
    assert state["leaf_assignment_requirements"]["PSP-P12-W05"] == {
        "selection": "runtime_catalog",
        "reasoning": "routine",
        "effect": "write",
        "effort": "medium",
        "capabilities": ["evidence_curation", "partner_coordination"],
    }
    assert state["leaf_assignment_requirements"]["PSP-P10-W08"] == {
        "selection": "runtime_catalog",
        "reasoning": "frontier_review",
        "effect": "write",
        "effort": "max",
        "capabilities": ["sales_analysis", "strategy", "decision_review"],
    }
    assert all(
        "slug" not in requirement and "model" not in requirement
        for requirement in [
            state["conductor_assignment_requirement"],
            *state["leaf_assignment_requirements"].values(),
        ]
    )
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
    assert len(state["leaf_contract_audit"]) == 7
    assert state["source_bindings"] == MODULE.EXPECTED_SOURCE_BINDINGS
    assert all(row["counts_as_closure"] is False for row in state["source_bindings"])
    assert all(row["acceptance"] and row["predicate"] and row["target_paths"] for row in state["leaf_contract_audit"])
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
    assert receipt["commercial_proof"]["real_public_case_studies"] == 0
    assert receipt["registry_audit"]["all_owned_leaves_audited"] is True


def test_recruitment_packages_remain_unsent_unagreed_and_non_effectful() -> None:
    _contract, fixture, state = _validated_inputs()
    fixture_state = MODULE.validate_fixture(fixture, state)

    assert len(fixture_state["recruitment_by_id"]) == 5
    assert all(row["invitation_status"] == "not_sent" for row in fixture["recruitment_records"])
    assert all(row["send_receipt_id"] is None for row in fixture["recruitment_records"])
    assert all(row["terms_status"] == "not_agreed" for row in fixture["recruitment_records"])
    assert all(row["usable_for_real_effect"] is False for row in fixture["recruitment_records"])


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
    paid["payment_receipt_id"] = None
    assert (
        MODULE.hypothetical_decision([paid], state["qualified_threshold"], revision_recorded=False)
        == "insufficient_evidence"
    )

    bad_fixture = copy.deepcopy(fixture)
    next(row for row in bad_fixture["outcomes"] if row["outcome_type"] == "paid_audit")["payment_receipt_id"] = None
    with pytest.raises(MODULE.ReadinessError, match="paid audit lacks payment evidence"):
        MODULE.validate_fixture(bad_fixture, state)


def test_typed_commercial_receipts_and_publication_gates_fail_closed() -> None:
    _contract, fixture, state = _validated_inputs()

    drifted = copy.deepcopy(fixture)
    drifted["payment_receipts"][0]["payment_status"] = "received"
    with pytest.raises(MODULE.ReadinessError, match="may not claim payment"):
        MODULE.validate_fixture(drifted, state)

    drifted = copy.deepcopy(fixture)
    drifted["acceptance_receipts"][0]["decision"] = "accepted"
    with pytest.raises(MODULE.ReadinessError, match="may not claim client acceptance"):
        MODULE.validate_fixture(drifted, state)

    drifted = copy.deepcopy(fixture)
    drifted["delivery_receipts"][0]["delivery_status"] = "delivered"
    with pytest.raises(MODULE.ReadinessError, match="may not claim real delivery"):
        MODULE.validate_fixture(drifted, state)

    drifted = copy.deepcopy(fixture)
    drifted["case_study_receipts"][0]["publication_status"] = "published"
    with pytest.raises(MODULE.ReadinessError, match="may not record publication"):
        MODULE.validate_fixture(drifted, state)

    drifted = copy.deepcopy(fixture)
    drifted["claim_promotion_receipts"][0]["promotion_status"] = "applied"
    with pytest.raises(MODULE.ReadinessError, match="may not promote claims"):
        MODULE.validate_fixture(drifted, state)


def test_strategy_decisions_record_before_and_after_without_application() -> None:
    _contract, fixture, state = _validated_inputs()
    fixture_state = MODULE.validate_fixture(fixture, state)

    assert set(fixture_state["decision_by_scenario"]) == {row["scenario_id"] for row in fixture["scenarios"]}
    assert all(row["before_strategy"] and row["after_strategy"] for row in fixture["strategy_decision_records"])
    assert all(row["external_outcome_evidence_ids"] == [] for row in fixture["strategy_decision_records"])
    assert all(row["apply"] is False for row in fixture["strategy_decision_records"])
    assert all(row["publishable"] is False for row in fixture["strategy_decision_records"])


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
    drifted["assignment_requirements"]["leaves"]["PSP-P12-W05"]["effort"] = "high"
    with pytest.raises(MODULE.ReadinessError, match="PSP-P12-W05 assignment requirements drifted"):
        MODULE.validate_contract(drifted, program, graph)

    drifted = copy.deepcopy(contract)
    drifted["leaf_gate_matrix"]["PSP-P12-W04"] = ["HG-CONTRACT"]
    with pytest.raises(MODULE.ReadinessError, match="PSP-P12-W04 human gates drifted"):
        MODULE.validate_contract(drifted, program, graph)

    drifted = copy.deepcopy(contract)
    drifted["leaf_dependency_matrix"]["PSP-P12-W06"] = ["PSP-P12-W02"]
    with pytest.raises(MODULE.ReadinessError, match="PSP-P12-W06 dependencies drifted"):
        MODULE.validate_contract(drifted, program, graph)

    drifted = copy.deepcopy(contract)
    drifted["source_bindings"][2]["integrated_main_head"] = "0" * 40
    with pytest.raises(MODULE.ReadinessError, match="C10 source bindings drifted"):
        MODULE.validate_contract(drifted, program, graph)

    drifted = copy.deepcopy(contract)
    drifted["authorization"] = "unchecked-extra-field"
    with pytest.raises(MODULE.ReadinessError, match="exact root schema"):
        MODULE.validate_contract(drifted, program, graph)

    drifted = copy.deepcopy(contract)
    drifted["source_bindings"][0]["counts_as_closure"] = True
    with pytest.raises(MODULE.ReadinessError, match="C10 source bindings drifted"):
        MODULE.validate_contract(drifted, program, graph)


def test_duplicate_yaml_and_json_members_fail_closed(tmp_path: Path) -> None:
    contract_path = tmp_path / "protocol.yaml"
    contract_raw = MODULE.DEFAULT_CONTRACT.read_text(encoding="utf-8")
    contract_path.write_text(
        contract_raw.replace("mode: preflight_only", "mode: hidden\nmode: preflight_only", 1),
        encoding="utf-8",
    )
    with pytest.raises(MODULE.ReadinessError, match="duplicate key 'mode'"):
        MODULE.load_inputs(contract_path=contract_path)

    fixture_path = tmp_path / "fixture.json"
    fixture_raw = MODULE.DEFAULT_FIXTURE.read_text(encoding="utf-8")
    fixture_path.write_text(
        fixture_raw.replace('"mode": "synthetic",', '"mode": "hidden",\n  "mode": "synthetic",', 1),
        encoding="utf-8",
    )
    with pytest.raises(MODULE.ReadinessError, match="duplicate JSON member: mode"):
        MODULE.load_inputs(fixture_path=fixture_path)


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
    observed = json.loads(RECEIPT.read_text(encoding="utf-8"))
    assert observed["bindings"]["source_bindings"] == MODULE.EXPECTED_SOURCE_BINDINGS


def test_receipt_writer_generates_the_deterministic_synthetic_run(tmp_path: Path) -> None:
    receipt_path = tmp_path / "generated-receipt.json"

    result = MODULE.write_receipt(receipt_path)

    assert result["status"] == "written"
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == MODULE.build_receipt()
    assert MODULE.verify_receipt(receipt_path)["status"] == "ok"
