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
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "institutio/positioning/preflights/psp-c07-private-inbound/contract.json"
)
DEFAULT_FIXTURES = (
    ROOT
    / "institutio/positioning/preflights/psp-c07-private-inbound/fixtures/synthetic-leads.json"
)
MAIL_TAG = re.compile(
    r"^\[(?P<surface>[^\]·]+?)\s*·\s*(?P<audience>[^\]]+?)\]\s*—\s*inbound$"
)


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


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version",
        "chunk_id",
        "phase_id",
        "status",
        "leaf_assignments",
        "formal_dependency_gate",
        "safety",
        "capture_contract",
        "integration_adapters",
        "scoring",
        "drafts",
        "ledger",
    }
    missing = sorted(required - contract.keys())
    if missing:
        errors.append(f"missing contract fields: {', '.join(missing)}")
    if contract.get("chunk_id") != "PSP-C07" or contract.get("phase_id") != "PSP-P08":
        errors.append("contract must remain scoped to PSP-C07/PSP-P08")
    if contract.get("status") != "PREPARED/PREFLIGHT":
        errors.append("status must remain PREPARED/PREFLIGHT")
    expected_assignments = {
        "PSP-P08-W01": ("gpt-5.6-terra", "high"),
        "PSP-P08-W02": ("gpt-5.6-sol", "xhigh"),
        "PSP-P08-W03": ("gpt-5.6-sol", "xhigh"),
        "PSP-P08-W04": ("gpt-5.6-terra", "high"),
        "PSP-P08-W05": ("gpt-5.6-luna", "medium"),
        "PSP-P08-W06": ("gpt-5.6-sol", "xhigh"),
        "PSP-P08-W07": ("gpt-5.6-sol", "xhigh"),
    }
    assignments = contract.get("leaf_assignments", {})
    if set(assignments) != set(expected_assignments):
        errors.append("leaf assignment set must remain exactly PSP-P08-W01 through W07")
    for work_id, (model, effort) in expected_assignments.items():
        observed = assignments.get(work_id, {})
        if observed.get("model") != model or observed.get("effort") != effort:
            errors.append(f"{work_id} must remain assigned to {model}/{effort}")

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
    if p03.get("current_preflight_head") != "c7c932205faa405e291f8030235a73cedeaa219e":
        errors.append("P03 current preflight head must include the W07 intake package")
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
    if upstream.get("status") != "PREPARED":
        errors.append("C06 upstream evidence must remain PREPARED, not complete")
    expected_c06_heads = {
        "portfolio_draft": "6cb7f291ef758d26d136620398c6e9c09f74d0ea",
        "limen_relay": "b3c8dcb8ee461fad7be971efc0fc60ca27726668",
    }
    for owner, expected_head in expected_c06_heads.items():
        if upstream.get(owner, {}).get("exact_head") != expected_head:
            errors.append(f"C06 {owner} exact head must remain pinned")
    visual = upstream.get("visual_selection", {})
    if visual.get("grounded_direction_count") != 3:
        errors.append("C06 preflight must preserve exactly three grounded directions")
    if visual.get("durable_artifacts_status") != "tracked_unselected":
        errors.append("C06 durable visual artifacts must remain tracked and unselected")
    if visual.get("manifest_path") != (
        "docs/positioning/visual-directions/psp-c06/manifest.json"
    ):
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

    adapters = contract.get("integration_adapters", {})
    for kind in ("tagged_mail", "form_submission"):
        if adapters.get(kind, {}).get("selection_state") != "contract_only":
            errors.append(f"{kind} adapter must remain contract_only")

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


