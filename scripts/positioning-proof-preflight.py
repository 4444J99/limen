#!/usr/bin/env python3
"""Fail-closed integration harness for the dependency-gated PSP-C04/P05 proof package."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "docs/positioning/proof/psp-c04-proof-contract.json"
FULL_HEAD = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
W07_RECEIPT_URL = re.compile(r"^https://github\.com/organvm/limen/issues/2188#issuecomment-[0-9]+$")
PHASE_RECEIPT_URLS = {
    "PSP-P03": re.compile(r"^https://github\.com/organvm/limen/issues/2181#issuecomment-[0-9]+$"),
    "PSP-P04": re.compile(r"^https://github\.com/organvm/limen/issues/2189#issuecomment-[0-9]+$"),
}
PHASE_RECEIPT_BLOCK = re.compile(
    r"<!--\s*positioning-phase-receipt:(PSP-P\d{2})\s*-->\s*```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)
W07_VALIDATOR_PATH = "docs/positioning/program/validate_p03_w07_blinded_reader.py"
W07_WORKFLOW_PATH = "docs/positioning/program/w07_blinded_reader_workflow.py"
W07_RESPONSE_PATH = re.compile(r"^docs/receipts/positioning/psp-p03-w07-reader-responses\.json$")
W07_MEMO_PATH = re.compile(r"^docs/receipts/positioning/psp-p03-w07-decision-memo\.md$")
ARCHITECTURE_DEMO_SCHEMA = "limen.positioning_architecture_demo_fixture.v1"
COST_REVIEW_SCHEMA = "limen.positioning_cost_failure_review.v1"
INDEPENDENT_REVIEWER_CLASSES = {"independent_human", "independent_model", "consented_collaborator"}
DEMO_ROOT_FIELDS = {"schema_version", "synthetic_only", "records"}
DEMO_RECORD_FIELDS = {
    "packet": {"type", "id", "synthetic", "authority"},
    "lease": {"type", "id", "synthetic", "packet_id"},
    "execution": {"type", "id", "synthetic", "lease_id"},
    "predicate": {"type", "id", "synthetic", "execution_id", "result"},
    "receipt": {"type", "id", "synthetic", "predicate_id"},
    "failure": {"type", "id", "synthetic", "predicate_id", "reason"},
    "recovery": {"type", "id", "synthetic", "failure_id", "action"},
    "harvest": {"type", "id", "synthetic", "receipt_id", "recovery_id", "outcome"},
}
DEMO_RELATIONSHIPS = {
    ("lease", "packet_id"): "packet",
    ("execution", "lease_id"): "lease",
    ("predicate", "execution_id"): "execution",
    ("receipt", "predicate_id"): "predicate",
    ("failure", "predicate_id"): "predicate",
    ("recovery", "failure_id"): "failure",
    ("harvest", "receipt_id"): "receipt",
    ("harvest", "recovery_id"): "recovery",
}
P02_ACCEPTED_HEAD = "8faa5fb9899231ebf5f87e78bb171544c11b79d7"
C03_CURRENT_HEAD = "b6af8086c9050634313f519c29a6dfcb922c3721"
C03_MERGE_COMMIT = "8f89ad16ca1df84b00cb8227c88f368d0d64631a"
C03_ACCEPTED_P03_ANCESTOR = "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec"
CANONICAL_PORTFOLIO = {"slug": "organvm-vii-kerygma/portfolio", "repository_id": 1155412125}
_W07_WORKFLOW: Any | None = None
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
EXPECTED_SURFACE_LEVELS = {
    "portfolio_front_door": "L1",
    "portfolio_flagship": "L2",
    "resume": "L1",
    "personal_profile": "L1",
    "organization_profile": "L1",
    "flagship_repository": "L2",
}
FORBIDDEN_DEMO_KEYS = {
    "credential",
    "customer",
    "email",
    "passcode",
    "passphrase",
    "passwd",
    "password",
    "pwd",
    "private_path",
    "private_repository",
    "secret",
    "tasks_yaml_body",
    "token",
}
PUBLIC_FAILURE_CLASSES = {
    "dependency_failure",
    "external_gate",
    "human_gate",
    "policy_failure",
    "predicate_failure",
    "resource_limit",
    "verification_failure",
}
INDEPENDENCE_DISPOSITIONS = {
    "independent_peer_review",
    "independent_public_source",
    "independent_third_party",
}
FORBIDDEN_DEMO_VALUE_PATTERNS = (
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}\b"),
    re.compile(r"(?i)https?://[^\s/:@]+:[^\s/@]+@"),
)


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
        if c03.get("status") != "p03_w01_w06_closed_p04_merged_w07_open":
            errors.append("C03 progress status mismatch")
        if c03.get("exact_head") != C03_CURRENT_HEAD:
            errors.append("C03 current preflight head mismatch")
        if c03.get("merge_commit") != C03_MERGE_COMMIT:
            errors.append("C03 merged integration commit mismatch")
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
    if c03_dependency.get("merge_commit") != C03_MERGE_COMMIT:
        errors.append("C03 dependency source must bind its merged main commit")
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
    if reproduction.get("review_schema") != COST_REVIEW_SCHEMA:
        errors.append("cost/failure reproduction must bind the independent review schema")
    reviewer_classes = reproduction.get("independent_reviewer_classes")
    if (
        not isinstance(reviewer_classes, list)
        or not all(isinstance(value, str) for value in reviewer_classes)
        or set(reviewer_classes) != INDEPENDENT_REVIEWER_CLASSES
    ):
        errors.append("cost/failure reproduction must bind the independent reviewer classes")
    public_failure_classes = reproduction.get("public_failure_classes")
    if (
        not isinstance(public_failure_classes, list)
        or not all(isinstance(value, str) for value in public_failure_classes)
        or set(public_failure_classes) != PUBLIC_FAILURE_CLASSES
    ):
        errors.append("cost/failure reproduction must declare the reviewed public failure vocabulary")

    receipt_plan = contract.get("exact_head_receipt_plan", {})
    if not receipt_plan.get("runner") or not receipt_plan.get("request_schema"):
        errors.append("exact-head receipt plan requires an executable runner and request schema")
    output_limit = receipt_plan.get("default_output_limit_bytes")
    if (
        not isinstance(output_limit, int)
        or isinstance(output_limit, bool)
        or not 1024 <= output_limit <= 10 * 1024 * 1024
    ):
        errors.append("exact-head receipt plan requires a bounded output budget")

    surface_model = contract.get("surface_audit_model", {})
    if surface_model.get("claim_inventory_source") != "p02_claims_ledger":
        errors.append("surface audit must discover material claims from the accepted claims ledger")
    if surface_model.get("surface_levels") != EXPECTED_SURFACE_LEVELS:
        errors.append("surface audit must bind every public surface to its canonical disclosure level")

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
    minimum_objects = validation.get("minimum_object_count")
    if not isinstance(minimum_objects, int) or isinstance(minimum_objects, bool) or minimum_objects < 2:
        errors.append("external validation must require at least two substantive objects")
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
    claims = discover_material_claims(contract)
    for surface in contract.get("surface_audit_model", {}).get("surfaces", []):
        for claim in claims:
            rows.append(
                {
                    "surface": surface,
                    "claim_id": claim["claim_id"],
                    "claim_text": claim["candidate_claim"],
                    "presence": "not_audited",
                    "source_ids": claim["source_ids"],
                    "observed_at": claim["observation_dates"],
                    "status": claim["status"],
                    "disclosure_level": claim["max_disclosure"],
                    "canonical_or_drift": "not_audited",
                    "contains_private_material": None,
                    "action": claim["action"],
                }
            )
    return rows


def _markdown_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _ledger_action(*dispositions: str) -> str:
    boundary = " ".join(dispositions).lower()
    unsafe_markers = (
        "conflicted",
        "contradicted",
        "do not publish",
        "ignored",
        "never use",
        "not yet published",
        "not_established",
        "nowhere",
        "remove",
        "superseded",
        "unsupported",
        "unverified",
        "withhold",
        "withheld",
    )
    return "withhold_or_remove" if any(marker in boundary for marker in unsafe_markers) else "audit_canonical_wording"


def _is_markdown_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _ledger_material_claims(content: str, source_id: str) -> list[dict[str, Any]]:
    reconciled = re.search(r"Reconciled (\d{4}-\d{2}-\d{2})", content)
    observed_at = [reconciled.group(1)] if reconciled else []
    in_claim_section = False
    claims: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^## [1-9]\.", line):
            in_claim_section = True
            continue
        if line.startswith("## "):
            in_claim_section = False
        if not in_claim_section or not line.startswith("|"):
            continue
        cells = _markdown_cells(line)
        next_cells = (
            _markdown_cells(lines[index + 1]) if index + 1 < len(lines) and lines[index + 1].startswith("|") else []
        )
        if (
            len(cells) < 3
            or _is_markdown_separator(cells)
            or _is_markdown_separator(next_cells)
            or cells[1].lower() == "status"
        ):
            continue
        claim_text = cells[0]
        if not claim_text or claim_text in seen_text:
            continue
        seen_text.add(claim_text)
        status = cells[1]
        public_safe_wording = cells[-2] if len(cells) >= 5 else claim_text
        tier = cells[-1] if len(cells) >= 5 else "ledger_only"
        action = _ledger_action(*cells[1:])
        claim_id = f"LEDGER-{hashlib.sha256(claim_text.encode()).hexdigest()[:16].upper()}"
        claims.append(
            {
                "claim_id": claim_id,
                "flagship_id": None,
                "candidate_claim": claim_text,
                "source_ids": [source_id],
                "observation_dates": observed_at,
                "status": status,
                "max_disclosure": tier,
                "limitations": [public_safe_wording],
                "publishable": action == "audit_canonical_wording",
                "reason_codes": ["accepted_claims_ledger_inventory"],
                "action": action,
            }
        )
    return claims


def discover_material_claims(contract: dict[str, Any], repository: Path = ROOT) -> list[dict[str, Any]]:
    """Discover the accepted ledger denominator, then retain the selected flagship proof cells."""
    dependencies = {row.get("id"): row for row in contract.get("dependency_sources", []) if isinstance(row, dict)}
    source_id = str(contract.get("surface_audit_model", {}).get("claim_inventory_source", ""))
    dependency = dependencies.get(source_id, {})
    content, blob = _read_git_object(
        repository,
        str(dependency.get("exact_head", "")),
        str(dependency.get("required_path", "")),
    )
    if content is None or blob != dependency.get("expected_blob"):
        raise ValueError("accepted claims-ledger inventory is unavailable or stale")
    claims = _ledger_material_claims(content, source_id)
    claims.extend(resolve_claims(contract))
    if not claims:
        raise ValueError("material public-claim inventory is empty")
    return sorted(claims, key=lambda row: str(row["claim_id"]))


def _disclosure_floor(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    levels = [int(match) for match in re.findall(r"\bL([123])\b", value.upper())]
    return min(levels) if levels else None


def audit_surface_manifest(contract: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    skeleton = build_surface_audit_skeleton(contract)
    expected_rows = {(row["surface"], row["claim_id"]): row for row in skeleton}
    expected = set(expected_rows)
    supplied_rows = manifest.get("rows") if isinstance(manifest, dict) else None
    errors: list[str] = []
    if not isinstance(supplied_rows, list):
        return {"status": "fail", "errors": ["surface manifest rows must be a list"], "coverage": {}}
    supplied: set[tuple[str, str]] = set()
    surface_levels = contract.get("surface_audit_model", {}).get("surface_levels", {})
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
        presence = row.get("presence")
        if not isinstance(presence, str) or presence not in {"present", "absent"}:
            errors.append(f"surface presence unresolved: {key[0]} / {key[1]}")
        if presence == "present":
            canonical = expected_rows.get(key, {})
            required_cells = set(contract.get("surface_audit_model", {}).get("required_cells", []))
            missing_required = sorted(
                field
                for field in required_cells
                if field not in row or row.get(field) is None or row.get(field) == "" or row.get(field) == []
            )
            if missing_required:
                errors.append(
                    f"present claim missing required evidence fields: {key[0]} / {key[1]}: {', '.join(missing_required)}"
                )
            source_ids = row.get("source_ids")
            valid_source_ids = (
                isinstance(source_ids, list)
                and bool(source_ids)
                and all(isinstance(source_id, str) and source_id for source_id in source_ids)
            )
            if not valid_source_ids:
                errors.append(f"source_ids must be a non-empty string list: {key[0]} / {key[1]}")
            expected_source_ids = expected_rows.get(key, {}).get("source_ids", [])
            expected_sources = set(expected_source_ids)
            if valid_source_ids and len(source_ids) != len(set(source_ids)):
                errors.append(f"source_ids contain duplicates: {key[0]} / {key[1]}")
            if valid_source_ids and (
                len(source_ids) != len(expected_source_ids) or set(source_ids) != expected_sources
            ):
                errors.append(f"source ids differ from canonical inventory: {key[0]} / {key[1]}")
            if not isinstance(row.get("disclosure_level"), str) or not row.get("disclosure_level"):
                errors.append(f"disclosure level missing: {key[0]} / {key[1]}")
            if not isinstance(row.get("action"), str) or not row.get("action"):
                errors.append(f"claim action missing: {key[0]} / {key[1]}")
            if row.get("action") != canonical.get("action"):
                errors.append(f"claim action differs from canonical inventory: {key[0]} / {key[1]}")
            if row.get("disclosure_level") != canonical.get("disclosure_level"):
                errors.append(f"disclosure level differs from canonical inventory: {key[0]} / {key[1]}")
            claim_floor = _disclosure_floor(canonical.get("disclosure_level"))
            surface_floor = _disclosure_floor(surface_levels.get(key[0]) if isinstance(surface_levels, dict) else None)
            if claim_floor is None or surface_floor is None or claim_floor > surface_floor:
                errors.append(f"claim disclosure tier does not authorize this surface: {key[0]} / {key[1]}")
            if canonical.get("action") != "audit_canonical_wording":
                errors.append(f"canonical claim is not eligible for public presence: {key[0]} / {key[1]}")
            if row.get("claim_text") != canonical.get("claim_text"):
                errors.append(f"claim text differs from canonical inventory: {key[0]} / {key[1]}")
            if row.get("canonical_or_drift") != "canonical":
                errors.append(f"present claim differs from canonical wording: {key[0]} / {key[1]}")
            observed_at = row.get("observed_at")
            valid_observations = (
                isinstance(observed_at, list)
                and bool(observed_at)
                and all(isinstance(value, str) and bool(value) for value in observed_at)
            )
            if valid_observations:
                try:
                    for value in observed_at:
                        _parse_date(value)
                except ValueError:
                    valid_observations = False
            if not valid_observations or observed_at != canonical.get("observed_at"):
                errors.append(f"observation dates differ from canonical evidence: {key[0]} / {key[1]}")
            if row.get("status") != canonical.get("status"):
                errors.append(f"claim status differs from canonical inventory: {key[0]} / {key[1]}")
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
    missing_root_fields = sorted(DEMO_ROOT_FIELDS - set(fixture))
    unexpected_root_fields = sorted(set(fixture) - DEMO_ROOT_FIELDS)
    if missing_root_fields:
        errors.append(f"demo fixture missing root fields: {', '.join(missing_root_fields)}")
    if unexpected_root_fields:
        errors.append(f"demo fixture has unknown root fields: {', '.join(unexpected_root_fields)}")
    if fixture.get("schema_version") != ARCHITECTURE_DEMO_SCHEMA:
        errors.append(f"demo fixture schema_version must be {ARCHITECTURE_DEMO_SCHEMA}")
    if fixture.get("synthetic_only") is not True:
        errors.append("demo fixture must declare synthetic_only true")
    records = fixture.get("records")
    if not isinstance(records, list):
        return {"status": "fail", "errors": [*errors, "demo records must be a list"]}
    record_types: set[str] = set()
    record_type_counts: dict[str, int] = {}
    records_by_id: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"demo record {index} must be an object")
            continue
        record_type = record.get("type")
        if not isinstance(record_type, str) or not record_type.strip():
            errors.append(f"demo record {index} requires a nonblank text type")
        else:
            record_types.add(record_type)
            record_type_counts[record_type] = record_type_counts.get(record_type, 0) + 1
            expected_fields = DEMO_RECORD_FIELDS.get(record_type)
            if expected_fields is None:
                errors.append(f"demo record {index} has unsupported type: {record_type}")
            else:
                missing_fields = sorted(expected_fields - set(record))
                unexpected_fields = sorted(set(record) - expected_fields)
                if missing_fields:
                    errors.append(
                        f"demo record {index} missing {record_type} fields: {', '.join(missing_fields)}"
                    )
                if unexpected_fields:
                    errors.append(
                        f"demo record {index} has unknown {record_type} fields: {', '.join(unexpected_fields)}"
                    )
                for field in sorted(expected_fields - {"type", "synthetic"}):
                    value = record.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"demo record {index} field {field} must be nonblank text")
        record_id = record.get("id")
        if isinstance(record_id, str) and record_id.strip():
            if record_id in records_by_id:
                errors.append(f"duplicate demo record id: {record_id}")
            else:
                records_by_id[record_id] = record
        else:
            errors.append(f"demo record {index} requires a nonblank text id")
        forbidden = sorted(_find_forbidden_demo_material(record))
        if forbidden:
            errors.append(f"demo record {index} contains forbidden material: {', '.join(forbidden)}")
        if record.get("synthetic") is not True:
            errors.append(f"demo record {index} must be marked synthetic")
    required = set(contract.get("synthetic_architecture_demo", {}).get("required_record_types", []))
    missing = sorted(required - record_types)
    if missing:
        errors.append(f"demo missing record types: {', '.join(missing)}")
    unexpected_types = sorted(record_types - set(DEMO_RECORD_FIELDS))
    if unexpected_types:
        errors.append(f"demo has unsupported record types: {', '.join(unexpected_types)}")
    for record_type in sorted(required):
        if record_type_counts.get(record_type) != 1:
            errors.append(f"demo requires exactly one {record_type} record")
    for record in records_by_id.values():
        record_type = record.get("type")
        if not isinstance(record_type, str):
            continue
        for (source_type, field), target_type in DEMO_RELATIONSHIPS.items():
            if record_type != source_type:
                continue
            target = records_by_id.get(record.get(field))
            if target is None or target.get("type") != target_type:
                errors.append(
                    f"demo {source_type} {record.get('id')} must link {field} to a {target_type} record"
                )
    packet = next((record for record in records_by_id.values() if record.get("type") == "packet"), None)
    if packet is not None and packet.get("authority") != "bounded":
        errors.append("demo packet authority must be bounded")
    predicate = next((record for record in records_by_id.values() if record.get("type") == "predicate"), None)
    if predicate is not None and predicate.get("result") not in {"pass", "fail", "blocked"}:
        errors.append("demo predicate result must be pass, fail, or blocked")
    return {"status": "pass" if not errors else "fail", "errors": errors, "record_count": len(records)}


def _normalized_demo_key(value: object) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value))
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _find_forbidden_demo_material(value: object, path: str = "$") -> set[str]:
    forbidden: set[str] = set()
    forbidden_compact = {key.replace("_", "") for key in FORBIDDEN_DEMO_KEYS}
    forbidden_segments = {
        "credential",
        "customer",
        "email",
        "passcode",
        "passphrase",
        "passwd",
        "password",
        "pwd",
        "secret",
        "token",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_demo_key(key)
            compact = normalized.replace("_", "")
            if (
                normalized in FORBIDDEN_DEMO_KEYS
                or compact in forbidden_compact
                or forbidden_segments.intersection(normalized.split("_"))
            ):
                forbidden.add(f"{path}.{key}")
            forbidden.update(_find_forbidden_demo_material(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            forbidden.update(_find_forbidden_demo_material(child, f"{path}[{index}]"))
    elif isinstance(value, str) and any(pattern.search(value) for pattern in FORBIDDEN_DEMO_VALUE_PATTERNS):
        forbidden.add(path)
    return forbidden


def validate_external_objects(
    contract: dict[str, Any],
    payload: dict[str, Any],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc).date()
    errors: list[str] = []
    if payload.get("outreach_performed") is not False:
        errors.append("preflight payload must prove no outreach")
    objects = payload.get("objects")
    if not isinstance(objects, list):
        return {"status": "fail", "errors": [*errors, "external validation objects must be a list"]}
    validation = contract.get("external_validation", {})
    required = set(validation.get("minimum_fields", []))
    acceptable_rows = validation.get("acceptable_objects")
    if not isinstance(acceptable_rows, list) or not acceptable_rows or not all(
        isinstance(value, str) and value.strip() for value in acceptable_rows
    ):
        errors.append("external validation must declare approved object classes")
        acceptable_objects: set[str] = set()
    else:
        acceptable_objects = set(acceptable_rows)
    minimum_count = int(validation.get("minimum_object_count", 0))
    provenance: set[str] = set()
    substantive_public_count = 0
    for index, row in enumerate(objects):
        if not isinstance(row, dict):
            errors.append(f"validation object {index} must be an object")
            continue
        missing = sorted(field for field in required if field not in row)
        if missing:
            errors.append(f"validation object {index} missing: {', '.join(missing)}")
        invalid_text = sorted(
            field
            for field in required
            if field in row and (not isinstance(row.get(field), str) or not row.get(field).strip())
        )
        if invalid_text:
            errors.append(f"validation object {index} fields must be nonblank text: {', '.join(invalid_text)}")
        object_class = row.get("object class")
        if not isinstance(object_class, str) or object_class not in acceptable_objects:
            errors.append(f"validation object {index} requires an approved object class")
        independence = str(row.get("independence disclosure") or "").strip().lower()
        if independence not in INDEPENDENCE_DISPOSITIONS:
            errors.append(f"validation object {index} lacks an affirmative independence disposition")
        raw_object_receipt = row.get("object URL or receipt")
        object_receipt = raw_object_receipt.strip() if isinstance(raw_object_receipt, str) else raw_object_receipt
        duplicate_receipt = False
        if isinstance(object_receipt, str) and object_receipt:
            if object_receipt in provenance:
                errors.append(f"validation object {index} duplicates an existing object receipt")
                duplicate_receipt = True
            provenance.add(object_receipt)
        observed_at = row.get("date")
        valid_date = True
        try:
            if not isinstance(observed_at, str):
                raise ValueError
            parsed_date = _parse_date(observed_at)
            if parsed_date > as_of:
                errors.append(f"validation object {index} date cannot be in the future")
                valid_date = False
        except ValueError:
            errors.append(f"validation object {index} date must be ISO-8601")
            valid_date = False
        consent_status = row.get("consent status")
        if not isinstance(consent_status, str) or consent_status not in {"public_consented", "withdrawn"}:
            errors.append(f"validation object {index} has no public consent disposition")
        if (
            consent_status == "public_consented"
            and not missing
            and not invalid_text
            and object_class in acceptable_objects
            and independence in INDEPENDENCE_DISPOSITIONS
            and isinstance(object_receipt, str)
            and bool(object_receipt)
            and not duplicate_receipt
            and valid_date
        ):
            substantive_public_count += 1
    if substantive_public_count < minimum_count:
        errors.append(f"external validation requires at least {minimum_count} substantive public-consented objects")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "object_count": len(objects),
        "substantive_public_count": substantive_public_count,
    }


def _live_w07_verification(repository: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(repository / "scripts/positioning-program.py"), "--verify-work", "PSP-P03-W07"],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"live PSP-P03-W07 verifier did not pass: {detail}")
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("live PSP-P03-W07 verifier returned a non-object")
    return value


def _live_phase_verification(repository: Path, phase_id: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(repository / "scripts/positioning-program.py"), "--verify-phase", phase_id],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"live {phase_id} verifier did not pass: {detail}")
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError(f"live {phase_id} verifier returned a non-object")
    receipt_url = value.get("receipt_url")
    if not isinstance(receipt_url, str) or not PHASE_RECEIPT_URLS[phase_id].fullmatch(receipt_url):
        raise ValueError(f"live {phase_id} receipt URL is not an immutable canonical issue comment")
    comment_match = re.search(r"#issuecomment-([0-9]+)$", receipt_url)
    if comment_match is None:
        raise ValueError(f"live {phase_id} receipt URL has no immutable comment identifier")
    request = Request(
        f"https://api.github.com/repos/organvm/limen/issues/comments/{comment_match.group(1)}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "limen-positioning-proof-preflight",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(request, timeout=30) as response:
        raw_comment = response.read(1_048_577)
    if len(raw_comment) > 1_048_576:
        raise ValueError(f"live {phase_id} receipt comment exceeds the bounded response size")
    comment = json.loads(raw_comment)
    if not isinstance(comment, dict) or comment.get("html_url") != receipt_url:
        raise ValueError(f"live {phase_id} receipt comment identity differs from the verifier result")
    body = comment.get("body")
    matches = PHASE_RECEIPT_BLOCK.findall(body) if isinstance(body, str) else []
    matches = [receipt for candidate_phase, receipt in matches if candidate_phase == phase_id]
    if len(matches) != 1:
        raise ValueError(f"live {phase_id} comment must contain exactly one marked phase receipt")
    receipt = json.loads(matches[0])
    if not isinstance(receipt, dict):
        raise ValueError(f"live {phase_id} marked receipt returned a non-object")
    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != value.get("receipt_sha256"):
        raise ValueError(f"live {phase_id} marked receipt digest differs from the verifier result")
    observed_heads = receipt.get("observed_heads")
    if not isinstance(observed_heads, dict):
        raise ValueError(f"live {phase_id} marked receipt has no observed_heads binding")
    value["observed_heads"] = observed_heads
    return value


def _canonical_limen_remote_head() -> tuple[str, str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS"} or key.startswith(
            "GIT_CONFIG_KEY_"
        ) or key.startswith("GIT_CONFIG_VALUE_"):
            environment.pop(key, None)
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_COUNT": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    completed = subprocess.run(
        ["git", "ls-remote", "--symref", "https://github.com/organvm/limen.git", "HEAD"],
        cwd=Path("/"),
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"canonical organvm/limen remote inspection failed: {detail}")
    default_branch: str | None = None
    default_head: str | None = None
    for line in completed.stdout.splitlines():
        if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
            default_branch = line.removeprefix("ref: refs/heads/").removesuffix("\tHEAD")
        elif line.endswith("\tHEAD"):
            candidate = line.removesuffix("\tHEAD")
            if FULL_HEAD.fullmatch(candidate):
                default_head = candidate
    if not isinstance(default_branch, str) or not default_branch.strip() or default_head is None:
        raise ValueError("canonical organvm/limen remote returned no exact default-branch head")
    return default_branch, default_head


def _live_authoritative_closure_verification(repository: Path, closure_head: str) -> dict[str, Any]:
    if not FULL_HEAD.fullmatch(closure_head):
        raise ValueError("authoritative closure verification requires a full exact head")
    default_branch, default_head = _canonical_limen_remote_head()
    ancestry_environment = dict(os.environ)
    ancestry_environment.update({"GIT_NO_REPLACE_OBJECTS": "1", "GIT_GRAFT_FILE": "/dev/null"})
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", closure_head, default_head],
        cwd=repository,
        env=ancestry_environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if ancestry.returncode != 0:
        raise ValueError("claimed C03 closure head is not contained by the authoritative default branch")
    value = {
        "status": "pass",
        "repository": "organvm/limen",
        "closure_head": closure_head,
        "default_branch": default_branch,
        "default_head": default_head,
        "contained": True,
    }
    errors = _validate_authoritative_closure_verification(value, closure_head)
    if errors:
        raise ValueError("; ".join(errors))
    return value


def _validate_authoritative_closure_verification(value: object, closure_head: str) -> list[str]:
    expected = {
        "status",
        "repository",
        "closure_head",
        "default_branch",
        "default_head",
        "contained",
    }
    if not isinstance(value, dict) or set(value) != expected:
        return ["authoritative closure verification has an invalid exact schema"]
    errors: list[str] = []
    if value.get("status") != "pass" or value.get("repository") != "organvm/limen":
        errors.append("authoritative closure verification did not pass for organvm/limen")
    if value.get("closure_head") != closure_head:
        errors.append("authoritative closure verification does not bind the claimed exact head")
    default_branch = value.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch.strip():
        errors.append("authoritative closure verification has no default branch")
    if not FULL_HEAD.fullmatch(str(value.get("default_head") or "")):
        errors.append("authoritative closure verification has no full default-branch head")
    if value.get("contained") is not True:
        errors.append("claimed C03 closure head is not contained by the authoritative default branch")
    return errors


def _validate_phase_receipt_bindings(
    value: object,
    repository: Path,
    closure_head: str | None,
    live_verifications: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    phases = tuple(PHASE_RECEIPT_URLS)
    if not isinstance(value, dict) or set(value) != set(phases):
        return ["closure receipt must bind exactly the PSP-P03 and PSP-P04 marked phase receipts"]
    if live_verifications is None:
        try:
            live_verifications = {phase_id: _live_phase_verification(repository, phase_id) for phase_id in phases}
        except (json.JSONDecodeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
            return [str(exc)]
    errors: list[str] = []
    valid_closure_head = isinstance(closure_head, str) and bool(FULL_HEAD.fullmatch(closure_head))
    if not valid_closure_head:
        errors.append("phase receipts require a full closure exact head")
    for phase_id in phases:
        binding = value.get(phase_id)
        observed = live_verifications.get(phase_id) if isinstance(live_verifications, dict) else None
        if not isinstance(binding, dict) or set(binding) != {"receipt_url", "receipt_sha256"}:
            errors.append(f"{phase_id} must bind exactly receipt_url and receipt_sha256")
            continue
        if not isinstance(observed, dict) or observed.get("status") != "pass" or observed.get("phase_id") != phase_id:
            errors.append(f"live {phase_id} verification did not return pass")
            continue
        receipt_url = observed.get("receipt_url")
        receipt_sha256 = observed.get("receipt_sha256")
        if not isinstance(receipt_url, str) or not PHASE_RECEIPT_URLS[phase_id].fullmatch(receipt_url):
            errors.append(f"live {phase_id} receipt URL is not an immutable canonical issue comment")
        if not isinstance(receipt_sha256, str) or not SHA256.fullmatch(receipt_sha256):
            errors.append(f"live {phase_id} receipt digest is not a lowercase SHA-256")
        if binding.get("receipt_url") != receipt_url:
            errors.append(f"{phase_id} receipt URL differs from the latest marked live phase receipt")
        if binding.get("receipt_sha256") != receipt_sha256:
            errors.append(f"{phase_id} receipt digest differs from the latest marked live phase receipt")
        observed_heads = observed.get("observed_heads")
        if not isinstance(observed_heads, dict) or set(observed_heads) != {"organvm/limen"}:
            errors.append(f"live {phase_id} receipt must bind exactly the organvm/limen observed head")
            continue
        observed_head = observed_heads.get("organvm/limen")
        if not isinstance(observed_head, str) or not FULL_HEAD.fullmatch(observed_head):
            errors.append(f"live {phase_id} receipt observed head is not a full Git head")
            continue
        if valid_closure_head:
            ancestry = subprocess.run(
                ["git", "merge-base", "--is-ancestor", observed_head, closure_head],
                cwd=repository,
                check=False,
                capture_output=True,
                timeout=30,
            )
            if ancestry.returncode != 0:
                errors.append(f"live {phase_id} receipt observed head is not an ancestor of the closure head")
    return errors


def _git_blob(repository: Path, head: str, path: str) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{head}:{path}"],
        cwd=repository,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise ValueError(f"W07 evidence blob is unavailable at {head}:{path}: {detail}")
    return completed.stdout


def _trusted_w07_workflow() -> Any:
    global _W07_WORKFLOW
    if _W07_WORKFLOW is None:
        path = ROOT / W07_WORKFLOW_PATH
        spec = importlib.util.spec_from_file_location("psp_c04_w07_workflow", path)
        if spec is None or spec.loader is None:
            raise ValueError(f"trusted W07 workflow is unavailable: {path}")
        workflow = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = workflow
        spec.loader.exec_module(workflow)
        _W07_WORKFLOW = workflow
    return _W07_WORKFLOW


def _canonical_w07_decision_memo(response_payload: dict[str, Any]) -> bytes:
    workflow = _trusted_w07_workflow()
    verdict = workflow.V.validate(response_payload)
    if verdict.state != "pass":
        raise ValueError("trusted W07 workflow did not accept the exact tracked response set")
    return workflow.decision_memo(response_payload, verdict).encode("utf-8")


def _verify_w07_response_blob(
    repository: Path,
    observed_head: str,
    closure_head: str,
    response_path: str,
    response_sha256: str,
    decision_memo_path: str,
    decision_memo_sha256: str,
    evidence: dict[str, Any],
) -> None:
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", observed_head, closure_head],
        cwd=repository,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if ancestry.returncode != 0:
        raise ValueError("W07 observed head is not contained by the claimed C03 closure head")

    response_blob = _git_blob(repository, observed_head, response_path)
    try:
        response_payload = json.loads(response_blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"W07 response-set blob is not valid UTF-8 JSON: {exc}") from exc
    canonical = json.dumps(response_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest() != response_sha256:
        raise ValueError("W07 response-set digest does not bind the exact tracked response blob")

    decision_memo_blob = _git_blob(repository, observed_head, decision_memo_path)
    if hashlib.sha256(decision_memo_blob).hexdigest() != decision_memo_sha256:
        raise ValueError("W07 decision-memo digest does not bind the exact tracked memo blob")

    with tempfile.TemporaryDirectory() as directory:
        response_target = Path(directory) / "w07-reader-responses.json"
        response_target.write_bytes(response_blob)
        completed = subprocess.run(
            [sys.executable, str(ROOT / W07_VALIDATOR_PATH), str(response_target)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=90,
        )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"trusted W07 blinded-reader predicate did not pass: {detail}")
    if decision_memo_blob != _canonical_w07_decision_memo(response_payload):
        raise ValueError("W07 decision memo differs from the canonical aggregate of the exact response set")
    match = re.search(
        r"SCORE: total=(\d+)/25 role=(\d+)/5 buyer=(\d+)/5 cta=(\d+)/5",
        completed.stdout,
    )
    if match is None:
        raise ValueError("exact-head W07 blinded-reader predicate omitted its score receipt")
    measured = tuple(int(value) for value in match.groups())
    expected = tuple(evidence[field] for field in ("total_score", "role_matches", "buyer_matches", "cta_matches"))
    if measured != expected:
        raise ValueError("W07 reader evidence counts differ from the exact-head predicate output")


def _validate_w07_receipt_binding(
    value: object,
    repository: Path,
    live_verification: dict[str, Any] | None = None,
    closure_head: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["closure receipt requires a structured W07 receipt binding"]
    if value.get("work_id") != "PSP-P03-W07":
        errors.append("W07 receipt work_id must be PSP-P03-W07")
    if value.get("issue_url") != "https://github.com/organvm/limen/issues/2188":
        errors.append("W07 receipt must bind the canonical issue")
    url = value.get("url")
    if not isinstance(url, str) or not W07_RECEIPT_URL.fullmatch(url):
        errors.append("W07 receipt URL must be an immutable #2188 issue comment")
    digest = value.get("sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append("W07 receipt digest must be a lowercase SHA-256")
    receipt = value.get("receipt")
    if not isinstance(receipt, dict):
        errors.append("W07 binding must embed the canonical marked receipt")
    elif isinstance(digest, str) and SHA256.fullmatch(digest):
        canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(canonical).hexdigest() != digest:
            errors.append("W07 receipt digest does not bind the embedded canonical receipt")
        if receipt.get("work_id") != "PSP-P03-W07" or receipt.get("outcome") != "succeeded":
            errors.append("embedded W07 receipt must record a successful PSP-P03-W07 outcome")
        evidence = receipt.get("reader_evidence")
        response_path: str | None = None
        memo_path: str | None = None
        observed_head: str | None = None
        if not isinstance(evidence, dict):
            errors.append("embedded W07 receipt must include the public-safe reader evidence summary")
        else:
            exact_counts = {
                "reader_count": 5,
                "independent_reader_count": 5,
                "synthetic_or_model_reader_count": 0,
                "unresolved_authority_objections": 0,
            }
            for field, expected in exact_counts.items():
                if evidence.get(field) != expected:
                    errors.append(f"W07 reader evidence {field} must be {expected}")
            for field in ("total_score", "role_matches", "buyer_matches", "cta_matches"):
                measured = evidence.get(field)
                minimum = 20 if field == "total_score" else 4
                maximum = 25 if field == "total_score" else 5
                if not isinstance(measured, int) or isinstance(measured, bool) or not minimum <= measured <= maximum:
                    errors.append(f"W07 reader evidence {field} must be between {minimum} and {maximum}")
            for field in ("response_set_sha256", "decision_memo_sha256"):
                measured = evidence.get(field)
                if not isinstance(measured, str) or not SHA256.fullmatch(measured):
                    errors.append(f"W07 reader evidence {field} must be a lowercase SHA-256")
            candidate_path = evidence.get("response_set_path")
            if (
                not isinstance(candidate_path, str)
                or not W07_RESPONSE_PATH.fullmatch(candidate_path)
                or ".." in Path(candidate_path).parts
            ):
                errors.append("W07 reader evidence must bind a safe tracked response_set_path")
            else:
                response_path = candidate_path
            candidate_memo_path = evidence.get("decision_memo_path")
            if (
                not isinstance(candidate_memo_path, str)
                or not W07_MEMO_PATH.fullmatch(candidate_memo_path)
                or ".." in Path(candidate_memo_path).parts
            ):
                errors.append("W07 reader evidence must bind the canonical tracked decision_memo_path")
            else:
                memo_path = candidate_memo_path
            changed_paths = receipt.get("changed_paths")
            for label, path in (("response_set_path", response_path), ("decision_memo_path", memo_path)):
                if path is not None and (not isinstance(changed_paths, list) or path not in changed_paths):
                    errors.append(f"W07 {label} must be present in the receipt changed_paths")
            observed_heads = receipt.get("observed_heads")
            observed_head = observed_heads.get("organvm/limen") if isinstance(observed_heads, dict) else None
            evidence_urls = receipt.get("evidence_urls")
            if not FULL_HEAD.fullmatch(str(observed_head or "")):
                errors.append("W07 evidence must bind a full exact observed head")
            else:
                for label, path in (("response_set_path", response_path), ("decision_memo_path", memo_path)):
                    expected_url = f"https://github.com/organvm/limen/blob/{observed_head}/{path}"
                    if path is not None and (not isinstance(evidence_urls, list) or expected_url not in evidence_urls):
                        errors.append(f"W07 {label} must bind an immutable exact-head evidence URL")
        predicate = receipt.get("predicate")
        expected_command = f"python3 {W07_VALIDATOR_PATH} {response_path}" if response_path is not None else None
        if not isinstance(predicate, dict) or predicate.get("command") != expected_command:
            errors.append("embedded W07 receipt must bind the exact manifest-owned blinded-reader predicate command")
    if errors:
        return errors
    assert isinstance(receipt, dict)
    assert isinstance(evidence, dict)
    assert isinstance(observed_head, str)
    assert isinstance(response_path, str)
    assert isinstance(memo_path, str)
    try:
        _verify_w07_response_blob(
            repository,
            observed_head,
            closure_head or "HEAD",
            response_path,
            evidence["response_set_sha256"],
            memo_path,
            evidence["decision_memo_sha256"],
            evidence,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return [str(exc)]
    try:
        observed = live_verification if live_verification is not None else _live_w07_verification(repository)
    except (json.JSONDecodeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return [str(exc)]
    if observed.get("status") != "pass" or observed.get("work_id") != "PSP-P03-W07":
        errors.append("live PSP-P03-W07 verification did not return pass")
    if observed.get("receipt_url") != url:
        errors.append("W07 receipt URL differs from the latest marked live receipt")
    if observed.get("receipt_sha256") != digest:
        errors.append("W07 receipt digest differs from the latest marked live receipt")
    return errors


def formalization_readiness(
    contract: dict[str, Any],
    closure_receipt: dict[str, Any] | None = None,
    repository: Path = ROOT,
    w07_verification: dict[str, Any] | None = None,
    phase_verifications: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    accepted_head = contract.get("dependency_progress", {}).get("c03", {}).get("merge_commit")
    residual = ["PSP-P03-W07 genuine five-reader receipt", "PSP-C03 formal closure predicates"]
    receipt_errors: list[str] = []
    final_head: str | None = None
    if closure_receipt is not None:
        if closure_receipt.get("chunk_id") != "PSP-C03":
            receipt_errors.append("closure receipt chunk must be PSP-C03")
        if closure_receipt.get("status") != "pass":
            receipt_errors.append("closure receipt status must be pass")
        final_head = closure_receipt.get("exact_head")
        if not isinstance(final_head, str) or not FULL_HEAD.fullmatch(final_head):
            receipt_errors.append("closure receipt requires a full exact head")
        else:
            try:
                authoritative = _live_authoritative_closure_verification(repository, final_head)
                receipt_errors.extend(_validate_authoritative_closure_verification(authoritative, final_head))
            except (json.JSONDecodeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
                receipt_errors.append(str(exc))
            ancestry = subprocess.run(
                ["git", "merge-base", "--is-ancestor", str(accepted_head), final_head],
                cwd=repository,
                check=False,
                capture_output=True,
            )
            if ancestry.returncode:
                receipt_errors.append("final C03 head is not a locally proven descendant of the accepted head")
        if "phase_predicates" in closure_receipt:
            receipt_errors.append("self-declared phase_predicates are not accepted as phase evidence")
        receipt_errors.extend(
            _validate_phase_receipt_bindings(
                closure_receipt.get("phase_receipts"),
                repository,
                closure_head=final_head,
                live_verifications=phase_verifications,
            )
        )
        receipt_errors.extend(
            _validate_w07_receipt_binding(
                closure_receipt.get("w07_receipt"),
                repository,
                live_verification=w07_verification,
                closure_head=final_head,
            )
        )
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
            try:
                payload = _load_optional_json(args.input)
                if payload is None:
                    result["rows"] = build_surface_audit_skeleton(contract)
                else:
                    result["audit"] = audit_surface_manifest(contract, payload)
                    result["status"] = result["audit"]["status"]
            except ValueError as exc:
                result["status"] = "fail"
                result["errors"].append(f"surface audit failed: {exc}")
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
            result["validation"] = validate_external_objects(contract, payload, as_of=as_of)
            result["status"] = result["validation"]["status"]
        elif args.mode == "formalization":
            payload = _load_optional_json(args.input)
            result["formalization"] = formalization_readiness(contract, payload)
            result["status"] = "pass" if result["formalization"]["ready"] else "fail"
            result["errors"].extend(result["formalization"]["errors"])
    print(json.dumps(result, indent=2) if args.json else result["status"].upper())
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
