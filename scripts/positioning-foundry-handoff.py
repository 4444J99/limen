#!/usr/bin/env python3
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/positioning/foundry/psp-c11/foundry-handoff-contract.json"
BASE_PATH = ROOT / "scripts/positioning-foundry-preflight.py"
GITVS_PATH = ROOT / "scripts/gitvs.py"
ACCESS = ROOT / "institutio/github/access.yaml"
TAX = {"infrastructure", "proof", "experiments", "products", "archives", "private_operations", "partner_work"}
ORDER = ["partner_work", "archives", "infrastructure", "proof", "products", "private_operations", "experiments"]
ROLES = {
    "portfolio_owner",
    "product_custodian",
    "operator_candidate",
    "security_data_steward",
    "qualified_counsel",
    "independent_reviewer",
}
ACTIONS = {
    "analysis": "allow",
    "operator_contact": "deny",
    "private_disclosure": "deny",
    "credentials_or_production": "deny",
    "term_selection": "deny",
    "signature_or_spend": "deny",
    "custody_or_rights_transfer": "deny",
    "publish_or_deploy": "deny",
    "observed_pilot_claim": "deny",
}
FORBIDDEN = {
    "private_repository_name",
    "private_repository_url",
    "private_description",
    "private_topics",
    "private_timestamps",
    "private_owner_identity",
    "contact_information",
    "customer_or_partner_identity",
    "customer_or_production_data",
    "credentials_or_tokens",
    "private_amounts",
    "valuation_or_equity",
    "legal_drafts",
}
TRIGGERS = {
    "evidence_floor_failed",
    "access_or_security_breach",
    "custody_or_rights_ambiguity",
    "operator_unavailable_or_breach",
    "economic_downside_failed",
}
EXPECTED_ROLLBACK_TRIGGERS = [
    {"id": "evidence_floor_failed", "decision": "park"},
    {"id": "access_or_security_breach", "decision": "terminate"},
    {"id": "custody_or_rights_ambiguity", "decision": "no_go"},
    {"id": "operator_unavailable_or_breach", "decision": "return"},
    {"id": "economic_downside_failed", "decision": "revise_or_return"},
]
STEPS = [
    "freeze_authority",
    "capture_state",
    "revoke_access",
    "rotate_credentials",
    "return_assets",
    "verify_deletion_and_custody",
    "reconcile_obligations",
    "record_disposition",
    "write_receipt",
]
EXPECTED_CONTRACT_KEYS = {
    "schema_version",
    "status",
    "source",
    "candidate_count",
    "decision",
    "authority",
    "privacy",
    "rollback",
}


def module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {path}")
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


BASE = module("psp_c11_base", BASE_PATH)
GITVS = module("psp_c11_gitvs", GITVS_PATH)


def load_json(path: Path) -> dict[str, Any]:
    def object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON member: {key}")
            value[key] = item
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_without_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors = []
    if set(contract) != EXPECTED_CONTRACT_KEYS:
        errors.append("handoff contract must use the exact public-safe root schema")
    try:
        source = contract["source"]["c02"]
        c10 = contract["source"]["c10"]
        decision_contract = contract["decision"]
        authority = contract["authority"]
        privacy = contract["privacy"]
        rollback = contract["rollback"]
        accepted = BASE.EXPECTED_C02_SOURCES["c02_estate_classification"]
        if contract["schema_version"] != "limen.psp_c11_handoff.v1" or contract["status"] != "PREPARED/PREFLIGHT":
            errors.append("contract identity drift")
        if source["url"] != accepted["url"] or source["merge_commit"] != accepted["merge_commit"]:
            errors.append("C02 classification binding drift")
        if set(source["taxonomy"]) != TAX or source["order"] != ORDER:
            errors.append("C02 taxonomy drift")
        if c10 != BASE.EXPECTED_C10_INTEGRATION:
            errors.append("C10 integrated readiness source-lock drift")
        if contract["candidate_count"] != 62:
            errors.append("candidate denominator drift")
        if (
            set(decision_contract["routes"]) != {"park", "bounded_experiment", "no_go"}
            or decision_contract["binding"] is not False
            or decision_contract["transfer_eligible"] is not False
        ):
            errors.append("decision contract drift")
        if (
            set(authority["roles"]) != ROLES
            or authority["actions"] != ACTIONS
            or authority["state"] != "no_operator_appointed_owner_custody_unchanged"
        ):
            errors.append("authority contract drift")
        if set(privacy["public_forbidden"]) != FORBIDDEN or privacy["private_classification"] != "withheld":
            errors.append("privacy contract drift")
        if rollback["triggers"] != EXPECTED_ROLLBACK_TRIGGERS or rollback["steps"] != STEPS:
            errors.append("rollback contract drift")
        if (
            rollback["synthetic_only"] is not True
            or rollback["final_custody"] != "owner_unchanged"
            or rollback["external_effects"] != []
        ):
            errors.append("rollback safety drift")
    except (KeyError, TypeError):
        errors.append("handoff contract shape invalid")
    return errors


