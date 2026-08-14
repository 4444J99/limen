#!/usr/bin/env python3
"""Focused, fail-closed acceptance predicate for PSP-P04-W01."""

from __future__ import annotations

import hashlib
import json
import re
import runpy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
OFFER_DIR = Path(__file__).resolve().parent
OFFER_PATH = OFFER_DIR / "agentic-delivery-audit.md"
RECORD_PATH = OFFER_DIR / "agentic-delivery-audit-decision-record.json"
CANONICAL_VALIDATOR_PATH = ROOT / "scripts/positioning-offer-artifacts.py"
CANONICAL = runpy.run_path(str(CANONICAL_VALIDATOR_PATH))
PRIVATE_PATTERNS = tuple(CANONICAL["PRIVATE_PATTERNS"])
PASS_LINE = "PASS: PSP-P04-W01 audit is priceable, scopeable, deliverable, and declineable without oral exceptions"
EXPECTED_RECORD_SHA256 = "64e3035c482b28383523d6e2f56a1794aafd15eb64a6a3de80b2a443d671f23c"
EXPECTED_TOP_LEVEL = {
    "schema_version",
    "status",
    "work_item",
    "reviewed_offer",
    "leased_evidence_baseline",
    "buyable_decision",
    "required_inputs",
    "missing_evidence_rule",
    "outputs",
    "delivery_sequence",
    "exclusions",
    "success_criteria",
    "pricing",
    "decline_or_pause_when",
    "escalation",
    "authority_and_handoff",
    "review_verdict",
    "effect_boundary",
    "evidence_links",
    "rollback",
}
EXPECTED_CONTRACT_LISTS = {
    "exclusions": [
        "production mutation, deployment, or operational command",
        "outbound messages, account changes, procurement, or vendor commitments",
        "organization redesign, team surveillance, management takeover, or executive substitution",
        "penetration testing, legal opinion, compliance certification, or financial audit",
        "unlimited repository, team, vendor, evidence, meeting, or revision scope",
        "on-call response, implementation delivery, or guaranteed business outcome",
    ],
    "success_criteria": [
        "The named decision owner can make the stated keep, kill, narrow, or govern decision.",
        "Every material recommendation resolves to evidence or an explicit uncertainty.",
        "The final artifact set stays within the agreed initiative, access, custody, and authority boundaries.",
        "Current owners can see, challenge, and correct findings before the verdict is finalized.",
        "The sponsor and named internal owner receive the evidence register, verdict, gate specification, options, and walkthrough.",
        "Access is returned, expired, or deleted under the agreed instructions, with no hidden follow-on work.",
    ],
    "decline_or_pause_when": [
        "no sponsor or decision owner will own the verdict",
        "the request contains multiple unbounded initiatives or no decision window",
        "diagnosis requires production write access, unsolicited outreach, covert monitoring, or account control",
        "required evidence is unavailable, unlawfully sourced, unsafe to transfer, or outside agreed custody",
        "the expected role is executive substitution, territorial control, team takeover, or an outcome guarantee",
        "a material security, privacy, legal, regulatory, or contractual question lacks an authorized owner",
        "the requested timeline cannot support an evidence-linked verdict",
    ],
}


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def require(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def exact_keys(errors: list[str], value: Any, expected: set[str], owner: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{owner} must be an object")
        return {}
    observed = set(value)
    if observed != expected:
        errors.append(f"{owner} keys differ: missing={sorted(expected - observed)} extra={sorted(observed - expected)}")
    return value


def public_fragments(value: Any, path: str = "record") -> list[str]:
    """Render every key and scalar so leakage cannot hide in JSON types."""

    if isinstance(value, dict):
        fragments: list[str] = []
        for key, child in value.items():
            child_path = f"{path}.{key}"
            fragments.append(str(key))
            fragments.extend(public_fragments(child, child_path))
        return fragments
    if isinstance(value, list):
        return [item for index, child in enumerate(value) for item in public_fragments(child, f"{path}[{index}]")]
    if isinstance(value, str):
        return [value, f"{path}={value}"]
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return [rendered, f"{path}={rendered}"]


def canonical_record_sha256(record: Any) -> str:
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def canonical_offer_errors(offer: str) -> list[str]:
    """Bind the reviewed offer to the exact render of the canonical YAML."""

    try:
        contract = CANONICAL["load_contract"]()
        errors = list(CANONICAL["validate_contract"](contract))
        rendered = CANONICAL["render_artifacts"](contract)
    except (OSError, ValueError) as exc:
        return [f"canonical offer validation failed: {exc}"]
    if errors:
        return [f"canonical offer contract: {error}" for error in errors]
    expected = rendered.get(OFFER_PATH.name)
    if offer != expected:
        return ["generated offer drifted from the exact canonical commercial-contract render"]
    return []


def main() -> int:
    errors: list[str] = []
    for path in (OFFER_PATH, RECORD_PATH):
        require(errors, path.is_file() and not path.is_symlink(), f"missing regular artifact: {path.name}")
    if errors:
        return report(errors)

    offer = OFFER_PATH.read_text(encoding="utf-8")
    try:
        record = json.loads(RECORD_PATH.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (json.JSONDecodeError, ValueError) as exc:
        return report([f"decision record JSON is invalid: {exc}"])

    record = exact_keys(errors, record, EXPECTED_TOP_LEVEL, "decision record")
    require(
        errors,
        canonical_record_sha256(record) == EXPECTED_RECORD_SHA256,
        "decision record contract digest differs",
    )
    errors.extend(canonical_offer_errors(offer))
    require(
        errors, record.get("schema_version") == "limen.positioning.audit_decision_record.v1", "schema_version mismatch"
    )
    require(errors, record.get("status") == "internal_review_contract", "status mismatch")
    require(errors, record.get("work_item") == "PSP-P04-W01", "work_item mismatch")
    require(errors, record.get("reviewed_offer") == OFFER_PATH.name, "reviewed_offer mismatch")
    require(
        errors,
        record.get("leased_evidence_baseline") == "58b0d4764ef2bf1d3b01ae8ebc1ac1137cae2930",
        "leased evidence baseline mismatch",
    )

    for token in (
        "<!-- Generated by scripts/positioning-offer-artifacts.py",
        "**Work item:** `PSP-P04-W01`",
        "**Buyer:** CTO, VP Engineering, Head of Platform",
        "**Trigger:** A material AI or software initiative is active",
        "**Timeline:** Two to three weeks from complete intake and agreed access.",
        "**Mode:** `read_only`",
        "**Range ID:** `RANGE-AUDIT`",
        "**Anchor ID:** `PRICE-AUDIT`",
        "**Approval gate:** `HG-PRICE-ANCHORS`",
        "**Public price:** `prohibited`",
    ):
        require(errors, token in offer, f"generated offer missing {token!r}")

    decision = exact_keys(
        errors,
        record.get("buyable_decision"),
        {"buyer", "trigger", "unit_of_work", "scope", "promise", "timeline", "commercial_form"},
        "buyable_decision",
    )
    for key in ("buyer", "trigger", "unit_of_work", "scope", "promise", "timeline", "commercial_form"):
        require(
            errors,
            isinstance(decision.get(key), str) and bool(decision[key].strip()),
            f"buyable_decision.{key} must be non-empty",
        )
    require(
        errors,
        decision.get("timeline") == "Two to three weeks from complete intake and agreed access.",
        "timeline contract mismatch",
    )
    require(errors, "Read-only" in str(decision.get("scope")), "scope must remain read-only")

    inputs = record.get("required_inputs")
    require(errors, isinstance(inputs, list) and len(inputs) == 6, "required_inputs must contain exactly six records")
    expected_input_ids = [
        "sponsor_and_decision",
        "bounded_scope",
        "read_only_evidence_register",
        "current_owner_access",
        "custody_instructions",
        "known_constraints",
    ]
    if isinstance(inputs, list):
        observed_ids: list[Any] = []
        for index, raw in enumerate(inputs):
            item = exact_keys(errors, raw, {"id", "contract"}, f"required_inputs[{index}]")
            observed_ids.append(item.get("id"))
            require(
                errors,
                isinstance(item.get("contract"), str) and bool(item["contract"].strip()),
                f"required_inputs[{index}].contract must be non-empty",
            )
        require(errors, observed_ids == expected_input_ids, "required input IDs or order differ")

    expected_outputs = [
        "current-state system and decision map",
        "failure, risk, and evidence register",
        "keep, kill, narrow, or govern verdict",
        "verification and authority gate specification",
        "sequenced implementation options with owner and dependency notes",
        "recorded walkthrough and handoff package",
    ]
    require(errors, record.get("outputs") == expected_outputs, "output contract differs")

    sequence = record.get("delivery_sequence")
    expected_stages = ["intake_checkpoint", "week_one", "week_two", "week_two_to_three", "closeout"]
    require(errors, isinstance(sequence, list) and len(sequence) == 5, "delivery_sequence must contain five stages")
    if isinstance(sequence, list):
        observed_stages: list[Any] = []
        for index, raw in enumerate(sequence):
            item = exact_keys(errors, raw, {"stage", "contract"}, f"delivery_sequence[{index}]")
            observed_stages.append(item.get("stage"))
        require(errors, observed_stages == expected_stages, "delivery stage IDs or order differ")

    for field, expected in EXPECTED_CONTRACT_LISTS.items():
        require(errors, record.get(field) == expected, f"{field} contract differs")

    pricing = exact_keys(
        errors,
        record.get("pricing"),
        {
            "model",
            "range_id",
            "anchor_id",
            "approval_gate",
            "public_numeric_amount",
            "price_when",
            "capacity_rule",
            "scope_trade_rule",
            "discount_rule",
        },
        "pricing",
    )
    require(errors, pricing.get("model") == "fixed_scope_decision_fee", "pricing model mismatch")
    require(errors, pricing.get("range_id") == "RANGE-AUDIT", "range_id mismatch")
    require(errors, pricing.get("anchor_id") == "PRICE-AUDIT", "anchor_id mismatch")
    require(errors, pricing.get("approval_gate") == "HG-PRICE-ANCHORS", "pricing gate mismatch")
    require(errors, pricing.get("public_numeric_amount") is False, "public numeric amount must be false")
    require(
        errors,
        pricing.get("price_when")
        == [
            "the evidence is accessible",
            "the decision is bounded",
            "the decision owner will participate",
        ],
        "price_when contract differs",
    )
    require(errors, "one named diagnostic window" in str(pricing.get("capacity_rule")), "capacity rule is not bounded")
    require(
        errors,
        "never preserves the same risk and scope for less" in str(pricing.get("discount_rule")),
        "discount rule is not scope-safe",
    )

    authority = exact_keys(
        errors,
        record.get("authority_and_handoff"),
        {
            "mode",
            "additive_leverage",
            "sponsor_granted_scope",
            "current_owner_visibility",
            "current_owners_retain_operational_authority",
            "prohibited_effects",
            "handoff_artifacts",
            "continuing_control",
        },
        "authority_and_handoff",
    )
    require(errors, authority.get("mode") == "read_only", "authority mode mismatch")
    for key in (
        "additive_leverage",
        "sponsor_granted_scope",
        "current_owner_visibility",
        "current_owners_retain_operational_authority",
    ):
        require(errors, authority.get(key) is True, f"authority_and_handoff.{key} must be true")
    require(errors, authority.get("continuing_control") is False, "handoff cannot create continuing control")
    expected_prohibited = [
        "mutate production",
        "send messages",
        "change accounts",
        "expand access",
        "replace an executive",
        "take over a team",
        "silently become implementation authority",
    ]
    require(errors, authority.get("prohibited_effects") == expected_prohibited, "prohibited effects differ")

    verdict = exact_keys(
        errors,
        record.get("review_verdict"),
        {"price", "scope", "deliver", "decline", "overall", "oral_exceptions_required", "basis"},
        "review_verdict",
    )
    for key in ("price", "scope", "deliver", "decline", "overall"):
        require(errors, verdict.get(key) == "PASS", f"review_verdict.{key} must be PASS")
    require(errors, verdict.get("oral_exceptions_required") is False, "oral exceptions must not be required")

    effect = exact_keys(
        errors,
        record.get("effect_boundary"),
        {
            "publishes_offer",
            "approves_numeric_price",
            "creates_proposal_or_sow",
            "authorizes_outbound_send",
            "binds_either_party",
            "authorizes_delivery_start",
            "human_gates_not_satisfied",
            "completion_condition",
        },
        "effect_boundary",
    )
    for key in (
        "publishes_offer",
        "approves_numeric_price",
        "creates_proposal_or_sow",
        "authorizes_outbound_send",
        "binds_either_party",
        "authorizes_delivery_start",
    ):
        require(errors, effect.get(key) is False, f"effect_boundary.{key} must be false")
    require(
        errors,
        effect.get("human_gates_not_satisfied")
        == [
            "HG-PRICE-ANCHORS",
            "HG-CONTRACT",
            "HG-OPERATOR-TERMS",
            "HG-PUBLICATION-SEND",
            "PSP-P03-W07",
        ],
        "human gate boundary differs",
    )

    public_text = "\n".join(public_fragments(record))
    for pattern in PRIVATE_PATTERNS:
        require(
            errors,
            pattern.search(public_text) is None,
            f"private-source leakage matched canonical pattern: {pattern.pattern!r}",
        )
    for label, pattern in {
        "numeric dollar amount": r"\$\s*\d",
        "named public currency": r"\b(?:USD|EUR|GBP)\b",
        "numeric currency glyph": r"[£€]\s*\d",
        "hourly or daily rate": r"\b(?:hourly|daily)\s+(?:rate|fee)\b",
    }.items():
        require(
            errors, re.search(pattern, public_text, flags=re.IGNORECASE) is None, f"public pricing leakage: {label}"
        )

    return report(errors)


def report(errors: list[str]) -> int:
    if errors:
        print("FAIL: PSP-P04-W01 audit offer contract")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1
    print(PASS_LINE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
