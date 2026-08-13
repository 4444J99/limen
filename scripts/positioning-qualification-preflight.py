#!/usr/bin/env python3
"""Validate the synthetic PSP-C09 ICP and buying-signal preflight."""

from __future__ import annotations

import argparse
from functools import lru_cache
import json
from pathlib import Path
import re
import runpy
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "positioning" / "sales" / "psp-c09" / "icp-and-buying-signals.preflight.json"
PROGRAM_SCRIPT = ROOT / "scripts" / "positioning-program.py"

SCHEMA_VERSION = "limen.psp-c09.icp-preflight.v1"
WORK_ID = "PSP-P10-W01"
ASSIGNMENT_POLICY = {
    "selection": "runtime_catalog",
    "registry": "institutio/positioning/program.yaml",
    "catalogPredicate": "python3 scripts/positioning-program.py --verify-model-assignments",
    "unavailableAction": "fail_blocked_no_silent_substitution",
}

EXPECTED_SOURCE_LOCK = {
    "commercialContract": "organvm/limen#2312@b6af8086c9050634313f519c29a6dfcb922c3721",
    "commercialContractAcceptedAncestor": "organvm/limen#2312@c94bc3748fcf2d1dc802a4bae972df23d9a9fbec",
    "commercialContractIntegrated": "organvm/limen@8f89ad16ca1df84b00cb8227c88f368d0d64631a",
    "deliveryOs": "organvm-iii-ergon/collaboration-operations-platform#135@432c31ea6bcaf2c175b0fde08b6e1733fe4c2926",
    "deliveryOsIntegrated": "organvm-iii-ergon/collaboration-operations-platform@9172619633bb9a09ea3a05eae9f48e987f2b3e7d",
    "proofLedContent": "organvm/limen#2316@78736b8133c98e59d85069ea54eba2f20ed7b0a2",
    "proofExperience": "organvm/limen#2313@543fa28df52c9db7be3b7307019dcf209361d0b9",
    "portfolioExperience": "organvm-vii-kerygma/portfolio#220@8974543ba9675ed0504141895812476efef5dd80",
    "portfolioExperienceIntegrated": "organvm-vii-kerygma/portfolio@a01b6d85f78d2d744c0c994f7220081bb54a85c5",
    "deliveryOsRelay": "organvm/limen#2315@d31ce37a85adf5d2e448dab8273a61e388f1e589",
    "deliveryOsRelayIntegrated": "organvm/limen@7a0682722185d17095a0b44de17d4bd5cf3284dd",
}

EXPECTED_UPSTREAM_STATE = {
    "p02Closed": True,
    "c03AcceptedThrough": "PSP-P03-W06",
    "c03ReaderGate": "PSP-P03-W07",
    "c03ReaderIssue": 2188,
    "c03ReaderEvidenceSatisfied": False,
    "c03FormalState": "open",
    "c04State": "prepared_preflight",
    "c05State": "prepared_preflight",
    "c06State": "prepared_preflight",
    "c07State": "prepared_preflight",
    "c08State": "prepared_preflight",
}

WORK_IDS = tuple(f"PSP-P10-W0{index}" for index in range(1, 8))
EXPECTED_ROOT_KEYS = {
    "schemaVersion",
    "status",
    "workId",
    "formalPredicateRun",
    "formalIssueClosed",
    "countsAsClosure",
    "syntheticOnly",
    "externalEffects",
    "sourceLock",
    "upstreamState",
    "idealClientProfile",
    "buyingCommittee",
    "triggerEvents",
    "painTypes",
    "hardDisqualifiers",
    "humanReviewReasons",
    "liveEvidenceSignals",
    "scorecard",
    "syntheticAccounts",
    "assignmentPolicy",
    "assignments",
}
EXPECTED_SCORECARD_KEYS = {
    "weights",
    "requiredForQualifiedAudit",
    "qualifiedAuditMinimum",
    "boundedFollowUpMinimum",
    "rule",
}
EXPECTED_FACT_KEYS = {
    "decision_owner",
    "bounded_initiative",
    "material_failure_cost",
    "read_only_evidence",
    "decision_window",
    "handoff_owner",
    "willing_to_stop_or_narrow",
}
EXPECTED_REQUIRED_SIGNALS = [
    "decision_owner",
    "bounded_initiative",
    "read_only_evidence",
    "decision_window",
    "handoff_owner",
    "willing_to_stop_or_narrow",
]
EXPECTED_ACCOUNT_KEYS = {
    "id",
    "facts",
    "hardDisqualifiers",
    "humanReviewReasons",
    "evidenceRefs",
    "uncertainty",
    "expectedScore",
    "expectedDisposition",
}
EXPECTED_HUMAN_REVIEW_REASONS = {
    "legal",
    "pricing",
    "regulated_data",
    "account_or_custody",
    "public_claim",
}
PROHIBITED_NORMALIZED_KEYS = {
    "company",
    "companyname",
    "contact",
    "contactemail",
    "contactname",
    "email",
    "emailaddress",
    "firstname",
    "fullname",
    "lastname",
    "paidoutcome",
    "personname",
    "phone",
    "phonenumber",
    "postaladdress",
    "realoutcome",
    "revenue",
    "socialhandle",
    "streetaddress",
    "userhandle",
    "username",
}
EMAIL_RE = re.compile(r"(?i)(?<![\w.+-])[\w.+-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+(?![\w.-])")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d(). -]{8,}\d)(?!\w)")