def classify(
    row: dict[str, Any],
    contract: dict[str, Any],
    estate: dict[str, Any],
    access: dict[str, Any],
) -> dict[str, Any]:
    if row.get("visibility") == "private":
        return {
            "policy": "c02",
            "primary": None,
            "governance": None,
            "maturity": None,
            "disposition": "private_redacted",
            "relevance": "private_only",
            "comparison": "private_classification_withheld",
        }
    repository = str(row.get("repository") or "")
    archived = row.get("current_state") == "archived"
    governance = GITVS.classify_repo(
        repository,
        estate,
        {"private": False, "archived": archived, "fork": row.get("fork") is True},
    )
    if not governance:
        raise ValueError(f"{repository}: missing governance classification")
    collaboration = repository in (access.get("grants") or {})
    if collaboration:
        primary = "partner_work"
    elif archived:
        primary = "archives"
    elif governance == "conductor":
        primary = "infrastructure"
    elif governance == "portal_public":
        primary = "proof"
    else:
        primary = "products"
    evidence = set((row.get("readiness") or {}).get("evidence") or [])
    if archived:
        maturity = "archived"
    elif "pushed_within_90_days" in evidence:
        maturity = "active"
    elif "pushed_within_365_days" in evidence:
        maturity = "maintained"
    else:
        maturity = "unvalidated"
    return {
        "policy": "c02",
        "primary": primary,
        "governance": governance,
        "maturity": maturity,
        "disposition": "public_partner" if collaboration else "public_evidence",
        "relevance": ("partner_scoped" if collaboration else contract["source"]["c02"]["relevance"][primary]),
        "comparison": "aligned_product" if primary == "products" else f"candidate_primary_{primary}",
    }


