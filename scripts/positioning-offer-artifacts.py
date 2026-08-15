#!/usr/bin/env python3
"""Generate and validate public-safe PSP-P04 offer artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "institutio/positioning/commercial-contract.yaml"
OUTPUT_DIR = ROOT / "docs/positioning/offers"

OFFER_FILES = {
    "audit": "agentic-delivery-audit.md",
    "install": "governance-install.md",
    "retainer": "bounded-delivery-governance-retainer.md",
    "partnership_review": "product-operating-partnership-review.md",
}
QUALIFICATION_FILE = "qualification-and-routing.md"
CAPACITY_FILE = "bounded-delivery-governance-retainer-capacity.json"
EXPECTED_FILES = frozenset((*OFFER_FILES.values(), QUALIFICATION_FILE, CAPACITY_FILE))
KNOWN_MATERIALIZED_FILES = frozenset((*EXPECTED_FILES, "agentic-delivery-audit-decision-record.json"))
WORK_ITEMS = {
    "audit": "PSP-P04-W01",
    "install": "PSP-P04-W02",
    "retainer": "PSP-P04-W03",
    "partnership_review": "PSP-P04-W07",
}
PRIMARY_SEQUENCE = ["audit", "install", "retainer"]
COMMERCIAL_ROUTES = frozenset((*PRIMARY_SEQUENCE, "partnership_review"))
EXPECTED_ROUTE_PRIORITY = [
    "human_review",
    "decline",
    "recruiter",
    "partnership_review",
    "retainer",
    "install",
    "audit",
]
QUALIFICATION_ROUTES = frozenset(EXPECTED_ROUTE_PRIORITY)
EXPECTED_OFFER_CONTRACT = {
    "audit": {
        "stage": "diagnose",
        "position": "primary_entry",
        "authority_mode": "read_only",
        "anchor_id": "PRICE-AUDIT",
        "range_id": "RANGE-AUDIT",
        "approval_gate": "HG-PRICE-ANCHORS",
    },
    "install": {
        "stage": "implement",
        "position": "primary_expansion",
        "authority_mode": "bounded_write",
        "anchor_id": "PRICE-INSTALL",
        "range_id": "RANGE-INSTALL",
        "approval_gate": "HG-PRICE-ANCHORS",
    },
    "retainer": {
        "stage": "sustain",
        "position": "primary_continuity",
        "authority_mode": "advisory_with_named_changes",
        "anchor_id": "PRICE-RETAINER",
        "range_id": "RANGE-RETAINER",
        "approval_gate": "HG-PRICE-ANCHORS",
    },
    "partnership_review": {
        "stage": "diligence",
        "position": "secondary_only",
        "authority_mode": "diligence_only",
        "anchor_id": "PRICE-PARTNERSHIP",
        "range_id": "RANGE-PARTNERSHIP",
        "approval_gate": "HG-OPERATOR-TERMS",
    },
}
REQUIRED_OFFER_FIELDS = frozenset(
    {
        "id",
        "name",
        "stage",
        "position",
        "buyer",
        "trigger",
        "entry_criteria",
        "promise",
        "deliverables",
        "exclusions",
        "timeline",
        "authority",
        "evidence",
        "economics",
        "handoff",
        "escalation",
        "claim_refs",
    }
)
REQUIRED_AUTHORITY_FIELDS = frozenset({"mode", "boundary"})
REQUIRED_EVIDENCE_FIELDS = frozenset({"acceptance", "artifacts"})
REQUIRED_ECONOMICS_FIELDS = frozenset(
    {
        "model",
        "anchor_id",
        "range_id",
        "approval_gate",
        "public_price",
        "capacity_rule",
        "discount_rule",
    }
)
REQUIRED_RETAINER_CAPACITY_FIELDS = frozenset(
    {
        "schema_version",
        "offer_id",
        "review_period",
        "included_delivery_days",
        "hours_per_delivery_day",
        "included_hours",
        "allocation",
        "allocation_rule",
        "consumption_rule",
        "quantity_limits",
        "rollover",
        "exhaustion_route",
        "cadence",
        "response_envelope",
        "decision_rights",
        "included_artifacts",
        "exclusions",
        "escalation",
        "escalation_routes",
        "renewal_exit",
    }
)
REQUIRED_CAPACITY_ALLOCATION_FIELDS = frozenset(
    {
        "scheduled_governance_days",
        "approved_change_days",
        "scheduled_contingency_days",
        "uncommitted_days",
    }
)
REQUIRED_CAPACITY_CADENCE_FIELDS = frozenset(
    {
        "evidence_reviews_per_period",
        "exception_reviews_per_period",
        "capacity_reviews_per_period",
        "closeouts_per_period",
        "change_window",
    }
)
REQUIRED_CAPACITY_QUANTITY_FIELDS = frozenset(
    {
        "active_change_items",
        "reviews_or_postmortems_per_period",
        "teams",
        "repositories",
        "included_revisions_per_change",
    }
)
REQUIRED_RESPONSE_ENVELOPE_FIELDS = frozenset(
    {
        "channel",
        "timezone",
        "business_hours",
        "service_window",
        "acknowledgement_target_business_days",
        "decision_target_business_days",
        "target_boundary",
        "clock_pause_conditions",
        "on_call",
        "emergency_response",
        "resolution_sla",
    }
)
REQUIRED_DECISION_RIGHTS_FIELDS = frozenset({"internal_owner", "sponsor", "provider", "provider_prohibited_actions"})
REQUIRED_ESCALATION_ROUTE_FIELDS = frozenset(
    {"capacity_exhaustion", "missing_owner", "authority_expansion", "security_privacy_legal_contract"}
)
REQUIRED_RENEWAL_EXIT_FIELDS = frozenset({"renewal_gate", "exit_trigger", "exit_steps"})
ALLOWED_CAPACITY_NUMERIC_PATHS = frozenset(
    {
        "included_delivery_days",
        "hours_per_delivery_day",
        "included_hours",
        *{f"allocation.{field}" for field in REQUIRED_CAPACITY_ALLOCATION_FIELDS},
        *{f"quantity_limits.{field}" for field in REQUIRED_CAPACITY_QUANTITY_FIELDS},
        *{f"cadence.{field}" for field in REQUIRED_CAPACITY_CADENCE_FIELDS if field != "change_window"},
        "response_envelope.acknowledgement_target_business_days",
        "response_envelope.decision_target_business_days",
    }
)
REQUIRED_PROHIBITED_EFFECTS = frozenset(
    {
        "external public-surface activation or promotion",
        "issue or phase closure",
        "P04 phase closure before PSP-P03 closes",
        "outbound sending",
        "spend or account mutation",
        "DNS or visibility changes",
        "contractual or partnership commitment",
    }
)

PRIVATE_PATTERNS = (
    re.compile(r"(?:^|[\s`(\"':])(?:/Users/|/home/|/private/|~/|file://)", re.IGNORECASE),
    re.compile(r"\b[A-Z]:\\Users\\", re.IGNORECASE),
    re.compile(
        r"(?:\.limen-private/|\.agent-runtime/|session-state/|archived_sessions/|"
        r"private-vault|positioning-seeds\.json)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        re.IGNORECASE,
    ),
)
PRICE_PATTERNS = (
    re.compile(r"[$£€]\s*\d"),
    re.compile(
        r"\b\d+(?:[,.]\d+)*\s*(?:USD|EUR|GBP|dollars?|euros?|pounds?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d+(?:[,.]\d+)*\s*(?:/\s*(?:hr|hour|day|month|year)|per\s+(?:hour|day|month|year))\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d+(?:\.\d+)?\s*[kK]\b"),
    re.compile(
        r"\b(?:fee|price|rate|discount|margin|equity|revenue[- ]share|transfer\s+term)"
        r"\s*(?:is|of|at|:|=)?\s*[$£€]?\s*\d",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d+(?:\.\d+)?\s*%\s*(?:discount|margin|equity|revenue[- ]share)\b",
        re.IGNORECASE,
    ),
)
NUMERIC_TOKEN_PATTERN = re.compile(r"\b\d+(?:[,.]\d+)*(?:\s*%)?\b")
FRONT_DOOR_MARKER = "**Front-door next step:**"
GENERATED_NOTICE = (
    "<!-- Generated by scripts/positioning-offer-artifacts.py from the canonical "
    "commercial contract; do not edit by hand. -->"
)


class OfferArtifactValidationError(ValueError):
    """Raised when the canonical source cannot be loaded safely."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping members."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> Any:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise OfferArtifactValidationError("YAML mapping keys must be hashable scalars") from exc
        if duplicate:
            raise OfferArtifactValidationError(f"duplicate YAML mapping key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            yield from _strings(item)


def _require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _require_fields(
    errors: list[str],
    value: Any,
    fields: Iterable[str],
    label: str,
) -> Mapping[str, Any]:
    mapping = _mapping(value)
    if not mapping:
        errors.append(f"{label} must be a non-empty mapping")
    for field in sorted(fields):
        field_value = mapping.get(field)
        if field not in mapping or field_value is None or (isinstance(field_value, str) and not field_value.strip()):
            errors.append(f"{label} missing required field: {field}")
    return mapping


def _require_exact_mapping(
    errors: list[str],
    value: Any,
    fields: Iterable[str],
    label: str,
) -> Mapping[str, Any]:
    expected = set(fields)
    mapping = _require_fields(errors, value, expected, label)
    non_string_keys = [key for key in mapping if not isinstance(key, str)]
    if non_string_keys:
        errors.append(
            f"{label} keys must be strings; found non-string keys {sorted(repr(key) for key in non_string_keys)}"
        )
        return mapping
    if mapping and set(mapping) != expected:
        errors.append(f"{label} fields must be exactly {sorted(expected)}; found {sorted(mapping)}")
    return mapping


def _is_bounded_int(value: Any, *, minimum: int, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _is_nonblank_text_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
        and len(value) == len(set(value))
    )


def _is_unique_text_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
        and len(value) == len(set(value))
    )