def evaluate_routes(
    journeys: list[dict[str, Any]], fixtures: dict[str, Any]
) -> dict[str, Any]:
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
            unexpected.extend(
                f"{name}.{key}" for key in sorted(set(value) - set(allowed))
            )
    if kind == "form_submission" and isinstance(event.get("source_tags"), dict):
        allowed_tags = set(capture["required_source_tags"])
        unexpected.extend(
            f"source_tags.{key}"
            for key in sorted(set(event["source_tags"]) - allowed_tags)
        )
    if unexpected:
        raise ValueError(f"unexpected capture fields: {', '.join(unexpected)}")


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
    if not all(isinstance(value, str) and value.strip() for value in source_tags.values()):
        raise ValueError("source tags must be nonempty strings")
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
    email = str(contact["email"]).strip().lower()
    if not email.endswith(".invalid"):
        raise ValueError("preflight accepts reserved .invalid addresses only")
    details = str(request["details"]).strip()
    if len(details) > int(contract["capture_contract"]["max_request_characters"]):
        raise ValueError("request details exceed the minimal capture limit")
    fingerprint = "|".join(
        (
            str(envelope["owner_partition"]),
            email,
            str(request["summary"]).strip().lower(),
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
            "name": str(contact["name"]).strip(),
            "email": email,
        },
        "request": {
            "summary": str(request["summary"]).strip(),
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
    confident = (
        top_score >= int(contract["scoring"]["minimum_auto_score"])
        and margin >= int(contract["scoring"]["minimum_margin"])
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


def generate_draft(record: dict[str, Any], scored: dict[str, Any], route: str) -> dict[str, str]:
    category = scored["category"]
    family = {
        "client": "client_acknowledgment",
        "recruiter": "recruiter_acknowledgment",
        "operator": "operator_review",
        "spam": "decline",
        "ambiguous": "manual_review",
    }[category]
    name = record["contact"]["name"]
    summary = record["request"]["summary"]
    body = (
        f"Draft for operator review only. Acknowledge {name}'s request about {summary}. "
        f"Suggested route: {route}. Do not promise price, availability, acceptance, or signature."
    )
    return {"status": "draft", "kind": family, "body": body}


@dataclass
class PrivateLedger:
    records: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)

    def upsert(self, record: dict[str, Any], decision: dict[str, Any]) -> bool:
        partition = str(record["owner_partition"])
        record_id = str(record["record_id"])
        bucket = self.records.setdefault(partition, {})
        created = record_id not in bucket
        bucket[record_id] = {
            "record": deepcopy(record),
            "decision": deepcopy(decision),
        }
        return created

    def get(self, owner_partition: str, record_id: str) -> dict[str, Any]:
        return deepcopy(self.records[owner_partition][record_id])

    def aggregate(self) -> dict[str, Any]:
        rows = [row for bucket in self.records.values() for row in bucket.values()]
        routes = Counter(row["decision"]["route"] for row in rows)
        categories = Counter(row["decision"]["category"] for row in rows)
        return {
            "private_record_count": len(rows),
            "owner_partition_count": len(self.records),
            "routes": dict(sorted(routes.items())),
            "categories": dict(sorted(categories.items())),
        }


@dataclass
class ClosedSendValve:
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
        draft = generate_draft(record, scored, route)
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


def live_gate(contract: dict[str, Any]) -> tuple[bool, str]:
    gate = contract["formal_dependency_gate"]
    if gate["commercial_upstream"]["PSP-P03"]["w07"]["state"] != "closed_with_predicate_receipt":
        return False, "PSP-P03-W07 five-reader predicate receipt is absent; PSP-P04 remains dependency-gated"
    if gate["phase_states"]["PSP-P04"] != "closed_with_predicate_receipt":
        return False, "PSP-P04 predicate receipt is absent"
    if gate["phase_states"]["PSP-P07"] != "closed_with_predicate_receipt":
        return False, "PSP-P07 predicate receipt is absent"
    if not gate["selected_capture_surface"]:
        return False, "no approved C06 capture surface is selected"
    if gate["separate_leaf_authority"] != "leased":
        return False, "separate P08 leaf authority is absent"
    return True, "live adapter may be implemented under a separately leased leaf"


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
        ready, reason = live_gate(contract)
        result = {
            "status": "pass" if ready else "blocked",
            "mode": args.mode,
            "reason": reason,
        }
        exit_code = 0 if ready else 2

    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"].upper())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