def decision(row: dict[str, Any], classification: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    demand = row.get("demand") or {}
    readiness = row.get("readiness") or {}
    economics = row.get("economics") or {}
    return {
        "candidate_id": row.get("candidate_id"),
        "visibility": row.get("visibility"),
        "classification": classification,
        "demand": {
            "score": demand.get("score"),
            "tier": demand.get("tier"),
            "evidence": demand.get("evidence"),
        },
        "readiness": {
            "score": readiness.get("metadata_screen_score"),
            "band": readiness.get("band"),
            "custody_risk": readiness.get("custody_risk"),
        },
        "economics": economics.get("status"),
        "decision": ("bounded_experiment" if row.get("preflight_disposition") == "experiment" else "park"),
        "basis": [
            classification["comparison"],
            f"demand:{demand.get('tier')}",
            f"readiness:{readiness.get('band')}",
            "transfer_floor_not_met",
        ],
        "next_action": demand.get("next_experiment"),
        "no_go": copy.deepcopy(contract["decision"]["no_go"]),
        "gates": copy.deepcopy(contract["decision"]["gates"]),
        "authority_state": "owner_custody_unchanged",
        "binding": False,
        "transfer_eligible": False,
        "external_effects": [],
    }


def rollback_drills(contract: dict[str, Any]) -> dict[str, Any]:
    exact_contract = (
        contract.get("rollback", {}).get("triggers") == EXPECTED_ROLLBACK_TRIGGERS
        and contract.get("rollback", {}).get("steps") == STEPS
    )
    rows = [
        {
            "id": item["id"],
            "decision": item["decision"],
            "steps": copy.deepcopy(contract["rollback"]["steps"]),
            "external_effects": [],
            "final_custody": "owner_unchanged",
            "pass": item == expected,
        }
        for item, expected in zip(contract["rollback"]["triggers"], EXPECTED_ROLLBACK_TRIGGERS, strict=False)
    ]
    return {
        "schema_version": "limen.psp_c11_rollback_drills.v1",
        "status": "pass" if exact_contract and len(rows) == 5 and all(row["pass"] for row in rows) else "fail",
        "synthetic_only": True,
        "human_acceptance_simulated": False,
        "observed_pilot": False,
        "drills": rows,
        "external_effects": [],
        "final_custody": "owner_unchanged",
    }


def build_package(contract: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    estate = GITVS.load_estate()
    access = load_yaml(ACCESS)
    classifications = []
    records = []
    for row in snapshot.get("candidates") or []:
        value = classify(row, contract, estate, access)
        classifications.append(
            {
                "candidate_id": row.get("candidate_id"),
                "visibility": row.get("visibility"),
                "repository": row.get("repository"),
                "classification": value,
            }
        )
        records.append(decision(row, value, contract))
    counts = collections.Counter(
        item["classification"]["primary"] for item in classifications if item["visibility"] == "public"
    )
    routes = collections.Counter(item["decision"] for item in records)
    return {
        "schema_version": "limen.psp_c11_handoff_package.v1",
        "status": "PREPARED/PREFLIGHT",
        "snapshot_identity": snapshot["candidate_denominator"]["identity_sha256"],
        "source_lock": {
            "c02_merge_commit": contract["source"]["c02"]["merge_commit"],
            "c10": copy.deepcopy(contract["source"]["c10"]),
        },
        "classification": {
            "policy_commit": contract["source"]["c02"]["merge_commit"],
            "count": len(classifications),
            "public_primary": dict(sorted(counts.items())),
            "private_withheld": sum(item["visibility"] == "private" for item in classifications),
            "records": classifications,
            "digest": digest(classifications),
        },
        "decisions": records,
        "decision_summary": {
            "count": len(records),
            "routes": dict(sorted(routes.items())),
            "binding": 0,
            "transfer_eligible": 0,
            "digest": digest(records),
        },
        "rollback": rollback_drills(contract),
        "external_effects": [],
    }


def validate_package(package: dict[str, Any], contract: dict[str, Any], snapshot: dict[str, Any]) -> list[str]:
    errors = []
    classifications = package.get("classification", {}).get("records") or []
    records = package.get("decisions") or []
    expected = {item.get("candidate_id") for item in snapshot.get("candidates") or []}
    if len(classifications) != 62 or len(records) != 62:
        errors.append("generated coverage incomplete")
    if {item.get("candidate_id") for item in classifications} != expected or {
        item.get("candidate_id") for item in records
    } != expected:
        errors.append("candidate identity coverage drift")
    by_id = {item["candidate_id"]: item for item in classifications}
    for source in snapshot.get("candidates") or []:
        row = by_id.get(source.get("candidate_id"), {})
        value = row.get("classification") or {}
        if source.get("visibility") == "private":
            if (
                row.get("repository") is not None
                or value.get("primary") is not None
                or value.get("comparison") != "private_classification_withheld"
            ):
                errors.append(f"{source.get('candidate_id')}: private detail exposed")
        elif value.get("primary") not in TAX:
            errors.append(f"{source.get('candidate_id')}: invalid C02 classification")
    fields = set(contract["decision"]["fields"])
    for row in records:
        candidate_id = row.get("candidate_id")
        if set(row) != fields:
            errors.append(f"{candidate_id}: decision shape drift")
        if row.get("binding") is not False or row.get("transfer_eligible") is not False:
            errors.append(f"{candidate_id}: binding or transfer overclaim")
        if row.get("authority_state") != "owner_custody_unchanged" or row.get("external_effects") != []:
            errors.append(f"{candidate_id}: authority or external-effect drift")
        if row.get("no_go") != contract["decision"]["no_go"] or row.get("gates") != contract["decision"]["gates"]:
            errors.append(f"{candidate_id}: no-go or gate drift")
    if package.get("classification", {}).get("digest") != digest(classifications):
        errors.append("classification digest drift")
    if package.get("source_lock") != {
        "c02_merge_commit": contract["source"]["c02"]["merge_commit"],
        "c10": contract["source"]["c10"],
    }:
        errors.append("package source-lock drift")
    if package.get("decision_summary", {}).get("digest") != digest(records):
        errors.append("decision digest drift")
    if (
        package.get("decision_summary", {}).get("binding") != 0
        or package.get("decision_summary", {}).get("transfer_eligible") != 0
    ):
        errors.append("decision summary overclaim")
    rollback = package.get("rollback") or {}
    if (
        rollback.get("status") != "pass"
        or len(rollback.get("drills") or []) != 5
        or rollback.get("external_effects") != []
        or rollback.get("final_custody") != "owner_unchanged"
    ):
        errors.append("rollback drills failed")
    if package.get("external_effects") != []:
        errors.append("package recorded external effects")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--records", action="store_true")
    parser.add_argument("--drills", action="store_true")
    args = parser.parse_args()
    try:
        contract = load_json(args.contract)
        base = BASE.load_json(BASE.CONTRACT)
        snapshot = BASE.load_json(BASE.SNAPSHOT)
        errors = validate_contract(contract)
        errors.extend(BASE.validate_contract(base))
        errors.extend(BASE.validate_snapshot(snapshot, base))
        package = build_package(contract, snapshot)
        errors.extend(validate_package(package, contract, snapshot))
        if args.drills:
            output = package["rollback"]
        elif args.records:
            output = {
                **package,
                "status": "pass" if not errors else "fail",
                "errors": errors,
            }
        else:
            output = {
                "schema_version": "limen.psp_c11_handoff_validation.v1",
                "status": "pass" if not errors else "fail",
                "classification": {key: value for key, value in package["classification"].items() if key != "records"},
                "decision_summary": package["decision_summary"],
                "rollback": package["rollback"],
                "external_effects": [],
                "errors": errors,
            }
        if errors and args.drills:
            output = {**output, "status": "fail", "errors": errors}
        print(json.dumps(output, indent=2, sort_keys=True) if args.json else output["status"].upper())
        return 0 if output["status"] == "pass" else 1
    except Exception as exc:
        output = {"status": "fail", "errors": [str(exc)]}
        print(json.dumps(output, indent=2) if args.json else f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