def _numeric_leaf_paths(value: Any, prefix: str = "") -> Iterable[str]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield prefix
    elif isinstance(value, Mapping):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _numeric_leaf_paths(item, path)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, item in enumerate(value):
            yield from _numeric_leaf_paths(item, f"{prefix}[{index}]")


def _offer_map(data: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    ladder = _mapping(data.get("offer_ladder"))
    result: dict[str, Mapping[str, Any]] = {}
    for raw_offer in _sequence(ladder.get("items")):
        offer = _mapping(raw_offer)
        offer_id = offer.get("id")
        if isinstance(offer_id, str):
            result[offer_id] = offer
    secondary = _mapping(ladder.get("secondary"))
    secondary_id = secondary.get("id")
    if isinstance(secondary_id, str):
        result[secondary_id] = secondary
    return result


def _audience_map(data: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for raw_audience in _sequence(data.get("audiences")):
        audience = _mapping(raw_audience)
        audience_id = audience.get("id")
        if isinstance(audience_id, str):
            result[audience_id] = audience
    return result


def _rule_matches(rule: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    all_terms = _sequence(rule.get("all"))
    any_terms = _sequence(rule.get("any"))
    none_terms = _sequence(rule.get("none"))
    return (
        all(facts.get(str(term), False) is True for term in all_terms)
        and (not any_terms or any(facts.get(str(term), False) is True for term in any_terms))
        and not any(facts.get(str(term), False) is True for term in none_terms)
    )


def evaluate_qualification_route(
    rules: Sequence[Mapping[str, Any]],
    facts: Mapping[str, bool],
    default_route: str,
) -> str:
    """Return the first priority-ordered matching route, or the explicit default."""
    for rule in sorted(rules, key=_priority_value):
        if _rule_matches(rule, facts):
            return str(rule["route"])
    return default_route


def _priority_value(rule: Mapping[str, Any]) -> int:
    priority = rule.get("priority")
    return priority if isinstance(priority, int) else 10**9


def validate_artifact_text(label: str, text: str) -> list[str]:
    """Return public-safety violations found in one rendered artifact."""
    errors: list[str] = []
    for pattern in PRIVATE_PATTERNS:
        match = pattern.search(text)
        if match:
            errors.append(f"private path or source leaked into {label}: {match.group(0).strip()}")
    for pattern in PRICE_PATTERNS:
        match = pattern.search(text)
        if match:
            errors.append(f"numeric price leaked into {label}: {match.group(0).strip()}")
    return errors


def validate_contract(data: Mapping[str, Any]) -> list[str]:
    """Validate the source fields and safety invariants used by public artifacts."""
    errors: list[str] = []
    _require(
        errors,
        data.get("schema_version") == "limen.positioning_commercial_contract.v1",
        "schema version must be limen.positioning_commercial_contract.v1",
    )

    contract = _require_fields(
        errors,
        data.get("contract"),
        {
            "status",
            "work_chunk",
            "canonical_source",
            "formal_dependency",
            "prohibited_preflight_effects",
        },
        "contract",
    )
    _require(
        errors,
        isinstance(contract.get("status"), str),
        "contract status must be explicit text",
    )
    _require(
        errors,
        contract.get("work_chunk") == "PSP-C03",
        "offer contract must remain owned by PSP-C03",
    )
    _require(
        errors,
        contract.get("canonical_source") == "institutio/positioning/commercial-contract.yaml",
        "canonical source path drifted",
    )
    dependency = _require_fields(
        errors,
        contract.get("formal_dependency"),
        {"chunk_id", "phase_id", "state", "consequence"},
        "contract.formal_dependency",
    )
    _require(
        errors,
        isinstance(dependency.get("state"), str),
        "formal dependency state must be explicit text",
    )
    prohibited_effects = [str(effect) for effect in _sequence(contract.get("prohibited_preflight_effects"))]
    for effect in sorted(REQUIRED_PROHIBITED_EFFECTS):
        _require(
            errors,
            any(effect in recorded_effect for recorded_effect in prohibited_effects),
            f"missing prohibited preflight effect: {effect}",
        )

    ladder = _require_fields(
        errors,
        data.get("offer_ladder"),
        {"primary_sequence", "items", "secondary"},
        "offer_ladder",
    )
    primary_items = [_mapping(item) for item in _sequence(ladder.get("items"))]
    primary_ids = [item.get("id") for item in primary_items]
    _require(
        errors,
        list(_sequence(ladder.get("primary_sequence"))) == PRIMARY_SEQUENCE,
        "primary sequence must remain audit -> install -> retainer",
    )
    _require(
        errors,
        primary_ids == PRIMARY_SEQUENCE,
        f"primary offer order drifted: expected {PRIMARY_SEQUENCE}, found {primary_ids}",
    )

    secondary = _mapping(ladder.get("secondary"))
    all_offers = [*primary_items, secondary]
    all_offer_ids = [offer.get("id") for offer in all_offers]
    _require(
        errors,
        all_offer_ids == [*PRIMARY_SEQUENCE, "partnership_review"],
        "offer set must contain audit, install, retainer, and partnership_review exactly once",
    )

    signatures: dict[str, set[str]] = {
        "stage": set(),
        "position": set(),
        "trigger": set(),
        "promise": set(),
    }
    symbolic_ids: set[str] = set()
    for offer in all_offers:
        offer_id = str(offer.get("id", "unknown"))
        required_fields = set(REQUIRED_OFFER_FIELDS)
        if offer_id == "partnership_review":
            required_fields.update({"public_cta", "disclosure_entry"})
        checked_offer = _require_fields(
            errors,
            offer,
            required_fields,
            f"offer {offer_id}",
        )
        for list_field in (
            "entry_criteria",
            "deliverables",
            "exclusions",
            "escalation",
            "claim_refs",
        ):
            _require(
                errors,
                bool(_sequence(checked_offer.get(list_field))),
                f"offer {offer_id} field {list_field} must be a non-empty list",
            )

        authority = _require_fields(
            errors,
            checked_offer.get("authority"),
            REQUIRED_AUTHORITY_FIELDS,
            f"offer {offer_id}.authority",
        )
        evidence = _require_fields(
            errors,
            checked_offer.get("evidence"),
            REQUIRED_EVIDENCE_FIELDS,
            f"offer {offer_id}.evidence",
        )
        _require(
            errors,
            bool(_sequence(evidence.get("artifacts"))),
            f"offer {offer_id}.evidence.artifacts must be a non-empty list",
        )
        economics = _require_fields(
            errors,
            checked_offer.get("economics"),
            REQUIRED_ECONOMICS_FIELDS,
            f"offer {offer_id}.economics",
        )

        expected = EXPECTED_OFFER_CONTRACT.get(offer_id)
        if expected:
            for field in ("stage", "position"):
                _require(
                    errors,
                    checked_offer.get(field) == expected[field],
                    f"offer {offer_id} {field} must remain {expected[field]}",
                )
            _require(
                errors,
                authority.get("mode") == expected["authority_mode"],
                f"offer {offer_id} authority must remain {expected['authority_mode']}",
            )
            for field in ("anchor_id", "range_id", "approval_gate"):
                _require(
                    errors,
                    economics.get(field) == expected[field],
                    f"offer {offer_id} {field} must remain {expected[field]}",
                )
        _require(
            errors,
            economics.get("public_price") == "prohibited",
            f"offer {offer_id} must prohibit public pricing",
        )

        for signature_name in signatures:
            signature = str(checked_offer.get(signature_name, "")).strip().lower()
            if signature and signature in signatures[signature_name]:
                errors.append(f"offer overlap: duplicate {signature_name} boundary for {offer_id}")
            signatures[signature_name].add(signature)
        for symbolic_field in ("anchor_id", "range_id"):
            symbolic = str(economics.get(symbolic_field, ""))
            if symbolic in symbolic_ids:
                errors.append(f"offer overlap: duplicate symbolic economics ID {symbolic}")
            symbolic_ids.add(symbolic)

    offer_by_id = _offer_map(data)
    audit_blob = " ".join(_strings(offer_by_id.get("audit", {}))).lower()
    install = offer_by_id.get("install", {})
    install_blob = " ".join(_strings(install)).lower()
    retainer = offer_by_id.get("retainer", {})
    retainer_blob = " ".join(_strings(retainer)).lower()
    partnership_blob = " ".join(_strings(offer_by_id.get("partnership_review", {}))).lower()
    _require(
        errors,
        "production mutation or deployment" in audit_blob,
        "Audit must exclude production mutation or deployment",
    )
    _require(
        errors,
        "one named sponsor, internal owner, team, and pipeline" in install_blob,
        "Install must remain bounded to one named team or pipeline",
    )
    install_entry_criteria = {str(value) for value in _sequence(install.get("entry_criteria"))}
    _require(
        errors,
        "one named sponsor, internal owner, team, and pipeline" in install_entry_criteria,
        "Install requires one named sponsor, internal owner, team, and pipeline",
    )
    _require(
        errors,
        "acceptance tests and a handoff owner agreed before work starts" in install_entry_criteria,
        "Install requires acceptance tests and a handoff owner before work starts",
    )
    install_evidence = _mapping(install.get("evidence"))
    install_acceptance = str(install_evidence.get("acceptance", "")).lower()
    install_artifacts = {str(value).lower() for value in _sequence(install_evidence.get("artifacts"))}
    install_handoff = str(install.get("handoff", "")).lower()
    _require(
        errors,
        install.get("timeline") == "Four to eight weeks for one team or pipeline after prerequisites are met."
        and {"tests", "acceptance receipt"}.issubset(install_artifacts)
        and "durable receipt" in install_acceptance
        and "named internal owner" in install_acceptance
        and "train the internal owner" in install_handoff
        and "transfer the runbook and evidence" in install_handoff
        and "test rollback" in install_handoff,
        "Install requires finite acceptance evidence and a named internal-owner handoff",
    )
    _require(
        errors,
        "enterprise-wide platform rewrite" in {str(value) for value in _sequence(install.get("exclusions"))},
        "Install must explicitly exclude an enterprise-wide platform rewrite",
    )
    _require(
        errors,
        "an accepted installed baseline" in retainer_blob
        and "on-call, emergency, or round-the-clock response" in retainer_blob
        and "unlimited implementation" in retainer_blob,
        ("Retainer must require an installed baseline and exclude on-call or unlimited implementation"),
    )
    capacity = _require_exact_mapping(
        errors,
        retainer.get("capacity_model"),
        REQUIRED_RETAINER_CAPACITY_FIELDS,
        "offer retainer.capacity_model",
    )
    numeric_paths = set(_numeric_leaf_paths(capacity))
    _require(
        errors,
        numeric_paths == ALLOWED_CAPACITY_NUMERIC_PATHS,
        "retainer capacity numeric fields must match the explicit non-monetary path allowlist",
    )
    _require(
        errors,
        capacity.get("schema_version") == "limen.positioning.retainer_capacity.v1",
        "retainer capacity schema must be limen.positioning.retainer_capacity.v1",
    )
    _require(errors, capacity.get("offer_id") == "retainer", "retainer capacity offer_id must be retainer")
    _require(
        errors,
        capacity.get("review_period") == "calendar_month",
        "retainer capacity review period must remain calendar_month",
    )
    included_days = capacity.get("included_delivery_days")
    hours_per_day = capacity.get("hours_per_delivery_day")
    included_hours = capacity.get("included_hours")
    _require(
        errors,
        _is_bounded_int(included_days, minimum=1, maximum=10),
        "retainer included_delivery_days must be a non-boolean integer from 1 through 10",
    )
    _require(
        errors,
        _is_bounded_int(included_days, minimum=1, maximum=10)
        and _is_bounded_int(hours_per_day, minimum=1, maximum=8)
        and _is_bounded_int(included_hours, minimum=1, maximum=80)
        and included_hours == included_days * hours_per_day,
        "retainer included_hours must exactly equal included_delivery_days times hours_per_delivery_day",
    )
    allocation = _require_exact_mapping(
        errors,
        capacity.get("allocation"),
        REQUIRED_CAPACITY_ALLOCATION_FIELDS,
        "offer retainer.capacity_model.allocation",
    )
    allocation_values = [allocation.get(field) for field in sorted(REQUIRED_CAPACITY_ALLOCATION_FIELDS)]
    _require(
        errors,
        all(_is_bounded_int(value, minimum=0, maximum=10) for value in allocation_values),
        "retainer allocation values must be non-boolean integers from 0 through 10",
    )
    if _is_bounded_int(included_days, minimum=1, maximum=10) and all(
        _is_bounded_int(value, minimum=0, maximum=10) for value in allocation_values
    ):
        _require(
            errors,
            sum(allocation_values) == included_days,
            "retainer allocation must equal included_delivery_days exactly",
        )
    _require(
        errors,
        isinstance(capacity.get("allocation_rule"), str)
        and capacity.get("allocation_rule", "").strip()
        and "not on-call" in capacity.get("allocation_rule", "").lower()
        and "expires at period close" in capacity.get("allocation_rule", "").lower(),
        "retainer allocation rule must make uncommitted capacity scheduled, non-on-call, and expiring",
    )
    consumption_rule = str(capacity.get("consumption_rule", "")).lower()
    _require(
        errors,
        isinstance(capacity.get("consumption_rule"), str)
        and all(
            term in consumption_rule
            for term in ("meeting", "review", "analysis", "message", "postmortem", "approved change", "capacity ledger")
        ),
        "retainer consumption rule must debit every service activity from one finite capacity ledger",
    )
    quantity_limits = _require_exact_mapping(
        errors,
        capacity.get("quantity_limits"),
        REQUIRED_CAPACITY_QUANTITY_FIELDS,
        "offer retainer.capacity_model.quantity_limits",
    )
    _require(
        errors,
        all(_is_bounded_int(quantity_limits.get(field), minimum=1, maximum=10) for field in quantity_limits)
        and quantity_limits.get("teams") == 1
        and quantity_limits.get("active_change_items") == 1,
        "retainer quantity limits must be finite positive integers with one team and one active change",
    )
    exhaustion_route = str(capacity.get("exhaustion_route", "")).lower()
    _require(
        errors,
        capacity.get("rollover") is False
        and isinstance(capacity.get("exhaustion_route"), str)
        and all(
            term in exhaustion_route
            for term in ("trade off", "next period", "change order", "governance install", "no standby")
        ),
        "retainer capacity must not roll over or imply standby and must route exhaustion deterministically",
    )

    cadence = _require_exact_mapping(
        errors,
        capacity.get("cadence"),
        REQUIRED_CAPACITY_CADENCE_FIELDS,
        "offer retainer.capacity_model.cadence",
    )
    _require(
        errors,
        all(
            _is_bounded_int(cadence.get(field), minimum=1, maximum=4)
            for field in REQUIRED_CAPACITY_CADENCE_FIELDS - {"change_window"}
        )
        and cadence.get("change_window") == "scheduled against the accepted backlog",
        "retainer cadence must name finite review and closeout counts plus a scheduled change window",
    )
    response = _require_exact_mapping(
        errors,
        capacity.get("response_envelope"),
        REQUIRED_RESPONSE_ENVELOPE_FIELDS,
        "offer retainer.capacity_model.response_envelope",
    )
    acknowledgement_days = response.get("acknowledgement_target_business_days")
    decision_days = response.get("decision_target_business_days")
    _require(
        errors,
        _is_bounded_int(acknowledgement_days, minimum=1, maximum=10)
        and _is_bounded_int(decision_days, minimum=1, maximum=10)
        and acknowledgement_days <= decision_days,
        "retainer response targets must be ordered non-boolean business-day integers from 1 through 10",
    )
    _require(
        errors,
        response.get("channel") == "named shared written channel"
        and response.get("timezone") == "sponsor-agreed named timezone recorded before the period"
        and response.get("business_hours") == "sponsor-agreed named business hours recorded before the period"
        and response.get("service_window") == "scheduled business days only"
        and isinstance(response.get("target_boundary"), str)
        and "no emergency or round-the-clock sla" in response.get("target_boundary", "").lower()
        and _is_nonblank_text_list(response.get("clock_pause_conditions"))
        and response.get("clock_pause_conditions")
        == [
            "outside the service window",
            "waiting on an owner decision",
            "waiting on required access or evidence",
        ]
        and response.get("on_call") is False
        and response.get("emergency_response") is False,
        "retainer response envelope must name channel, timezone, hours, pause conditions, and no on-call or emergency SLA",
    )
    _require(
        errors,
        response.get("resolution_sla") is False,
        "retainer response envelope must not promise a resolution SLA",
    )

    decision_rights = _require_exact_mapping(
        errors,
        capacity.get("decision_rights"),
        REQUIRED_DECISION_RIGHTS_FIELDS,
        "offer retainer.capacity_model.decision_rights",
    )
    _require(
        errors,
        all(
            isinstance(decision_rights.get(field), str) and decision_rights.get(field, "").strip()
            for field in ("internal_owner", "sponsor", "provider")
        )
        and "owns daily decisions" in str(decision_rights.get("internal_owner", "")).lower()
        and "only named accepted-backlog changes" in str(decision_rights.get("provider", "")).lower()
        and decision_rights.get("provider_prohibited_actions")
        == ["direct staff", "own daily operations", "approve production effects", "substitute for an executive"],
        "retainer decision rights must preserve internal ownership and bounded provider authority",
    )

    retainer_evidence = _mapping(retainer.get("evidence"))
    for field, source_values in (
        ("included_artifacts", _sequence(retainer_evidence.get("artifacts"))),
        ("exclusions", _sequence(retainer.get("exclusions"))),
        ("escalation", _sequence(retainer.get("escalation"))),
    ):
        capacity_values = capacity.get(field)
        _require(
            errors,
            _is_nonblank_text_list(capacity_values) and list(capacity_values) == list(source_values),
            f"retainer capacity {field} must exactly match the canonical offer",
        )
    retainer_acceptance = str(retainer_evidence.get("acceptance", "")).lower()
    _require(
        errors,
        "capacity ledger" in retainer_acceptance
        and "consumed hours did not exceed included hours" in retainer_acceptance
        and "dated written renew, narrow, or exit decision" in retainer_acceptance
        and "capacity ledger" in _sequence(retainer_evidence.get("artifacts")),
        "retainer acceptance must prove capacity consumption and a dated renewal or exit verdict",
    )

    escalation_routes = _require_exact_mapping(
        errors,
        capacity.get("escalation_routes"),
        REQUIRED_ESCALATION_ROUTE_FIELDS,
        "offer retainer.capacity_model.escalation_routes",
    )
    _require(
        errors,
        all(
            isinstance(escalation_routes.get(field), str) and escalation_routes.get(field, "").strip()
            for field in REQUIRED_ESCALATION_ROUTE_FIELDS
        )
        and "next period" in str(escalation_routes.get("capacity_exhaustion", "")).lower()
        and "pause service and exit" in str(escalation_routes.get("missing_owner", "")).lower()
        and "stop the proposed change" in str(escalation_routes.get("authority_expansion", "")).lower()
        and "human review" in str(escalation_routes.get("security_privacy_legal_contract", "")).lower(),
        "retainer escalation routes must deterministically cover capacity, owner, authority, and protected exceptions",
    )

    renewal_exit = _require_exact_mapping(
        errors,
        capacity.get("renewal_exit"),
        REQUIRED_RENEWAL_EXIT_FIELDS,
        "offer retainer.capacity_model.renewal_exit",
    )
    _require(
        errors,
        isinstance(renewal_exit.get("renewal_gate"), str)
        and renewal_exit.get("renewal_gate", "").strip()
        and isinstance(renewal_exit.get("exit_trigger"), str)
        and renewal_exit.get("exit_trigger", "").strip()
        and _is_nonblank_text_list(renewal_exit.get("exit_steps"))
        and "dated written renew or narrow decision" in renewal_exit.get("renewal_gate", "").lower()
        and renewal_exit.get("exit_steps")
        == [
            "return the latest records and runbook",
            "remove access",
            "record current internal ownership",
            "record the next review date or stop decision",
        ],
        "retainer renewal and exit must be explicit, finite, and return ownership internally",
    )
    _require(
        errors,
        secondary.get("public_cta") is False
        and secondary.get("disclosure_entry") == "L3"
        and secondary.get("position") == "secondary_only",
        "public partnership promotion is prohibited; partnership must remain secondary and L3-only",
    )
    for phrase in (
        "no equity, licence, revenue, custody, or transfer term is implied",
        "no operating, account, custody, financial, publication, or legal authority exists",
        "no economic term exists before readiness",
    ):
        _require(
            errors,
            phrase in partnership_blob,
            f"partnership no-implied-terms boundary missing: {phrase}",
        )

    audiences = _audience_map(data)
    _require(
        errors,
        set(audiences) == {"direct_client", "recruiter_executive", "product_operating_partner"},
        ("audience set must remain direct client, recruiter/executive, and product-operating partner"),
    )
    direct_client = audiences.get("direct_client", {})
    direct_cta = str(direct_client.get("primary_cta", ""))
    _require(
        errors,
        direct_client.get("public_door") is True and "Agentic Delivery Audit" in direct_cta,
        "the direct-client front door must remain the Agentic Delivery Audit",
    )
    _require(
        errors,
        "partner" not in direct_cta.lower(),
        "public partnership promotion leaked into the direct-client CTA",
    )
    partner_audience = audiences.get("product_operating_partner", {})
    partner_cta = str(partner_audience.get("primary_cta", "")).lower()
    _require(
        errors,
        partner_audience.get("public_door") is False
        and partner_audience.get("disclosure_entry") == "L3"
        and "no public call to action" in partner_cta
        and "qualified diligence" in partner_cta,
        "product-operating partner audience must remain closed-front-door L3 diligence",
    )

    narrative_by_id = {
        str(level.get("id")): level for level in (_mapping(item) for item in _sequence(data.get("narrative_ladder")))
    }
    for level_id in ("L1", "L2"):
        level = narrative_by_id.get(level_id, {})
        _require(
            errors,
            "product_operating_partner" not in _sequence(level.get("audience_ids"))
            and "product_operating_partner" not in _mapping(level.get("next_actions")),
            f"public partnership promotion is prohibited in {level_id}",
        )
    _require(
        errors,
        "product_operating_partner" in _sequence(narrative_by_id.get("L3", {}).get("audience_ids")),
        "partnership diligence must remain available at L3",
    )

    economics = _require_fields(
        errors,
        data.get("economics_contract"),
        {"public_rule", "private_anchor_rule", "range_structure"},
        "economics_contract",
    )
    range_structure = _require_fields(
        errors,
        economics.get("range_structure"),
        {"floor", "target", "exception", "public_representation"},
        "economics_contract.range_structure",
    )
    public_rule = str(economics.get("public_rule", "")).lower()
    for term in (
        "numeric fee",
        "rate",
        "discount",
        "margin",
        "equity",
        "revenue-share",
        "transfer term",
        "public surface",
    ):
        _require(
            errors,
            term in public_rule,
            f"no-public-price rule missing term: {term}",
        )
    private_anchor_rule = str(economics.get("private_anchor_rule", "")).lower()
    _require(
        errors,
        "symbolic anchor id" in private_anchor_rule
        and "actual amount remains in its sanctioned private owner" in private_anchor_rule,
        "symbolic-anchor private custody rule drifted",
    )
    public_representation = str(range_structure.get("public_representation", ""))
    for range_id in (
        "RANGE-AUDIT",
        "RANGE-INSTALL",
        "RANGE-RETAINER",
        "RANGE-PARTNERSHIP",
    ):
        _require(
            errors,
            range_id in public_representation,
            f"public range rule missing {range_id}",
        )
    _require(
        errors,
        "never expose the underlying numbers" in public_representation.lower(),
        "public range rule must prohibit underlying-number disclosure",
    )
    public_economics_text = "\n".join(
        _strings(
            [
                economics,
                *[_mapping(offer.get("economics")) for offer in all_offers],
            ]
        )
    )
    numeric_economics = NUMERIC_TOKEN_PATTERN.search(public_economics_text)
    _require(
        errors,
        numeric_economics is None,
        (
            "numeric price leaked into canonical public economics"
            + (f": {numeric_economics.group(0)}" if numeric_economics else "")
        ),
    )

    qualification = _require_fields(
        errors,
        data.get("qualification"),
        {"default_route", "routing_priority", "rules", "scenarios", "decline_language", "review_language"},
        "qualification",
    )
    default_route = qualification.get("default_route")
    _require(
        errors,
        isinstance(default_route, str) and default_route == "human_review",
        "qualification.default_route must be human_review",
    )
    raw_rules = qualification.get("rules")
    _require(errors, isinstance(raw_rules, list), "qualification.rules must be a list")
    rules = [_mapping(rule) for rule in _sequence(raw_rules)]
    raw_route_priority = qualification.get("routing_priority")
    _require(errors, isinstance(raw_route_priority, list), "qualification.routing_priority must be a list")
    route_priority = list(_sequence(raw_route_priority))
    _require(
        errors,
        route_priority == EXPECTED_ROUTE_PRIORITY,
        f"routing priority drifted: expected {EXPECTED_ROUTE_PRIORITY}",
    )
    _require(
        errors,
        _is_unique_text_list(raw_route_priority),
        "qualification.routing_priority must contain unique non-blank route strings",
    )
    rule_ids = [rule.get("id") for rule in rules]
    priorities = [rule.get("priority") for rule in rules]
    integer_priorities = [
        priority for priority in priorities if isinstance(priority, int) and not isinstance(priority, bool)
    ]
    _require(
        errors,
        _is_unique_text_list(rule_ids),
        "qualification rule IDs must be unique non-blank strings",
    )
    _require(
        errors,
        len(integer_priorities) == len(priorities) and len(integer_priorities) == len(set(integer_priorities)),
        "qualification priorities must be unique",
    )
    for rule in rules:
        rule_id = str(rule.get("id", "unknown"))
        _require_fields(
            errors,
            rule,
            {"id", "route", "priority", "any", "all", "none"},
            f"qualification rule {rule_id}",
        )
        _require(
            errors,
            isinstance(rule.get("route"), str) and rule.get("route") in QUALIFICATION_ROUTES,
            f"qualification rule {rule_id}.route must be a supported route string",
        )
        _require(
            errors,
            isinstance(rule.get("priority"), int) and not isinstance(rule.get("priority"), bool),
            f"qualification rule {rule_id}.priority must be an integer",
        )
        for condition in ("any", "all", "none"):
            _require(
                errors,
                _is_unique_text_list(rule.get(condition)),
                f"qualification rule {rule_id}.{condition} must be a list of unique non-blank strings",
            )
    rule_routes = {rule.get("route") for rule in rules if isinstance(rule.get("route"), str)}
    _require(
        errors,
        rule_routes == QUALIFICATION_ROUTES,
        f"qualification rules must cover exactly {sorted(QUALIFICATION_ROUTES)}",
    )
    sorted_routes = [rule.get("route") for rule in sorted(rules, key=_priority_value)]
    _require(
        errors,
        sorted_routes == route_priority,
        "routing priority must match rule priority order",
    )
    operator_rules = [rule for rule in rules if rule.get("route") == "partnership_review"]
    _require(
        errors,
        len(operator_rules) == 1 and "public_front_door" in _sequence(operator_rules[0].get("none")),
        "partnership routing must explicitly exclude the public front door",
    )

    raw_scenarios = qualification.get("scenarios")
    _require(
        errors,
        isinstance(raw_scenarios, list) and bool(raw_scenarios),
        "qualification scenario matrix must be a non-empty list",
    )
    scenarios = [_mapping(scenario) for scenario in _sequence(raw_scenarios)]
    scenario_ids = [scenario.get("id") for scenario in scenarios]
    _require(
        errors,
        _is_unique_text_list(scenario_ids),
        "qualification scenario IDs must be unique non-blank strings",
    )
    scenario_routes: set[str] = set()
    for scenario in scenarios:
        scenario = _require_fields(
            errors,
            scenario,
            {"id", "facts", "expected_route"},
            "qualification scenario",
        )
        scenario_id = str(scenario.get("id", "unknown"))
        raw_facts = scenario.get("facts")
        facts = _mapping(raw_facts)
        _require(
            errors,
            bool(facts)
            and isinstance(raw_facts, Mapping)
            and all(isinstance(key, str) and bool(key.strip()) and isinstance(value, bool) for key, value in facts.items()),
            f"scenario {scenario_id} facts must be a non-empty mapping of non-blank boolean inputs",
        )
        expected_route = scenario.get("expected_route")
        _require(
            errors,
            isinstance(expected_route, str) and expected_route in QUALIFICATION_ROUTES,
            f"scenario {scenario_id}.expected_route must be a supported route string",
        )
        if isinstance(expected_route, str):
            scenario_routes.add(expected_route)
        route = evaluate_qualification_route(rules, facts, default_route if isinstance(default_route, str) else "")
        _require(
            errors,
            route == expected_route,
            f"scenario {scenario_id} expected {expected_route} but routed to {route}",
        )
        matches = sorted((rule for rule in rules if _rule_matches(rule, facts)), key=_priority_value)
        commercial_matches = {str(rule.get("route")) for rule in matches if rule.get("route") in COMMERCIAL_ROUTES}
        _require(
            errors,
            len(commercial_matches) <= 1,
            f"offer overlap in scenario {scenario_id}: {sorted(commercial_matches)}",
        )
    _require(
        errors,
        scenario_routes == QUALIFICATION_ROUTES,
        f"qualification scenario matrix must cover exactly {sorted(QUALIFICATION_ROUTES)}",
    )

    public_payload = {
        "contract": {
            "canonical_source": contract.get("canonical_source"),
            "formal_dependency": dependency,
            "prohibited_preflight_effects": contract.get("prohibited_preflight_effects"),
        },
        "offers": all_offers,
        "qualification": qualification,
        "economics": {
            "public_rule": economics.get("public_rule"),
            "private_anchor_rule": economics.get("private_anchor_rule"),
            "public_representation": range_structure.get("public_representation"),
        },
        "front_door_cta": direct_cta,
        "partnership_entry": partner_audience.get("primary_cta"),
    }
    errors.extend(validate_artifact_text("canonical PSP-P04 public payload", "\n".join(_strings(public_payload))))
    return errors


def _bullet_lines(values: Sequence[Any]) -> list[str]:
    return [f"- {value}" for value in values]


def _code_values(values: Sequence[Any]) -> str:
    if not values:
        return "—"
    return ", ".join(f"`{value}`" for value in values)


def _table_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _preamble(data: Mapping[str, Any], title: str, work_item: str) -> list[str]:
    contract = _mapping(data["contract"])
    dependency = _mapping(contract["formal_dependency"])
    return [
        GENERATED_NOTICE,
        f"<!-- Canonical source: {contract['canonical_source']} -->",
        f"# {title}",
        "",
        (
            f"> **Program status:** `{contract['status']}`; dependency "
            f"`{dependency['chunk_id']}` / `{dependency['phase_id']}` is "
            f"`{dependency['state']}`. {dependency['consequence']}"
        ),
        "",
        f"**Work item:** `{work_item}`",
        "",
    ]


def _economics_lines(data: Mapping[str, Any], economics: Mapping[str, Any]) -> list[str]:
    global_economics = _mapping(data["economics_contract"])
    range_structure = _mapping(global_economics["range_structure"])
    return [
        "## Symbolic economics",
        "",
        f"- **Model:** `{economics['model']}`",
        f"- **Range ID:** `{economics['range_id']}`",
        f"- **Anchor ID:** `{economics['anchor_id']}`",
        f"- **Approval gate:** `{economics['approval_gate']}`",
        f"- **Public price:** `{economics['public_price']}`",
        f"- **Capacity rule:** {economics['capacity_rule']}",
        f"- **Discount rule:** {economics['discount_rule']}",
        "",
        "### Public economics boundary",
        "",
        str(global_economics["public_rule"]),
        "",
        str(global_economics["private_anchor_rule"]),
        "",
        str(range_structure["public_representation"]),
        "",
    ]


def _effect_boundary_lines(data: Mapping[str, Any]) -> list[str]:
    effects = _sequence(_mapping(data["contract"])["prohibited_preflight_effects"])
    return [
        "## Preflight effect boundary",
        "",
        "The canonical contract prohibits:",
        "",
        *_bullet_lines(effects),
        "",
    ]


def _retainer_capacity_lines(offer: Mapping[str, Any]) -> list[str]:
    capacity = _mapping(offer["capacity_model"])
    allocation = _mapping(capacity["allocation"])
    quantity_limits = _mapping(capacity["quantity_limits"])
    cadence = _mapping(capacity["cadence"])
    response = _mapping(capacity["response_envelope"])
    decision_rights = _mapping(capacity["decision_rights"])
    escalation_routes = _mapping(capacity["escalation_routes"])
    renewal_exit = _mapping(capacity["renewal_exit"])
    lines = [
        "## Capacity model",
        "",
        f"- **Schema:** `{capacity['schema_version']}`",
        f"- **Review period:** `{capacity['review_period']}`",
        f"- **Included delivery days:** `{capacity['included_delivery_days']}`",
        f"- **Hours per delivery day:** `{capacity['hours_per_delivery_day']}`",
        f"- **Included hours:** `{capacity['included_hours']}`",
        f"- **Allocation rule:** {capacity['allocation_rule']}",
        f"- **Consumption rule:** {capacity['consumption_rule']}",
        f"- **Rollover:** `{str(capacity['rollover']).lower()}`",
        f"- **Exhaustion route:** {capacity['exhaustion_route']}",
        "",
        "### Declared allocation",
        "",
        "| Capacity class | Days |",
        "| --- | ---: |",
    ]
    for field in (
        "scheduled_governance_days",
        "approved_change_days",
        "scheduled_contingency_days",
        "uncommitted_days",
    ):
        lines.append(f"| `{field}` | `{allocation[field]}` |")
    lines.extend(
        [
            "",
            "### Quantity limits",
            "",
            "| Limit | Maximum |",
            "| --- | ---: |",
        ]
    )
    for field in (
        "active_change_items",
        "reviews_or_postmortems_per_period",
        "teams",
        "repositories",
        "included_revisions_per_change",
    ):
        lines.append(f"| `{field}` | `{quantity_limits[field]}` |")
    lines.extend(
        [
            "",
            "### Cadence",
            "",
            f"- **Evidence reviews per period:** `{cadence['evidence_reviews_per_period']}`",
            f"- **Exception reviews per period:** `{cadence['exception_reviews_per_period']}`",
            f"- **Capacity reviews per period:** `{cadence['capacity_reviews_per_period']}`",
            f"- **Closeouts per period:** `{cadence['closeouts_per_period']}`",
            f"- **Change window:** {cadence['change_window']}",
            "",
            "### Response envelope",
            "",
            f"- **Channel:** {response['channel']}",
            f"- **Timezone:** {response['timezone']}",
            f"- **Business hours:** {response['business_hours']}",
            f"- **Service window:** {response['service_window']}",
            (f"- **Acknowledgement target:** `{response['acknowledgement_target_business_days']}` business days"),
            f"- **Decision target:** `{response['decision_target_business_days']}` business days",
            f"- **Target boundary:** {response['target_boundary']}",
            "- **Clock pause conditions:**",
            *[f"  - {condition}" for condition in _sequence(response["clock_pause_conditions"])],
            f"- **On-call:** `{str(response['on_call']).lower()}`",
            f"- **Emergency response:** `{str(response['emergency_response']).lower()}`",
            f"- **Resolution SLA:** `{str(response['resolution_sla']).lower()}`",
            "",
            "### Decision rights",
            "",
            f"- **Internal owner:** {decision_rights['internal_owner']}",
            f"- **Sponsor:** {decision_rights['sponsor']}",
            f"- **Provider:** {decision_rights['provider']}",
            "- **Provider prohibited actions:**",
            *[f"  - {action}" for action in _sequence(decision_rights["provider_prohibited_actions"])],
            "",
            "### Included artifacts",
            "",
            *_bullet_lines(_sequence(capacity["included_artifacts"])),
            "",
            "### Capacity exclusions",
            "",
            *_bullet_lines(_sequence(capacity["exclusions"])),
            "",
            "### Capacity escalation",
            "",
            *_bullet_lines(_sequence(capacity["escalation"])),
            "",
            "### Deterministic escalation routes",
            "",
            f"- **Capacity exhaustion:** {escalation_routes['capacity_exhaustion']}",
            f"- **Missing owner:** {escalation_routes['missing_owner']}",
            f"- **Authority expansion:** {escalation_routes['authority_expansion']}",
            (
                "- **Security, privacy, legal, or contract exception:** "
                f"{escalation_routes['security_privacy_legal_contract']}"
            ),
            "",
            "### Renewal and exit",
            "",
            f"- **Renewal gate:** {renewal_exit['renewal_gate']}",
            f"- **Exit trigger:** {renewal_exit['exit_trigger']}",
            "- **Exit steps:**",
            *[f"  - {step}" for step in _sequence(renewal_exit["exit_steps"])],
            "",
        ]
    )
    return lines


def render_offer_page(
    data: Mapping[str, Any],
    offer: Mapping[str, Any],
    work_item: str,
    *,
    front_door_cta: str | None = None,
) -> str:
    """Render one offer without adding scope or terms beyond the source."""
    lines = _preamble(data, str(offer["name"]), work_item)
    if front_door_cta:
        lines.extend([f"{FRONT_DOOR_MARKER} {front_door_cta}", ""])
    lines.extend(
        [
            "## Decision contract",
            "",
            f"- **Offer ID:** `{offer['id']}`",
            f"- **Stage:** `{offer['stage']}`",
            f"- **Position:** `{offer['position']}`",
            f"- **Buyer:** {offer['buyer']}",
            f"- **Trigger:** {offer['trigger']}",
            f"- **Promise:** {offer['promise']}",
            f"- **Timeline:** {offer['timeline']}",
            "",
            "## Entry criteria",
            "",
            *_bullet_lines(_sequence(offer["entry_criteria"])),
            "",
            "## Outputs",
            "",
            *_bullet_lines(_sequence(offer["deliverables"])),
            "",
            "## Bounded authority",
            "",
            f"**Mode:** `{_mapping(offer['authority'])['mode']}`",
            "",
            str(_mapping(offer["authority"])["boundary"]),
            "",
            "## Exclusions",
            "",
            *_bullet_lines(_sequence(offer["exclusions"])),
            "",
            "## Acceptance",
            "",
            str(_mapping(offer["evidence"])["acceptance"]),
            "",
            "### Acceptance evidence artifacts",
            "",
            *_bullet_lines(_sequence(_mapping(offer["evidence"])["artifacts"])),
            "",
            "## Handoff",
            "",
            str(offer["handoff"]),
            "",
            "## Escalation",
            "",
            *_bullet_lines(_sequence(offer["escalation"])),
            "",
            "## Claim boundaries",
            "",
            _code_values(_sequence(offer["claim_refs"])),
            "",
        ]
    )
    if offer.get("id") == "retainer":
        lines.extend(_retainer_capacity_lines(offer))
    lines.extend(_economics_lines(data, _mapping(offer["economics"])))
    lines.extend(_effect_boundary_lines(data))
    return "\n".join(lines).rstrip() + "\n"


def render_retainer_capacity_model(data: Mapping[str, Any]) -> str:
    """Render the machine-readable capacity contract from the canonical offer."""
    contract = _mapping(data["contract"])
    retainer = _offer_map(data)["retainer"]
    payload = {
        "schema_version": "limen.positioning.retainer_capacity_artifact.v1",
        "canonical_source": contract["canonical_source"],
        "work_item": WORK_ITEMS["retainer"],
        "offer": {
            "id": retainer["id"],
            "name": retainer["name"],
            "timeline": retainer["timeline"],
            "authority": retainer["authority"],
            "acceptance": _mapping(retainer["evidence"])["acceptance"],
        },
        "capacity_model": retainer["capacity_model"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def render_partnership_page(
    data: Mapping[str, Any],
    offer: Mapping[str, Any],
    partner_audience: Mapping[str, Any],
) -> str:
    """Render the L3 partnership diligence boundary without a public CTA."""
    lines = _preamble(data, str(offer["name"]), WORK_ITEMS["partnership_review"])
    lines.extend(
        [
            "## Access and visibility",
            "",
            f"- **Disclosure entry:** `{offer['disclosure_entry']}`",
            f"- **Position:** `{offer['position']}`",
            f"- **Public call to action:** `{str(offer['public_cta']).lower()}`",
            f"- **Public door:** `{str(partner_audience['public_door']).lower()}`",
            "",
            str(partner_audience["primary_cta"]),
            "",
        ]
    )
    body = render_offer_page(
        data,
        offer,
        WORK_ITEMS["partnership_review"],
    ).splitlines()
    decision_start = body.index("## Decision contract")
    lines.extend(body[decision_start:])
    return "\n".join(lines).rstrip() + "\n"


def render_qualification_page(data: Mapping[str, Any]) -> str:
    qualification = _mapping(data["qualification"])
    offer_by_id = _offer_map(data)
    audiences = _audience_map(data)
    direct_cta = str(audiences["direct_client"]["primary_cta"])
    partner_entry = str(audiences["product_operating_partner"]["primary_cta"])
    lines = _preamble(data, "Qualification and routing", "PSP-P04-W04")
    lines.extend(
        [
            f"{FRONT_DOOR_MARKER} {direct_cta}",
            "",
            f"**Partnership visibility boundary:** {partner_entry}",
            "",
            "## Offer separation",
            "",
            "| Route | Stage | Authority | Trigger |",
            "| --- | --- | --- | --- |",
        ]
    )
    for offer_id in (*PRIMARY_SEQUENCE, "partnership_review"):
        offer = offer_by_id[offer_id]
        lines.append(
            "| "
            + " | ".join(
                (
                    f"`{offer_id}`",
                    f"`{offer['stage']}`",
                    f"`{_mapping(offer['authority'])['mode']}`",
                    _table_cell(offer["trigger"]),
                )
            )
            + " |"
        )
    lines.extend(["", "## Routing priority", ""])
    for index, route in enumerate(_sequence(qualification["routing_priority"]), 1):
        lines.append(f"{index}. `{route}`")
    lines.extend(
        [
            "",
            f"**Default route:** `{qualification['default_route']}`. Unmatched or insufficient-evidence requests remain in human review.",
            "",
            "Rules are evaluated in this priority order; the first match is the route.",
            "",
            "## Routing rules",
            "",
            "| Priority | Rule | Route | Any | All | None |",
            "| ---: | --- | --- | --- | --- | --- |",
        ]
    )
    rules = [_mapping(rule) for rule in _sequence(qualification["rules"])]
    for rule in rules:
        lines.append(
            "| "
            + " | ".join(
                (
                    str(rule["priority"]),
                    f"`{rule['id']}`",
                    f"`{rule['route']}`",
                    _code_values(_sequence(rule["any"])),
                    _code_values(_sequence(rule["all"])),
                    _code_values(_sequence(rule["none"])),
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Scenario matrix",
            "",
            "| Scenario | Facts | Expected route |",
            "| --- | --- | --- |",
        ]
    )
    for raw_scenario in _sequence(qualification["scenarios"]):
        scenario = _mapping(raw_scenario)
        facts = _mapping(scenario["facts"])
        rendered_facts = ", ".join(f"`{key}={str(value).lower()}`" for key, value in facts.items())
        lines.append(f"| `{scenario['id']}` | {rendered_facts} | `{scenario['expected_route']}` |")
    lines.extend(
        [
            "",
            "## Decline boundary",
            "",
            str(qualification["decline_language"]),
            "",
            "## Human-review boundary",
            "",
            str(qualification["review_language"]),
            "",
        ]
    )
    global_economics = _mapping(data["economics_contract"])
    range_structure = _mapping(global_economics["range_structure"])
    lines.extend(
        [
            "## Public economics boundary",
            "",
            str(global_economics["public_rule"]),
            "",
            str(global_economics["private_anchor_rule"]),
            "",
            str(range_structure["public_representation"]),
            "",
        ]
    )
    lines.extend(_effect_boundary_lines(data))
    return "\n".join(lines).rstrip() + "\n"


def render_artifacts(data: Mapping[str, Any]) -> dict[str, str]:
    """Return the complete deterministic artifact manifest."""
    offer_by_id = _offer_map(data)
    audiences = _audience_map(data)
    direct_cta = str(audiences["direct_client"]["primary_cta"])
    artifacts = {
        OFFER_FILES["audit"]: render_offer_page(
            data,
            offer_by_id["audit"],
            WORK_ITEMS["audit"],
            front_door_cta=direct_cta,
        ),
        OFFER_FILES["install"]: render_offer_page(data, offer_by_id["install"], WORK_ITEMS["install"]),
        OFFER_FILES["retainer"]: render_offer_page(data, offer_by_id["retainer"], WORK_ITEMS["retainer"]),
        CAPACITY_FILE: render_retainer_capacity_model(data),
        QUALIFICATION_FILE: render_qualification_page(data),
        OFFER_FILES["partnership_review"]: render_partnership_page(
            data,
            offer_by_id["partnership_review"],
            audiences["product_operating_partner"],
        ),
    }
    return dict(sorted(artifacts.items()))


def _offer_coverage_values(data: Mapping[str, Any], offer: Mapping[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for field in (
        "id",
        "name",
        "stage",
        "position",
        "buyer",
        "trigger",
        "promise",
        "timeline",
        "handoff",
    ):
        values.append((field, str(offer[field])))
    for field in ("entry_criteria", "deliverables", "exclusions", "escalation", "claim_refs"):
        values.extend((field, str(item)) for item in _sequence(offer[field]))
    authority = _mapping(offer["authority"])
    values.extend((f"authority.{field}", str(authority[field])) for field in REQUIRED_AUTHORITY_FIELDS)
    evidence = _mapping(offer["evidence"])
    values.append(("evidence.acceptance", str(evidence["acceptance"])))
    values.extend(("evidence.artifacts", str(item)) for item in _sequence(evidence["artifacts"]))
    economics = _mapping(offer["economics"])
    values.extend((f"economics.{field}", str(economics[field])) for field in REQUIRED_ECONOMICS_FIELDS)
    if "disclosure_entry" in offer:
        values.append(("disclosure_entry", str(offer["disclosure_entry"])))
    if "public_cta" in offer:
        values.append(("public_cta", str(offer["public_cta"]).lower()))
    global_economics = _mapping(data["economics_contract"])
    values.extend(
        (
            ("economics_contract.public_rule", str(global_economics["public_rule"])),
            (
                "economics_contract.private_anchor_rule",
                str(global_economics["private_anchor_rule"]),
            ),
            (
                "economics_contract.range_structure.public_representation",
                str(_mapping(global_economics["range_structure"])["public_representation"]),
            ),
        )
    )
    return values


def validate_offer_page_coverage(
    data: Mapping[str, Any],
    offer: Mapping[str, Any],
    text: str,
    label: str,
) -> list[str]:
    errors: list[str] = []
    for field, value in _offer_coverage_values(data, offer):
        if value not in text:
            errors.append(f"{label} missing canonical {field} value: {value}")
    return errors


def validate_qualification_page_coverage(data: Mapping[str, Any], text: str, label: str) -> list[str]:
    errors: list[str] = []
    qualification = _mapping(data["qualification"])
    required_values: list[tuple[str, str]] = [
        ("decline_language", str(qualification["decline_language"])),
        ("review_language", str(qualification["review_language"])),
        ("default_route", f"**Default route:** `{qualification['default_route']}`"),
    ]
    audiences = _audience_map(data)
    required_values.extend(
        (
            (
                "direct_client.primary_cta",
                str(audiences["direct_client"]["primary_cta"]),
            ),
            (
                "product_operating_partner.primary_cta",
                str(audiences["product_operating_partner"]["primary_cta"]),
            ),
        )
    )
    for offer_id in (*PRIMARY_SEQUENCE, "partnership_review"):
        offer = _offer_map(data)[offer_id]
        required_values.extend(
            (
                ("offer.id", offer_id),
                ("offer.stage", str(offer["stage"])),
                ("offer.authority.mode", str(_mapping(offer["authority"])["mode"])),
                ("offer.trigger", str(offer["trigger"])),
            )
        )
    required_values.extend(("routing_priority", str(route)) for route in _sequence(qualification["routing_priority"]))
    for raw_rule in _sequence(qualification["rules"]):
        rule = _mapping(raw_rule)
        for field in ("id", "route", "priority"):
            required_values.append((f"rule.{field}", str(rule[field])))
        for field in ("any", "all", "none"):
            required_values.extend((f"rule.{field}", str(item)) for item in _sequence(rule[field]))
    for raw_scenario in _sequence(qualification["scenarios"]):
        scenario = _mapping(raw_scenario)
        required_values.extend(
            (
                ("scenario.id", str(scenario["id"])),
                ("scenario.expected_route", str(scenario["expected_route"])),
            )
        )
        required_values.extend(
            ("scenario.fact", f"{key}={str(value).lower()}") for key, value in _mapping(scenario["facts"]).items()
        )
    economics = _mapping(data["economics_contract"])
    required_values.extend(
        (
            ("economics_contract.public_rule", str(economics["public_rule"])),
            (
                "economics_contract.private_anchor_rule",
                str(economics["private_anchor_rule"]),
            ),
            (
                "economics_contract.range_structure.public_representation",
                str(_mapping(economics["range_structure"])["public_representation"]),
            ),
        )
    )
    for field, value in required_values:
        if value not in text:
            errors.append(f"{label} missing canonical {field} value: {value}")
    return errors


def validate_front_door_ctas(artifacts: Mapping[str, str]) -> list[str]:
    """Ensure front-door language routes only to the Audit."""
    errors: list[str] = []
    found: list[tuple[str, str]] = []
    for filename, text in artifacts.items():
        for line in text.splitlines():
            if line.startswith(FRONT_DOOR_MARKER):
                found.append((filename, line))
                lowered = line.lower()
                if "agentic delivery audit" not in lowered:
                    errors.append(f"front-door CTA in {filename} does not route to the Audit")
                if "partner" in lowered or "operator" in lowered:
                    errors.append(f"public partnership promotion leaked into front-door CTA in {filename}")
    partner_file = OFFER_FILES["partnership_review"]
    if any(filename == partner_file for filename, _line in found):
        errors.append("partnership artifact must not contain a front-door CTA")
    expected_locations = {OFFER_FILES["audit"], QUALIFICATION_FILE}
    actual_locations = {filename for filename, _line in found}
    if actual_locations != expected_locations:
        errors.append(
            f"front-door CTA locations drifted: expected {sorted(expected_locations)}, found {sorted(actual_locations)}"
        )
    return errors


def validate_artifact_directory(data: Mapping[str, Any], output_dir: Path = OUTPUT_DIR) -> list[str]:
    """Compare materialized files with the source-derived manifest."""
    errors: list[str] = []
    expected = render_artifacts(data)
    actual: dict[str, str] = {}
    if not output_dir.exists():
        return [f"missing offer artifact directory: {output_dir}"]
    actual_files = {
        path.relative_to(output_dir).as_posix()
        for pattern in ("*.md", "*.json")
        for path in output_dir.rglob(pattern)
        if path.is_file()
    }
    for missing in sorted(EXPECTED_FILES - actual_files):
        errors.append(f"missing generated offer artifact: {missing}")
    for unexpected in sorted(actual_files - KNOWN_MATERIALIZED_FILES):
        errors.append(f"unexpected unmanaged offer artifact: {unexpected}")
    for filename in sorted(actual_files):
        path = output_dir / filename
        text = path.read_text(encoding="utf-8")
        actual[filename] = text
        errors.extend(validate_artifact_text(filename, text))
        if filename in expected and text != expected[filename]:
            errors.append(f"generated offer artifact drifted from canonical YAML: {filename}")

    offer_by_id = _offer_map(data)
    for offer_id, filename in OFFER_FILES.items():
        if filename in actual:
            errors.extend(
                validate_offer_page_coverage(
                    data,
                    offer_by_id[offer_id],
                    actual[filename],
                    filename,
                )
            )
    if QUALIFICATION_FILE in actual:
        errors.extend(
            validate_qualification_page_coverage(
                data,
                actual[QUALIFICATION_FILE],
                QUALIFICATION_FILE,
            )
        )
    errors.extend(validate_front_door_ctas(actual))
    return errors


def validate_repository(data: Mapping[str, Any], output_dir: Path = OUTPUT_DIR) -> list[str]:
    errors = validate_contract(data)
    if errors:
        return errors
    return validate_artifact_directory(data, output_dir)


def write_artifacts(data: Mapping[str, Any], output_dir: Path = OUTPUT_DIR) -> tuple[Path, ...]:
    errors = validate_contract(data)
    if errors:
        raise OfferArtifactValidationError("\n".join(errors))
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, text in render_artifacts(data).items():
        path = output_dir / filename
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return tuple(written)


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    loaded = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    if not isinstance(loaded, dict):
        raise OfferArtifactValidationError("contract root must be a mapping")
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="regenerate the six offer artifacts")
    parser.add_argument("--check", action="store_true", help="validate source and generated artifacts")
    args = parser.parse_args()
    if not args.render and not args.check:
        parser.error("choose --render and/or --check")

    try:
        data = load_contract()
    except (OSError, yaml.YAMLError, OfferArtifactValidationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    source_errors = validate_contract(data)
    if source_errors:
        for error in source_errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    if args.render:
        written = write_artifacts(data)
        print(f"rendered {len(written)} PSP-P04 offer artifacts in {OUTPUT_DIR.relative_to(ROOT)}")
    if args.check:
        errors = validate_artifact_directory(data)
        if errors:
            for error in errors:
                print(f"FAIL: {error}", file=sys.stderr)
            return 1
        print("PASS: 6 PSP-P04 offer artifacts match the canonical contract and public-safety boundaries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
