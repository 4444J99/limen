#!/usr/bin/env python3
"""Fail-closed integration harness for the dependency-gated PSP-C04/P05 proof package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "docs/positioning/proof/psp-c04-proof-contract.json"
FULL_HEAD = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_DEMO_KEYS = {
    "credential",
    "customer",
    "email",
    "private_path",
    "private_repository",
    "secret",
    "tasks_yaml_body",
    "token",
}


def load_contract(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("contract root must be an object")
    return data


def _expected_leaf_ids() -> list[str]:
    return [f"PSP-P05-W0{index}" for index in range(1, 7)]


def validate(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_roots = {
        "schema_version",
        "chunk_id",
        "phase_id",
        "status",
        "formalization_gate",
        "dependency_progress",
        "dependency_sources",
        "program_binding",
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

    program_binding = contract.get("program_binding")
    if not isinstance(program_binding, dict):
        errors.append("program_binding must be an object")
    else:
        if program_binding.get("source_path") != "institutio/positioning/program.yaml":
            errors.append("program binding must name the canonical manifest")
        audits = program_binding.get("leaf_audit")
        if not isinstance(audits, list):
            errors.append("program binding leaf audit must be a list")
        else:
            audited_ids = [row.get("work_id") for row in audits if isinstance(row, dict)]
            if audited_ids != _expected_leaf_ids():
                errors.append("program binding must audit PSP-P05-W01 through W06 in order")
            for row in audits:
                if not isinstance(row, dict):
                    continue
                work_id = row.get("work_id", "<unknown>")
                for field in ("outcome", "acceptance", "target_paths", "executable_artifacts", "residual_gates"):
                    if not row.get(field):
                        errors.append(f"{work_id} audit missing {field}")

    formalization = contract.get("formalization_gate")
    if not isinstance(formalization, dict):
        errors.append("formalization_gate must be an object")
    elif formalization.get("required_chunks") != ["PSP-C03"]:
        errors.append("formalization must require only PSP-C03 after PSP-P02 closure")

    progress = contract.get("dependency_progress")
    if not isinstance(progress, dict):
        errors.append("dependency_progress must be an object")
        c03: dict[str, Any] = {}
    else:
        p02 = progress.get("p02")
        if not isinstance(p02, dict) or p02.get("status") != "closed":
            errors.append("PSP-P02 must be recorded closed")
        raw_c03 = progress.get("c03")
        if not isinstance(raw_c03, dict):
            errors.append("dependency_progress.c03 must be an object")
            c03 = {}
        else:
            c03 = raw_c03
    if c03:
        if c03.get("status") != "w01_w06_closed_w07_open":
            errors.append("C03 progress status mismatch")
        if c03.get("exact_head") != "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec":
            errors.append("C03 accepted head mismatch")
        if c03.get("closed_leaves") != [f"PSP-P03-W0{index}" for index in range(1, 7)]:
            errors.append("C03 closed leaves must be W01-W06")
        sole_unsatisfied = c03.get("sole_unsatisfied_leaf")
        if not isinstance(sole_unsatisfied, dict):
            errors.append("C03 sole_unsatisfied_leaf must be an object")
        else:
            if sole_unsatisfied.get("work_id") != "PSP-P03-W07":
                errors.append("C03 sole unsatisfied leaf must be PSP-P03-W07")
            if sole_unsatisfied.get("outbound_from_c04") is not False:
                errors.append("C04 must not solicit W07 readers")
        receipt = c03.get("w06_receipt")
        if not isinstance(receipt, dict):
            errors.append("C03 w06_receipt must be an object")
        else:
            if receipt.get("url") != "https://github.com/organvm/limen/issues/2187#issuecomment-5271254820":
                errors.append("C03 W06 receipt URL mismatch")
            if receipt.get("sha256") != "260081dfbffc75d55824c0e6ed7d7718a7e397763afb689c94d2230963d79617":
                errors.append("C03 W06 receipt SHA mismatch")

    dependencies = contract.get("dependency_sources", [])
    if not isinstance(dependencies, list):
        errors.append("dependency_sources must be a list")
        dependencies = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            errors.append("dependency source must be an object")
            continue
        dependency_id = dependency.get("id", "<unknown>")
        exact_head = dependency.get("exact_head")
        if not isinstance(exact_head, str) or not FULL_HEAD.fullmatch(exact_head):
            errors.append(f"dependency {dependency_id} requires a full exact head")
        if dependency.get("integration") != "exact_committed_head_only":
            errors.append(f"dependency {dependency_id} must integrate exact committed heads only")
        if not dependency.get("required_path"):
            errors.append(f"dependency {dependency_id} requires a source path")
    c03_dependency = next(
        (dependency for dependency in dependencies if dependency.get("id") == "c03_identity_offers"),
        {},
    )
    if c03_dependency.get("exact_head") != c03.get("exact_head"):
        errors.append("C03 dependency source must match accepted progress head")

    sources = contract.get("sources", [])
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []
    source_ids = {source.get("id") for source in sources if isinstance(source, dict)}
    for source in sources:
        if not isinstance(source, dict):
            errors.append("source must be an object")
            continue
        if not source.get("observed_at"):
            errors.append(f"source {source.get('id', '<unknown>')} has no observation date")
        if not source.get("max_age_days"):
            errors.append(f"source {source.get('id', '<unknown>')} has no freshness budget")

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

    if flagship_ids != {"limen", "public_records", "ai_chat_exporter"}:
        errors.append("flagship set must be Limen, public_records, and ai_chat_exporter")

    withheld = " ".join(contract.get("claim_policy", {}).get("withheld_classes", [])).lower()
    for term in ("adoption", "revenue", "ranking", "percentile", "private"):
        if term not in withheld:
            errors.append(f"withheld classes must cover {term}")

    reproduction = contract.get("cost_failure_reproduction", {})
    if reproduction.get("status") != "executable_synthetic_fixture_only":
        errors.append("cost/failure reproduction must be executable with synthetic fixtures only")
    if not reproduction.get("runner") or not reproduction.get("fixture"):
        errors.append("cost/failure reproduction requires runner and fixture")

    receipt_plan = contract.get("exact_head_receipt_plan", {})
    if not receipt_plan.get("runner") or not receipt_plan.get("request_schema"):
        errors.append("exact-head receipt plan requires an executable runner and request schema")

    demo = contract.get("synthetic_architecture_demo", {})
    if demo.get("status") != "contract_only_no_ui" or not demo.get("prohibited_inputs"):
        errors.append("architecture demo must remain contract-only with prohibited inputs")
    if not demo.get("fixture") or not demo.get("validator_mode"):
        errors.append("architecture demo requires a synthetic fixture and validator mode")

    validation = contract.get("external_validation", {})
    if validation.get("status") != "rubric_only_no_outreach":
        errors.append("external validation must remain rubric-only/no-outreach")
    if validation.get("human_gate") != "HG-PUBLICATION-SEND":
        errors.append("external validation must retain HG-PUBLICATION-SEND")
    return errors


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def source_freshness(contract: dict[str, Any], as_of: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in contract.get("sources", []):
        observed = _parse_date(source["observed_at"])
        age_days = (as_of - observed).days
        declared = source.get("status")
        fresh_by_age = 0 <= age_days <= int(source["max_age_days"])
        current = declared == "current" and fresh_by_age
        rows.append(
            {
                "source_id": source["id"],
                "observed_at": source["observed_at"],
                "age_days": age_days,
                "max_age_days": source["max_age_days"],
                "declared_status": declared,
                "fresh_by_age": fresh_by_age,
                "current": current,
                "action": "eligible" if current else "refresh_or_withhold",
            }
        )
    return rows


def resolve_dependency_sources(contract: dict[str, Any], repository: Path = ROOT) -> list[dict[str, Any]]:
    """Resolve pinned dependency files directly from Git objects without merging branches."""
    rows: list[dict[str, Any]] = []
    for dependency in contract.get("dependency_sources", []):
        source_spec = f"{dependency['exact_head']}:{dependency['required_path']}"
        completed = subprocess.run(
            ["git", "show", source_spec],
            cwd=repository,
            check=False,
            capture_output=True,
        )
        if completed.returncode:
            rows.append(
                {
                    "source_id": dependency["id"],
                    "exact_head": dependency["exact_head"],
                    "path": dependency["required_path"],
                    "resolved": False,
                    "reason": "missing_exact_head_object_or_path",
                }
            )
            continue
        blob = subprocess.run(
            ["git", "rev-parse", f"{source_spec}^{{blob}}"],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
        rows.append(
            {
                "source_id": dependency["id"],
                "exact_head": dependency["exact_head"],
                "path": dependency["required_path"],
                "resolved": True,
                "blob": blob.stdout.strip() if blob.returncode == 0 else None,
                "sha256": hashlib.sha256(completed.stdout).hexdigest(),
                "bytes": len(completed.stdout),
            }
        )
    return rows


def resolve_claims(
    contract: dict[str, Any],
    *,
    as_of: date | None = None,
    dependency_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Resolve candidate claims to dated sources without promoting them."""
    as_of = as_of or datetime.now(timezone.utc).date()
    sources = {source["id"]: source for source in contract.get("sources", [])}
    freshness = {row["source_id"]: row for row in source_freshness(contract, as_of)}
    dependency_ok = all(row.get("resolved") for row in dependency_rows or [])
    publishable_statuses = set(contract.get("claim_policy", {}).get("publishable_statuses", []))
    resolved: list[dict[str, Any]] = []
    for flagship in contract.get("flagships", []):
        source_rows = [sources[source_id] for source_id in flagship.get("required_source_ids", []) if source_id in sources]
        current_sources = bool(source_rows) and all(freshness[row["id"]]["current"] for row in source_rows)
        publishable = flagship.get("status") in publishable_statuses and current_sources and dependency_ok
        reasons: list[str] = []
        if flagship.get("status") not in publishable_statuses:
            reasons.append("claim_not_ratified")
        if not current_sources:
            reasons.append("source_refresh_required")
        if dependency_rows is not None and not dependency_ok:
            reasons.append("dependency_source_unresolved")
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
                "reason_codes": reasons,
                "action": "eligible_for_surface_audit" if publishable else "withhold_until_refresh_and_ratification",
            }
        )
    return resolved


