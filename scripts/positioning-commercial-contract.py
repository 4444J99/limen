#!/usr/bin/env python3
"""Validate and render the PSP-C03 identity and commercial contract."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "institutio/positioning/commercial-contract.yaml"
PROGRAM_PATH = ROOT / "institutio/positioning/program.yaml"
RENDER_PATH = ROOT / "docs/positioning/commercial-contract.md"
P03_MATRIX_PATH = ROOT / "docs/receipts/positioning/preflights/2026-08-10-psp-p03-leaf-evidence.md"
P04_MATRIX_PATH = ROOT / "docs/receipts/positioning/preflights/2026-08-10-psp-p04-leaf-evidence.md"
RELAY_PATH = ROOT / "docs/receipts/positioning/relays/2026-08-10-psp-c03-identity-offers-preflight.md"

P03_WORK = {f"PSP-P03-W{index:02d}" for index in range(1, 8)}
P04_WORK = {f"PSP-P04-W{index:02d}" for index in range(1, 8)}
PRIMARY_ROUTES = {"audit", "install", "retainer", "partnership_review"}
PRIVATE_MARKERS = (
    "/Users/",
    ".copilot/",
    "session-state/",
    ".limen-private/",
    "d53ec957-c8eb-4e9f-a345-6b30699bc263",
    "af59ff01-dba2-4c71-acbf-adcdf6008db9",
)
PRICE_PATTERN = re.compile(
    r"(?:[$£€]\s*\d)|(?:\b\d+(?:,\d{3})*(?:\.\d+)?\s*(?:usd|dollars?|/hr|per\s+(?:hour|day|month|year))\b)|(?:\b\d+\s*[kK]\b)",
    re.IGNORECASE,
)


class ContractValidationError(ValueError):
    """A deterministic contract validation failure."""


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _public_copy_strings(data: dict[str, Any]) -> Iterable[str]:
    identity = data["identity"]
    for key in ("canonical_title", "headline", "operating_thesis", "supporting_line", "authorship_disclosure"):
        yield str(identity[key])
    for audience in data["audiences"]:
        for key in ("label", "job", "primary_cta"):
            yield str(audience[key])
    for level in data["narrative_ladder"]:
        yield from _strings(level.get("beats", []))
        yield from _strings(level.get("next_actions", {}))
    for offer in [*data["offer_ladder"]["items"], data["offer_ladder"]["secondary"]]:
        for key in ("name", "trigger", "promise", "timeline", "handoff"):
            yield str(offer[key])


def _require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def _rule_matches(rule: dict[str, Any], facts: dict[str, bool]) -> bool:
    all_terms = rule.get("all", [])
    any_terms = rule.get("any", [])
    none_terms = rule.get("none", [])
    return (
        all(facts.get(term, False) for term in all_terms)
        and (not any_terms or any(facts.get(term, False) for term in any_terms))
        and not any(facts.get(term, False) for term in none_terms)
    )


def _program_assignment(work: dict[str, Any], program: dict[str, Any]) -> dict[str, str]:
    assignments = program["model_assignments"]
    work_id = work["id"]
    if work_id in assignments["object_overrides"]:
        return assignments["object_overrides"][work_id]
    sensitive = set(assignments["sensitive_capabilities"])
    if work["reasoning"] != "frontier_review" and sensitive.intersection(work["capabilities"]):
        return assignments["sensitive_assignment"]
    if work["reasoning"] != "frontier_review" and work["target_repo"].startswith("multi-repository:"):
        return assignments["multi_repository_assignment"]
    return assignments["work_matrix"][work["reasoning"]][work["effect"]]


def validate_contract(data: dict[str, Any]) -> list[str]:
    """Return all semantic errors in one verification batch."""
    errors: list[str] = []

    _require(errors, data.get("schema_version") == "limen.positioning_commercial_contract.v1", "schema version must be v1")
    contract = data.get("contract", {})
    _require(errors, contract.get("status") == "preflight_dependency_blocked", "contract must remain dependency-blocked")
    dependency = contract.get("formal_dependency", {})
    _require(errors, dependency.get("chunk_id") == "PSP-C02", "formal dependency must be PSP-C02")
    _require(errors, dependency.get("state") == "open", "preflight must record PSP-C02 as open")
    prohibited = set(contract.get("prohibited_preflight_effects", []))
    for effect in ("public-surface publication", "issue or phase closure", "merge to main", "outbound sending"):
        _require(errors, effect in prohibited, f"missing prohibited preflight effect: {effect}")

    sources = {source["id"] for source in data.get("evidence_policy", {}).get("public_sources", [])}
    claims = data.get("claim_register", [])
    claim_ids = [claim.get("id") for claim in claims]
    claim_by_id = {claim.get("id"): claim for claim in claims}
    _require(errors, len(claim_ids) == len(set(claim_ids)), "claim IDs must be unique")
    for claim in claims:
        for ref in claim.get("evidence_refs", []):
            _require(errors, ref in sources, f"claim {claim.get('id')} has unknown evidence ref {ref}")
        if claim.get("kind") == "evidence_sensitive":
            _require(errors, claim.get("status") == "provisional_c02", f"evidence-sensitive claim {claim.get('id')} is not provisional_c02")
    for ref in _collect_key(data, "claim_refs"):
        _require(errors, ref in set(claim_ids), f"unknown claim ref {ref}")

    identity = data.get("identity", {})
    if "C03-IDENTITY-001" in claim_by_id:
        _require(errors, identity.get("canonical_title", "").lower() in claim_by_id["C03-IDENTITY-001"].get("statement", "").lower(), "identity title contradicts its registered claim")
    if "C03-HEADLINE-001" in claim_by_id:
        _require(errors, identity.get("headline") == claim_by_id["C03-HEADLINE-001"].get("statement"), "headline contradicts its registered claim")
    if "C03-AUTHORSHIP-001" in claim_by_id:
        _require(errors, identity.get("authorship_disclosure") == claim_by_id["C03-AUTHORSHIP-001"].get("statement"), "authorship disclosure contradicts its registered claim")

    audience_by_id = {audience["id"]: audience for audience in data.get("audiences", [])}
    _require(errors, set(audience_by_id) == {"direct_client", "recruiter_executive", "product_operating_partner"}, "audiences must be client, recruiter/executive, and product-operating partner")
    if "direct_client" in audience_by_id:
        _require(errors, "Audit" in audience_by_id["direct_client"].get("primary_cta", ""), "client CTA must enter through the Audit")
    if "recruiter_executive" in audience_by_id:
        _require(errors, "role" in audience_by_id["recruiter_executive"].get("primary_cta", "").lower(), "recruiter CTA must be role-specific")
    if "product_operating_partner" in audience_by_id:
        partner = audience_by_id["product_operating_partner"]
        _require(errors, partner.get("public_door") is False and partner.get("disclosure_entry") == "L3", "partnership must be non-public and diligence-only")

    narrative_by_id = {level["id"]: level for level in data.get("narrative_ladder", [])}
    _require(errors, set(narrative_by_id) == {"L1", "L2", "L3"}, "narrative ladder must contain L1, L2, and L3")
    for level in ("L1", "L2"):
        if level in narrative_by_id:
            _require(errors, "product_operating_partner" not in narrative_by_id[level].get("audience_ids", []), f"{level} must not solicit partnership")
    if "L3" in narrative_by_id:
        _require(errors, "product_operating_partner" in narrative_by_id["L3"].get("audience_ids", []), "L3 must contain gated partnership diligence")

    ladder = data.get("offer_ladder", {})
    _require(errors, ladder.get("primary_sequence") == ["audit", "install", "retainer"], "primary offer sequence must be audit -> install -> retainer")
    offers = ladder.get("items", [])
    offer_by_id = {offer["id"]: offer for offer in offers}
    _require(errors, set(offer_by_id) == {"audit", "install", "retainer"}, "primary offers must be audit, install, and retainer")
    required_offer_fields = {
        "entry_criteria", "deliverables", "exclusions", "timeline", "authority", "evidence",
        "economics", "handoff", "escalation", "claim_refs",
    }
    for offer in offers:
        missing = sorted(required_offer_fields - set(offer))
        _require(errors, not missing, f"offer {offer.get('id')} is missing {', '.join(missing)}")
        economics = offer.get("economics", {})
        _require(errors, economics.get("anchor_id", "").startswith("PRICE-"), f"offer {offer.get('id')} lacks symbolic price anchor")
        _require(errors, economics.get("range_id", "").startswith("RANGE-"), f"offer {offer.get('id')} lacks symbolic price range")
        _require(errors, economics.get("public_price") == "prohibited", f"offer {offer.get('id')} must prohibit public pricing")
    if "audit" in offer_by_id:
        _require(errors, offer_by_id["audit"].get("authority", {}).get("mode") == "read_only", "Audit authority must be read-only")
    if "install" in offer_by_id:
        install_blob = " ".join(_strings(offer_by_id["install"])).lower()
        _require(errors, "one team or pipeline" in install_blob, "Install must be bounded to one team or pipeline")
    if "retainer" in offer_by_id:
        retainer_blob = " ".join(_strings(offer_by_id["retainer"])).lower()
        _require(errors, "on-call" in retainer_blob and "unlimited" in retainer_blob, "Retainer must exclude on-call and unlimited capacity")

    secondary = ladder.get("secondary", {})
    _require(errors, secondary.get("id") == "partnership_review", "secondary offer must be partnership_review")
    _require(errors, secondary.get("public_cta") is False and secondary.get("disclosure_entry") == "L3", "partnership offer must remain secondary and L3-only")
    secondary_economics = secondary.get("economics", {})
    _require(errors, secondary_economics.get("range_id") == "RANGE-PARTNERSHIP", "partnership must use the symbolic partnership range")

    economics = data.get("economics_contract", {})
    _require(errors, set(economics.get("range_structure", {})) == {"floor", "target", "exception", "public_representation"}, "economics must define floor, target, exception, and public representation")
    economics_text = " ".join(_strings([economics, *[offer.get("economics", {}) for offer in offers], secondary_economics]))
    _require(errors, PRICE_PATTERN.search(economics_text) is None, "numeric pricing leaked into the public contract")

    qualification = data.get("qualification", {})
    rules = qualification.get("rules", [])
    priorities = [rule.get("priority") for rule in rules]
    _require(errors, len(priorities) == len(set(priorities)), "qualification priorities must be unique")
    for scenario in qualification.get("scenarios", []):
        matches = sorted((rule for rule in rules if _rule_matches(rule, scenario.get("facts", {}))), key=lambda rule: rule["priority"])
        _require(errors, bool(matches), f"scenario {scenario.get('id')} has no qualification route")
        if matches:
            _require(errors, matches[0].get("route") == scenario.get("expected_route"), f"scenario {scenario.get('id')} expected {scenario.get('expected_route')} but routed to {matches[0].get('route')}")
        commercial_matches = [rule["route"] for rule in matches if rule.get("route") in PRIMARY_ROUTES]
        _require(errors, len(commercial_matches) <= 1, f"scenario {scenario.get('id')} overlaps commercial offers: {commercial_matches}")

    public_copy = " ".join(_public_copy_strings(data)).lower()
    for unsupported in ("best in the world", "top 1%", "runs forever", "zero maintenance", "replace the whole team"):
        _require(errors, unsupported not in public_copy, f"unsupported public language found: {unsupported}")
    return errors


def _collect_key(value: Any, key: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(value, dict):
        for item_key, item_value in value.items():
            if item_key == key and isinstance(item_value, list):
                found.extend(item_value)
            else:
                found.extend(_collect_key(item_value, key))
    elif isinstance(value, list):
        for item in value:
            found.extend(_collect_key(item, key))
    return found


def render_contract(data: dict[str, Any]) -> str:
    identity = data["identity"]
    audiences = data["audiences"]
    offers = [*data["offer_ladder"]["items"], data["offer_ladder"]["secondary"]]
    lines = [
        "<!-- Generated by scripts/positioning-commercial-contract.py; edit the YAML source. -->",
        "# Production-systems identity and commercial contract",
        "",
        "> **Preflight only — blocked on PSP-C02.** Evidence-sensitive language remains provisional. This document does not publish an offer, set a fee, grant authority, or close PSP-P03/PSP-P04 work.",
        "",
        "## Identity contract",
        "",
        f"**{identity['canonical_title']}.** {identity['headline']}",
        "",
        identity["operating_thesis"],
        "",
        f"Authorship: {identity['authorship_disclosure']}",
        "",
        "The commercial promise is a bounded decision and operating system—not control of the buyer's organization. Authority comes from a written mandate; current owners remain visible; every path ends in evidence and handoff.",
        "",
        "## Audience contracts",
        "",
    ]
    for audience in audiences:
        door = "public entry" if audience["public_door"] else "gated diligence only"
        lines.extend([
            f"### {audience['label']}",
            "",
            f"**Job:** {audience['job']}",
            "",
            f"**Entry:** {audience['disclosure_entry']} ({door}). **Next step:** {audience['primary_cta']}",
            "",
        ])
    lines.extend(["## Narrative ladder", ""])
    for level in data["narrative_ladder"]:
        lines.extend([f"### {level['label']} ({level['id']})", ""])
        for beat in level["beats"]:
            lines.append(f"- {beat}")
        lines.extend(["", f"**Stop rule:** {level['stop_rule']}", ""])
    lines.extend([
        "## Bounded authority and interview language",
        "",
        data["interview_threat_contract"]["objective"],
        "",
    ])
    for response in data["interview_threat_contract"]["responses"]:
        lines.extend([f"- **{response['prompt']}** {response['answer']}"])
    lines.extend(["", "## Offer ladder", "", "| Stage | Offer | Entry and promise | Authority | Timeline | Economics |", "| --- | --- | --- | --- | --- | --- |"])
    for offer in offers:
        economics = offer["economics"]
        lines.append(
            f"| {offer['stage']} | {offer['name']} | {offer['trigger']} {offer['promise']} | {offer['authority']['mode']}: {offer['authority']['boundary']} | {offer['timeline']} | {economics['range_id']} / {economics['anchor_id']}; numeric terms remain privately gated |"
        )
    lines.extend(["", "### Offer boundaries", ""])
    for offer in offers:
        lines.extend([f"#### {offer['name']}", "", "Entry criteria:", ""])
        lines.extend(f"- {item}" for item in offer["entry_criteria"])
        lines.extend(["", "Deliverables:", ""])
        lines.extend(f"- {item}" for item in offer["deliverables"])
        lines.extend(["", "Exclusions:", ""])
        lines.extend(f"- {item}" for item in offer["exclusions"])
        lines.extend(["", f"**Acceptance:** {offer['evidence']['acceptance']}", "", f"**Handoff:** {offer['handoff']}", ""])
    economics = data["economics_contract"]
    lines.extend([
        "## Economics and qualification",
        "",
        economics["public_rule"],
        "",
        f"- **Floor:** {economics['range_structure']['floor']}",
        f"- **Target:** {economics['range_structure']['target']}",
        f"- **Exception:** {economics['range_structure']['exception']}",
        "",
        "A request routes by evidence: guarded legal, data, account, public-claim, or pricing exceptions go to human review; prohibited scope is declined; employment stays role-specific; partnership stays behind diligence; client work enters through audit, then install, then a bounded retainer only when its prerequisites exist.",
        "",
        "## Claim and evidence boundary",
        "",
        "| Claim ID | Status | Permitted statement | Limitation |",
        "| --- | --- | --- | --- |",
    ])
    for claim in data["claim_register"]:
        lines.append(f"| {claim['id']} | {claim['status']} | {claim['statement']} | {claim['limits']} |")
    lines.extend([
        "",
        "## Open human gates",
        "",
        "- `HG-PRICE-ANCHORS`: approves the private floor, target, and exception amounts behind each symbolic range.",
        "- `HG-CONTRACT`: approves terms before sending, signature, liability, data, payment, or service commitment.",
        "- `HG-OPERATOR-TERMS`: approves any equity, licence, revenue, custody, access, or product-transfer term.",
        "",
        "Until those gates and PSP-C02 are satisfied, this remains a truthful strategy preflight, not a public offer or agreement.",
        "",
    ])
    return "\n".join(lines)


def _matrix_ids(text: str, prefix: str) -> set[str]:
    return set(re.findall(rf"\b{re.escape(prefix)}-W\d{{2}}\b", text))


def validate_p03_matrix(text: str) -> list[str]:
    """Validate P03 coverage and the threat-language leaf's canonical evidence owner."""
    errors: list[str] = []
    found = _matrix_ids(text, "PSP-P03")
    if found != P03_WORK:
        errors.append(f"P03 evidence matrix coverage mismatch: expected {sorted(P03_WORK)}, found {sorted(found)}")
    rows = [line for line in text.splitlines() if "| PSP-P03-W06 |" in line]
    if len(rows) != 1:
        errors.append("PSP-P03-W06 must appear in exactly one evidence-matrix row")
    elif "`interview_threat_contract`" not in rows[0]:
        errors.append("PSP-P03-W06 must map to interview_threat_contract")
    return errors