@lru_cache(maxsize=1)
def expected_assignments() -> dict[str, dict[str, Any]]:
    """Derive capability/effort requirements without freezing provider slugs."""
    program = runpy.run_path(str(PROGRAM_SCRIPT))
    graph = program["index_program"](program["load_manifest"]())
    chunk_work = [graph["work_by_id"][work_id] for work_id in WORK_IDS]
    chunk_assignment = program["chunk_assignment_for"]("PSP-C09", graph)
    requirements: dict[str, dict[str, Any]] = {
        "PSP-C09": {
            "selection": "runtime_catalog",
            "role": "chunk_conductor",
            "effort": chunk_assignment["effort"],
            "capabilities": sorted({capability for packet in chunk_work for capability in packet["capabilities"]}),
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


def score_account(account: dict[str, Any], scorecard: dict[str, Any]) -> int:
    facts = account.get("facts", {})
    return sum(int(weight) for signal, weight in scorecard["weights"].items() if facts.get(signal) is True)


def disposition(account: dict[str, Any], scorecard: dict[str, Any]) -> str:
    score = score_account(account, scorecard)
    if account.get("hardDisqualifiers"):
        return "decline"
    if account.get("humanReviewReasons"):
        return "human_review"
    facts = account.get("facts", {})
    if any(facts.get(signal) is not True for signal in scorecard["requiredForQualifiedAudit"]):
        return "one_bounded_follow_up" if score >= scorecard["boundedFollowUpMinimum"] else "decline"
    if account.get("uncertainty") == "high":
        return "one_bounded_follow_up"
    if score >= scorecard["qualifiedAuditMinimum"]:
        return "qualified_audit"
    if score >= scorecard["boundedFollowUpMinimum"]:
        return "one_bounded_follow_up"
    return "decline"


def _walk(value: Any) -> tuple[set[str], list[str]]:
    keys: set[str] = set()
    strings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            child_keys, child_strings = _walk(child)
            keys.update(child_keys)
            strings.extend(child_strings)
    elif isinstance(value, list):
        for child in value:
            child_keys, child_strings = _walk(child)
            keys.update(child_keys)
            strings.extend(child_strings)
    elif isinstance(value, str):
        strings.append(value)
    return keys, strings


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.casefold())


def _contains_phone(value: str) -> bool:
    return any(sum(character.isdigit() for character in match.group(0)) >= 10 for match in PHONE_RE.finditer(value))


def _is_unique_nonempty_text_list(value: Any, *, minimum: int = 0) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= minimum
        and all(isinstance(item, str) and bool(item.strip()) for item in value)
        and len(value) == len(set(value))
    )


