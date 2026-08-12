#!/usr/bin/env python3
"""Validate PSP-C10 reversible readiness without creating commercial proof.

This tool accepts synthetic fixtures only. It exercises recruitment, authority,
pilot, evidence, adjudication, claim-refresh, and 90-day experiment contracts,
but it cannot send, agree terms, accept payment, deliver, publish, or close a
PSP leaf. The tracked Production-Systems Program remains authoritative.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import re
import sys
from types import ModuleType
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT = ROOT / "docs" / "positioning" / "program" / "psp-c10-readiness" / "protocol.yaml"
DEFAULT_FIXTURE = ROOT / "docs" / "positioning" / "program" / "psp-c10-readiness" / "synthetic-fixture.json"
DEFAULT_RECEIPT = (
    ROOT
    / "docs"
    / "receipts"
    / "positioning"
    / "preflights"
    / "2026-08-10-psp-c10-readiness-synthetic.json"
)
PROGRAM_SCRIPT = ROOT / "scripts" / "positioning-program.py"
PROGRAM_MANIFEST = ROOT / "institutio" / "positioning" / "program.yaml"
CONTRACT_SCHEMA = "limen.positioning_c10_readiness.v3"
FIXTURE_SCHEMA = "limen.positioning_c10_synthetic_fixture.v3"
RECEIPT_SCHEMA = "limen.positioning_c10_synthetic_receipt.v3"
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class ReadinessError(RuntimeError):
    """Raised when the preflight contract or fixture fails closed."""


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ReadinessError(f"cannot load YAML {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(f"{path} must contain a mapping")
    return value


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ReadinessError(f"{path} must contain a mapping")
    return value


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ReadinessError(message)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReadinessError(f"{label} must be a mapping")
    return value


def _list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReadinessError(f"{label} must be a list")
    return value


def _load_program_module() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("positioning_program_c10", str(PROGRAM_SCRIPT))
    spec = importlib.util.spec_from_loader("positioning_program_c10", loader)
    if spec is None:
        raise ReadinessError("cannot construct positioning-program module spec")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def load_inputs(
    contract_path: Path = DEFAULT_CONTRACT,
    fixture_path: Path = DEFAULT_FIXTURE,
) -> tuple[dict[str, Any], dict[str, Any], ModuleType, dict[str, Any]]:
    contract = _load_yaml(contract_path)
    fixture = _load_json(fixture_path)
    program = _load_program_module()
    try:
        graph = program.index_program(program.load_manifest(PROGRAM_MANIFEST))
    except program.ProgramError as exc:
        raise ReadinessError(str(exc)) from exc
    return contract, fixture, program, graph


def _assignment_pair(row: dict[str, Any]) -> dict[str, str]:
    return {"slug": str(row["slug"]), "effort": str(row["effort"])}


def _registry_projection(
    program: ModuleType,
    graph: dict[str, Any],
    chunk_id: str,
    work_ids: list[str],
) -> dict[str, Any]:
    chunk = graph["chunk_by_id"][chunk_id]
    return {
        "success_90_day": dict(graph["program"]["success_90_day"]),
        "chunk": {
            "id": chunk_id,
            "depends_on": list(chunk["depends_on"]),
            "phase_ids": list(chunk["phase_ids"]),
            "exclude_work_ids": list(chunk["exclude_work_ids"]),
            "extra_work_ids": list(chunk["extra_work_ids"]),
            "objective": str(chunk["objective"]),
            "exit_gate": str(chunk["exit_gate"]),
            "assignment": _assignment_pair(program.chunk_assignment_for(chunk_id, graph)),
        },
        "work": [
            {
                "id": work_id,
                "title": str(graph["work_by_id"][work_id]["title"]),
                "depends_on": list(graph["work_by_id"][work_id]["depends_on"]),
                "human_gates": list(graph["work_by_id"][work_id]["human_gates"]),
                "target_repo": str(graph["work_by_id"][work_id]["target_repo"]),
                "target_paths": list(graph["work_by_id"][work_id]["target_paths"]),
                "capabilities": list(graph["work_by_id"][work_id]["capabilities"]),
                "effect": str(graph["work_by_id"][work_id]["effect"]),
                "acceptance": str(graph["work_by_id"][work_id]["acceptance"]),
                "predicate": str(graph["work_by_id"][work_id]["predicate"]),
                "assignment": _assignment_pair(program.model_assignment_for(work_id, graph)),
            }
            for work_id in work_ids
        ],
    }


def validate_contract(
    contract: dict[str, Any],
    program: ModuleType,
    graph: dict[str, Any],
) -> dict[str, Any]:
    _expect(contract.get("schema_version") == CONTRACT_SCHEMA, "unsupported C10 readiness contract schema")
    _expect(contract.get("mode") == "preflight_only", "C10 readiness contract must be preflight_only")

    scope = _mapping(contract.get("scope"), "scope")
    chunk_id = str(scope.get("chunk_id") or "")
    _expect(chunk_id == "PSP-C10", "scope.chunk_id must be PSP-C10")
    expected_leaves = list(graph["chunk_work"][chunk_id])
    _expect(scope.get("leaf_ids") == expected_leaves, "scope.leaf_ids drifted from the PSP-C10 registry")
    _expect(scope.get("phase_ids") == ["PSP-P12"], "scope.phase_ids must contain only PSP-P12")
    _expect(scope.get("extra_work_ids") == ["PSP-P10-W08"], "scope.extra_work_ids must contain PSP-P10-W08")
    _expect(
        scope.get("formal_predecessor_chunks") == list(graph["chunk_by_id"][chunk_id]["depends_on"]),
        "formal predecessor chunks drifted from the registry",
    )

    truth = _mapping(contract.get("truth_boundary"), "truth_boundary")
    required_false = {
        "synthetic_closes_leaf",
        "synthetic_closes_phase",
        "synthetic_closes_chunk",
        "synthetic_counts_as_outreach",
        "synthetic_counts_as_payment",
        "synthetic_counts_as_conversion",
        "synthetic_counts_as_revenue",
        "synthetic_counts_as_testimonial_or_reference",
        "synthetic_counts_as_delivery_acceptance",
        "synthetic_counts_as_external_outcome",
        "synthetic_can_refresh_public_claims",
        "prepared_dependency_counts_as_closed",
        "agent_or_synthetic_testimonial_counts_as_real",
    }
    for key in required_false:
        _expect(truth.get(key) is False, f"truth_boundary.{key} must remain false")

    routing = _mapping(contract.get("model_routing"), "model_routing")
    _expect(routing.get("exact_assignment_required") is True, "exact model assignments must remain required")
    conductor = program.chunk_assignment_for(chunk_id, graph)
    _expect(
        routing.get("conductor") == _assignment_pair(conductor),
        "PSP-C10 conductor assignment drifted from the registry",
    )
    leaf_assignments: dict[str, dict[str, str]] = {}
    configured_leaves = _mapping(routing.get("leaves"), "model_routing.leaves")
    for work_id in expected_leaves:
        assignment = program.model_assignment_for(work_id, graph)
        pair = _assignment_pair(assignment)
        _expect(configured_leaves.get(work_id) == pair, f"{work_id} model assignment drifted from the registry")
        leaf_assignments[work_id] = pair
    _expect(set(configured_leaves) == set(expected_leaves), "model_routing.leaves contains extra or missing work IDs")

    gate_matrix = _mapping(contract.get("leaf_gate_matrix"), "leaf_gate_matrix")
    _expect(set(gate_matrix) == set(expected_leaves), "leaf_gate_matrix contains extra or missing work IDs")
    for work_id in expected_leaves:
        expected_gates = list(graph["work_by_id"][work_id]["human_gates"])
        _expect(gate_matrix.get(work_id) == expected_gates, f"{work_id} human gates drifted from the registry")

    dependency_matrix = _mapping(contract.get("leaf_dependency_matrix"), "leaf_dependency_matrix")
    _expect(set(dependency_matrix) == set(expected_leaves), "leaf_dependency_matrix contains extra or missing work IDs")
    for work_id in expected_leaves:
        expected_dependencies = list(graph["work_by_id"][work_id]["depends_on"])
        _expect(
            dependency_matrix.get(work_id) == expected_dependencies,
            f"{work_id} dependencies drifted from the registry",
        )

    recruitment = _mapping(contract.get("recruitment"), "recruitment")
    _expect(recruitment.get("cohort_limit") == 3, "recruitment.cohort_limit must preserve the W01 bound of three")
    success_90_day = _mapping(graph["program"].get("success_90_day"), "program.success_90_day")
    threshold = int(success_90_day["qualified_door_mails"])
    _expect(
        recruitment.get("qualified_door_mail_threshold") == threshold,
        "recruitment threshold drifted from program.success_90_day",
    )
    criteria = _list(recruitment.get("required_criteria"), "recruitment.required_criteria")
    criterion_ids = [str(_mapping(row, "recruitment criterion").get("id") or "") for row in criteria]
    _expect(len(criterion_ids) == len(set(criterion_ids)) >= 1, "recruitment criteria IDs must be unique")
    exclusions = _list(recruitment.get("hard_exclusions"), "recruitment.hard_exclusions")
    exclusion_ids = [str(_mapping(row, "recruitment exclusion").get("id") or "") for row in exclusions]
    _expect(len(exclusion_ids) == len(set(exclusion_ids)) >= 1, "recruitment exclusion IDs must be unique")
    recruitment_package = _mapping(recruitment.get("package_contract"), "recruitment.package_contract")
    recruitment_fields = [
        str(item) for item in _list(recruitment_package.get("required_fields"), "recruitment package fields")
    ]
    _expect(len(recruitment_fields) == len(set(recruitment_fields)), "recruitment package fields must be unique")
    _expect(
        recruitment_package.get("synthetic_invitation_status") == "not_sent",
        "synthetic recruitment invitation status must remain not_sent",
    )
    _expect(
        recruitment_package.get("synthetic_terms_status") == "not_agreed",
        "synthetic recruitment terms status must remain not_agreed",
    )

    receipts = _mapping(contract.get("receipt_contracts"), "receipt_contracts")
    authority_contract = _mapping(receipts.get("authority"), "receipt_contracts.authority")
    consent_contract = _mapping(receipts.get("consent"), "receipt_contracts.consent")
    payment_contract = _mapping(receipts.get("payment"), "receipt_contracts.payment")
    acceptance_contract = _mapping(receipts.get("acceptance"), "receipt_contracts.acceptance")
    delivery_contract = _mapping(receipts.get("delivery"), "receipt_contracts.delivery")
    case_study_contract = _mapping(receipts.get("case_study"), "receipt_contracts.case_study")
    claim_promotion_contract = _mapping(receipts.get("claim_promotion"), "receipt_contracts.claim_promotion")
    expected_gate_ids = sorted({gate for gates in gate_matrix.values() for gate in gates})
    _expect(sorted(authority_contract.get("gate_ids") or []) == expected_gate_ids, "authority gate catalog drifted")
    _expect(authority_contract.get("synthetic_decision") == "fixture_only", "synthetic authority must be fixture_only")
    _expect(consent_contract.get("synthetic_decision") == "fixture_only", "synthetic consent must be fixture_only")
    _expect(payment_contract.get("synthetic_status") == "fixture_only", "synthetic payment must be fixture_only")
    _expect(
        payment_contract.get("public_fixture_amount_disclosure") == "not_recorded",
        "synthetic payment fixtures may not record an amount",
    )
    _expect(
        acceptance_contract.get("synthetic_decision") == "fixture_only",
        "synthetic acceptance must be fixture_only",
    )
    _expect(delivery_contract.get("synthetic_status") == "fixture_only", "synthetic delivery must be fixture_only")
    _expect(
        case_study_contract.get("synthetic_publication_status") == "not_published",
        "synthetic case studies must remain unpublished",
    )
    _expect(
        claim_promotion_contract.get("synthetic_promotion_status") == "blocked_synthetic",
        "synthetic claim promotion must remain blocked",
    )
    receipt_family_fields: dict[str, list[str]] = {}
    for name, family in (
        ("payment", payment_contract),
        ("acceptance", acceptance_contract),
        ("delivery", delivery_contract),
        ("case_study", case_study_contract),
        ("claim_promotion", claim_promotion_contract),
    ):
        fields = [str(item) for item in _list(family.get("required_fields"), f"{name} required fields")]
        _expect(len(fields) == len(set(fields)), f"{name} required fields must be unique")
        receipt_family_fields[name] = fields

    pilot = _mapping(contract.get("bounded_pilot"), "bounded_pilot")
    _expect(pilot.get("active_engagement_limit") == 1, "bounded pilot must allow at most one active engagement")
    _expect(pilot.get("team_limit") == 1, "bounded pilot must remain one-team scoped")
    stages = _list(pilot.get("stages"), "bounded_pilot.stages")
    stage_ids: list[str] = []
    effectful = {"send", "contract", "delivery", "delivery_acceptance", "publish"}
    for raw_stage in stages:
        stage = _mapping(raw_stage, "bounded pilot stage")
        stage_id = str(stage.get("id") or "")
        stage_ids.append(stage_id)
        work_ids = _list(stage.get("work_ids"), f"stage {stage_id}.work_ids")
        _expect(work_ids and set(work_ids) <= set(expected_leaves), f"stage {stage_id} escapes PSP-C10 scope")
        human_gates = _list(stage.get("human_gates"), f"stage {stage_id}.human_gates")
        _expect(set(human_gates) <= set(expected_gate_ids), f"stage {stage_id} names an unknown human gate")
        if stage.get("real_effect") in effectful:
            _expect(bool(human_gates), f"effectful stage {stage_id} must fail closed behind a human gate")
        _expect(bool(stage.get("evidence")), f"stage {stage_id} must name return evidence")
    _expect(len(stage_ids) == len(set(stage_ids)) >= 1, "bounded pilot stage IDs must be unique")

    evidence = _mapping(contract.get("evidence_capture"), "evidence_capture")
    evidence_fields = [str(item) for item in _list(evidence.get("required_fields"), "evidence required fields")]
    _expect(len(evidence_fields) == len(set(evidence_fields)), "evidence required fields must be unique")
    _expect("synthetic" in str(evidence.get("synthetic_visibility")), "synthetic visibility must be explicit")

    adjudication = _mapping(contract.get("outcome_adjudication"), "outcome_adjudication")
    paid_path = _mapping(adjudication.get("paid_path"), "outcome_adjudication.paid_path")
    _expect(paid_path.get("minimum_paid_audits") == 1, "paid-audit threshold must remain one")
    _expect(paid_path.get("requires_payment_receipt") is True, "paid audits require payment evidence")
    bounded_path = _mapping(adjudication.get("bounded_pilot_path"), "outcome_adjudication.bounded_pilot_path")
    for key in ("satisfies_p10_w08", "counts_as_conversion", "counts_as_revenue", "counts_as_commercial_proof"):
        _expect(bounded_path.get(key) is False, f"bounded_pilot_path.{key} must remain false")
    no_path = _mapping(adjudication.get("no_path"), "outcome_adjudication.no_path")
    _expect(
        no_path.get("minimum_unique_qualified_no_outcomes") == threshold,
        "no-outcome decision threshold drifted from program.success_90_day",
    )
    _expect(no_path.get("revision_receipt_required") is True, "five no-outcomes require a recorded revision")
    _expect(
        adjudication.get("decisions") == ["keep", "narrow", "pivot", "insufficient_evidence"],
        "adjudication decisions must preserve keep/narrow/pivot and insufficient evidence",
    )
    _expect(
        adjudication.get("synthetic_decisions_are_hypothetical") is True, "synthetic decisions must be hypothetical"
    )

    claims = _mapping(contract.get("claim_refresh"), "claim_refresh")
    _expect(claims.get("dispositions") == ["strengthen", "narrow", "invalidate"], "claim dispositions drifted")
    _expect(claims.get("synthetic_apply") is False, "synthetic claim changes must never apply")
    _expect(claims.get("synthetic_publishable") is False, "synthetic claim changes must never publish")

    decisions = _mapping(contract.get("strategy_decision_records"), "strategy_decision_records")
    decision_fields = [
        str(item) for item in _list(decisions.get("required_fields"), "strategy decision required fields")
    ]
    _expect(len(decision_fields) == len(set(decision_fields)), "strategy decision fields must be unique")
    for key in ("synthetic_apply", "synthetic_publishable", "synthetic_real_effect"):
        _expect(decisions.get(key) is False, f"strategy_decision_records.{key} must remain false")

    testimonial_policy = _mapping(contract.get("testimonial_reference_policy"), "testimonial_reference_policy")
    _expect(
        testimonial_policy.get("synthetic_or_agent_authored_objects_forbidden") is True,
        "synthetic or agent-authored testimonial objects must remain forbidden",
    )
    _expect(
        testimonial_policy.get("attribution_requires_real_human_source") is True,
        "testimonial attribution must require a real human source",
    )
    _expect(
        testimonial_policy.get("preflight_collection_status") == "not_attempted",
        "preflight testimonial collection status must remain not_attempted",
    )

    experiment = _mapping(contract.get("experiment_90_day"), "experiment_90_day")
    _expect(experiment.get("duration_days") == 90, "experiment duration must remain 90 days")
    _expect(experiment.get("denominator_threshold") == threshold, "experiment denominator threshold drifted")
    required_outcome_fields = _list(experiment.get("required_outcome_fields"), "experiment outcome fields")
    _expect(
        set(required_outcome_fields)
        == {
            "candidate_id",
            "qualification_receipt",
            "outcome_type",
            "reason",
            "terms_authority_receipt_id",
            "payment_receipt_id",
            "acceptance_receipt_id",
            "delivery_receipt_ids",
            "evidence_ids",
            "occurred_at",
        },
        "90-day experiment outcome fields drifted",
    )
    extension = _mapping(experiment.get("extension"), "experiment_90_day.extension")
    _expect(extension.get("maximum_count") == 1, "90-day experiment extension must be single-use")
    _expect(extension.get("may_not_reduce_thresholds") is True, "extension may not weaken evidence thresholds")
    terminal = _mapping(experiment.get("terminal_receipt"), "experiment_90_day.terminal_receipt")
    _expect(
        terminal.get("synthetic_terminal_receipt_forbidden") is True, "synthetic terminal receipts must be forbidden"
    )

    registry_projection = _registry_projection(program, graph, chunk_id, expected_leaves)
    for leaf in registry_projection["work"]:
        work_id = leaf["id"]
        _expect(bool(leaf["title"]), f"{work_id} title is empty")
        _expect(bool(leaf["target_paths"]), f"{work_id} target paths are empty")
        _expect(bool(leaf["capabilities"]), f"{work_id} capabilities are empty")
        _expect(bool(leaf["acceptance"]), f"{work_id} acceptance is empty")
        _expect(bool(leaf["predicate"]), f"{work_id} predicate is empty")

    return {
        "chunk_id": chunk_id,
        "leaf_ids": expected_leaves,
        "criterion_ids": criterion_ids,
        "exclusion_ids": exclusion_ids,
        "gate_ids": expected_gate_ids,
        "conductor_assignment": _assignment_pair(conductor),
        "leaf_assignments": leaf_assignments,
        "qualified_threshold": threshold,
        "authority_required_fields": list(authority_contract["required_fields"]),
        "consent_required_fields": list(consent_contract["required_fields"]),
        "consent_types": list(consent_contract["consent_types"]),
        "recruitment_required_fields": recruitment_fields,
        "recruitment_cohort_dispositions": list(recruitment_package["cohort_dispositions"]),
        "receipt_family_fields": receipt_family_fields,
        "evidence_required_fields": evidence_fields,
        "evidence_classes": list(evidence["evidence_classes"]),
        "stage_ids": stage_ids,
        "leaf_dependencies": {work_id: list(dependency_matrix[work_id]) for work_id in expected_leaves},
        "leaf_contract_audit": list(registry_projection["work"]),
        "strategy_decision_required_fields": decision_fields,
        "registry_projection_sha256": _sha256_json(registry_projection),
    }


def _validate_fixture_receipts(
    fixture: dict[str, Any],
    contract_state: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    authority_rows = _list(fixture.get("authority_receipts"), "authority_receipts")
    authority_by_id: dict[str, dict[str, Any]] = {}
    seen_gates: set[str] = set()
    for raw in authority_rows:
        row = _mapping(raw, "authority receipt")
        missing = set(contract_state["authority_required_fields"]) - set(row)
        _expect(not missing, f"authority receipt is missing fields: {sorted(missing)}")
        receipt_id = str(row["receipt_id"])
        _expect(receipt_id.startswith("SYN-AUTH-"), "synthetic authority receipt IDs must use SYN-AUTH-")
        _expect(receipt_id not in authority_by_id, f"duplicate authority receipt {receipt_id}")
        _expect(row.get("mode") == "synthetic", f"{receipt_id} must remain synthetic")
        _expect(row.get("gate_id") in contract_state["gate_ids"], f"{receipt_id} names an unknown gate")
        _expect(row.get("decision") == "fixture_only", f"{receipt_id} cannot grant real authority")
        _expect(row.get("usable_for_real_effect") is False, f"{receipt_id} cannot authorize a real effect")
        _expect(
            str(row.get("evidence_locator") or "").startswith("fixture://"), f"{receipt_id} must use fixture evidence"
        )
        _expect(
            SHA256_RE.fullmatch(str(row.get("exact_artifact_sha256") or "")) is not None,
            f"{receipt_id} digest is invalid",
        )
        authority_by_id[receipt_id] = row
        seen_gates.add(str(row["gate_id"]))
    _expect(seen_gates == set(contract_state["gate_ids"]), "fixture must exercise every human gate without granting it")

    consent_rows = _list(fixture.get("consent_receipts"), "consent_receipts")
    consent_by_id: dict[str, dict[str, Any]] = {}
    seen_types: set[str] = set()
    for raw in consent_rows:
        row = _mapping(raw, "consent receipt")
        missing = set(contract_state["consent_required_fields"]) - set(row)
        _expect(not missing, f"consent receipt is missing fields: {sorted(missing)}")
        receipt_id = str(row["receipt_id"])
        _expect(receipt_id.startswith("SYN-CONSENT-"), "synthetic consent receipt IDs must use SYN-CONSENT-")
        _expect(receipt_id not in consent_by_id, f"duplicate consent receipt {receipt_id}")
        _expect(row.get("mode") == "synthetic", f"{receipt_id} must remain synthetic")
        _expect(row.get("consent_type") in contract_state["consent_types"], f"{receipt_id} has unknown consent type")
        _expect(row.get("decision") == "fixture_only", f"{receipt_id} cannot grant real consent")
        _expect(row.get("usable_for_real_effect") is False, f"{receipt_id} cannot authorize a real effect")
        _expect(
            str(row.get("evidence_locator") or "").startswith("fixture://"), f"{receipt_id} must use fixture evidence"
        )
        consent_by_id[receipt_id] = row
        seen_types.add(str(row["consent_type"]))
    _expect(seen_types == set(contract_state["consent_types"]), "fixture must exercise every consent receipt type")
    return authority_by_id, consent_by_id


def validate_fixture(fixture: dict[str, Any], contract_state: dict[str, Any]) -> dict[str, Any]:
    _expect(fixture.get("schema_version") == FIXTURE_SCHEMA, "unsupported C10 synthetic fixture schema")
    _expect(fixture.get("mode") == "synthetic", "preflight validator accepts synthetic fixtures only")
    _expect(fixture.get("contains_real_identity") is False, "synthetic fixture may not contain a real identity")
    _expect(fixture.get("contains_private_evidence") is False, "synthetic fixture may not contain private evidence")
    _expect(fixture.get("real_world_assertions") is False, "synthetic fixture may not assert real-world outcomes")
    _expect(fixture.get("external_effects") == [], "synthetic fixture may not record external effects")
    _expect(
        fixture.get("testimonial_objects") == [], "synthetic or agent-authored testimonials may not be real objects"
    )
    serialized = json.dumps(fixture, sort_keys=True)
    _expect("@" not in serialized, "synthetic fixture must not contain email-like personal identifiers")

    candidates = _list(fixture.get("candidates"), "candidates")
    candidate_by_id: dict[str, dict[str, Any]] = {}
    for raw in candidates:
        row = _mapping(raw, "candidate")
        candidate_id = str(row.get("candidate_id") or "")
        _expect(candidate_id.startswith("SYN-DM-"), "synthetic candidate IDs must use SYN-DM-")
        _expect(candidate_id not in candidate_by_id, f"duplicate candidate {candidate_id}")
        criteria = _mapping(row.get("criteria"), f"candidate {candidate_id}.criteria")
        _expect(set(criteria) == set(contract_state["criterion_ids"]), f"candidate {candidate_id} criteria drifted")
        _expect(
            all(value is True for value in criteria.values()), f"candidate {candidate_id} must qualify in the fixture"
        )
        candidate_by_id[candidate_id] = row
    _expect(
        len(candidate_by_id) >= contract_state["qualified_threshold"],
        "fixture must exercise the full qualified denominator threshold",
    )
    cohort = _list(fixture.get("cohort_selected"), "cohort_selected")
    _expect(len(cohort) <= 3, "synthetic cohort exceeds the W01 limit")
    _expect(len(cohort) == len(set(cohort)), "synthetic cohort IDs must be unique")
    _expect(set(cohort) <= set(candidate_by_id), "synthetic cohort references an unknown candidate")

    recruitment_rows = _list(fixture.get("recruitment_records"), "recruitment_records")
    recruitment_by_id: dict[str, dict[str, Any]] = {}
    recruitment_by_candidate: dict[str, dict[str, Any]] = {}
    for raw in recruitment_rows:
        row = _mapping(raw, "recruitment record")
        missing = set(contract_state["recruitment_required_fields"]) - set(row)
        _expect(not missing, f"recruitment record is missing fields: {sorted(missing)}")
        record_id = str(row["recruitment_record_id"])
        candidate_id = str(row["candidate_id"])
        _expect(record_id.startswith("SYN-RECRUIT-"), "synthetic recruitment IDs must use SYN-RECRUIT-")
        _expect(record_id not in recruitment_by_id, f"duplicate recruitment record {record_id}")
        _expect(candidate_id in candidate_by_id, f"{record_id} references unknown candidate {candidate_id}")
        _expect(candidate_id not in recruitment_by_candidate, f"duplicate recruitment candidate {candidate_id}")
        _expect(row.get("mode") == "synthetic", f"{record_id} must remain synthetic")
        _expect(
            str(row.get("qualification_receipt_id") or "").startswith("SYN-QUAL-"),
            f"{record_id} lacks a synthetic qualification receipt",
        )
        criteria = _mapping(row.get("criteria"), f"{record_id}.criteria")
        _expect(criteria == candidate_by_id[candidate_id]["criteria"], f"{record_id} criteria drifted from candidate")
        exclusions = _mapping(row.get("exclusion_results"), f"{record_id}.exclusion_results")
        _expect(set(exclusions) == set(contract_state["exclusion_ids"]), f"{record_id} exclusions drifted")
        _expect(all(value is False for value in exclusions.values()), f"{record_id} exercises an exclusion")
        _expect(
            row.get("cohort_disposition") in contract_state["recruitment_cohort_dispositions"],
            f"{record_id} has an unknown cohort disposition",
        )
        _expect(
            SHA256_RE.fullmatch(str(row.get("invitation_artifact_sha256") or "")) is not None,
            f"{record_id} invitation digest is invalid",
        )
        _expect(row.get("invitation_status") == "not_sent", f"{record_id} may not record an invitation send")
        _expect(row.get("send_receipt_id") is None, f"{record_id} may not carry a synthetic send receipt")
        _expect(row.get("terms_status") == "not_agreed", f"{record_id} may not record agreed terms")
        _expect(row.get("usable_for_real_effect") is False, f"{record_id} cannot authorize a real effect")
        recruitment_by_id[record_id] = row
        recruitment_by_candidate[candidate_id] = row
    _expect(
        set(recruitment_by_candidate) == set(candidate_by_id),
        "fixture must provide exactly one recruitment record per candidate",
    )
    selected_recruitment = [
        row for row in recruitment_by_id.values() if row["cohort_disposition"] == "selected"
    ]
    _expect(
        {str(row["candidate_id"]) for row in selected_recruitment} == set(cohort),
        "selected recruitment records drifted from cohort_selected",
    )
    _expect(
        sorted(row["cohort_slot"] for row in selected_recruitment) == list(range(1, len(cohort) + 1)),
        "selected recruitment cohort slots must be consecutive",
    )
    for row in recruitment_by_id.values():
        if row["cohort_disposition"] != "selected":
            _expect(row.get("cohort_slot") is None, f"{row['recruitment_record_id']} non-selected slot must be null")

    authority_by_id, consent_by_id = _validate_fixture_receipts(fixture, contract_state)

    payment_rows = _list(fixture.get("payment_receipts"), "payment_receipts")
    payment_by_id: dict[str, dict[str, Any]] = {}
    for raw in payment_rows:
        row = _mapping(raw, "payment receipt")
        missing = set(contract_state["receipt_family_fields"]["payment"]) - set(row)
        _expect(not missing, f"payment receipt is missing fields: {sorted(missing)}")
        receipt_id = str(row["receipt_id"])
        _expect(receipt_id.startswith("SYN-PAY-"), "synthetic payment IDs must use SYN-PAY-")
        _expect(receipt_id not in payment_by_id, f"duplicate payment receipt {receipt_id}")
        _expect(row.get("mode") == "synthetic", f"{receipt_id} must remain synthetic")
        _expect(row.get("candidate_id") in candidate_by_id, f"{receipt_id} references an unknown candidate")
        _expect(row.get("payment_status") == "fixture_only", f"{receipt_id} may not claim payment")
        _expect(row.get("amount_disclosure") == "not_recorded", f"{receipt_id} may not record a fixture amount")
        _expect(row.get("currency_disclosure") == "not_recorded", f"{receipt_id} may not record fixture currency")
        _expect(str(row.get("source_locator") or "").startswith("fixture://"), f"{receipt_id} source must be fixture")
        _expect(SHA256_RE.fullmatch(str(row.get("content_sha256") or "")) is not None, f"{receipt_id} digest invalid")
        _expect(row.get("usable_for_real_effect") is False, f"{receipt_id} cannot evidence real payment")
        payment_by_id[receipt_id] = row

    acceptance_rows = _list(fixture.get("acceptance_receipts"), "acceptance_receipts")
    acceptance_by_id: dict[str, dict[str, Any]] = {}
    for raw in acceptance_rows:
        row = _mapping(raw, "acceptance receipt")
        missing = set(contract_state["receipt_family_fields"]["acceptance"]) - set(row)
        _expect(not missing, f"acceptance receipt is missing fields: {sorted(missing)}")
        receipt_id = str(row["receipt_id"])
        _expect(receipt_id.startswith("SYN-ACCEPT-"), "synthetic acceptance IDs must use SYN-ACCEPT-")
        _expect(receipt_id not in acceptance_by_id, f"duplicate acceptance receipt {receipt_id}")
        _expect(row.get("mode") == "synthetic", f"{receipt_id} must remain synthetic")
        _expect(row.get("candidate_id") in candidate_by_id, f"{receipt_id} references an unknown candidate")
        _expect(row.get("decision") == "fixture_only", f"{receipt_id} may not claim client acceptance")
        _expect(
            row.get("simulated_condition") in {"accepted", "rejected", "revision_requested"},
            f"{receipt_id} has an invalid simulated condition",
        )
        _expect(str(row.get("source_locator") or "").startswith("fixture://"), f"{receipt_id} source must be fixture")
        _expect(
            SHA256_RE.fullmatch(str(row.get("deliverable_sha256") or "")) is not None,
            f"{receipt_id} deliverable digest invalid",
        )
        for authority_id in _list(row.get("authority_receipt_ids"), f"{receipt_id}.authority_receipt_ids"):
            _expect(authority_id in authority_by_id, f"{receipt_id} references unknown authority {authority_id}")
        _expect(row.get("usable_for_real_effect") is False, f"{receipt_id} cannot evidence real acceptance")
        acceptance_by_id[receipt_id] = row

    delivery_rows = _list(fixture.get("delivery_receipts"), "delivery_receipts")
    delivery_by_id: dict[str, dict[str, Any]] = {}
    for raw in delivery_rows:
        row = _mapping(raw, "delivery receipt")
        missing = set(contract_state["receipt_family_fields"]["delivery"]) - set(row)
        _expect(not missing, f"delivery receipt is missing fields: {sorted(missing)}")
        receipt_id = str(row["receipt_id"])
        _expect(receipt_id.startswith("SYN-DELIVERY-"), "synthetic delivery IDs must use SYN-DELIVERY-")
        _expect(receipt_id not in delivery_by_id, f"duplicate delivery receipt {receipt_id}")
        _expect(row.get("mode") == "synthetic", f"{receipt_id} must remain synthetic")
        _expect(row.get("stage_id") in contract_state["stage_ids"], f"{receipt_id} names an unknown stage")
        _expect(row.get("work_id") in contract_state["leaf_ids"], f"{receipt_id} escapes PSP-C10 scope")
        _expect(row.get("custody_status") == "fixture_only", f"{receipt_id} may not claim real custody")
        _expect(row.get("delivery_status") == "fixture_only", f"{receipt_id} may not claim real delivery")
        _expect(str(row.get("source_locator") or "").startswith("fixture://"), f"{receipt_id} source must be fixture")
        _expect(
            SHA256_RE.fullmatch(str(row.get("deliverable_sha256") or "")) is not None,
            f"{receipt_id} deliverable digest invalid",
        )
        for authority_id in _list(row.get("authority_receipt_ids"), f"{receipt_id}.authority_receipt_ids"):
            _expect(authority_id in authority_by_id, f"{receipt_id} references unknown authority {authority_id}")
        _expect(row.get("usable_for_real_effect") is False, f"{receipt_id} cannot evidence real delivery")
        delivery_by_id[receipt_id] = row

    scenarios = _list(fixture.get("scenarios"), "scenarios")
    scenario_by_id: dict[str, dict[str, Any]] = {}
    for raw in scenarios:
        row = _mapping(raw, "scenario")
        scenario_id = str(row.get("scenario_id") or "")
        _expect(scenario_id.startswith("SYN-SCENARIO-"), "scenario IDs must use SYN-SCENARIO-")
        _expect(scenario_id not in scenario_by_id, f"duplicate scenario {scenario_id}")
        _expect(
            row.get("expected_hypothetical_decision") in {"keep", "narrow", "pivot", "insufficient_evidence"},
            f"{scenario_id} has invalid expected decision",
        )
        _expect(isinstance(row.get("revision_recorded"), bool), f"{scenario_id} must state revision_recorded")
        scenario_by_id[scenario_id] = row

    evidence_rows = _list(fixture.get("evidence"), "evidence")
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for raw in evidence_rows:
        row = _mapping(raw, "evidence record")
        missing = set(contract_state["evidence_required_fields"]) - set(row)
        _expect(not missing, f"evidence record is missing fields: {sorted(missing)}")
        evidence_id = str(row["evidence_id"])
        _expect(evidence_id.startswith("SYN-EV-"), "synthetic evidence IDs must use SYN-EV-")
        _expect(evidence_id not in evidence_by_id, f"duplicate evidence record {evidence_id}")
        _expect(row.get("mode") == "synthetic", f"{evidence_id} must remain synthetic")
        _expect(row.get("scenario_id") in scenario_by_id, f"{evidence_id} references an unknown scenario")
        _expect(row.get("subject_id") in candidate_by_id, f"{evidence_id} references an unknown candidate")
        _expect(row.get("work_id") in contract_state["leaf_ids"], f"{evidence_id} escapes PSP-C10 scope")
        _expect(
            row.get("evidence_class") in contract_state["evidence_classes"], f"{evidence_id} has unknown evidence class"
        )
        _expect(
            str(row.get("source_locator") or "").startswith("fixture://"), f"{evidence_id} must use fixture evidence"
        )
        _expect(row.get("visibility") == "internal_synthetic", f"{evidence_id} must remain internal_synthetic")
        _expect(row.get("consent_receipt_id") in consent_by_id, f"{evidence_id} lacks a synthetic consent receipt")
        for authority_id in _list(row.get("authority_receipt_ids"), f"{evidence_id}.authority_receipt_ids"):
            _expect(authority_id in authority_by_id, f"{evidence_id} references unknown authority {authority_id}")
        _expect(
            SHA256_RE.fullmatch(str(row.get("content_sha256") or "")) is not None, f"{evidence_id} digest is invalid"
        )
        evidence_by_id[evidence_id] = row

    outcomes = _list(fixture.get("outcomes"), "outcomes")
    outcome_by_id: dict[str, dict[str, Any]] = {}
    for raw in outcomes:
        row = _mapping(raw, "outcome")
        outcome_id = str(row.get("outcome_id") or "")
        _expect(outcome_id.startswith("SYN-OUT-"), "synthetic outcome IDs must use SYN-OUT-")
        _expect(outcome_id not in outcome_by_id, f"duplicate outcome {outcome_id}")
        _expect(row.get("mode") == "synthetic", f"{outcome_id} must remain synthetic")
        _expect(row.get("scenario_id") in scenario_by_id, f"{outcome_id} references an unknown scenario")
        _expect(row.get("candidate_id") in candidate_by_id, f"{outcome_id} references an unknown candidate")
        _expect(row.get("qualified") is True, f"{outcome_id} must use a qualified fixture candidate")
        _expect(
            str(row.get("qualification_receipt") or "").startswith("SYN-QUAL-"),
            f"{outcome_id} lacks a synthetic qualification receipt",
        )
        _expect(
            row.get("outcome_type") in {"paid_audit", "explicitly_bounded_pilot", "no_outcome"},
            f"{outcome_id} has invalid type",
        )
        _expect(bool(str(row.get("reason") or "").strip()), f"{outcome_id} must record a reason")
        _expect(isinstance(row.get("declared_outcome_met"), bool), f"{outcome_id} must state outcome status")
        evidence_ids = _list(row.get("evidence_ids"), f"{outcome_id}.evidence_ids")
        for evidence_id in evidence_ids:
            _expect(evidence_id in evidence_by_id, f"{outcome_id} references unknown evidence {evidence_id}")
        evidence_classes = {str(evidence_by_id[evidence_id]["evidence_class"]) for evidence_id in evidence_ids}
        delivery_ids = _list(row.get("delivery_receipt_ids"), f"{outcome_id}.delivery_receipt_ids")
        for delivery_id in delivery_ids:
            _expect(delivery_id in delivery_by_id, f"{outcome_id} references unknown delivery {delivery_id}")
        if row.get("outcome_type") == "paid_audit":
            terms_id = str(row.get("terms_authority_receipt_id") or "")
            payment_id = str(row.get("payment_receipt_id") or "")
            acceptance_id = str(row.get("acceptance_receipt_id") or "")
            _expect(terms_id in authority_by_id, f"{outcome_id} paid audit lacks terms evidence")
            _expect(
                authority_by_id[terms_id]["gate_id"] == "HG-CONTRACT",
                f"{outcome_id} terms evidence is not contract authority",
            )
            _expect(payment_id in payment_by_id, f"{outcome_id} paid audit lacks payment evidence")
            _expect(acceptance_id in acceptance_by_id, f"{outcome_id} paid audit lacks client acceptance")
            _expect(bool(delivery_ids), f"{outcome_id} paid audit lacks a delivery receipt")
            _expect(
                payment_by_id[payment_id]["candidate_id"] == row["candidate_id"],
                f"{outcome_id} payment candidate binding is inconsistent",
            )
            _expect(
                acceptance_by_id[acceptance_id]["candidate_id"] == row["candidate_id"],
                f"{outcome_id} acceptance candidate binding is inconsistent",
            )
            engagement_ids = {
                str(payment_by_id[payment_id]["engagement_id"]),
                str(acceptance_by_id[acceptance_id]["engagement_id"]),
                *(str(delivery_by_id[delivery_id]["engagement_id"]) for delivery_id in delivery_ids),
            }
            _expect(len(engagement_ids) == 1, f"{outcome_id} commercial receipt engagement binding drifted")
            _expect(
                {"payment", "client_acceptance"} <= evidence_classes,
                f"{outcome_id} paid audit evidence classes are incomplete",
            )
        elif row.get("outcome_type") == "explicitly_bounded_pilot":
            terms_id = str(row.get("terms_authority_receipt_id") or "")
            acceptance_id = str(row.get("acceptance_receipt_id") or "")
            _expect(terms_id in authority_by_id, f"{outcome_id} bounded pilot lacks fixture terms authority")
            _expect(row.get("payment_receipt_id") is None, f"{outcome_id} bounded pilot may not imply payment")
            _expect(acceptance_id in acceptance_by_id, f"{outcome_id} bounded pilot lacks an acceptance branch")
            _expect(bool(delivery_ids), f"{outcome_id} bounded pilot lacks a delivery branch")
            engagement_ids = {
                str(acceptance_by_id[acceptance_id]["engagement_id"]),
                *(str(delivery_by_id[delivery_id]["engagement_id"]) for delivery_id in delivery_ids),
            }
            _expect(len(engagement_ids) == 1, f"{outcome_id} bounded-pilot engagement binding drifted")
            _expect("bounded_pilot" in evidence_classes, f"{outcome_id} lacks bounded-pilot evidence")
        else:
            _expect(row.get("terms_authority_receipt_id") is None, f"{outcome_id} no-outcome may not imply terms")
            _expect(row.get("payment_receipt_id") is None, f"{outcome_id} no-outcome may not imply payment")
            _expect(row.get("acceptance_receipt_id") is None, f"{outcome_id} no-outcome may not imply acceptance")
            _expect(delivery_ids == [], f"{outcome_id} no-outcome may not imply delivery")
            _expect("no_outcome" in evidence_classes, f"{outcome_id} lacks no-outcome evidence")
        outcome_by_id[outcome_id] = row

    for scenario_id, scenario in scenario_by_id.items():
        outcome_ids = _list(scenario.get("outcome_ids"), f"{scenario_id}.outcome_ids")
        _expect(len(outcome_ids) == len(set(outcome_ids)) >= 1, f"{scenario_id} outcome IDs must be unique")
        for outcome_id in outcome_ids:
            _expect(outcome_id in outcome_by_id, f"{scenario_id} references unknown outcome {outcome_id}")
            _expect(
                outcome_by_id[outcome_id]["scenario_id"] == scenario_id,
                f"{outcome_id} scenario binding is inconsistent",
            )

    decision_rows = _list(fixture.get("strategy_decision_records"), "strategy_decision_records")
    decision_by_scenario: dict[str, dict[str, Any]] = {}
    decision_ids: set[str] = set()
    for raw in decision_rows:
        row = _mapping(raw, "strategy decision record")
        missing = set(contract_state["strategy_decision_required_fields"]) - set(row)
        _expect(not missing, f"strategy decision record is missing fields: {sorted(missing)}")
        decision_id = str(row["decision_record_id"])
        scenario_id = str(row["scenario_id"])
        _expect(decision_id.startswith("SYN-DECISION-"), "synthetic decision IDs must use SYN-DECISION-")
        _expect(decision_id not in decision_ids, f"duplicate strategy decision {decision_id}")
        _expect(scenario_id in scenario_by_id, f"{decision_id} references an unknown scenario")
        _expect(scenario_id not in decision_by_scenario, f"duplicate decision for {scenario_id}")
        _expect(row.get("mode") == "synthetic", f"{decision_id} must remain synthetic")
        _expect(
            row.get("decision") == scenario_by_id[scenario_id]["expected_hypothetical_decision"],
            f"{decision_id} decision drifted from its scenario",
        )
        _expect(bool(str(row.get("decision_basis") or "").strip()), f"{decision_id} lacks a decision basis")
        _expect(bool(str(row.get("before_strategy") or "").strip()), f"{decision_id} lacks before strategy")
        _expect(bool(str(row.get("after_strategy") or "").strip()), f"{decision_id} lacks after strategy")
        _list(row.get("changed_assumptions"), f"{decision_id}.changed_assumptions")
        source_outcome_ids = _list(row.get("source_outcome_ids"), f"{decision_id}.source_outcome_ids")
        _expect(
            source_outcome_ids == scenario_by_id[scenario_id]["outcome_ids"],
            f"{decision_id} source outcomes drifted from its scenario",
        )
        _expect(
            row.get("external_outcome_evidence_ids") == [],
            f"{decision_id} may not claim external outcome evidence",
        )
        _expect(row.get("apply") is False, f"{decision_id} may not apply a real strategy decision")
        _expect(row.get("publishable") is False, f"{decision_id} may not be publishable")
        _expect(row.get("usable_for_real_effect") is False, f"{decision_id} cannot authorize a real effect")
        decision_ids.add(decision_id)
        decision_by_scenario[scenario_id] = row
    _expect(set(decision_by_scenario) == set(scenario_by_id), "fixture must record one decision per scenario")

    case_study_rows = _list(fixture.get("case_study_receipts"), "case_study_receipts")
    case_study_by_id: dict[str, dict[str, Any]] = {}
    for raw in case_study_rows:
        row = _mapping(raw, "case-study receipt")
        missing = set(contract_state["receipt_family_fields"]["case_study"]) - set(row)
        _expect(not missing, f"case-study receipt is missing fields: {sorted(missing)}")
        receipt_id = str(row["receipt_id"])
        _expect(receipt_id.startswith("SYN-CASE-"), "synthetic case-study IDs must use SYN-CASE-")
        _expect(receipt_id not in case_study_by_id, f"duplicate case-study receipt {receipt_id}")
        _expect(row.get("mode") == "synthetic", f"{receipt_id} must remain synthetic")
        for outcome_id in _list(row.get("source_outcome_ids"), f"{receipt_id}.source_outcome_ids"):
            _expect(outcome_id in outcome_by_id, f"{receipt_id} references unknown outcome {outcome_id}")
        _expect(
            SHA256_RE.fullmatch(str(row.get("exact_copy_sha256") or "")) is not None,
            f"{receipt_id} copy digest invalid",
        )
        _expect(row.get("client_copy_decision") == "fixture_only", f"{receipt_id} may not claim client approval")
        _expect(
            row.get("owner_publication_decision") == "fixture_only",
            f"{receipt_id} may not claim owner publication approval",
        )
        _expect(row.get("consent_receipt_id") in consent_by_id, f"{receipt_id} references unknown consent")
        _expect(
            row.get("identity_authority_receipt_id") in authority_by_id,
            f"{receipt_id} references unknown identity authority",
        )
        _expect(
            row.get("contract_authority_receipt_id") in authority_by_id,
            f"{receipt_id} references unknown contract authority",
        )
        _expect(row.get("publication_status") == "not_published", f"{receipt_id} may not record publication")
        _expect(row.get("usable_for_real_effect") is False, f"{receipt_id} cannot evidence a real case study")
        case_study_by_id[receipt_id] = row

    proposals = _list(fixture.get("claim_refresh_proposals"), "claim_refresh_proposals")
    proposal_by_id: dict[str, dict[str, Any]] = {}
    for raw in proposals:
        row = _mapping(raw, "claim refresh proposal")
        proposal_id = str(row.get("proposal_id") or "")
        _expect(proposal_id.startswith("SYN-CLAIM-"), "synthetic claim proposal IDs must use SYN-CLAIM-")
        _expect(proposal_id not in proposal_by_id, f"duplicate claim proposal {proposal_id}")
        _expect(row.get("mode") == "synthetic", f"{proposal_id} must remain synthetic")
        _expect(
            row.get("disposition") in {"strengthen", "narrow", "invalidate"}, f"{proposal_id} has invalid disposition"
        )
        _expect(row.get("apply") is False, f"{proposal_id} may not mutate the claims ledger")
        _expect(row.get("publishable") is False, f"{proposal_id} may not become public proof")
        _expect(row.get("prominence") == "nowhere", f"{proposal_id} must remain nowhere")
        for outcome_id in _list(row.get("source_outcome_ids"), f"{proposal_id}.source_outcome_ids"):
            _expect(outcome_id in outcome_by_id, f"{proposal_id} references unknown outcome {outcome_id}")
        proposal_by_id[proposal_id] = row

    promotion_rows = _list(fixture.get("claim_promotion_receipts"), "claim_promotion_receipts")
    promotion_by_id: dict[str, dict[str, Any]] = {}
    promoted_proposals: set[str] = set()
    for raw in promotion_rows:
        row = _mapping(raw, "claim-promotion receipt")
        missing = set(contract_state["receipt_family_fields"]["claim_promotion"]) - set(row)
        _expect(not missing, f"claim-promotion receipt is missing fields: {sorted(missing)}")
        receipt_id = str(row["receipt_id"])
        proposal_id = str(row["proposal_id"])
        _expect(receipt_id.startswith("SYN-PROMOTE-"), "synthetic promotion IDs must use SYN-PROMOTE-")
        _expect(receipt_id not in promotion_by_id, f"duplicate claim-promotion receipt {receipt_id}")
        _expect(proposal_id in proposal_by_id, f"{receipt_id} references unknown proposal {proposal_id}")
        _expect(proposal_id not in promoted_proposals, f"duplicate promotion gate for {proposal_id}")
        _expect(row.get("mode") == "synthetic", f"{receipt_id} must remain synthetic")
        _expect(row.get("disposition") == proposal_by_id[proposal_id]["disposition"], f"{receipt_id} disposition drifted")
        _expect(
            row.get("source_outcome_ids") == proposal_by_id[proposal_id]["source_outcome_ids"],
            f"{receipt_id} source outcomes drifted",
        )
        _expect(row.get("external_outcome_evidence_ids") == [], f"{receipt_id} may not claim external outcomes")
        for consent_id in _list(row.get("consent_receipt_ids"), f"{receipt_id}.consent_receipt_ids"):
            _expect(consent_id in consent_by_id, f"{receipt_id} references unknown consent {consent_id}")
        for authority_id in _list(
            row.get("owner_authority_receipt_ids"), f"{receipt_id}.owner_authority_receipt_ids"
        ):
            _expect(authority_id in authority_by_id, f"{receipt_id} references unknown authority {authority_id}")
        _expect(bool(_list(row.get("target_claim_keys"), f"{receipt_id}.target_claim_keys")), f"{receipt_id} lacks targets")
        for digest_field in ("prior_claim_set_sha256", "proposed_claim_set_sha256"):
            _expect(
                SHA256_RE.fullmatch(str(row.get(digest_field) or "")) is not None,
                f"{receipt_id} {digest_field} invalid",
            )
        _expect(row.get("promotion_status") == "blocked_synthetic", f"{receipt_id} may not promote claims")
        _expect(row.get("usable_for_real_effect") is False, f"{receipt_id} cannot mutate real claims")
        promotion_by_id[receipt_id] = row
        promoted_proposals.add(proposal_id)
    _expect(promoted_proposals == set(proposal_by_id), "every claim proposal requires one blocked promotion gate")

    return {
        "candidate_by_id": candidate_by_id,
        "cohort": cohort,
        "recruitment_by_id": recruitment_by_id,
        "authority_by_id": authority_by_id,
        "consent_by_id": consent_by_id,
        "payment_by_id": payment_by_id,
        "acceptance_by_id": acceptance_by_id,
        "delivery_by_id": delivery_by_id,
        "scenario_by_id": scenario_by_id,
        "outcome_by_id": outcome_by_id,
        "evidence_by_id": evidence_by_id,
        "decision_by_scenario": decision_by_scenario,
        "case_study_by_id": case_study_by_id,
        "claim_proposal_count": len(proposals),
        "promotion_by_id": promotion_by_id,
    }


def hypothetical_decision(
    outcomes: list[dict[str, Any]],
    threshold: int,
    *,
    revision_recorded: bool,
) -> str:
    accepted = [
        row
        for row in outcomes
        if row["outcome_type"] == "paid_audit"
        and bool(row["terms_authority_receipt_id"])
        and bool(row["payment_receipt_id"])
        and bool(row["acceptance_receipt_id"])
        and bool(row["delivery_receipt_ids"])
    ]
    if accepted:
        return "keep" if any(row["declared_outcome_met"] is True for row in accepted) else "narrow"
    qualified_no_ids = {
        str(row["candidate_id"])
        for row in outcomes
        if row["outcome_type"] == "no_outcome" and row["qualified"] is True and str(row["reason"]).strip()
    }
    if len(qualified_no_ids) >= threshold and revision_recorded:
        return "pivot"
    return "insufficient_evidence"


def build_receipt(
    contract_path: Path = DEFAULT_CONTRACT,
    fixture_path: Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    contract, fixture, program, graph = load_inputs(contract_path, fixture_path)
    contract_state = validate_contract(contract, program, graph)
    fixture_state = validate_fixture(fixture, contract_state)

    scenario_results: dict[str, dict[str, Any]] = {}
    for scenario_id, scenario in fixture_state["scenario_by_id"].items():
        rows = [fixture_state["outcome_by_id"][outcome_id] for outcome_id in scenario["outcome_ids"]]
        decision = hypothetical_decision(
            rows,
            contract_state["qualified_threshold"],
            revision_recorded=bool(scenario["revision_recorded"]),
        )
        _expect(
            decision == scenario["expected_hypothetical_decision"],
            f"{scenario_id} expected {scenario['expected_hypothetical_decision']} but produced {decision}",
        )
        scenario_results[scenario_id] = {
            "hypothetical_decision": decision,
            "decision_record_id": fixture_state["decision_by_scenario"][scenario_id]["decision_record_id"],
            "outcome_count": len(rows),
            "real_world_decision": "not_adjudicated",
            "status": "synthetic_branch_exercised",
        }

    stages = list(contract["bounded_pilot"]["stages"])
    stage_results = []
    for stage in stages:
        blocked = bool(stage["human_gates"]) or bool(stage["requires_real_outcome"])
        stage_results.append(
            {
                "stage_id": stage["id"],
                "synthetic_status": "pass",
                "real_effect_status": "blocked_pending_real_authority_or_outcome" if blocked else "not_performed",
                "human_gates": list(stage["human_gates"]),
                "requires_real_outcome": bool(stage["requires_real_outcome"]),
            }
        )

    external_gates = [
        "REAL-OUTREACH",
        "REAL-AGREEMENT",
        "REAL-PAID-AUDIT",
        "REAL-BOUNDED-PILOT",
        "REAL-DELIVERY-ACCEPTANCE",
        "REAL-CASE-STUDY-PUBLICATION",
        "REAL-TESTIMONIAL-OR-REFERENCE",
        "REAL-EXTERNAL-OUTCOME",
        "REAL-CLAIM-PROMOTION",
    ]
    return {
        "schema_version": RECEIPT_SCHEMA,
        "mode": "synthetic",
        "status": "prepared_preflight",
        "dry_run_id": fixture["dry_run_id"],
        "fixture_time_anchor": fixture["fixture_time_anchor"],
        "scope": {
            "chunk_id": contract_state["chunk_id"],
            "leaf_ids": contract_state["leaf_ids"],
            "formal_predecessor_chunks": list(contract["scope"]["formal_predecessor_chunks"]),
            "formal_predecessors_satisfied": "not_evaluated_by_synthetic_dry_run",
        },
        "bindings": {
            "contract_path": _relative(contract_path),
            "contract_sha256": _sha256_path(contract_path),
            "fixture_path": _relative(fixture_path),
            "fixture_sha256": _sha256_path(fixture_path),
            "program_manifest_path": _relative(PROGRAM_MANIFEST),
            "program_registry_projection_sha256": contract_state["registry_projection_sha256"],
        },
        "model_routing": {
            "conductor": contract_state["conductor_assignment"],
            "leaves": contract_state["leaf_assignments"],
            "verified_against_registry": True,
        },
        "registry_audit": {
            "owned_leaf_count": len(contract_state["leaf_contract_audit"]),
            "all_owned_leaves_audited": True,
            "leaf_contracts": contract_state["leaf_contract_audit"],
        },
        "operational_readiness": {
            "status": "synthetic_dry_run_pass",
            "recruitment_criteria_validated": len(contract_state["criterion_ids"]),
            "qualified_fixture_candidates": len(fixture_state["candidate_by_id"]),
            "bounded_fixture_cohort": len(fixture_state["cohort"]),
            "unsent_recruitment_records_validated": len(fixture_state["recruitment_by_id"]),
            "authority_receipt_types_validated": len(fixture_state["authority_by_id"]),
            "consent_receipt_types_validated": len(fixture_state["consent_by_id"]),
            "fixture_only_payment_receipts_validated": len(fixture_state["payment_by_id"]),
            "fixture_only_acceptance_receipts_validated": len(fixture_state["acceptance_by_id"]),
            "fixture_only_delivery_receipts_validated": len(fixture_state["delivery_by_id"]),
            "unpublished_case_study_receipts_validated": len(fixture_state["case_study_by_id"]),
            "pilot_stages_validated": len(stage_results),
            "evidence_records_validated": len(fixture_state["evidence_by_id"]),
            "adjudication_branches_validated": sorted(
                result["hypothetical_decision"] for result in scenario_results.values()
            ),
            "before_after_strategy_decisions_validated": len(fixture_state["decision_by_scenario"]),
            "claim_refresh_proposals_validated": fixture_state["claim_proposal_count"],
            "blocked_claim_promotion_receipts_validated": len(fixture_state["promotion_by_id"]),
            "testimonial_or_reference_collection": "not_attempted",
            "experiment_duration_days": contract["experiment_90_day"]["duration_days"],
        },
        "commercial_proof": {
            "established": False,
            "real_qualified_denominator": 0,
            "real_outreach": 0,
            "real_agreements": 0,
            "real_conversions": 0,
            "real_paid_audits": 0,
            "real_bounded_pilots": 0,
            "real_revenue_receipts": 0,
            "real_delivery_acceptances": 0,
            "real_public_case_studies": 0,
            "real_testimonials_or_references": 0,
            "real_external_outcomes": 0,
            "public_claims_refreshed": 0,
        },
        "program_completion": {
            "leaf_predicates_satisfied": [],
            "phase_predicate_satisfied": False,
            "chunk_exit_gate_satisfied": False,
            "issues_closed": [],
        },
        "authority": {
            "real_human_gate_grants": 0,
            "human_gates": {gate_id: "not_granted_by_synthetic_run" for gate_id in contract_state["gate_ids"]},
            "external_gates": {gate_id: "not_satisfied" for gate_id in external_gates},
        },
        "pilot_stage_results": stage_results,
        "scenario_results": scenario_results,
        "claim_refresh": {
            "proposals_only": True,
            "promotion_gates": "blocked_synthetic",
            "applied": 0,
            "publishable": 0,
            "claims_ledger_changed": False,
        },
        "external_effects": [],
        "truth_statement": (
            "Synthetic readiness passed. No outreach, agreement, payment, conversion, revenue, delivery "
            "acceptance, client reference, public case study, testimonial, external outcome, public claim "
            "refresh, leaf completion, phase completion, or chunk completion is established."
        ),
    }


def check_summary(
    contract_path: Path = DEFAULT_CONTRACT,
    fixture_path: Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    receipt = build_receipt(contract_path, fixture_path)
    return {
        "status": "ok",
        "mode": receipt["mode"],
        "chunk_id": receipt["scope"]["chunk_id"],
        "leaf_count": len(receipt["scope"]["leaf_ids"]),
        "contract_sha256": receipt["bindings"]["contract_sha256"],
        "fixture_sha256": receipt["bindings"]["fixture_sha256"],
        "program_registry_projection_sha256": receipt["bindings"]["program_registry_projection_sha256"],
        "model_routing": receipt["model_routing"],
        "commercial_proof": False,
        "external_effects": [],
    }


def write_receipt(
    receipt_path: Path = DEFAULT_RECEIPT,
    contract_path: Path = DEFAULT_CONTRACT,
    fixture_path: Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    receipt = build_receipt(contract_path, fixture_path)
    content = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(content, encoding="utf-8")
    return {
        "status": "written",
        "receipt": _relative(receipt_path),
        "receipt_sha256": _sha256_path(receipt_path),
        "commercial_proof": False,
        "external_effects": [],
    }


def verify_receipt(
    receipt_path: Path,
    contract_path: Path = DEFAULT_CONTRACT,
    fixture_path: Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    observed = _load_json(receipt_path)
    expected = build_receipt(contract_path, fixture_path)
    _expect(observed == expected, f"synthetic receipt drifted from deterministic dry run: {receipt_path}")
    return {
        "status": "ok",
        "receipt": _relative(receipt_path),
        "receipt_sha256": _sha256_path(receipt_path),
        "commercial_proof": False,
        "external_effects": [],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true", help="validate the contract and synthetic fixture")
    actions.add_argument("--dry-run", action="store_true", help="emit the deterministic synthetic readiness receipt")
    actions.add_argument(
        "--write-receipt",
        type=Path,
        nargs="?",
        const=DEFAULT_RECEIPT,
        metavar="PATH",
        help="write the deterministic synthetic receipt (default: tracked preflight receipt)",
    )
    actions.add_argument("--verify-receipt", type=Path, metavar="PATH", help="verify a committed synthetic receipt")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.check:
            result = check_summary(args.contract, args.fixture)
        elif args.dry_run:
            result = build_receipt(args.contract, args.fixture)
        elif args.write_receipt is not None:
            result = write_receipt(args.write_receipt, args.contract, args.fixture)
        else:
            result = verify_receipt(args.verify_receipt, args.contract, args.fixture)
    except (OSError, ReadinessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
