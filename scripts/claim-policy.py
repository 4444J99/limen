#!/usr/bin/env python3
"""Fail-closed policy validation for a public positioning claim-ledger export.

The W05 ledger remains its own owner.  This module consumes its deliberately narrow,
public-safe export contract and emits only claim identifiers and policy verdicts.  It
does not fetch sources or publish, generate, or alter any public artifact.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "limen.positioning.claim-ledger-export.v1"
PUBLISHABLE = "publishable"
RFC3339_Z = "%Y-%m-%dT%H:%M:%SZ"


class ContractError(ValueError):
    """The W05 export did not satisfy the integration contract."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read claim-ledger export: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("claim-ledger export must be a JSON object")
    return value


def _parse_time(value: object, field: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be an RFC3339 UTC timestamp")
    try:
        return dt.datetime.strptime(value, RFC3339_Z).replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise ContractError(f"{field} must use YYYY-MM-DDTHH:MM:SSZ") from exc


def _claim_id(claim: dict[str, Any], index: int) -> str:
    value = claim.get("id")
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise ContractError(f"claims[{index}].id must be a lowercase public-safe identifier")
    return value


def evaluate_export(document: dict[str, Any], as_of: dt.datetime) -> dict[str, Any]:
    """Return a public-safe verdict report for a W05 ledger export.

    Expected claim fields are ``id``, ``statement``, ``publication_status``,
    ``visibility``, ``source``, and ``valid_until``.  ``source.current_sha256``
    is optional; when supplied it must equal the recorded digest.  That provides a
    deterministic source-change quarantine signal without a network dependency.
    """
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(f"schema_version must be {SCHEMA_VERSION}")
    claims = document.get("claims")
    if not isinstance(claims, list) or not claims:
        raise ContractError("claims must be a non-empty list")
    forbidden = document.get("forbidden_language", [])
    if not isinstance(forbidden, list) or not all(isinstance(item, str) and item for item in forbidden):
        raise ContractError("forbidden_language must be a list of non-empty strings")

    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict):
            raise ContractError(f"claims[{index}] must be an object")
        claim_id = _claim_id(claim, index)
        if claim_id in seen:
            raise ContractError(f"duplicate claim identifier: {claim_id}")
        seen.add(claim_id)
        reasons: list[str] = []
        statement = claim.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            reasons.append("unsupported")
            statement = ""
        if claim.get("publication_status") != PUBLISHABLE:
            reasons.append("withdrawn_or_unapproved")
        if claim.get("visibility") != "public":
            reasons.append("private_or_restricted")
        source = claim.get("source")
        if not isinstance(source, dict) or not isinstance(source.get("url"), str) or not source["url"]:
            reasons.append("unsourced")
        else:
            _parse_time(source.get("observed_at"), f"claim {claim_id} source.observed_at")
            recorded = source.get("sha256")
            current = source.get("current_sha256")
            if not isinstance(recorded, str) or not re.fullmatch(r"[a-f0-9]{64}", recorded):
                reasons.append("unsourced")
            if current is not None and current != recorded:
                reasons.append("source_changed")
        if _parse_time(claim.get("valid_until"), f"claim {claim_id} valid_until") < as_of:
            reasons.append("stale")
        if any(term.casefold() in statement.casefold() for term in forbidden):
            reasons.append("forbidden_language")
        if reasons:
            rejected.append({"claim_id": claim_id, "reasons": sorted(set(reasons))})
        else:
            accepted.append(claim_id)
    return {
        "schema_version": "limen.positioning.claim-policy-report.v1",
        "as_of": as_of.strftime(RFC3339_Z),
        "accepted_claim_ids": sorted(accepted),
        "rejected_claims": sorted(rejected, key=lambda item: item["claim_id"]),
    }


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", required=True, type=Path, help="W05 claim-ledger export JSON")
    parser.add_argument("--as-of", required=True, help="RFC3339 UTC evaluation time")
    parser.add_argument("--report", type=Path, help="optional public-safe JSON verdict path")
    parser.add_argument("--json", action="store_true", help="print the public-safe verdict report")
    args = parser.parse_args(argv)
    try:
        report = evaluate_export(_read_json(args.claims), _parse_time(args.as_of, "--as-of"))
    except ContractError as exc:
        print(f"claim-policy: FAIL: {exc}", file=sys.stderr)
        return 2
    if args.report:
        _atomic_json(args.report, report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    if report["rejected_claims"]:
        print(f"claim-policy: QUARANTINE ({len(report['rejected_claims'])} claim(s))", file=sys.stderr)
        return 1
    print(f"claim-policy: PASS ({len(report['accepted_claim_ids'])} claim(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