def validate(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if set(data) != EXPECTED_ROOT_KEYS:
        failures.append("manifest must contain the exact public preflight schema")
    if data.get("schemaVersion") != SCHEMA_VERSION:
        failures.append(f"schemaVersion must be {SCHEMA_VERSION}")
    if data.get("workId") != WORK_ID:
        failures.append(f"workId must be {WORK_ID}")
    if data.get("status") != "prepared_preflight":
        failures.append("status must remain prepared_preflight")
    if (
        data.get("formalPredicateRun") is not False
        or data.get("formalIssueClosed") is not False
        or data.get("countsAsClosure") is not False
    ):
        failures.append("formal work must remain open")
    if data.get("syntheticOnly") is not True or data.get("externalEffects") != []:
        failures.append("preflight must remain synthetic and effect-free")
    if data.get("sourceLock") != EXPECTED_SOURCE_LOCK:
        failures.append("source lock drifted from exact upstream heads")
    if data.get("upstreamState") != EXPECTED_UPSTREAM_STATE:
        failures.append("upstream state must preserve the accepted/open/prepared boundary")
    if data.get("assignmentPolicy") != ASSIGNMENT_POLICY:
        failures.append("assignment policy must require runtime catalog discovery and fail-closed substitution")
    if data.get("assignments") != expected_assignments():
        failures.append("assignment capability/effort requirements drifted from the canonical runtime registry")

    if data.get("humanReviewReasons") != sorted(EXPECTED_HUMAN_REVIEW_REASONS):
        failures.append(
            "human-review reasons must exactly preserve legal/pricing/regulated/custody/public-claim routes"
        )

    scorecard = data.get("scorecard", {})
    if not isinstance(scorecard, dict) or set(scorecard) != EXPECTED_SCORECARD_KEYS:
        failures.append("scorecard must use the exact public schema")
        scorecard = {}
    weights = scorecard.get("weights", {})
    if (
        not isinstance(weights, dict)
        or set(weights) != EXPECTED_FACT_KEYS
        or not all(
            isinstance(weight, int) and not isinstance(weight, bool) and weight > 0 for weight in weights.values()
        )
        or sum(weights.values()) != 10
    ):
        failures.append("scorecard weights must total 10")
        weights = {}
    if scorecard.get("requiredForQualifiedAudit") != EXPECTED_REQUIRED_SIGNALS:
        failures.append(
            "qualified audit requires sponsor, scope, evidence, window, handoff owner, and willingness to narrow"
        )
    accounts = data.get("syntheticAccounts", [])
    if not isinstance(accounts, list) or len(accounts) != 10:
        failures.append("exactly ten synthetic accounts are required")
        accounts = []

    seen: set[str] = set()
    allowed_uncertainty = {"low", "medium", "high"}
    allowed_dispositions = {"qualified_audit", "one_bounded_follow_up", "human_review", "decline"}
    for account in accounts:
        if not isinstance(account, dict):
            failures.append("synthetic account must be a mapping")
            continue
        account_id = account.get("id", "<missing>")
        if set(account) != EXPECTED_ACCOUNT_KEYS:
            failures.append(f"{account_id}: account must use the exact synthetic schema")
        if not str(account_id).startswith("synthetic_account_"):
            failures.append(f"{account_id}: id must be synthetic")
        if account_id in seen:
            failures.append(f"{account_id}: duplicate id")
        seen.add(account_id)
        if not _is_unique_nonempty_text_list(account.get("evidenceRefs"), minimum=2):
            failures.append(f"{account_id}: evidenceRefs must be a list of at least two unique nonblank strings")
        facts = account.get("facts")
        if (
            not isinstance(facts, dict)
            or set(facts) != EXPECTED_FACT_KEYS
            or not all(isinstance(value, bool) for value in facts.values())
        ):
            failures.append(f"{account_id}: facts must contain the exact boolean scorecard signals")
            continue
        if not _is_unique_nonempty_text_list(account.get("hardDisqualifiers")):
            failures.append(f"{account_id}: hardDisqualifiers must be unique nonblank strings")
        review_reasons = account.get("humanReviewReasons")
        if not _is_unique_nonempty_text_list(review_reasons):
            failures.append(f"{account_id}: humanReviewReasons must be a unique text list")
        elif not set(review_reasons).issubset(EXPECTED_HUMAN_REVIEW_REASONS):
            failures.append(f"{account_id}: unsupported human-review reason")
        if account.get("uncertainty") not in allowed_uncertainty:
            failures.append(f"{account_id}: invalid uncertainty")
        if account.get("expectedDisposition") not in allowed_dispositions:
            failures.append(f"{account_id}: invalid expected disposition")
        actual_score = score_account(account, scorecard)
        if actual_score != account.get("expectedScore"):
            failures.append(f"{account_id}: expected score {account.get('expectedScore')} != {actual_score}")
        actual_disposition = disposition(account, scorecard)
        if actual_disposition != account.get("expectedDisposition"):
            failures.append(f"{account_id}: expected {account.get('expectedDisposition')} != {actual_disposition}")

    keys, strings = _walk(data)
    leaked_keys = sorted(key for key in keys if _normalized_key(key) in PROHIBITED_NORMALIZED_KEYS)
    if leaked_keys:
        failures.append(f"real-contact/commercial outcome keys prohibited: {', '.join(leaked_keys)}")
    if any(EMAIL_RE.search(value) or _contains_phone(value) for value in strings):
        failures.append("real contact details are prohibited in all public preflight values")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print(
            json.dumps(
                {
                    "status": "failed",
                    "synthetic_accounts": 0,
                    "assignments": 0,
                    "failures": ["manifest must be a mapping"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1
    failures = validate(data)
    result = {
        "status": "ok" if not failures else "failed",
        "synthetic_accounts": len(data.get("syntheticAccounts", [])),
        "assignments": len(data.get("assignments", {})) if isinstance(data.get("assignments"), dict) else 0,
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