def validate_artifact_text(label: str, text: str) -> list[str]:
    errors: list[str] = []
    for marker in PRIVATE_MARKERS:
        if marker in text:
            errors.append(f"private-source marker leaked into {label}: {marker}")
    if PRICE_PATTERN.search(text):
        errors.append(f"numeric pricing leaked into {label}")
    return errors


def validate_repository(data: dict[str, Any]) -> list[str]:
    errors = validate_contract(data)
    expected_render = render_contract(data)
    if not RENDER_PATH.exists():
        errors.append(f"missing generated render: {RENDER_PATH.relative_to(ROOT)}")
    elif RENDER_PATH.read_text() != expected_render:
        errors.append("generated commercial-contract.md is stale")

    artifacts: dict[Path, str] = {}
    for path in (RENDER_PATH, P03_MATRIX_PATH, P04_MATRIX_PATH, RELAY_PATH):
        if not path.exists():
            errors.append(f"missing required artifact: {path.relative_to(ROOT)}")
            continue
        artifacts[path] = path.read_text()
    for path, text in artifacts.items():
        errors.extend(validate_artifact_text(str(path.relative_to(ROOT)), text))

    if P03_MATRIX_PATH in artifacts:
        errors.extend(validate_p03_matrix(artifacts[P03_MATRIX_PATH]))
    if P04_MATRIX_PATH in artifacts:
        found = _matrix_ids(artifacts[P04_MATRIX_PATH], "PSP-P04")
        if found != P04_WORK:
            errors.append(f"P04 evidence matrix coverage mismatch: expected {sorted(P04_WORK)}, found {sorted(found)}")
    if RELAY_PATH in artifacts:
        relay = artifacts[RELAY_PATH]
        for required in ("PSP-C04", "PSP-P05", "PSP-P06", "Sol / xhigh", "PSP-C05", "PSP-P11", "Sol / max", "blocked on PSP-C02"):
            if required not in relay:
                errors.append(f"successor relay missing exact marker: {required}")
        for downstream_head in (
            "e9c2db2360acd5fd57a48d063e64990dc8f3a768",
            "fa86b67a7283c15ab801302ffac655c30898b6a1",
            "b62f83f192112f94e73735e06a765b3ad6d97d9b",
            "4ae8e81665e35e6a5d403a3e13935021ce6544ec",
        ):
            if downstream_head not in relay:
                errors.append(f"successor relay omits preserved downstream head: {downstream_head}")
    if PROGRAM_PATH.exists():
        program = yaml.safe_load(PROGRAM_PATH.read_text())
        registered_gates = set(program.get("human_gates", {}))
        referenced_gates = set(data.get("economics_contract", {}).get("gates", []))
        referenced_gates.update(_gate_ids(data.get("commercial_templates", {}).get("required_gates", [])))
        missing_gates = sorted(referenced_gates - registered_gates)
        if missing_gates:
            errors.append(f"commercial contract references unregistered human gates: {missing_gates}")
        phase_artifacts = {
            "PSP-P03": artifacts.get(P03_MATRIX_PATH, ""),
            "PSP-P04": artifacts.get(P04_MATRIX_PATH, ""),
            "PSP-P05": artifacts.get(RELAY_PATH, ""),
            "PSP-P06": artifacts.get(RELAY_PATH, ""),
            "PSP-P11": artifacts.get(RELAY_PATH, ""),
        }
        for phase in program.get("phases", []):
            if phase.get("id") not in phase_artifacts:
                continue
            artifact = phase_artifacts[phase["id"]]
            for work in phase.get("work", []):
                rows = [line for line in artifact.splitlines() if f"| {work['id']} |" in line]
                if len(rows) != 1:
                    errors.append(f"{work['id']} must appear in exactly one registry-aligned row")
                    continue
                row = rows[0]
                assignment = _program_assignment(work, program)
                expected_model = f"{assignment['slug']} / {assignment['effort']}"
                if expected_model not in row:
                    errors.append(f"{work['id']} model drift: expected {expected_model}")
                if phase["id"] in {"PSP-P05", "PSP-P06", "PSP-P11"}:
                    for target_path in work.get("target_paths", []):
                        if f"`{target_path}`" not in row:
                            errors.append(f"{work['id']} relay omits registered target path {target_path}")
        chunks = {chunk["id"]: chunk for chunk in program.get("execution_chunks", {}).get("chunks", [])}
        relay = artifacts.get(RELAY_PATH, "")
        for chunk_id in ("PSP-C04", "PSP-C05"):
            chunk = chunks.get(chunk_id, {})
            conductor = chunk.get("conductor", {})
            expected = f"{conductor.get('slug')} / {conductor.get('effort')}"
            if expected not in relay:
                errors.append(f"{chunk_id} conductor drift: expected {expected}")
            if chunk.get("depends_on") != ["PSP-C03"]:
                errors.append(f"{chunk_id} dependency drift: expected only PSP-C03")
    return errors


def _gate_ids(values: Iterable[Any]) -> set[str]:
    found: set[str] = set()
    for value in values:
        found.update(re.findall(r"\bHG-[A-Z-]+\b", str(value)))
    return found


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text())
    if not isinstance(loaded, dict):
        raise ContractValidationError("contract root must be a mapping")
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true", help="regenerate the public Markdown view")
    parser.add_argument("--check", action="store_true", help="validate source and repository artifacts")
    args = parser.parse_args()
    if not args.render and not args.check:
        parser.error("choose --render and/or --check")

    data = load_contract()
    semantic_errors = validate_contract(data)
    if semantic_errors:
        for error in semantic_errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    if args.render:
        RENDER_PATH.parent.mkdir(parents=True, exist_ok=True)
        RENDER_PATH.write_text(render_contract(data))
        print(f"rendered {RENDER_PATH.relative_to(ROOT)}")
    if args.check:
        errors = validate_repository(data)
        if errors:
            for error in errors:
                print(f"FAIL: {error}", file=sys.stderr)
            return 1
        print("PASS: PSP-C03 commercial contract is coherent, bounded, evidence-linked, and dependency-blocked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
