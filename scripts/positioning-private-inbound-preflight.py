#!/usr/bin/env python3
"""Dependency-gated synthetic preflight for PSP-C07 private inbound operations.

The module has no network, send, publication, deployment, or account-mutation
capability. It models the future C06 capture boundary and emits only a redacted,
aggregate-safe traversal receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "institutio/positioning/preflights/psp-c07-private-inbound/contract.json"
DEFAULT_FIXTURES = ROOT / "institutio/positioning/preflights/psp-c07-private-inbound/fixtures/synthetic-leads.json"
PROGRAM_SCRIPT = ROOT / "scripts/positioning-program.py"
MAIL_TAG = re.compile(r"^\[(?P<surface>[^\]·]+?)\s*·\s*(?P<audience>[^\]]+?)\]\s*—\s*inbound$")
LIVE_GATE_ORDER = (
    "PSP-P03-W07",
    "PSP-P04",
    "PSP-P07",
    "PSP-C06-selected-capture-surface",
    "PSP-P08-separate-leaf-authority",
)
WORK_IDS = tuple(f"PSP-P08-W0{index}" for index in range(1, 8))
ASSIGNMENT_POLICY = {
    "selection": "runtime_catalog",
    "registry": "institutio/positioning/program.yaml",
    "catalog_predicate": "python3 scripts/positioning-program.py --verify-model-assignments",
    "unavailable_action": "fail_blocked_no_silent_substitution",
}


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be an object")
    return data


def _field_names(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key).lower()
            yield from _field_names(child)
    elif isinstance(value, list):
        for child in value:
            yield from _field_names(child)


@lru_cache(maxsize=1)
def expected_assignment_requirements() -> dict[str, dict[str, Any]]:
    """Derive execution requirements without freezing provider model names."""
    program = runpy.run_path(str(PROGRAM_SCRIPT))
    graph = program["index_program"](program["load_manifest"]())
    packets = [graph["work_by_id"][work_id] for work_id in WORK_IDS]
    chunk_assignment = program["chunk_assignment_for"]("PSP-C07", graph)
    requirements: dict[str, dict[str, Any]] = {
        "PSP-C07": {
            "selection": "runtime_catalog",
            "role": "chunk_conductor",
            "effort": chunk_assignment["effort"],
            "capabilities": sorted({capability for packet in packets for capability in packet["capabilities"]}),
        }
    }
    for work_id in WORK_IDS:
        packet = graph["work_by_id"][work_id]
        assignment = program["model_assignment_for"](work_id, graph)
        requirements[work_id] = {
            "selection": "runtime_catalog",
            "reasoning": packet["reasoning"],
            "effect": packet["effect"],
            "effort": assignment["effort"],
            "capabilities": packet["capabilities"],
        }
    return requirements


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "chunk_id",
        "phase_id",
        "status",
        "counts_as_closure",
        "assignment_policy",
        "assignment_requirements",
        "leaf_coverage",
        "formal_dependency_gate",
        "safety",
        "cta_intake_mapping",
        "minimum_data_schema",
        "capture_contract",
        "integration_adapters",
        "custody",
        "scoring",
        "drafts",
        "ledger",
        "views",
        "retention",
        "abuse_controls",
    }
    missing = sorted(required - contract.keys())
    if missing:
        errors.append(f"missing contract fields: {', '.join(missing)}")
    if contract.get("chunk_id") != "PSP-C07" or contract.get("phase_id") != "PSP-P08":
        errors.append("contract must remain scoped to PSP-C07/PSP-P08")
    if contract.get("status") != "PREPARED/PREFLIGHT":
        errors.append("status must remain PREPARED/PREFLIGHT")
    if contract.get("counts_as_closure") is not False:
        errors.append("preflight must never count as formal closure")
    if contract.get("schema_version") != "limen.psp_c07_private_inbound_preflight.v3":
        errors.append("contract schema must remain at private-inbound preflight v3")
    if contract.get("assignment_policy") != ASSIGNMENT_POLICY:
        errors.append("assignment policy must require runtime catalog discovery and fail closed")
    if contract.get("assignment_requirements") != expected_assignment_requirements():
        errors.append("assignment requirements drifted from the canonical runtime registry")
    coverage = contract.get("leaf_coverage", {})
    if set(coverage) != set(WORK_IDS):
        errors.append("leaf coverage must remain exactly PSP-P08-W01 through W07")
    for work_id in WORK_IDS:
        observed = coverage.get(work_id, {})
        if observed.get("reversible_status") != "implemented_in_preflight":
            errors.append(f"{work_id} reversible coverage must remain implemented in preflight")
        if observed.get("formal_status") != "open_dependency_gated":
            errors.append(f"{work_id} formal status must remain open and dependency-gated")
        if not observed.get("components"):
            errors.append(f"{work_id} must name its reversible components")

    gate = contract.get("formal_dependency_gate", {})
    if gate.get("required_chunk") != "PSP-C06" or gate.get("required_phases") != [
        "PSP-P04",
        "PSP-P07",
    ]:
        errors.append("live activation must require PSP-C06 plus PSP-P04 and PSP-P07")
    expected_phase_states = {
        "PSP-P03": "open_W07_five_reader_gate",
        "PSP-P04": "open_blocked_on_PSP-P03",
        "PSP-P07": "open_prepared_only",
    }
    if gate.get("phase_states") != expected_phase_states:
        errors.append("preflight must preserve the current P03/P04/P07 phase frontier")
    expected_leaf_dependencies = {
        "PSP-P08-W01": ["PSP-P07-W09"],
        "PSP-P08-W02": ["PSP-P04-W04", "PSP-P08-W01"],
        "PSP-P08-W03": ["PSP-P08-W02"],
        "PSP-P08-W04": ["PSP-P08-W03", "PSP-P04-W04"],
        "PSP-P08-W05": ["PSP-P08-W04", "PSP-P04-W04"],
        "PSP-P08-W06": ["PSP-P08-W03", "PSP-P08-W04"],
        "PSP-P08-W07": [
            "PSP-P08-W01",
            "PSP-P08-W02",
            "PSP-P08-W03",
            "PSP-P08-W04",
            "PSP-P08-W05",
            "PSP-P08-W06",
        ],
    }
    if gate.get("leaf_dependencies") != expected_leaf_dependencies:
        errors.append("P08 leaf dependencies must exactly match the live program registry")
    commercial = gate.get("commercial_upstream", {})
    p03 = commercial.get("PSP-P03", {})
    if commercial.get("PSP-P02", {}).get("state") != "closed":
        errors.append("P02 must remain recorded as closed")
    if p03.get("state") != "open":
        errors.append("P03 must remain open while W07 lacks reader evidence")
    if p03.get("accepted_w01_w06_head") != "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec":
        errors.append("P03 accepted W01-W06 head must remain pinned")
    if p03.get("current_preflight_source_head") != "b6af8086c9050634313f519c29a6dfcb922c3721":
        errors.append("P03 current preflight source head must include the W07 intake package")
    if p03.get("integrated_main_head") != "8f89ad16ca1df84b00cb8227c88f368d0d64631a":
        errors.append("P03 integrated main head must remain pinned")
    if p03.get("closed_work_ids") != [f"PSP-P03-W0{index}" for index in range(1, 7)]:
        errors.append("P03 must name exactly W01-W06 as closed")
    w06 = p03.get("w06_receipt", {})
    if w06.get("url") != "https://github.com/organvm/limen/issues/2187#issuecomment-5271254820":
        errors.append("W06 marked receipt URL must remain pinned")
    if w06.get("sha256") != "260081dfbffc75d55824c0e6ed7d7718a7e397763afb689c94d2230963d79617":
        errors.append("W06 marked receipt digest must remain pinned")
    w07 = p03.get("w07", {})
    if (
        w07.get("state") != "open"
        or w07.get("required_reader_count") != 5
        or w07.get("evidence_requirements") != ["genuine", "independent", "target_like"]
        or w07.get("synthetic_or_model_evidence_allowed") is not False
    ):
        errors.append("W07 must remain open for five genuine independent target-like readers")
    if commercial.get("PSP-P04", {}).get("state") != "open_blocked_on_PSP-P03":
        errors.append("P04 must remain open and blocked on P03")
    if gate.get("selected_capture_surface") is not None:
        errors.append("preflight must not select or wire a C06 capture surface")
    if gate.get("separate_leaf_authority") is not None:
        errors.append("preflight must not claim separate P08 leaf authority")
    if gate.get("live_capture_activation") != "forbidden_until_predicate_receipt":
        errors.append("live activation must fail closed on a predicate receipt")
    upstream = gate.get("upstream_preflight", {})
    if upstream.get("status") != "MERGED_PREPARED":
        errors.append("C06 upstream evidence must remain merged/prepared, not complete")
    expected_c06_heads = {
        "portfolio_package": {
            "source_head": "7c150fc81184df1715824be28b32472baadbb3b6",
            "integrated_main_head": "797cda3fb903b07d4152e5bbde9f468beeeab3e0",
        },
        "limen_relay": {
            "source_head": "854b6385de6b340485baaf59b1be55bd4d243a4d",
            "integrated_main_head": "690617fc2aeea79acfe5604799e6413d70b6e4dd",
        },
    }
    for owner, expected_heads in expected_c06_heads.items():
        observed = upstream.get(owner, {})
        for field_name, expected_head in expected_heads.items():
            if observed.get(field_name) != expected_head:
                errors.append(f"C06 {owner} {field_name} must remain pinned")
    visual = upstream.get("visual_selection", {})
    if visual.get("grounded_direction_count") != 3:
        errors.append("C06 preflight must preserve exactly three grounded directions")
    if visual.get("durable_artifacts_status") != "tracked_unselected":
        errors.append("C06 durable visual artifacts must remain tracked and unselected")
    if visual.get("manifest_path") != ("docs/positioning/visual-directions/psp-c06/manifest.json"):
        errors.append("C06 visual manifest must use its durable portfolio path")
    if len(visual.get("mockup_paths", [])) != 3:
        errors.append("C06 preflight must preserve exactly three durable mockup paths")
    if visual.get("status") != "awaiting_operator_selection":
        errors.append("C06 visual selection must remain operator-gated")
    if visual.get("implementation_authorized") is not False:
        errors.append("C06 visual implementation must remain unauthorized")
    if visual.get("deployment_authorized") is not False:
        errors.append("C06 deployment must remain unauthorized")
    link_health = upstream.get("link_health", {})
    if link_health.get("dead_legacy_link_count") != 11:
        errors.append("C06 preflight must preserve the observed 11-dead-link finding")
    if link_health.get("canonical_paths_status") != "resolving":
        errors.append("C06 preflight must preserve canonical-path resolution evidence")

    safety = contract.get("safety", {})
    if safety.get("mode") != "synthetic_only":
        errors.append("preflight mode must be synthetic_only")
    if safety.get("send_valve") != "hard_closed":
        errors.append("send valve must be hard_closed")
    if safety.get("transport_capabilities") != []:
        errors.append("preflight must expose no transport capabilities")
    forbidden = set(safety.get("forbidden_effects", []))
    for effect in {"send", "publish", "deploy", "dns", "account_mutation"}:
        if effect not in forbidden:
            errors.append(f"missing forbidden effect: {effect}")
    if safety.get("pii_log_policy") != "field_names_and_counts_only":
        errors.append("public output must be field-names-and-counts only")
    public_fields = set(safety.get("public_receipt_allowlist", []))
    public_journey_fields = set(safety.get("public_journey_allowlist", []))
    unsafe_public = {
        "contact",
        "email",
        "name",
        "request",
        "details",
        "body",
        "draft_body",
        "payload",
    }
    leaked = sorted((public_fields | public_journey_fields) & unsafe_public)
    if leaked:
        errors.append(f"unsafe public receipt fields: {', '.join(leaked)}")

    capture = contract.get("capture_contract", {})
    if set(capture.get("accepted_kinds", [])) != {"tagged_mail", "form_submission"}:
        errors.append("capture contract must support tagged_mail and form_submission only")
    if not capture.get("forbidden_field_names"):
        errors.append("capture contract requires a sensitive-field denylist")
    allowed_kind_fields = capture.get("allowed_kind_fields", {})
    if set(allowed_kind_fields) != {"tagged_mail", "form_submission"}:
        errors.append("capture contract requires strict per-kind field allowlists")
    if set(capture.get("minimal_consent_fields", [])) != {"process_contact"}:
        errors.append("capture contract must collect process_contact consent only")
    try:
        re.compile(str(capture.get("source_tag_pattern", "")))
    except re.error:
        errors.append("capture source tag pattern must compile")
    if capture.get("reject_header_control_characters") is not True:
        errors.append("capture contract must reject header control characters")
    if int(capture.get("max_synthetic_batch_events", 0)) <= 0:
        errors.append("capture contract must bound synthetic batch size")

    cta_mapping = contract.get("cta_intake_mapping", {})
    if cta_mapping.get("status") != "contract_only_unwired":
        errors.append("CTA mapping must remain contract-only and unwired")
    if cta_mapping.get("activation_authorized") is not False:
        errors.append("CTA activation must remain unauthorized")
    doors = cta_mapping.get("doors", {})
    if set(doors) != {"client_primary", "recruiter_primary"}:
        errors.append("CTA mapping must expose only client and recruiter primary doors")
    expected_audiences = {"client_primary": "client", "recruiter_primary": "hire"}
    for door, audience in expected_audiences.items():
        observed = doors.get(door, {})
        if observed.get("audience_tag") != audience:
            errors.append(f"{door} must preserve its {audience} audience tag")
        if set(observed.get("allowed_capture_kinds", [])) != {
            "form_submission",
            "tagged_mail",
        }:
            errors.append(f"{door} must support form and tagged-mail contracts")
        if observed.get("mail_fallback") is not True:
            errors.append(f"{door} must retain a tagged-mail fallback")

    minimum = contract.get("minimum_data_schema", {})
    expected_minimum_fields = {
        "contact.name": ("string", 120),
        "contact.email": ("string", 254),
        "request.summary": ("string", 160),
        "request.details": ("string", 2000),
    }
    fields = minimum.get("fields", {})
    if set(fields) != {*expected_minimum_fields, "consent.process_contact"}:
        errors.append("minimum-data schema must remain exact")
    for path, (field_type, max_length) in expected_minimum_fields.items():
        observed = fields.get(path, {})
        if (
            observed.get("type") != field_type
            or observed.get("required") is not True
            or observed.get("max_length") != max_length
        ):
            errors.append(f"minimum-data field {path} must remain required and bounded")
    consent = fields.get("consent.process_contact", {})
    if consent.get("type") != "boolean" or consent.get("const") is not True:
        errors.append("minimum-data consent must require affirmative process_contact")

    adapters = contract.get("integration_adapters", {})
    for kind in ("tagged_mail", "form_submission"):
        if adapters.get(kind, {}).get("selection_state") != "contract_only":
            errors.append(f"{kind} adapter must remain contract_only")

    custody = contract.get("custody", {})
    if custody.get("status") != "adapter_boundary_only":
        errors.append("private custody must remain an adapter-only boundary")
    if custody.get("encryption_required") is not True:
        errors.append("private custody must require encryption")
    if custody.get("plaintext_persistence_allowed") is not False:
        errors.append("private custody must forbid plaintext persistence")
    if custody.get("key_material_in_contract_allowed") is not False:
        errors.append("private custody contract must forbid embedded key material")
    if set(custody.get("required_adapter_methods", [])) != {"seal", "open", "delete"}:
        errors.append("private custody adapter must require seal/open/delete")
    if custody.get("synthetic_harness", {}).get("production_encryption_claim") is not False:
        errors.append("synthetic custody must not claim production encryption")

    drafts = contract.get("drafts", {})
    if drafts.get("status") != "draft_only":
        errors.append("response templates must remain draft-only")
    families = set(drafts.get("families", []))
    if families != set(drafts.get("templates", {})):
        errors.append("every draft family must have exactly one declarative template")
    if set(drafts.get("allowed_placeholders", [])) != {"name", "summary", "route"}:
        errors.append("draft templates must use only bounded approved placeholders")

    views = contract.get("views", {})
    private_view = views.get("private_operator", {})
    aggregate_view = views.get("aggregate_dashboard", {})
    if private_view.get("partition_required") is not True:
        errors.append("private operator views must require an owner partition")
    if private_view.get("contact_fields_in_projection") is not False:
        errors.append("private operator projections must exclude contact fields")
    if aggregate_view.get("row_export_allowed") is not False:
        errors.append("aggregate dashboard must forbid row export")

    retention = contract.get("retention", {})
    if set(retention.get("category_days", {})) != {
        "spam",
        "ambiguous",
        "operator",
        "client",
        "recruiter",
    }:
        errors.append("retention defaults must cover every route category")
    if retention.get("deletion_receipt") != "aggregate_only_no_identifier":
        errors.append("deletion receipts must remain aggregate-only")
    if retention.get("expired_action") != "delete":
        errors.append("expired private records must be deleted")

    abuse = contract.get("abuse_controls", {})
    for key in (
        "content_is_data_only",
        "reject_control_characters_in_tags",
        "reject_oversize_fields",
        "reject_unknown_fields",
        "no_tool_execution_from_content",
    ):
        if abuse.get(key) is not True:
            errors.append(f"abuse control {key} must remain enabled")

    ledger = contract.get("ledger", {})
    if ledger.get("partition_key") != "owner_partition":
        errors.append("private ledger must partition by owner_partition")
    if ledger.get("public_projection") != "aggregate_counts_only":
        errors.append("ledger public projection must be aggregate_counts_only")
    if ledger.get("live_record_id_strategy") != "private_random_or_keyed_identifier_never_public":
        errors.append("live record identifiers must be private, random or keyed, and never public")
    return errors


def validate_fixtures(fixtures: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if fixtures.get("synthetic") is not True:
        errors.append("fixtures must declare synthetic: true")
    events = fixtures.get("events")
    if not isinstance(events, list) or not events:
        return errors + ["fixtures must contain events"]
    batch_limit = int(contract.get("capture_contract", {}).get("max_synthetic_batch_events", 0))
    if batch_limit and len(events) > batch_limit:
        errors.append(f"fixtures exceed the synthetic batch limit of {batch_limit}")
    expectations = fixtures.get("expectations")
    if not isinstance(expectations, dict) or not expectations:
        errors.append("fixtures must declare labeled expectations")
    capture = contract.get("capture_contract")
    if not isinstance(capture, dict):
        return errors + ["fixtures cannot validate without capture_contract"]
    forbidden = set(capture.get("forbidden_field_names", []))
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"event {index} must be an object")
            continue
        event_name = event.get("fixture_id", f"event-{index}")
        present_forbidden = sorted(forbidden & set(_field_names(event)))
        if present_forbidden:
            errors.append(f"{event_name} overcollects: {', '.join(present_forbidden)}")
        email = event.get("contact", {}).get("email", "")
        if not isinstance(email, str) or not email.endswith(".invalid"):
            errors.append(f"{event_name} must use a reserved .invalid address")
        owner_partition = event.get("owner_partition")
        if not isinstance(owner_partition, str) or not owner_partition.startswith("synthetic-"):
            errors.append(f"{event_name} must use a synthetic owner partition")
    return errors


def evaluate_routes(journeys: list[dict[str, Any]], fixtures: dict[str, Any]) -> dict[str, Any]:
    expectations = fixtures["expectations"]
    evaluated = [row for row in journeys if row["fixture_id"] in expectations]
    correct = 0
    confusion: Counter[str] = Counter()
    for row in evaluated:
        expected = expectations[row["fixture_id"]]
        observed = str(row["category"])
        wanted = str(expected["category"])
        confusion[f"{wanted}->{observed}"] += 1
        if observed == wanted and row["route"] == expected["route"]:
            correct += 1
    total = len(evaluated)
    return {
        "labeled_scenarios": total,
        "correct_category_and_route": correct,
        "accuracy": correct / total if total else 0.0,
        "confusion": dict(sorted(confusion.items())),
    }


def _require_keys(value: dict[str, Any], required: Iterable[str], context: str) -> None:
    missing = sorted(set(required) - value.keys())
    if missing:
        raise ValueError(f"{context} missing fields: {', '.join(missing)}")


def _reject_sensitive_fields(event: dict[str, Any], contract: dict[str, Any]) -> None:
    forbidden = set(contract["capture_contract"]["forbidden_field_names"])
    present = sorted(forbidden & set(_field_names(event)))
    if present:
        raise ValueError(f"sensitive overcollection rejected: {', '.join(present)}")


def _reject_unexpected_fields(event: dict[str, Any], contract: dict[str, Any]) -> None:
    capture = contract["capture_contract"]
    kind = str(event["kind"])
    allowed_top = set(capture["required_common_fields"])
    allowed_top.update(capture["allowed_kind_fields"].get(kind, []))
    unexpected = [f"event.{key}" for key in sorted(set(event) - allowed_top)]
    nested = (
        ("contact", capture["minimal_contact_fields"]),
        ("request", capture["minimal_request_fields"]),
        ("consent", capture["minimal_consent_fields"]),
    )
    for name, allowed in nested:
        value = event.get(name, {})
        if isinstance(value, dict):
            unexpected.extend(f"{name}.{key}" for key in sorted(set(value) - set(allowed)))
    if kind == "form_submission" and isinstance(event.get("source_tags"), dict):
        allowed_tags = set(capture["required_source_tags"])
        unexpected.extend(f"source_tags.{key}" for key in sorted(set(event["source_tags"]) - allowed_tags))
    if unexpected:
        raise ValueError(f"unexpected capture fields: {', '.join(unexpected)}")


def _validate_source_tag(value: Any, field_name: str, contract: dict[str, Any]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"source tag {field_name} must be a nonempty string")
    normalized = value.strip().lower()
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError(f"source tag {field_name} contains control characters")
    pattern = str(contract["capture_contract"]["source_tag_pattern"])
    if re.fullmatch(pattern, normalized) is None:
        raise ValueError(f"source tag {field_name} violates the bounded tag pattern")
    return normalized


def _bounded_text(
    value: Any,
    path: str,
    max_length: int,
    *,
    allow_content_newlines: bool = False,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{path} must be nonempty")
    if len(normalized) > max_length:
        raise ValueError(f"{path} exceeds its minimal-data limit")
    for character in normalized:
        if ord(character) < 32 or ord(character) == 127:
            if allow_content_newlines and character in {"\n", "\t"}:
                continue
            raise ValueError(f"{path} contains control characters")
    return normalized


def resolve_cta_intake(
    cta_id: str,
    capture_kind: str,
    *,
    surface: str,
    proof: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Resolve an unwired CTA contract without creating or activating a public surface."""

    mapping = contract["cta_intake_mapping"]
    if mapping["activation_authorized"] is not False:
        raise ValueError("CTA mapping must remain activation-disabled in preflight")
    try:
        door = mapping["doors"][cta_id]
    except KeyError as exc:
        raise ValueError(f"unknown CTA contract: {cta_id}") from exc
    if capture_kind not in door["allowed_capture_kinds"]:
        raise ValueError(f"CTA {cta_id} does not allow capture kind {capture_kind}")
    return {
        "cta_id": cta_id,
        "capture_kind": capture_kind,
        "selection_state": "contract_only",
        "activation_authorized": False,
        "mail_fallback": bool(door["mail_fallback"]),
        "source_tags": {
            "surface": _validate_source_tag(surface, "surface", contract),
            "proof": _validate_source_tag(proof, "proof", contract),
            "audience": _validate_source_tag(door["audience_tag"], "audience", contract),
        },
    }


