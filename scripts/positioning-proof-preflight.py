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
P02_ACCEPTED_HEAD = "8faa5fb9899231ebf5f87e78bb171544c11b79d7"
C03_CURRENT_HEAD = "b6af8086c9050634313f519c29a6dfcb922c3721"
C03_ACCEPTED_P03_ANCESTOR = "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec"
CANONICAL_PORTFOLIO = {"slug": "organvm-vii-kerygma/portfolio", "repository_id": 1155412125}
EXPECTED_FLAGSHIPS = {
    "limen": {
        "claim_id": "C02-PROOF-LIMEN",
        "candidate_claim": "Limen demonstrates governed multi-agent delivery with public operating, failure, and verification receipts.",
        "evidence_wording": "Limen is a live orchestration and governance system, operating continuously in production in its owner's environment since May 2026.",
        "accepted_source_status": "verified",
    },
    "public_records": {
        "claim_id": "C02-PROOF-PUBLIC-RECORDS",
        "candidate_claim": "Four implemented state collectors (CA, TX, FL, and NY) sit on a broader architecture.",
        "evidence_wording": "Four implemented state collectors on a fifty-state architecture",
        "accepted_source_status": "repository_asserted_with_public_anchor",
    },
    "ai_chat_exporter": {
        "claim_id": "C02-PROOF-AI-CHAT-EXPORTER",
        "candidate_claim": "The public AI Chat Exporter surface presents five export formats without a server dependency.",
        "evidence_wording": "The public product surface presents five export formats: Markdown, HTML, JSON, PNG, and text.",
        "accepted_source_status": "verified",
    },
}
EXPECTED_DEPENDENCY_BINDINGS = {
    "p02_live_registry": (
        P02_ACCEPTED_HEAD,
        "institutio/positioning/program.yaml",
        "de8c489667f2ad797dde60dfb84a9fa1fb4b0e16",
    ),
    "p02_flagship_selection": (
        P02_ACCEPTED_HEAD,
        "docs/positioning/flagship-proof-set.yaml",
        "5d4776efc7a811b0163cdfea5cf083409157feae",
    ),
    "p02_public_evidence": (
        P02_ACCEPTED_HEAD,
        "docs/positioning/evidence/flagship-evidence.yaml",
        "ce59d44794f44e0511436cbabbcd4fba1a938891",
    ),
    "p02_claim_policy": (
        P02_ACCEPTED_HEAD,
        "docs/positioning/program/CLAIM-CORRECTION-PROTOCOL.md",
        "57565f0d0dc72d2200b41be0e21fe6d323ec7f83",
    ),
    "p02_claims_ledger": (
        P02_ACCEPTED_HEAD,
        "docs/positioning/claims-ledger.md",
        "3e49114563075dcd6926e3b7f8fd24bf8b9c3fee",
    ),
    "c03_identity_offers": (
        C03_CURRENT_HEAD,
        "institutio/positioning/commercial-contract.yaml",
        "11ebfe5cb972c5b535059e5aa1f607ea64e90d17",
    ),
}
EXPECTED_OFFER_BINDINGS = {
    "agentic_delivery_audit": (
        "docs/positioning/offers/agentic-delivery-audit.md",
        "34bd10760afe6e8e8b778e0f6ad59c8aa1766097",
        ["L2", "L3"],
    ),
    "governance_install": (
        "docs/positioning/offers/governance-install.md",
        "2ddb46f8d2a4bc122720d4a2d890298ee1c5e380",
        ["L2", "L3"],
    ),
    "bounded_governance_retainer": (
        "docs/positioning/offers/bounded-delivery-governance-retainer.md",
        "1b46928d216fb2ed7299907a292ecc92511b0d60",
        ["L2", "L3"],
    ),
    "qualification_and_routing": (
        "docs/positioning/offers/qualification-and-routing.md",
        "1cf8bd4e42d96533973418f2de26e1aad313d205",
        ["L2", "L3"],
    ),
    "product_operating_partnership_review": (
        "docs/positioning/offers/product-operating-partnership-review.md",
        "9240e1fc1142eca6ca58d792f09581e1b514e046",
        ["L3"],
    ),
}
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
        "counts_as_closure",
        "formalization_gate",
        "dependency_progress",
        "dependency_sources",
        "commercial_artifact_set",
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
    if contract.get("counts_as_closure") is not False:
        errors.append("counts_as_closure must remain false")

    program_binding = contract.get("program_binding")
    if not isinstance(program_binding, dict):
        errors.append("program_binding must be an object")
    else:
        if program_binding.get("source_path") != "institutio/positioning/program.yaml":
            errors.append("program binding must name the canonical manifest")
        if program_binding.get("exact_head") != P02_ACCEPTED_HEAD:
            errors.append("program binding must use the accepted PSP-P02 head")
        if not FULL_HEAD.fullmatch(str(program_binding.get("expected_blob", ""))):
            errors.append("program binding requires the exact registry blob")
        if program_binding.get("canonical_portfolio") != CANONICAL_PORTFOLIO:
            errors.append("program binding must name the live canonical portfolio owner")
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
        elif p02.get("exact_head") != P02_ACCEPTED_HEAD:
            errors.append("PSP-P02 progress head mismatch")
        raw_c03 = progress.get("c03")
        if not isinstance(raw_c03, dict):
            errors.append("dependency_progress.c03 must be an object")
            c03 = {}
        else:
            c03 = raw_c03
    if c03:
        if c03.get("status") != "p03_w01_w06_closed_p04_staged_w07_open":
            errors.append("C03 progress status mismatch")
        if c03.get("exact_head") != C03_CURRENT_HEAD:
            errors.append("C03 current preflight head mismatch")
        if c03.get("accepted_p03_ancestor") != C03_ACCEPTED_P03_ANCESTOR:
            errors.append("C03 accepted P03 ancestor mismatch")
        if c03.get("closed_leaves") != [f"PSP-P03-W0{index}" for index in range(1, 7)]:
            errors.append("C03 closed leaves must be W01-W06")
        sole_unsatisfied = c03.get("sole_unsatisfied_leaf")
        if not isinstance(sole_unsatisfied, dict):
            errors.append("C03 sole_unsatisfied_leaf must be an object")
        else:
            if sole_unsatisfied.get("work_id") != "PSP-P03-W07":
                errors.append("C03 sole unsatisfied leaf must be PSP-P03-W07")
            if sole_unsatisfied.get("required_independent_readers") != 5:
                errors.append("C03 W07 must require five independent readers")
            if sole_unsatisfied.get("current_valid_readers") != 0:
                errors.append("C03 W07 valid-reader count must remain zero until genuine receipts exist")
            if sole_unsatisfied.get("synthetic_or_model_readers_allowed") is not False:
                errors.append("C03 W07 must reject synthetic or model readers")
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
    dependency_ids = {dependency.get("id") for dependency in dependencies if isinstance(dependency, dict)}
    if dependency_ids != set(EXPECTED_DEPENDENCY_BINDINGS):
        errors.append("dependency sources must bind the complete accepted P02 and current C03 artifact set")
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            errors.append("dependency source must be an object")
            continue
        dependency_id = dependency.get("id", "<unknown>")
        exact_head = dependency.get("exact_head")
        if not isinstance(exact_head, str) or not FULL_HEAD.fullmatch(exact_head):
            errors.append(f"dependency {dependency_id} requires a full exact head")
        expected_blob = dependency.get("expected_blob")
        if not isinstance(expected_blob, str) or not FULL_HEAD.fullmatch(expected_blob):
            errors.append(f"dependency {dependency_id} requires a full expected blob")
        if dependency.get("integration") != "exact_committed_head_only":
            errors.append(f"dependency {dependency_id} must integrate exact committed heads only")
        if not dependency.get("required_path"):
            errors.append(f"dependency {dependency_id} requires a source path")
    c03_dependency = next(
        (dependency for dependency in dependencies if dependency.get("id") == "c03_identity_offers"),
        {},
    )
    if c03_dependency.get("exact_head") != c03.get("exact_head"):
        errors.append("C03 dependency source must match current progress head")
    for dependency in dependencies:
        dependency_id = dependency.get("id", "<unknown>")
        expected_binding = EXPECTED_DEPENDENCY_BINDINGS.get(dependency_id)
        if (
            expected_binding
            and (
                dependency.get("exact_head"),
                dependency.get("required_path"),
                dependency.get("expected_blob"),
            )
            != expected_binding
        ):
            errors.append(f"dependency {dependency_id} is not pinned to its accepted upstream object")

    commercial_artifacts = contract.get("commercial_artifact_set")
    if not isinstance(commercial_artifacts, dict):
        errors.append("commercial_artifact_set must be an object")
    else:
        if commercial_artifacts.get("source_head") != C03_CURRENT_HEAD:
            errors.append("commercial artifact set must use the current C03 preflight head")
        artifacts = commercial_artifacts.get("artifacts")
        if not isinstance(artifacts, list):
            errors.append("commercial artifact set must contain an artifacts list")
        else:
            artifact_ids = {artifact.get("id") for artifact in artifacts if isinstance(artifact, dict)}
            if artifact_ids != set(EXPECTED_OFFER_BINDINGS):
                errors.append("commercial artifact set must bind the five generated offers")
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    errors.append("commercial artifact must be an object")
                    continue
                artifact_id = artifact.get("id", "<unknown>")
                if not artifact.get("path"):
                    errors.append(f"commercial artifact {artifact_id} requires a path")
                if not FULL_HEAD.fullmatch(str(artifact.get("expected_blob", ""))):
                    errors.append(f"commercial artifact {artifact_id} requires a full expected blob")
                if "L1" in artifact.get("levels", []):
                    errors.append(f"commercial artifact {artifact_id} must not expose an L1 offer payload")
                expected_offer = EXPECTED_OFFER_BINDINGS.get(artifact_id)
                if (
                    expected_offer
                    and (
                        artifact.get("path"),
                        artifact.get("expected_blob"),
                        artifact.get("levels"),
                    )
                    != expected_offer
                ):
                    errors.append(f"commercial artifact {artifact_id} is not pinned to the accepted C03 object")
            partnership = next(
                (artifact for artifact in artifacts if artifact.get("id") == "product_operating_partnership_review"),
                {},
            )
            if partnership.get("levels") != ["L3"] or partnership.get("public_front_door") is not False:
                errors.append("product operating partnership review must remain L3-only and off the public front door")

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
        expected_flagship = EXPECTED_FLAGSHIPS.get(flagship_id)
        if expected_flagship:
            for field, expected_value in expected_flagship.items():
                if flagship.get(field) != expected_value:
                    errors.append(f"flagship {flagship_id} has stale {field}")
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
                    "expected_blob": dependency["expected_blob"],
                    "resolved": False,
                    "reason": "missing_exact_head_object_or_path",
                }
            )
            continue
        blob = subprocess.run(
            ["git", "rev-parse", source_spec],
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
        )
        actual_blob = blob.stdout.strip() if blob.returncode == 0 else None
        blob_match = actual_blob == dependency["expected_blob"]
        rows.append(
            {
                "source_id": dependency["id"],
                "exact_head": dependency["exact_head"],
                "path": dependency["required_path"],
                "expected_blob": dependency["expected_blob"],
                "resolved": blob_match,
                "reason": "resolved" if blob_match else "blob_mismatch",
                "blob": actual_blob,
                "blob_match": blob_match,
                "sha256": hashlib.sha256(completed.stdout).hexdigest(),
                "bytes": len(completed.stdout),
            }
        )
    return rows


