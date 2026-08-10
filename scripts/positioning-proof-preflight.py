#!/usr/bin/env python3
"""Validate the dependency-blocked PSP-C04/P05 proof contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "docs/positioning/proof/psp-c04-proof-contract.json"


def load_contract(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("contract root must be an object")
    return data


def validate(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_roots = {
        "schema_version",
        "chunk_id",
        "phase_id",
        "status",
        "formalization_gate",
        "dependency_sources",
        "claim_policy",
        "flagships",
        "sources",
        "surface_audit_model",
        "cost_failure_reproduction",
        "exact_head_receipt_plan",
        "synthetic_architecture_demo",
        "external_validation",
    }
    missing = sorted(required_roots - contract.keys())
    if missing:
        errors.append(f"missing root fields: {', '.join(missing)}")
    if contract.get("status") != "PREPARED/PREFLIGHT":
        errors.append("status must remain PREPARED/PREFLIGHT")

    formalization = contract.get("formalization_gate", {})
    if set(formalization.get("required_chunks", [])) != {"PSP-C02", "PSP-C03"}:
        errors.append("formalization requires PSP-C02 and PSP-C03")

    dependencies = contract.get("dependency_sources", [])
    for dependency in dependencies:
        dependency_id = dependency.get("id", "<unknown>")
        exact_head = dependency.get("exact_head")
        if not isinstance(exact_head, str) or len(exact_head) != 40:
            errors.append(f"dependency {dependency_id} requires a full exact head")
        if dependency.get("integration") != "exact_committed_head_only":
            errors.append(f"dependency {dependency_id} must integrate exact committed heads only")

    sources = contract.get("sources", [])
    source_ids = {source.get("id") for source in sources if isinstance(source, dict)}
    for source in sources:
        if not source.get("observed_at"):
            errors.append(f"source {source.get('id', '<unknown>')} has no observation date")

    flagship_ids: set[str] = set()
    for flagship in contract.get("flagships", []):
        flagship_id = flagship.get("id")
        if not flagship_id:
            errors.append("flagship missing id")
            continue
        if flagship_id in flagship_ids:
            errors.append(f"duplicate flagship id: {flagship_id}")
        flagship_ids.add(flagship_id)
        if flagship.get("status") != "candidate":
            errors.append(f"flagship {flagship_id} must remain candidate in preflight")
        missing_sources = sorted(set(flagship.get("required_source_ids", [])) - source_ids)
        if missing_sources:
            errors.append(f"flagship {flagship_id} has unresolved sources: {', '.join(missing_sources)}")
        if not flagship.get("limitations"):
            errors.append(f"flagship {flagship_id} requires limitations")

    expected_flagships = {"limen", "public_records", "ai_chat_exporter"}
    if flagship_ids != expected_flagships:
        errors.append("flagship set must be Limen, public_records, and ai_chat_exporter")

    withheld = " ".join(contract.get("claim_policy", {}).get("withheld_classes", [])).lower()
    for term in ("adoption", "revenue", "ranking", "percentile", "private"):
        if term not in withheld:
            errors.append(f"withheld classes must cover {term}")

    demo = contract.get("synthetic_architecture_demo", {})
    if demo.get("status") != "contract_only_no_ui" or not demo.get("prohibited_inputs"):
        errors.append("architecture demo must remain contract-only with prohibited inputs")

    validation = contract.get("external_validation", {})
    if validation.get("status") != "rubric_only_no_outreach":
        errors.append("external validation must remain rubric-only/no-outreach")
    if validation.get("human_gate") != "HG-PUBLICATION-SEND":
        errors.append("external validation must retain HG-PUBLICATION-SEND")
    return errors


def resolve_claims(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve candidate claims to their source rows without promoting them."""
    sources = {source["id"]: source for source in contract.get("sources", [])}
    publishable_statuses = set(contract.get("claim_policy", {}).get("publishable_statuses", []))
    resolved: list[dict[str, Any]] = []
    for flagship in contract.get("flagships", []):
        source_rows = [sources[source_id] for source_id in flagship.get("required_source_ids", []) if source_id in sources]
        current_sources = bool(source_rows) and all(row.get("status") == "current" for row in source_rows)
        publishable = flagship.get("status") in publishable_statuses and current_sources
        resolved.append(
            {
                "claim_id": flagship["id"],
                "candidate_claim": flagship["candidate_claim"],
                "source_ids": [row["id"] for row in source_rows],
                "observation_dates": sorted({row["observed_at"] for row in source_rows}),
                "status": flagship["status"],
                "max_disclosure": flagship["max_disclosure"],
                "limitations": flagship["limitations"],
                "publishable": publishable,
                "action": "eligible_for_surface_audit" if publishable else "withhold_until_refresh_and_ratification",
            }
        )
    return resolved


def build_surface_audit_skeleton(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Create the complete preflight surface-by-claim denominator."""
    rows: list[dict[str, Any]] = []
    claims = resolve_claims(contract)
    for surface in contract.get("surface_audit_model", {}).get("surfaces", []):
        for claim in claims:
            rows.append(
                {
                    "surface": surface,
                    "claim_id": claim["claim_id"],
                    "source_ids": claim["source_ids"],
                    "observed_at": claim["observation_dates"],
                    "status": "preflight_pending",
                    "disclosure_level": claim["max_disclosure"],
                    "canonical_or_drift": "not_audited",
                    "action": claim["action"],
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--mode", choices=("validate", "resolve", "surface-audit"), default="validate")
    args = parser.parse_args()
    contract = load_contract(args.contract)
    errors = validate(contract)
    result: dict[str, Any] = {"contract": str(args.contract), "status": "pass" if not errors else "fail", "errors": errors}
    if not errors and args.mode == "resolve":
        result["claims"] = resolve_claims(contract)
    if not errors and args.mode == "surface-audit":
        result["rows"] = build_surface_audit_skeleton(contract)
    print(json.dumps(result, indent=2) if args.json else result["status"].upper())
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