def build_surface_audit_skeleton(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Create the complete surface-by-claim denominator without touching public copy."""
    rows: list[dict[str, Any]] = []
    claims = resolve_claims(contract)
    for surface in contract.get("surface_audit_model", {}).get("surfaces", []):
        for claim in claims:
            rows.append(
                {
                    "surface": surface,
                    "claim_id": claim["claim_id"],
                    "presence": "not_audited",
                    "source_ids": claim["source_ids"],
                    "observed_at": claim["observation_dates"],
                    "status": "preflight_pending",
                    "disclosure_level": claim["max_disclosure"],
                    "canonical_or_drift": "not_audited",
                    "contains_private_material": None,
                    "action": claim["action"],
                }
            )
    return rows


def audit_surface_manifest(contract: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    expected = {
        (row["surface"], row["claim_id"])
        for row in build_surface_audit_skeleton(contract)
    }
    supplied_rows = manifest.get("rows") if isinstance(manifest, dict) else None
    errors: list[str] = []
    if not isinstance(supplied_rows, list):
        return {"status": "fail", "errors": ["surface manifest rows must be a list"], "coverage": {}}
    supplied: set[tuple[str, str]] = set()
    for row in supplied_rows:
        if not isinstance(row, dict):
            errors.append("surface row must be an object")
            continue
        key = (str(row.get("surface")), str(row.get("claim_id")))
        if key in supplied:
            errors.append(f"duplicate surface cell: {key[0]} / {key[1]}")
        supplied.add(key)
        if row.get("contains_private_material") is not False:
            errors.append(f"private material not disproven: {key[0]} / {key[1]}")
        if row.get("presence") not in {"present", "absent"}:
            errors.append(f"surface presence unresolved: {key[0]} / {key[1]}")
        if row.get("presence") == "present":
            if row.get("canonical_or_drift") not in {"canonical", "drift"}:
                errors.append(f"drift verdict missing: {key[0]} / {key[1]}")
            if not row.get("observed_at"):
                errors.append(f"observation date missing: {key[0]} / {key[1]}")
            if row.get("status") in {"unsupported", "contradictory", "private", "stale"}:
                errors.append(f"unsafe material claim: {key[0]} / {key[1]}")
    missing = sorted(expected - supplied)
    unexpected = sorted(supplied - expected)
    if missing:
        errors.append(f"missing surface cells: {len(missing)}")
    if unexpected:
        errors.append(f"unexpected surface cells: {len(unexpected)}")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "coverage": {
            "expected": len(expected),
            "supplied": len(supplied & expected),
            "missing": [f"{surface}:{claim}" for surface, claim in missing],
            "unexpected": [f"{surface}:{claim}" for surface, claim in unexpected],
        },
    }


def validate_demo_fixture(contract: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if fixture.get("synthetic_only") is not True:
        errors.append("demo fixture must declare synthetic_only true")
    records = fixture.get("records")
    if not isinstance(records, list):
        return {"status": "fail", "errors": [*errors, "demo records must be a list"]}
    record_types = {record.get("type") for record in records if isinstance(record, dict)}
    required = set(contract.get("synthetic_architecture_demo", {}).get("required_record_types", []))
    missing = sorted(required - record_types)
    if missing:
        errors.append(f"demo missing record types: {', '.join(missing)}")
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"demo record {index} must be an object")
            continue
        forbidden = sorted(FORBIDDEN_DEMO_KEYS & set(record))
        if forbidden:
            errors.append(f"demo record {index} contains forbidden keys: {', '.join(forbidden)}")
        if record.get("synthetic") is not True:
            errors.append(f"demo record {index} must be marked synthetic")
    return {"status": "pass" if not errors else "fail", "errors": errors, "record_count": len(records)}


def validate_external_objects(contract: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if payload.get("outreach_performed") is not False:
        errors.append("preflight payload must prove no outreach")
    objects = payload.get("objects")
    if not isinstance(objects, list):
        return {"status": "fail", "errors": [*errors, "external validation objects must be a list"]}
    required = set(contract.get("external_validation", {}).get("minimum_fields", []))
    for index, row in enumerate(objects):
        if not isinstance(row, dict):
            errors.append(f"validation object {index} must be an object")
            continue
        missing = sorted(field for field in required if field not in row)
        if missing:
            errors.append(f"validation object {index} missing: {', '.join(missing)}")
        if row.get("consent status") not in {"public_consented", "withdrawn"}:
            errors.append(f"validation object {index} has no public consent disposition")
    return {"status": "pass" if not errors else "fail", "errors": errors, "object_count": len(objects)}


def formalization_readiness(
    contract: dict[str, Any],
    closure_receipt: dict[str, Any] | None = None,
    repository: Path = ROOT,
) -> dict[str, Any]:
    accepted_head = contract.get("dependency_progress", {}).get("c03", {}).get("exact_head")
    residual = ["PSP-P03-W07 genuine five-reader receipt", "PSP-C03 formal closure predicates"]
    receipt_errors: list[str] = []
    if closure_receipt is not None:
        if closure_receipt.get("chunk_id") != "PSP-C03":
            receipt_errors.append("closure receipt chunk must be PSP-C03")
        if closure_receipt.get("status") != "pass":
            receipt_errors.append("closure receipt status must be pass")
        final_head = closure_receipt.get("exact_head")
        if not isinstance(final_head, str) or not FULL_HEAD.fullmatch(final_head):
            receipt_errors.append("closure receipt requires a full exact head")
        else:
            ancestry = subprocess.run(
                ["git", "merge-base", "--is-ancestor", str(accepted_head), final_head],
                cwd=repository,
                check=False,
                capture_output=True,
            )
            if ancestry.returncode:
                receipt_errors.append("final C03 head is not a locally proven descendant of the accepted head")
        phases = closure_receipt.get("phase_predicates")
        if not isinstance(phases, dict) or any(phases.get(phase) != "pass" for phase in ("PSP-P03", "PSP-P04")):
            receipt_errors.append("PSP-P03 and PSP-P04 phase predicates must both pass")
        w07 = closure_receipt.get("w07_receipt")
        if not isinstance(w07, dict) or not w07.get("url") or not w07.get("sha256"):
            receipt_errors.append("closure receipt requires the W07 URL and digest")
        if not receipt_errors:
            residual = []
    dependency_rows = resolve_dependency_sources(contract, repository)
    unresolved_sources = [row["source_id"] for row in dependency_rows if not row.get("resolved")]
    if unresolved_sources:
        receipt_errors.append(f"unresolved pinned sources: {', '.join(unresolved_sources)}")
    ready = closure_receipt is not None and not receipt_errors and not residual
    return {
        "status": "ready_for_formal_c04_activation" if ready else "PREPARED/PREFLIGHT",
        "ready": ready,
        "accepted_c03_head": accepted_head,
        "residual_gates": residual,
        "errors": receipt_errors,
        "dependency_sources": dependency_rows,
        "automatic_actions": contract.get("formalization_gate", {}).get("automatic_after_dependencies", []) if ready else [],
        "prohibited_actions": contract.get("formalization_gate", {}).get("never_automatic", []),
    }


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--mode",
        choices=(
            "validate",
            "resolve",
            "surface-audit",
            "dependency-sources",
            "freshness",
            "demo",
            "external-validation",
            "formalization",
        ),
        default="validate",
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    contract = load_contract(args.contract)
    errors = validate(contract)
    result: dict[str, Any] = {
        "contract": str(args.contract),
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }
    if not errors:
        as_of = args.as_of or datetime.now(timezone.utc).date()
        if args.mode == "dependency-sources":
            result["sources"] = resolve_dependency_sources(contract)
            if not all(row["resolved"] for row in result["sources"]):
                result["status"] = "fail"
        elif args.mode == "freshness":
            result["sources"] = source_freshness(contract, as_of)
        elif args.mode == "resolve":
            dependency_rows = resolve_dependency_sources(contract)
            result["dependency_sources"] = dependency_rows
            result["claims"] = resolve_claims(contract, as_of=as_of, dependency_rows=dependency_rows)
        elif args.mode == "surface-audit":
            payload = _load_optional_json(args.input)
            if payload is None:
                result["rows"] = build_surface_audit_skeleton(contract)
            else:
                result["audit"] = audit_surface_manifest(contract, payload)
                result["status"] = result["audit"]["status"]
        elif args.mode == "demo":
            payload = _load_optional_json(args.input)
            if payload is None:
                raise ValueError("--mode demo requires --input")
            result["demo"] = validate_demo_fixture(contract, payload)
            result["status"] = result["demo"]["status"]
        elif args.mode == "external-validation":
            payload = _load_optional_json(args.input)
            if payload is None:
                raise ValueError("--mode external-validation requires --input")
            result["validation"] = validate_external_objects(contract, payload)
            result["status"] = result["validation"]["status"]
        elif args.mode == "formalization":
            payload = _load_optional_json(args.input)
            result["formalization"] = formalization_readiness(contract, payload)
    print(json.dumps(result, indent=2) if args.json else result["status"].upper())
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