def _read_git_object(repository: Path, head: str, path: str) -> tuple[str | None, str | None]:
    source_spec = f"{head}:{path}"
    content = subprocess.run(
        ["git", "show", source_spec],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    blob = subprocess.run(
        ["git", "rev-parse", source_spec],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    if content.returncode or blob.returncode:
        return None, None
    return content.stdout, blob.stdout.strip()


def verify_upstream_bindings(contract: dict[str, Any], repository: Path = ROOT) -> dict[str, Any]:
    """Verify accepted registry, claim, commercial, and generated-offer objects without checkout mutation."""
    errors: list[str] = []
    checked: list[dict[str, Any]] = []
    binding = contract.get("program_binding", {})
    registry_content, registry_blob = _read_git_object(
        repository,
        str(binding.get("exact_head")),
        str(binding.get("source_path")),
    )
    if registry_blob != binding.get("expected_blob"):
        errors.append("accepted PSP-P02 registry blob mismatch")
    elif registry_content is None:
        errors.append("accepted PSP-P02 registry object is unavailable")
    else:
        required_registry_markers = (
            "canonical_slug: organvm-vii-kerygma/portfolio",
            "github_repository_id: 1155412125",
            "target_repo: organvm-vii-kerygma/portfolio",
        )
        missing_markers = [marker for marker in required_registry_markers if marker not in registry_content]
        if missing_markers:
            errors.append("accepted PSP-P02 registry does not bind the live portfolio owner")
    checked.append(
        {
            "id": "p02_live_registry",
            "head": binding.get("exact_head"),
            "path": binding.get("source_path"),
            "blob": registry_blob,
            "blob_match": registry_blob == binding.get("expected_blob"),
        }
    )

    dependencies = {row.get("id"): row for row in contract.get("dependency_sources", [])}
    claims_dependency = dependencies.get("p02_claims_ledger", {})
    ledger_content, ledger_blob = _read_git_object(
        repository,
        str(claims_dependency.get("exact_head")),
        str(claims_dependency.get("required_path")),
    )
    commercial_dependency = dependencies.get("c03_identity_offers", {})
    commercial_content, commercial_blob = _read_git_object(
        repository,
        str(commercial_dependency.get("exact_head")),
        str(commercial_dependency.get("required_path")),
    )
    checked.extend(
        [
            {
                "id": "p02_claims_ledger",
                "head": claims_dependency.get("exact_head"),
                "path": claims_dependency.get("required_path"),
                "blob": ledger_blob,
                "blob_match": ledger_blob == claims_dependency.get("expected_blob"),
            },
            {
                "id": "c03_identity_offers",
                "head": commercial_dependency.get("exact_head"),
                "path": commercial_dependency.get("required_path"),
                "blob": commercial_blob,
                "blob_match": commercial_blob == commercial_dependency.get("expected_blob"),
            },
        ]
    )
    if ledger_blob != claims_dependency.get("expected_blob") or ledger_content is None:
        errors.append("accepted PSP-P02 claims ledger binding failed")
    if commercial_blob != commercial_dependency.get("expected_blob") or commercial_content is None:
        errors.append("current C03 commercial contract binding failed")
    if ledger_content is not None and commercial_content is not None:
        for flagship in contract.get("flagships", []):
            claim_id = flagship.get("claim_id")
            if claim_id not in commercial_content:
                errors.append(f"claim {claim_id} is absent from the current C03 contract")
            if flagship.get("evidence_wording") not in ledger_content:
                errors.append(f"claim {claim_id} evidence wording is stale")
            if flagship.get("candidate_claim") not in commercial_content:
                errors.append(f"claim {claim_id} commercial wording is stale")

    artifact_set = contract.get("commercial_artifact_set", {})
    source_head = artifact_set.get("source_head")
    for artifact in artifact_set.get("artifacts", []):
        _content, actual_blob = _read_git_object(repository, str(source_head), str(artifact.get("path")))
        blob_match = actual_blob == artifact.get("expected_blob")
        checked.append(
            {
                "id": artifact.get("id"),
                "head": source_head,
                "path": artifact.get("path"),
                "blob": actual_blob,
                "blob_match": blob_match,
            }
        )
        if not blob_match:
            errors.append(f"commercial artifact {artifact.get('id')} blob mismatch")
    return {"status": "pass" if not errors else "fail", "errors": errors, "checked": checked}


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
        source_rows = [
            sources[source_id] for source_id in flagship.get("required_source_ids", []) if source_id in sources
        ]
        current_sources = bool(source_rows) and all(freshness[row["id"]]["current"] for row in source_rows)
        source_status = flagship.get("accepted_source_status")
        publishable = (
            source_status in publishable_statuses
            and current_sources
            and dependency_ok
            and contract.get("status") != "PREPARED/PREFLIGHT"
        )
        reasons: list[str] = []
        if contract.get("status") == "PREPARED/PREFLIGHT":
            reasons.append("c04_formalization_pending")
        if source_status not in publishable_statuses:
            reasons.append("source_status_not_publishable")
        if not current_sources:
            reasons.append("source_refresh_required")
        if dependency_rows is not None and not dependency_ok:
            reasons.append("dependency_source_unresolved")
        resolved.append(
            {
                "claim_id": flagship["claim_id"],
                "flagship_id": flagship["id"],
                "candidate_claim": flagship["candidate_claim"],
                "source_ids": [row["id"] for row in source_rows],
                "observation_dates": sorted({row["observed_at"] for row in source_rows}),
                "status": source_status,
                "max_disclosure": flagship["max_disclosure"],
                "limitations": flagship["limitations"],
                "publishable": publishable,
                "reason_codes": reasons,
                "action": "eligible_for_surface_audit" if publishable else "withhold_until_refresh_and_formalization",
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
    expected = {(row["surface"], row["claim_id"]) for row in build_surface_audit_skeleton(contract)}
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
    upstream_bindings = verify_upstream_bindings(contract, repository)
    receipt_errors.extend(upstream_bindings["errors"])
    if contract.get("counts_as_closure") is not False:
        receipt_errors.append("C04 preflight must not count as closure")
    ready = closure_receipt is not None and not receipt_errors and not residual
    return {
        "status": "ready_for_formal_c04_activation" if ready else "PREPARED/PREFLIGHT",
        "ready": ready,
        "accepted_c03_head": accepted_head,
        "residual_gates": residual,
        "errors": receipt_errors,
        "dependency_sources": dependency_rows,
        "upstream_bindings": upstream_bindings,
        "automatic_actions": contract.get("formalization_gate", {}).get("automatic_after_dependencies", [])
        if ready
        else [],
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
            "upstream-bindings",
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
        if args.mode == "validate":
            result["sources"] = resolve_dependency_sources(contract)
            result["upstream_bindings"] = verify_upstream_bindings(contract)
            unresolved = [row["source_id"] for row in result["sources"] if not row["resolved"]]
            if unresolved:
                result["errors"].append(f"unresolved pinned sources: {', '.join(unresolved)}")
            result["errors"].extend(result["upstream_bindings"]["errors"])
            if result["errors"]:
                result["status"] = "fail"
        elif args.mode == "dependency-sources":
            result["sources"] = resolve_dependency_sources(contract)
            if not all(row["resolved"] for row in result["sources"]):
                result["status"] = "fail"
        elif args.mode == "upstream-bindings":
            result["upstream_bindings"] = verify_upstream_bindings(contract)
            result["status"] = result["upstream_bindings"]["status"]
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
