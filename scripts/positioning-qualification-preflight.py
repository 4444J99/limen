#!/usr/bin/env python3
"""Validate the synthetic PSP-C09 ICP and buying-signal preflight."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "positioning" / "sales" / "psp-c09" / "icp-and-buying-signals.preflight.json"

EXPECTED_SOURCE_LOCK = {
    "commercialContract": "organvm/limen#2312@b5bc01585a10615e85e1ef5b31a2356c24fb9bc9",
    "deliveryOs": "organvm-iii-ergon/collaboration-operations-platform#135@4ae8e81665e35e6a5d403a3e13935021ce6544ec",
    "proofLedContent": "organvm/limen#2316@36bf386c22e64785db8e7843899bf9aabf85bf89",
}

EXPECTED_ASSIGNMENTS = {
    "PSP-C09": {"model": "gpt-5.6-sol", "effort": "xhigh"},
    "PSP-P10-W01": {"model": "gpt-5.6-terra", "effort": "high"},
    "PSP-P10-W02": {"model": "gpt-5.6-terra", "effort": "high"},
    "PSP-P10-W03": {"model": "gpt-5.6-sol", "effort": "xhigh"},
    "PSP-P10-W04": {"model": "gpt-5.6-terra", "effort": "high"},
    "PSP-P10-W05": {"model": "gpt-5.6-luna", "effort": "medium"},
    "PSP-P10-W06": {"model": "gpt-5.6-terra", "effort": "high"},
    "PSP-P10-W07": {"model": "gpt-5.6-luna", "effort": "medium"},
}

PROHIBITED_KEYS = {
    "company",
    "companyName",
    "contact",
    "contactEmail",
    "contactName",
    "email",
    "phone",
    "revenue",
    "paidOutcome",
    "realOutcome",
}


def score_account(account: dict[str, Any], scorecard: dict[str, Any]) -> int:
    facts = account.get("facts", {})
    return sum(int(weight) for signal, weight in scorecard["weights"].items() if facts.get(signal) is True)


def disposition(account: dict[str, Any], scorecard: dict[str, Any]) -> str:
    score = score_account(account, scorecard)
    if account.get("hardDisqualifiers"):
        return "decline"
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


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def validate(data: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if data.get("status") != "prepared_preflight":
        failures.append("status must remain prepared_preflight")
    if data.get("formalPredicateRun") is not False or data.get("formalIssueClosed") is not False:
        failures.append("formal work must remain open")
    if data.get("syntheticOnly") is not True or data.get("externalEffects") != []:
        failures.append("preflight must remain synthetic and effect-free")
    if data.get("sourceLock") != EXPECTED_SOURCE_LOCK:
        failures.append("source lock drifted from exact upstream heads")
    if data.get("assignments") != EXPECTED_ASSIGNMENTS:
        failures.append("model/effort assignments drifted from the live registry")

    scorecard = data.get("scorecard", {})
    weights = scorecard.get("weights", {})
    if sum(weights.values()) != 10:
        failures.append("scorecard weights must total 10")
    accounts = data.get("syntheticAccounts", [])
    if len(accounts) != 10:
        failures.append("exactly ten synthetic accounts are required")

    seen: set[str] = set()
    allowed_uncertainty = {"low", "medium", "high"}
    allowed_dispositions = {"qualified_audit", "one_bounded_follow_up", "decline"}
    for account in accounts:
        account_id = account.get("id", "<missing>")
        if not str(account_id).startswith("synthetic_account_"):
            failures.append(f"{account_id}: id must be synthetic")
        if account_id in seen:
            failures.append(f"{account_id}: duplicate id")
        seen.add(account_id)
        if len(account.get("evidenceRefs", [])) < 2:
            failures.append(f"{account_id}: at least two evidence refs required")
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

    leaked_keys = sorted(_walk_keys(data) & PROHIBITED_KEYS)
    if leaked_keys:
        failures.append(f"real-contact/commercial outcome keys prohibited: {', '.join(leaked_keys)}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures = validate(data)
    result = {
        "status": "ok" if not failures else "failed",
        "synthetic_accounts": len(data.get("syntheticAccounts", [])),
        "assignments": len(data.get("assignments", {})),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