def adapt_capture(event: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    """Adapt a future tagged-mail or form event into one capture-neutral envelope."""

    _require_keys(
        event,
        contract["capture_contract"]["required_common_fields"],
        "capture event",
    )
    _reject_sensitive_fields(event, contract)
    kind = event["kind"]
    if kind not in contract["capture_contract"]["accepted_kinds"]:
        raise ValueError(f"unsupported capture kind: {kind}")
    _reject_unexpected_fields(event, contract)

    if kind == "tagged_mail":
        match = MAIL_TAG.fullmatch(str(event.get("subject", "")))
        if match is None:
            raise ValueError("tagged_mail subject does not satisfy the inbound tag contract")
        source_tags = {
            "surface": match.group("surface").strip(),
            "proof": str(event.get("proof_tag", "")).strip(),
            "audience": match.group("audience").strip(),
        }
    else:
        source_tags = deepcopy(event.get("source_tags", {}))

    _require_keys(
        source_tags,
        contract["capture_contract"]["required_source_tags"],
        "source tags",
    )
    source_tags = {
        field_name: _validate_source_tag(source_tags[field_name], field_name, contract)
        for field_name in contract["capture_contract"]["required_source_tags"]
    }
    return {
        "fixture_id": event["fixture_id"],
        "kind": kind,
        "event_id": event["event_id"],
        "received_at": event["received_at"],
        "owner_partition": event["owner_partition"],
        "source_tags": source_tags,
        "contact": deepcopy(event["contact"]),
        "request": deepcopy(event["request"]),
        "consent": deepcopy(event["consent"]),
    }


def normalize_capture(envelope: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    contact = envelope["contact"]
    request = envelope["request"]
    _require_keys(contact, contract["capture_contract"]["minimal_contact_fields"], "contact")
    _require_keys(request, contract["capture_contract"]["minimal_request_fields"], "request")
    if envelope["consent"].get("process_contact") is not True:
        raise ValueError("processing consent is required")
    fields = contract["minimum_data_schema"]["fields"]
    name = _bounded_text(
        contact["name"],
        "contact.name",
        int(fields["contact.name"]["max_length"]),
    )
    email = _bounded_text(
        contact["email"],
        "contact.email",
        int(fields["contact.email"]["max_length"]),
    ).lower()
    if not email.endswith(".invalid"):
        raise ValueError("preflight accepts reserved .invalid addresses only")
    summary = _bounded_text(
        request["summary"],
        "request.summary",
        int(fields["request.summary"]["max_length"]),
    )
    details = _bounded_text(
        request["details"],
        "request.details",
        int(fields["request.details"]["max_length"]),
        allow_content_newlines=True,
    )
    fingerprint = "|".join(
        (
            str(envelope["owner_partition"]),
            email,
            summary.lower(),
            str(envelope["source_tags"]["surface"]).strip().lower(),
        )
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    return {
        "record_id": f"lead_{digest[:16]}",
        "dedupe_key": digest,
        "owner_partition": str(envelope["owner_partition"]),
        "received_at": envelope["received_at"],
        "source": deepcopy(envelope["source_tags"]),
        "contact": {
            "name": name,
            "email": email,
        },
        "request": {
            "summary": summary,
            "details": details,
        },
        "consent": {"process_contact": True},
        "stage": "normalized",
    }


def score_lead(record: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    haystack = " ".join(
        (
            str(record["source"]["audience"]),
            str(record["request"]["summary"]),
            str(record["request"]["details"]),
        )
    ).lower()
    audience = str(record["source"]["audience"]).lower()
    scores: dict[str, int] = {}
    for category, rule in contract["scoring"]["routes"].items():
        score = 0
        if audience in {str(item).lower() for item in rule["audience_hints"]}:
            score += 3
        score += sum(1 for signal in rule["signals"] if str(signal).lower() in haystack)
        scores[category] = score
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    category, top_score = ranked[0]
    next_score = ranked[1][1] if len(ranked) > 1 else 0
    margin = top_score - next_score
    confident = top_score >= int(contract["scoring"]["minimum_auto_score"]) and margin >= int(
        contract["scoring"]["minimum_margin"]
    )
    return {
        "scores": scores,
        "category": category if confident else "ambiguous",
        "confidence": "high" if confident else "low",
        "top_score": top_score,
        "margin": margin,
    }


def route_lead(scored: dict[str, Any], contract: dict[str, Any]) -> str:
    if scored["confidence"] != "high":
        return str(contract["scoring"]["ambiguous_route"])
    return str(contract["scoring"]["routes"][scored["category"]]["route"])


def generate_draft(
    record: dict[str, Any],
    scored: dict[str, Any],
    route: str,
    contract: dict[str, Any],
) -> dict[str, str]:
    category = scored["category"]
    family = {
        "client": "client_acknowledgment",
        "recruiter": "recruiter_acknowledgment",
        "operator": "operator_review",
        "spam": "decline",
        "ambiguous": "manual_review",
    }[category]
    template = contract["drafts"]["templates"][family]
    values = {
        "name": str(record["contact"]["name"]),
        "summary": str(record["request"]["summary"]),
        "route": route,
    }
    return {
        "status": "draft",
        "kind": family,
        "subject": str(template["subject"]).format(**values),
        "body": str(template["body"]).format(**values),
        "send_authority": "absent",
    }


@dataclass
class PrivateCustodyBoundary:
    """Adapter boundary for sealed persistence; it intentionally supplies no crypto."""

    seal: Callable[[bytes], bytes]
    open_sealed: Callable[[bytes], bytes]
    sealed_records: dict[str, dict[str, bytes]] = field(default_factory=dict)

    def persist(self, record: dict[str, Any], decision: dict[str, Any]) -> bool:
        partition = str(record["owner_partition"])
        record_id = str(record["record_id"])
        plaintext = json.dumps(
            {"record": record, "decision": decision},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        sealed = self.seal(plaintext)
        if not isinstance(sealed, bytes) or sealed == plaintext:
            raise ValueError("custody adapter must return non-plaintext sealed bytes")
        bucket = self.sealed_records.setdefault(partition, {})
        created = record_id not in bucket
        bucket[record_id] = sealed
        return created

    def get(self, owner_partition: str, record_id: str) -> dict[str, Any]:
        sealed = self.sealed_records[owner_partition][record_id]
        plaintext = self.open_sealed(sealed)
        if not isinstance(plaintext, bytes):
            raise ValueError("custody adapter must open sealed values as bytes")
        value = json.loads(plaintext.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("custody adapter opened a non-object payload")
        return value

    def delete(self, owner_partition: str, record_id: str) -> bool:
        bucket = self.sealed_records.get(owner_partition)
        if not bucket or record_id not in bucket:
            return False
        del bucket[record_id]
        if not bucket:
            del self.sealed_records[owner_partition]
        return True


@dataclass
class PrivateLedger:
    records: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    dedupe_index: dict[str, set[str]] = field(default_factory=dict)

    def upsert(self, record: dict[str, Any], decision: dict[str, Any]) -> bool:
        partition = str(record["owner_partition"])
        record_id = str(record["record_id"])
        bucket = self.records.setdefault(partition, {})
        created = record_id not in bucket
        bucket[record_id] = {
            "record": deepcopy(record),
            "decision": deepcopy(decision),
        }
        self.dedupe_index.setdefault(partition, set()).add(str(record["dedupe_key"]))
        return created

    def get(self, owner_partition: str, record_id: str) -> dict[str, Any]:
        return deepcopy(self.records[owner_partition][record_id])

    def delete(self, owner_partition: str, record_id: str) -> bool:
        bucket = self.records.get(owner_partition)
        if not bucket or record_id not in bucket:
            return False
        dedupe_key = str(bucket[record_id]["record"]["dedupe_key"])
        del bucket[record_id]
        partition_dedupe = self.dedupe_index.get(owner_partition, set())
        partition_dedupe.discard(dedupe_key)
        if not bucket:
            del self.records[owner_partition]
        if not partition_dedupe:
            self.dedupe_index.pop(owner_partition, None)
        return True

    def private_view(self, owner_partition: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record_id, row in sorted(self.records.get(owner_partition, {}).items()):
            record = row["record"]
            decision = row["decision"]
            rows.append(
                {
                    "record_id": record_id,
                    "received_at": record["received_at"],
                    "category": decision["category"],
                    "confidence": decision["confidence"],
                    "route": decision["route"],
                    "stage": decision["stage"],
                    "draft_kind": decision["draft"]["kind"],
                }
            )
        return rows

    def aggregate(self) -> dict[str, Any]:
        rows = [row for bucket in self.records.values() for row in bucket.values()]
        routes = Counter(row["decision"]["route"] for row in rows)
        categories = Counter(row["decision"]["category"] for row in rows)
        stages = Counter(row["decision"]["stage"] for row in rows)
        draft_kinds = Counter(row["decision"]["draft"]["kind"] for row in rows)
        return {
            "private_record_count": len(rows),
            "owner_partition_count": len(self.records),
            "routes": dict(sorted(routes.items())),
            "categories": dict(sorted(categories.items())),
            "stages": dict(sorted(stages.items())),
            "draft_kinds": dict(sorted(draft_kinds.items())),
        }


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def retention_action(
    record: dict[str, Any],
    category: str,
    *,
    as_of: datetime,
    contract: dict[str, Any],
    trigger: str | None = None,
) -> str:
    retention = contract["retention"]
    if trigger is not None:
        if trigger not in retention["immediate_delete_triggers"]:
            raise ValueError(f"unsupported retention trigger: {trigger}")
        return "delete"
    days = int(retention["category_days"][category])
    current = as_of if as_of.tzinfo else as_of.replace(tzinfo=timezone.utc)
    age_seconds = (current.astimezone(timezone.utc) - _parse_utc(record["received_at"])).total_seconds()
    return "delete" if age_seconds >= days * 86400 else "retain"


def apply_retention(
    ledger: PrivateLedger,
    custody: PrivateCustodyBoundary,
    owner_partition: str,
    record_id: str,
    category: str,
    *,
    as_of: datetime,
    contract: dict[str, Any],
    trigger: str | None = None,
) -> dict[str, Any]:
    row = ledger.get(owner_partition, record_id)
    action = retention_action(row["record"], category, as_of=as_of, contract=contract, trigger=trigger)
    deleted_count = 0
    sealed_deleted_count = 0
    if action == "delete":
        deleted_count = int(ledger.delete(owner_partition, record_id))
        sealed_deleted_count = int(custody.delete(owner_partition, record_id))
    return {
        "action": action,
        "deleted_count": deleted_count,
        "sealed_deleted_count": sealed_deleted_count,
        "receipt_scope": "aggregate_only_no_identifier",
    }


@dataclass
class ClosedSendValve:
    authority_state: str = "absent"
    external_send_count: int = 0
    blocked_send_attempt_count: int = 0

    def attempt_send(self, _draft: dict[str, str]) -> None:
        self.blocked_send_attempt_count += 1
        raise PermissionError("PSP-C07 preflight send valve is hard closed")


def run_synthetic_journeys(
    fixtures: dict[str, Any], contract: dict[str, Any]
) -> tuple[dict[str, Any], PrivateLedger, ClosedSendValve]:
    errors = validate_contract(contract) + validate_fixtures(fixtures, contract)
    if errors:
        raise ValueError("; ".join(errors))
    ledger = PrivateLedger()
    valve = ClosedSendValve()
    journeys: list[dict[str, Any]] = []
    seen_dedupe: set[str] = set()
    for event in fixtures["events"]:
        envelope = adapt_capture(event, contract)
        record = normalize_capture(envelope, contract)
        if record["dedupe_key"] in seen_dedupe:
            continue
        seen_dedupe.add(record["dedupe_key"])
        scored = score_lead(record, contract)
        route = route_lead(scored, contract)
        draft = generate_draft(record, scored, route, contract)
        decision = {
            "category": scored["category"],
            "confidence": scored["confidence"],
            "route": route,
            "draft": draft,
            "stage": "review_pending",
        }
        ledger.upsert(record, decision)
        journeys.append(
            {
                "fixture_id": envelope["fixture_id"],
                "record_id": record["record_id"],
                "stages": [
                    "captured",
                    "normalized",
                    "scored",
                    "routed",
                    "drafted",
                    "review_pending",
                ],
                "category": scored["category"],
                "route": route,
                "confidence": scored["confidence"],
                "draft_kind": draft["kind"],
            }
        )
    receipt = {
        "schema_version": "limen.psp_c07_preflight_receipt.v1",
        "status": "pass",
        "mode": "synthetic_preflight",
        "dependency_gate": "blocked_on_PSP-P03-W07_PSP-P04_PSP-P07",
        "journeys": journeys,
        "aggregate": ledger.aggregate(),
        "evaluation": evaluate_routes(journeys, fixtures),
        "external_send_count": valve.external_send_count,
        "blocked_send_attempt_count": valve.blocked_send_attempt_count,
    }
    return receipt, ledger, valve


def live_gate_status(contract: dict[str, Any]) -> dict[str, Any]:
    gate = contract["formal_dependency_gate"]
    if gate["commercial_upstream"]["PSP-P03"]["w07"]["state"] != "closed_with_predicate_receipt":
        return {
            "ready": False,
            "blocking_dependency": LIVE_GATE_ORDER[0],
            "reason": "PSP-P03-W07 five-reader predicate receipt is absent; PSP-P04 remains dependency-gated",
            "gate_order": list(LIVE_GATE_ORDER),
        }
    if gate["phase_states"]["PSP-P04"] != "closed_with_predicate_receipt":
        return {
            "ready": False,
            "blocking_dependency": LIVE_GATE_ORDER[1],
            "reason": "PSP-P04 predicate receipt is absent",
            "gate_order": list(LIVE_GATE_ORDER),
        }
    if gate["phase_states"]["PSP-P07"] != "closed_with_predicate_receipt":
        return {
            "ready": False,
            "blocking_dependency": LIVE_GATE_ORDER[2],
            "reason": "PSP-P07 predicate receipt is absent",
            "gate_order": list(LIVE_GATE_ORDER),
        }
    if not gate["selected_capture_surface"]:
        return {
            "ready": False,
            "blocking_dependency": LIVE_GATE_ORDER[3],
            "reason": "no approved C06 capture surface is selected",
            "gate_order": list(LIVE_GATE_ORDER),
        }
    if gate["separate_leaf_authority"] != "leased":
        return {
            "ready": False,
            "blocking_dependency": LIVE_GATE_ORDER[4],
            "reason": "separate P08 leaf authority is absent",
            "gate_order": list(LIVE_GATE_ORDER),
        }
    return {
        "ready": True,
        "blocking_dependency": None,
        "reason": "live adapter may be implemented under a separately leased leaf",
        "gate_order": list(LIVE_GATE_ORDER),
    }


def live_gate(contract: dict[str, Any]) -> tuple[bool, str]:
    status = live_gate_status(contract)
    return bool(status["ready"]), str(status["reason"])


def _redaction_errors(receipt: dict[str, Any], fixtures: dict[str, Any]) -> list[str]:
    rendered = json.dumps(receipt, sort_keys=True)
    leaks: list[str] = []
    for event in fixtures.get("events", []):
        for value in (
            event.get("contact", {}).get("name"),
            event.get("contact", {}).get("email"),
            event.get("request", {}).get("summary"),
            event.get("request", {}).get("details"),
        ):
            if value and str(value) in rendered:
                leaks.append(str(event.get("fixture_id", "unknown")))
                break
    return sorted(set(leaks))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument(
        "--mode",
        choices=("validate", "traverse", "live-gate"),
        default="validate",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    contract = load_json(args.contract)
    fixtures = load_json(args.fixtures)
    errors = validate_contract(contract) + validate_fixtures(fixtures, contract)
    result: dict[str, Any] = {
        "status": "pass" if not errors else "fail",
        "mode": args.mode,
        "errors": errors,
    }
    exit_code = 0 if not errors else 1
    if not errors and args.mode == "traverse":
        receipt, _ledger, _valve = run_synthetic_journeys(fixtures, contract)
        redaction_errors = _redaction_errors(receipt, fixtures)
        if redaction_errors:
            result = {
                "status": "fail",
                "mode": args.mode,
                "errors": [f"public receipt leaked fixtures: {', '.join(redaction_errors)}"],
            }
            exit_code = 1
        else:
            result = receipt
    elif not errors and args.mode == "live-gate":
        gate_status = live_gate_status(contract)
        ready = bool(gate_status["ready"])
        result = {
            "status": "pass" if ready else "blocked",
            "mode": args.mode,
            "reason": gate_status["reason"],
            "blocking_dependency": gate_status["blocking_dependency"],
            "gate_order": gate_status["gate_order"],
        }
        exit_code = 0 if ready else 2

    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"].upper())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
