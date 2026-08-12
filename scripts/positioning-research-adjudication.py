#!/usr/bin/env python3
"""Validate the PSP-P02-W08 public-safe research-adjudication formalization."""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATH = ROOT / "docs/positioning/program/research-adjudication.json"
RECEIPT_PATH = ROOT / "docs/receipts/positioning/psp-p02-w08-live-profile-preflight-20260810.json"
PROGRAM_PATH = ROOT / "institutio/positioning/program.yaml"
ISSUE_MAP_PATH = ROOT / "institutio/positioning/github-map.json"
ISSUE_INDEX_PATH = ROOT / "docs/positioning/program/ISSUE-INDEX.md"
RESEARCH_DOC_PATH = ROOT / "docs/positioning/program/RESEARCH-ADJUDICATION.md"
FLAGSHIP_EVIDENCE_PATH = ROOT / "docs/positioning/evidence/flagship-evidence.yaml"
CLAIMS_LEDGER_PATH = ROOT / "docs/positioning/claims-ledger.md"
W01_TRACKED_RECEIPT_PATH = ROOT / "docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json"

ARTIFACT_SCHEMA = "limen.positioning_research_adjudication.v1"
RECEIPT_SCHEMA = "limen.psp-p02-w08-live-profile-formalization.v1"
IDENTITY_SCHEMA = "limen.positioning_repository_identities.v1"
WORK_ID = "PSP-P02-W08"
PORTFOLIO_REPOSITORY_ID = 1155412125
PORTFOLIO_CANONICAL_SLUG = "organvm-vii-kerygma/portfolio"
PORTFOLIO_RETIRED_SLUG = "organvm/portfolio"
HEAD_RE = re.compile(r"[0-9a-f]{40}\Z")
RFC3339_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\Z")
CLAIM_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
SOURCE_ID_RE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*\Z")
SAFE_PUBLIC_FRAGMENT_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*\Z")
CREDENTIAL_FRAGMENT_RE = re.compile(
    r"(?:^|[-_.])(?:access[-_]?token|api[-_]?key|authorization|bearer|credential|jwt|oauth|password|passwd|secret|session|signature)(?:$|[-_.])",
    re.IGNORECASE,
)
EXPECTED_CLAIM_COUNT = 13
FORMAL_STATUS = "formal_ready_projection_pending"
PROJECTION_STATUS = "projection_pending"
ACCEPTED_DEPENDENCIES = {
    "PSP-P02-W01": {
        "issue_number": 2173,
        "issue": "https://github.com/organvm/limen/issues/2173",
        "issue_state": "closed",
        "accepted_head": "10cf8476d5e88309c71d5fac25167ec7b7af59c4",
        "marked_receipt": "https://github.com/organvm/limen/issues/2173#issuecomment-5246643968",
        "canonical_receipt_sha256": "2928726feed64960d73b059889a39fceb318bf7bbc68c4b120d41527eaf10df6",
        "tracked_receipt_path": "docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json",
        "tracked_receipt_blob": "f8d27123269dfe49aecb2a5a4d2fbd5c83c2f0fd",
    },
    "PSP-P02-W05": {
        "issue_number": 2177,
        "issue": "https://github.com/organvm/limen/issues/2177",
        "issue_state": "closed",
        "accepted_head": "d8b44e60e404b044436addf8108732cc28c06371",
        "marked_receipt": "https://github.com/organvm/limen/issues/2177#issuecomment-5265859179",
        "canonical_receipt_sha256": "9179271ac02d5df5ddf1502ceabf84a8caa2b7394fd8fba70a3f75f05bfe8164",
        "claims_ledger_path": "docs/positioning/claims-ledger.md",
        "claims_ledger_blob": "3e49114563075dcd6926e3b7f8fd24bf8b9c3fee",
    },
}
RECEIPT_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
PROFILE_RENDERED_CONTRIBUTIONS = 33130
PROFILE_FRESH_CONTRIBUTIONS = 33168
PROFILE_CONTRIBUTION_WORDING = "33,130 contributions in the last year"
EXPECTED_HTTP_RECEIPTS = {
    "current_profile_blog_field": ("https://organvm.github.io/portfolio/", 404),
    "canonical_transferred_portfolio_pages": (
        "https://organvm-vii-kerygma.github.io/portfolio/",
        200,
    ),
}
LAYERS = ("measurement", "inference", "implication", "prominence")
DISPOSITION_VOCABULARIES = {
    "measurement": ("verified", "partially_verified", "contradicted", "unverified", "not_applicable"),
    "inference": ("supported", "bounded", "contradicted", "unsupported", "not_applicable"),
    "implication": ("supported", "bounded", "contradicted", "not_established", "not_applicable"),
    "prominence": ("retain_l1", "retain_l2", "supporting_only", "narrow", "correct_immediately", "withhold"),
}
LAVREA_AXES = {
    "contributions_year",
    "pull_requests_year",
    "repos_owned",
    "language_breadth",
    "orgs_operated",
    "full_stack_coverage",
    "composite_python_full_stack",
    "tenure",
}


class AdjudicationError(RuntimeError):
    """Raised when an adjudication input or live identity cannot be inspected."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdjudicationError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdjudicationError(f"{path} must contain a mapping")
    return value


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise AdjudicationError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdjudicationError(f"{path} must contain a mapping")
    return value


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _credential_free_https_url(value: object) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        return False
    fragment = unquote(parsed.fragment)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and (
            not fragment
            or (
                SAFE_PUBLIC_FRAGMENT_RE.fullmatch(fragment) is not None
                and CREDENTIAL_FRAGMENT_RE.search(fragment) is None
            )
        )
        and not any(character.isspace() for character in value)
    )


def _rfc3339(value: object) -> datetime | None:
    if not isinstance(value, str) or RFC3339_RE.fullmatch(value) is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _nonnegative_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _git_blob_oid(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _canonical_sha256(value: object) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _accepted_dependency_contract(work_id: str) -> dict[str, Any]:
    return {
        "work_id": work_id,
        **{
            key: value
            for key, value in ACCEPTED_DEPENDENCIES[work_id].items()
            if key != "issue_number"
        },
    }


def _artifact_claim_projection(claims: list[object]) -> list[dict[str, Any]]:
    projection: list[dict[str, Any]] = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        integration = claim.get("w05_integration")
        if not isinstance(integration, dict):
            integration = {}
        projection.append(
            {
                "id": claim.get("id"),
                "layers": {
                    layer: (claim.get(layer) or {}).get("disposition")
                    if isinstance(claim.get(layer), dict)
                    else None
                    for layer in LAYERS
                },
                "publishable_status": integration.get("publishable_status"),
                "public_wording": integration.get("public_wording"),
                "required_receipts": integration.get("required_receipts"),
            }
        )
    return projection


def _ledger_claim_projection(ledger: str) -> list[dict[str, str]]:
    section = ledger.partition("## 9. Research-criticism import")[2].partition("## Never-publish list")[0]
    row_re = re.compile(
        r"^\| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \| `([^`]+)` \|$"
    )
    rows: list[dict[str, str]] = []
    for line in section.splitlines():
        match = row_re.fullmatch(line)
        if match is None:
            continue
        claim_id, measurement, inference, implication, prominence, publishable_status = match.groups()
        rows.append(
            {
                "id": claim_id,
                "measurement": measurement,
                "inference": inference,
                "implication": implication,
                "prominence": prominence,
                "publishable_status": publishable_status,
            }
        )
    return rows


def _work_rows(program: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for phase in program.get("phases") or []:
        if isinstance(phase, dict):
            rows.extend(row for row in phase.get("work") or [] if isinstance(row, dict))
    return rows


def validate_bundle(
    artifact: dict[str, Any],
    receipt: dict[str, Any],
    program: dict[str, Any],
    issue_map: dict[str, Any],
    issue_index: str,
    research_doc: str,
    flagship_evidence: dict[str, Any],
    claims_ledger: str,
) -> list[str]:
    """Return all static public-safety, evidence, and integration failures."""

    errors: list[str] = []
    if artifact.get("schema") != ARTIFACT_SCHEMA:
        errors.append(f"artifact.schema must be {ARTIFACT_SCHEMA}")
    if receipt.get("schema") != RECEIPT_SCHEMA:
        errors.append(f"receipt.schema must be {RECEIPT_SCHEMA}")
    if artifact.get("work_id") != WORK_ID or receipt.get("work_id") != WORK_ID:
        errors.append(f"artifact and receipt must both belong to {WORK_ID}")
    if artifact.get("status") != FORMAL_STATUS:
        errors.append(f"artifact status must be {FORMAL_STATUS}")
    if receipt.get("verdict") != FORMAL_STATUS:
        errors.append(f"receipt verdict must be {FORMAL_STATUS}")
    if artifact.get("receipt") != str(RECEIPT_PATH.relative_to(ROOT)):
        errors.append("artifact must name the tracked W08 live-profile receipt")

    expected_dependencies = [
        _accepted_dependency_contract("PSP-P02-W01"),
        _accepted_dependency_contract("PSP-P02-W05"),
    ]
    formalization = artifact.get("formalization") or {}
    if formalization.get("readiness") != "formal_ready":
        errors.append("artifact formalization must be formal-ready")
    if formalization.get("projection_status") != PROJECTION_STATUS:
        errors.append("artifact must remain projection_pending")
    if formalization.get("accepted_dependencies") != expected_dependencies:
        errors.append("artifact must bind the exact accepted W01 and W05 receipts")
    if formalization.get("post_merge_projection_command") != "python3 scripts/positioning-program.py --sync --apply":
        errors.append("artifact must retain the authorized post-merge projection command")
    if formalization.get("post_merge_verify_command") != "python3 scripts/positioning-program.py --verify-remote":
        errors.append("artifact must retain the post-merge remote-parity predicate")

    formal = receipt.get("formal_completion") or {}
    if formal.get("allowed") is not False:
        errors.append("formal completion must remain false until post-merge projection parity")
    if formal.get("readiness") != "formal_ready":
        errors.append("receipt must record formal readiness")
    if formal.get("projection_status") != PROJECTION_STATUS:
        errors.append("receipt must remain projection_pending")
    dependencies = formal.get("dependencies") or []
    if dependencies != expected_dependencies:
        errors.append("receipt must bind the exact accepted W01 and W05 receipts")
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        work_id = dependency.get("work_id")
        if not _credential_free_https_url(dependency.get("issue")):
            errors.append(f"dependency {work_id} needs a public issue URL")
        if not _credential_free_https_url(dependency.get("marked_receipt")):
            errors.append(f"dependency {work_id} needs its accepted marked receipt URL")
        if not HEAD_RE.fullmatch(str(dependency.get("accepted_head") or "")):
            errors.append(f"dependency {work_id} needs its accepted 40-character head")
        if not re.fullmatch(r"[0-9a-f]{64}", str(dependency.get("canonical_receipt_sha256") or "")):
            errors.append(f"dependency {work_id} needs its canonical receipt SHA-256")
    try:
        if _git_blob_oid(W01_TRACKED_RECEIPT_PATH) != ACCEPTED_DEPENDENCIES["PSP-P02-W01"][
            "tracked_receipt_blob"
        ]:
            errors.append("tracked W01 receipt blob differs from the accepted binding")
        if _git_blob_oid(CLAIMS_LEDGER_PATH) != ACCEPTED_DEPENDENCIES["PSP-P02-W05"][
            "claims_ledger_blob"
        ]:
            errors.append("claims-ledger blob differs from the accepted W05 binding")
    except OSError as exc:
        errors.append(f"cannot read accepted dependency artifact: {exc}")
    if (formal.get("live_reference") or {}).get("issue_state") != "open":
        errors.append("the profile-engine live reference must remain recorded as open")

    privacy = receipt.get("privacy_review") or {}
    if privacy.get("public_only") is not True:
        errors.append("receipt must be public-only")
    if privacy.get("private_repository_names") != 0 or privacy.get("private_only_sources") != 0:
        errors.append("receipt must declare zero private repository names and private-only sources")

    coverage = artifact.get("coverage") or {}
    claims = artifact.get("claims")
    if not isinstance(claims, list):
        errors.append("claims must be a list")
        claims = []
    if len(claims) != EXPECTED_CLAIM_COUNT:
        errors.append(f"claims must contain exactly {EXPECTED_CLAIM_COUNT} adjudicated rows")
    if coverage.get("denominator") != len(claims) or coverage.get("adjudicated") != len(claims):
        errors.append("claim coverage denominator and adjudicated count must match the claim rows")
    if not _text(coverage.get("basis")) or not _text(coverage.get("rule")):
        errors.append("claim coverage needs a basis and adjudication rule")

    vocabularies = artifact.get("disposition_vocabularies") or {}
    for layer in LAYERS:
        vocabulary = vocabularies.get(layer)
        expected_vocabulary = list(DISPOSITION_VOCABULARIES[layer])
        if vocabulary != expected_vocabulary:
            errors.append(f"{layer} disposition vocabulary must match the canonical ordered vocabulary")

    sources = artifact.get("sources")
    if not isinstance(sources, dict) or not sources:
        errors.append("sources must be a nonempty mapping")
        sources = {}
    for source_id, source in sources.items():
        prefix = f"source {source_id}"
        if not isinstance(source_id, str) or not SOURCE_ID_RE.fullmatch(source_id):
            errors.append(f"{prefix} id must use the public-safe uppercase token format")
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        if source.get("public") is not True:
            errors.append(f"{prefix} must be public")
        url = source.get("url")
        if not _credential_free_https_url(url):
            errors.append(f"{prefix} must use a credential-free HTTPS public URL")
        if str(source.get("kind", "")).startswith("head_pinned"):
            head = source.get("head")
            if not isinstance(head, str) or not HEAD_RE.fullmatch(head):
                errors.append(f"{prefix} needs a 40-character exact head")
            elif head not in str(url):
                errors.append(f"{prefix} URL must contain its exact head")
        if "blob" in source and (
            not isinstance(source.get("blob"), str) or not HEAD_RE.fullmatch(str(source.get("blob")))
        ):
            errors.append(f"{prefix} blob must be a 40-character object ID")

    w01_source = sources.get("W01_CENSUS_RECEIPT") or {}
    if (
        w01_source.get("head") != ACCEPTED_DEPENDENCIES["PSP-P02-W01"]["accepted_head"]
        or w01_source.get("blob") != ACCEPTED_DEPENDENCIES["PSP-P02-W01"]["tracked_receipt_blob"]
    ):
        errors.append("W01 source must bind the accepted head and tracked receipt blob")
    ledger_source = sources.get("CLAIMS_LEDGER") or {}
    if (
        ledger_source.get("head") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["accepted_head"]
        or ledger_source.get("blob") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["claims_ledger_blob"]
    ):
        errors.append("claims-ledger source must bind the accepted W05 head and blob")

    claim_ids: list[str] = []
    for index, claim in enumerate(claims):
        prefix = f"claim[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        claim_id = claim.get("id")
        if not isinstance(claim_id, str) or not CLAIM_ID_RE.fullmatch(claim_id):
            errors.append(f"{prefix}.id must use the public-safe lowercase token format")
            claim_id = prefix
        claim_ids.append(str(claim_id))
        prefix = str(claim_id)
        if not _text(claim.get("research_rebuke")) or not _text(claim.get("exact_public_wording")):
            errors.append(f"{prefix} needs the rebuke and exact public wording")
        for layer in LAYERS:
            value = claim.get(layer)
            if not isinstance(value, dict) or set(value) != {"disposition", "rationale", "citations"}:
                errors.append(f"{prefix}.{layer} must contain exactly disposition, rationale, and citations")
                continue
            if value.get("disposition") not in set(vocabularies.get(layer) or []):
                errors.append(f"{prefix}.{layer} uses an unknown disposition")
            if not _text(value.get("rationale")):
                errors.append(f"{prefix}.{layer} needs a rationale")
            citations = value.get("citations")
            if not isinstance(citations, list) or not citations:
                errors.append(f"{prefix}.{layer} needs at least one citation")
            else:
                unknown = sorted(str(citation) for citation in citations if citation not in sources)
                if unknown:
                    errors.append(f"{prefix}.{layer} has unknown citations: {', '.join(unknown)}")
        integration = claim.get("w05_integration")
        required_keys = {"ledger_action", "publishable_status", "public_wording", "required_receipts"}
        if not isinstance(integration, dict) or set(integration) != required_keys:
            errors.append(f"{prefix}.w05_integration must contain the complete import contract")
        else:
            if not _text(integration.get("public_wording")):
                errors.append(f"{prefix}.w05_integration must preserve bounded public wording")
            if not isinstance(integration.get("required_receipts"), list) or not integration.get("required_receipts"):
                errors.append(f"{prefix}.w05_integration needs required receipts")

        measurement = claim.get("measurement") or {}
        prominence = claim.get("prominence") or {}
        if measurement.get("disposition") in {"verified", "partially_verified"} and prominence.get(
            "disposition"
        ) == "withhold":
            wording = str((integration or {}).get("public_wording") or "").lower()
            if not any(token in wording for token in ("measurement", "github", "python", "language", "output")):
                errors.append(f"{prefix} withholds prominence without preserving its verified measurement")

    duplicates = sorted({claim_id for claim_id in claim_ids if claim_ids.count(claim_id) > 1})
    if duplicates:
        errors.append(f"duplicate claim ids: {', '.join(duplicates)}")

    artifact_projection = _artifact_claim_projection(claims)
    w05_import = flagship_evidence.get("w08_research_import") or {}
    imported_claims = w05_import.get("claims")
    expected_import_keys = {
        "id",
        "layers",
        "publishable_status",
        "public_wording",
        "required_receipts",
    }
    if not isinstance(imported_claims, list) or len(imported_claims) != EXPECTED_CLAIM_COUNT:
        errors.append("accepted W05 import must contain exactly 13 claims")
        imported_claims = []
    elif any(not isinstance(row, dict) or set(row) != expected_import_keys for row in imported_claims):
        errors.append("every accepted W05 import row must contain the exact publishable contract")
    if imported_claims != artifact_projection:
        errors.append(
            "all 13 artifact claims must exactly match the accepted W05 four-layer and publishable projection"
        )

    expected_ledger_projection = [
        {
            "id": row["id"],
            **row["layers"],
            "publishable_status": row["publishable_status"],
        }
        for row in artifact_projection
    ]
    if _ledger_claim_projection(claims_ledger) != expected_ledger_projection:
        errors.append("accepted claims-ledger table must exactly match all 13 formalized claim dispositions")

    axes = artifact.get("lavrea_axis_audit")
    if not isinstance(axes, list):
        errors.append("lavrea_axis_audit must be a list")
        axes = []
    axis_names = {row.get("axis") for row in axes if isinstance(row, dict)}
    if axis_names != LAVREA_AXES or len(axes) != len(LAVREA_AXES):
        errors.append("LAVREA audit must cover each of the eight axes exactly once")
    for row in axes:
        if not isinstance(row, dict):
            continue
        axis = row.get("axis")
        if not _text(row.get("measurement_disposition")) or not _text(row.get("inference_disposition")):
            errors.append(f"LAVREA axis {axis} needs distinct measurement and inference dispositions")
        if not _text(row.get("primary_source_result")):
            errors.append(f"LAVREA axis {axis} needs a primary-source result")
        citations = row.get("citations")
        if not isinstance(citations, list) or not citations or any(citation not in sources for citation in citations):
            errors.append(f"LAVREA axis {axis} needs valid citations")

    w05 = artifact.get("w05_import_contract") or {}
    if w05.get("target") != "docs/positioning/claims-ledger.md" or w05.get("edited_here") is not False:
        errors.append("W05 contract must target, but not edit, the claims ledger")
    if w05.get("consumer_work_id") != "PSP-P02-W05":
        errors.append("W05 contract must name PSP-P02-W05 as consumer")
    if w05.get("accepted_consumer_head") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["accepted_head"]:
        errors.append("W05 contract must bind the accepted consumer head")
    if w05.get("accepted_target_blob") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["claims_ledger_blob"]:
        errors.append("W05 contract must bind the accepted claims-ledger blob")
    if w05.get("accepted_projection") != "docs/positioning/evidence/flagship-evidence.yaml#w08_research_import":
        errors.append("W05 contract must name the accepted 13-claim projection")
    if w05.get("source_claim_ids") != claim_ids:
        errors.append("W05 contract claim IDs must match adjudicated claim order")
    if "must not collapse" not in str(w05.get("import_rule") or ""):
        errors.append("W05 contract must forbid collapsing measurements into inferences")
    if "PSP-P02-W01" not in str(w05.get("completion_gate") or "") or "PSP-P02-W05" not in str(
        w05.get("completion_gate") or ""
    ):
        errors.append("W08 completion gate must name W01 and W05")

    identities = program.get("repository_identities") or {}
    identity = (identities.get("repositories") or {}).get("portfolio") or {}
    if identities.get("schema_version") != IDENTITY_SCHEMA:
        errors.append(f"repository identity schema must be {IDENTITY_SCHEMA}")
    expected_identity = {
        "github_repository_id": PORTFOLIO_REPOSITORY_ID,
        "canonical_slug": PORTFOLIO_CANONICAL_SLUG,
        "visibility": "public",
        "default_branch": "main",
        "archived": False,
        "source": f"https://api.github.com/repositories/{PORTFOLIO_REPOSITORY_ID}",
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            errors.append(f"portfolio repository identity {key} must be {expected!r}")
    if identity.get("previous_slugs") != [PORTFOLIO_RETIRED_SLUG]:
        errors.append("portfolio repository identity must retain exactly the retired slug as history")
    if "immutable GitHub repository ID" not in str(identity.get("resolution_rule") or ""):
        errors.append("portfolio identity must require immutable-ID resolution")

    work_rows = _work_rows(program)
    retired_work = [row.get("id") for row in work_rows if row.get("target_repo") == PORTFOLIO_RETIRED_SLUG]
    if retired_work:
        errors.append(f"work packets still use the retired portfolio slug: {', '.join(map(str, retired_work))}")
    canonical_work_ids = [
        str(row.get("id")) for row in work_rows if row.get("target_repo") == PORTFOLIO_CANONICAL_SLUG
    ]

    relay = artifact.get("repository_drift_relay") or {}
    if relay.get("stable_repository_id") != PORTFOLIO_REPOSITORY_ID:
        errors.append("repository-drift relay must carry the stable portfolio repository ID")
    if relay.get("canonical_slug") != PORTFOLIO_CANONICAL_SLUG:
        errors.append("repository-drift relay must carry the canonical portfolio slug")
    if relay.get("live_issue_projection_updated") is not False:
        errors.append("formalization must not claim live issue projection was updated")
    if relay.get("projection_status") != PROJECTION_STATUS:
        errors.append("repository-drift relay must remain projection_pending")
    if relay.get("affected_work_ids") != canonical_work_ids:
        errors.append("repository-drift relay work IDs must match canonical manifest targets in order")
    if relay.get("affected_issue_body_count") != len(canonical_work_ids):
        errors.append("repository-drift relay count must match canonical manifest targets")

    receipt_identity = receipt.get("portfolio_repository_identity") or {}
    if receipt_identity.get("github_repository_id") != PORTFOLIO_REPOSITORY_ID:
        errors.append("live receipt must carry the stable portfolio repository ID")
    if receipt_identity.get("canonical_slug") != PORTFOLIO_CANONICAL_SLUG:
        errors.append("live receipt must carry the canonical portfolio slug")
    if receipt_identity.get("projection_refresh_performed") is not False:
        errors.append("live receipt must record that issue projection was not performed")
    if receipt_identity.get("projection_status") != PROJECTION_STATUS:
        errors.append("live receipt must retain projection_pending")
    if receipt_identity.get("confirmed_private_target_changed") is not False:
        errors.append("the confirmed private collaboration target must remain unchanged")

    issues = issue_map.get("issues") or {}
    expected_issue_rows = []
    for work_id in canonical_work_ids:
        mapped = issues.get(work_id) or {}
        number = mapped.get("number")
        if not isinstance(number, int):
            errors.append(f"{work_id} is missing its generated issue number")
            continue
        expected_issue_rows.append({"work_id": work_id, "issue": number})
        expected_index_fragment = f"| `{work_id}` "
        if expected_index_fragment not in issue_index or PORTFOLIO_CANONICAL_SLUG not in next(
            (line for line in issue_index.splitlines() if expected_index_fragment in line), ""
        ):
            errors.append(f"generated issue index does not project the canonical target for {work_id}")
    if receipt_identity.get("live_issue_bodies_requiring_refresh") != expected_issue_rows:
        errors.append("live issue-body refresh list must match the generated issue map")
    if PORTFOLIO_RETIRED_SLUG in issue_index:
        errors.append("generated issue index still contains the retired portfolio slug")

    public_profile = receipt.get("public_profile") or {}
    manifest = public_profile.get("stats_manifest") or {}
    rendered = manifest.get("rendered_values") or {}
    if not HEAD_RE.fullmatch(str(public_profile.get("head") or "")):
        errors.append("public-profile receipt needs an exact 40-character head")
    if rendered.get("personal_public_repositories") != 8:
        errors.append("profile manifest personal public repository count must be 8")
    if rendered.get("ecosystem_public_repositories") != 227:
        errors.append("profile manifest organization public repository count must be 227")
    if rendered.get("ecosystem_original_repositories") != 198:
        errors.append("profile manifest original repository count must be 198")

    api_receipts = {
        row.get("id"): row for row in receipt.get("api_query_receipts") or [] if isinstance(row, dict)
    }
    org_public = api_receipts.get("public_organization_repository_counts") or {}
    org_original = api_receipts.get("public_original_organization_repository_counts") or {}
    contribution_receipt = api_receipts.get("contribution_calendar_fresh_observation") or {}
    contributions = contribution_receipt.get("result") or {}
    w01_result = (api_receipts.get("w01_public_safe_census") or {}).get("result") or {}
    if sum((org_public.get("counts") or {}).values()) != 227 or org_public.get("total") != 227:
        errors.append("fresh public organization repository counts must sum to 227")
    if sum((org_original.get("counts") or {}).values()) != 198 or org_original.get("total") != 198:
        errors.append("fresh public original repository counts must sum to 198")
    rendered_contributions = rendered.get("contributions_last_year")
    total_contributions = contributions.get("total_contributions")
    sum_of_daily_counts = contributions.get("sum_of_daily_counts")
    if not _nonnegative_integer(rendered_contributions):
        errors.append("rendered contribution count must be a non-negative integer")
    elif rendered_contributions != PROFILE_RENDERED_CONTRIBUTIONS:
        errors.append(
            f"rendered contribution count must preserve the adjudicated {PROFILE_RENDERED_CONTRIBUTIONS} observation"
        )
    if not _nonnegative_integer(total_contributions) or not _nonnegative_integer(sum_of_daily_counts):
        errors.append("fresh contribution total and daily-count sum must be non-negative integers")
    elif total_contributions != sum_of_daily_counts:
        errors.append("fresh contribution total must equal its daily-count sum")
    elif total_contributions != PROFILE_FRESH_CONTRIBUTIONS:
        errors.append(
            f"fresh contribution total must preserve the recorded {PROFILE_FRESH_CONTRIBUTIONS} observation"
        )
    contribution_observed_at = _rfc3339(contribution_receipt.get("observed_at"))
    contribution_start = _iso_date(contributions.get("starts_at"))
    contribution_end = _iso_date(contributions.get("ends_at"))
    if contribution_observed_at is None or contribution_start is None or contribution_end is None:
        errors.append("fresh contribution observation needs valid dates and an RFC3339 observation time")
    elif contribution_end != contribution_observed_at.date() or contribution_end - contribution_start != timedelta(
        days=365
    ):
        errors.append("fresh contribution observation must cover the recorded trailing-year window")
    if contribution_receipt.get("source") != (
        "https://docs.github.com/en/graphql/reference/users#contributioncalendar"
    ) or not _text(contribution_receipt.get("reproduction")):
        errors.append("fresh contribution observation must retain its public source and reproduction")
    contribution_claim = next(
        (claim for claim in claims if isinstance(claim, dict) and claim.get("id") == "profile-contributions-last-year"),
        {},
    )
    if contribution_claim.get("exact_public_wording") != PROFILE_CONTRIBUTION_WORDING or (
        f"{PROFILE_RENDERED_CONTRIBUTIONS:,}"
        not in str((contribution_claim.get("w05_integration") or {}).get("public_wording") or "")
    ):
        errors.append("contribution claim wording must remain bound to the rendered observation")
    if w01_result.get("public_repository_count") != 8 + 227:
        errors.append("W01 public count must reconcile 8 personal plus 227 organization repositories")

    http_rows = receipt.get("http_receipts") or []
    http = {row.get("id"): row for row in http_rows if isinstance(row, dict)}
    if len(http_rows) != len(http) or set(http) != set(EXPECTED_HTTP_RECEIPTS):
        errors.append("HTTP receipts must contain each expected endpoint exactly once")
    for receipt_id, (expected_url, expected_status) in EXPECTED_HTTP_RECEIPTS.items():
        row = http.get(receipt_id) or {}
        if row.get("url") != expected_url or not _credential_free_https_url(row.get("url")):
            errors.append(f"HTTP receipt {receipt_id} must bind the exact credential-free endpoint URL")
        if row.get("status") != expected_status:
            errors.append(f"HTTP receipt {receipt_id} must preserve observed status {expected_status}")
        if _rfc3339(row.get("observed_at")) is None:
            errors.append(f"HTTP receipt {receipt_id} needs an RFC3339 observation time")
        reproduction = row.get("reproduction")
        if not _text(reproduction) or "curl " not in str(reproduction) or expected_url not in str(reproduction):
            errors.append(f"HTTP receipt {receipt_id} must reproduce the exact endpoint URL")

    daily = receipt.get("daily_generation_receipt") or {}
    runs = daily.get("runs") or []
    if daily.get("scheduled_runs_observed") != 8 or daily.get("successful_runs") != 8 or len(runs) != 8:
        errors.append("daily generation receipt must contain eight observed successful runs")
    window_start = _rfc3339(daily.get("window_start"))
    window_end = _rfc3339(daily.get("window_end"))
    if window_start is None or window_end is None or window_start > window_end:
        errors.append("daily generation receipt needs a valid bounded observation window")
    run_ids: set[int] = set()
    run_urls: set[str] = set()
    run_times: list[datetime] = []
    for row in runs:
        if not isinstance(row, dict):
            errors.append("every daily generation run must be a mapping")
            continue
        run_id = row.get("run_id")
        if not isinstance(run_id, int) or isinstance(run_id, bool) or run_id <= 0:
            errors.append("every daily generation run needs a positive integer run_id")
            continue
        expected_url = f"https://github.com/4444J99/4444J99/actions/runs/{run_id}"
        if row.get("url") != expected_url or not _credential_free_https_url(row.get("url")):
            errors.append(f"daily generation run {run_id} must bind its exact credential-free URL")
        if row.get("event") != "schedule":
            errors.append(f"daily generation run {run_id} must record event=schedule")
        if row.get("conclusion") != "success":
            errors.append(f"daily generation run {run_id} must be a success")
        if not HEAD_RE.fullmatch(str(row.get("resulting_head") or "")):
            errors.append(f"daily generation run {run_id} needs an exact resulting head")
        created_at = _rfc3339(row.get("created_at"))
        if created_at is None:
            errors.append(f"daily generation run {run_id} needs an RFC3339 creation time")
        else:
            run_times.append(created_at)
        run_ids.add(run_id)
        run_urls.add(str(row.get("url") or ""))
    if len(run_ids) != len(runs) or len(run_urls) != len(runs):
        errors.append("daily generation runs must use distinct run IDs and URLs")
    if window_start is not None and window_end is not None and run_times:
        if any(created_at < window_start or created_at > window_end for created_at in run_times):
            errors.append("daily generation run times must fall inside the observation window")
        observed_days = sorted({created_at.date() for created_at in run_times})
        expected_days = [observed_days[0] + timedelta(days=offset) for offset in range(8)]
        if len(observed_days) != 8 or observed_days != expected_days:
            errors.append("daily generation receipt must contain one scheduled run on eight consecutive UTC days")
        elif window_start.date() != observed_days[0] or window_end.date() != observed_days[-1]:
            errors.append("daily generation window must bind the first and last observed UTC days")

    ledger = receipt.get("claims_ledger_integration") or {}
    if ledger.get("ledger_edited_in_this_lane") is not False or ledger.get("accepted_by") != "PSP-P02-W05":
        errors.append("formalization must consume, but not mutate, the accepted W05 claims ledger")
    if ledger.get("accepted_head") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["accepted_head"]:
        errors.append("claims-ledger integration must bind the accepted W05 head")
    if ledger.get("accepted_blob") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["claims_ledger_blob"]:
        errors.append("claims-ledger integration must bind the accepted W05 blob")
    if ledger.get("marked_receipt") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["marked_receipt"]:
        errors.append("claims-ledger integration must bind the accepted W05 marked receipt")
    if ledger.get("claim_projection") != "exact_match_13_claims_four_layers_and_publishable_fields":
        errors.append("claims-ledger integration must record the exact 13-claim comparison")
    if ledger.get("integration_artifact") != str(ARTIFACT_PATH.relative_to(ROOT)):
        errors.append("receipt must point to the tracked formalization artifact")

    required_doc_fragments = (
        str(PORTFOLIO_REPOSITORY_ID),
        PORTFOLIO_CANONICAL_SLUG,
        "13 research-rebuked claims",
        "all eight LAVREA axes",
        ACCEPTED_DEPENDENCIES["PSP-P02-W01"]["accepted_head"],
        ACCEPTED_DEPENDENCIES["PSP-P02-W01"]["marked_receipt"],
        ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["accepted_head"],
        ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["marked_receipt"],
        ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["claims_ledger_blob"],
        "formal-ready",
        PROJECTION_STATUS,
        "#2205–#2211",
        "#2261",
    )
    for fragment in required_doc_fragments:
        if fragment not in research_doc:
            errors.append(f"research adjudication summary is missing {fragment!r}")
    return errors


def _gh_json(args: list[str]) -> Any:
    result = subprocess.run(
        ["gh", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if result.returncode != 0:
        raise AdjudicationError((result.stderr or result.stdout or "GitHub query failed").strip())
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AdjudicationError("GitHub query returned invalid JSON") from exc


def validate_live_identity(
    program: dict[str, Any],
    fetch: Callable[[list[str]], Any] = _gh_json,
) -> list[str]:
    """Resolve the portfolio by immutable repository ID and compare canonical live metadata."""

    errors: list[str] = []
    identity = ((program.get("repository_identities") or {}).get("repositories") or {}).get("portfolio") or {}
    repository_id = identity.get("github_repository_id")
    if repository_id != PORTFOLIO_REPOSITORY_ID:
        return ["cannot verify live identity without the expected stable repository ID"]
    try:
        live = fetch(["api", f"repositories/{repository_id}"])
    except AdjudicationError as exc:
        return [f"cannot resolve stable repository identity: {exc}"]
    expectations = {
        "id": repository_id,
        "full_name": identity.get("canonical_slug"),
        "visibility": identity.get("visibility"),
        "default_branch": identity.get("default_branch"),
        "archived": identity.get("archived"),
    }
    for key, expected in expectations.items():
        if live.get(key) != expected:
            errors.append(f"stable repository ID resolves {key}={live.get(key)!r}, expected {expected!r}")
    if live.get("private") is not False:
        errors.append("stable portfolio repository must remain public")
    if (live.get("permissions") or {}).get("admin") is not True:
        errors.append("authenticated live identity receipt no longer has admin access")
    return errors


def validate_live_dependencies(
    fetch: Callable[[list[str]], Any] = _gh_json,
) -> list[str]:
    """Bind the latest marked W01/W05 receipts to their accepted exact heads."""

    errors: list[str] = []
    for work_id, expected in ACCEPTED_DEPENDENCIES.items():
        issue_number = expected["issue_number"]
        try:
            issue = fetch(["api", f"repos/organvm/limen/issues/{issue_number}"])
            comments = fetch(
                ["api", f"repos/organvm/limen/issues/{issue_number}/comments?per_page=100"]
            )
        except AdjudicationError as exc:
            errors.append(f"cannot resolve accepted {work_id} receipt: {exc}")
            continue
        if not isinstance(issue, dict) or issue.get("state") != "closed":
            errors.append(f"accepted dependency {work_id} issue must remain closed")
        if not isinstance(comments, list):
            errors.append(f"accepted dependency {work_id} comments must be a list")
            continue
        marker = f"<!-- positioning-receipt:{work_id} -->"
        marked = [row for row in comments if isinstance(row, dict) and marker in str(row.get("body") or "")]
        if not marked:
            errors.append(f"accepted dependency {work_id} has no marked receipt")
            continue
        latest = max(marked, key=lambda row: int(row.get("id") or 0))
        if latest.get("html_url") != expected["marked_receipt"]:
            errors.append(f"accepted dependency {work_id} latest marked receipt URL differs")
        blocks = RECEIPT_BLOCK_RE.findall(str(latest.get("body") or ""))
        parsed: list[dict[str, Any]] = []
        for block in blocks:
            try:
                value = json.loads(block)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and value.get("work_id") == work_id:
                parsed.append(value)
        if len(parsed) != 1:
            errors.append(f"accepted dependency {work_id} latest marked comment needs one receipt block")
            continue
        receipt = parsed[0]
        if _canonical_sha256(receipt) != expected["canonical_receipt_sha256"]:
            errors.append(f"accepted dependency {work_id} canonical receipt SHA-256 differs")
        if receipt.get("outcome") != "succeeded":
            errors.append(f"accepted dependency {work_id} receipt outcome must remain succeeded")
        observed_head = (receipt.get("observed_heads") or {}).get("organvm/limen")
        if observed_head != expected["accepted_head"]:
            errors.append(f"accepted dependency {work_id} observed head differs")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate static adjudication and relay artifacts")
    parser.add_argument("--verify-live", action="store_true", help="also resolve the portfolio by immutable GitHub ID")
    args = parser.parse_args()
    if not args.check and not args.verify_live:
        parser.error("one of --check or --verify-live is required")

    try:
        artifact = _load_json(ARTIFACT_PATH)
        receipt = _load_json(RECEIPT_PATH)
        program = _load_yaml(PROGRAM_PATH)
        issue_map = _load_json(ISSUE_MAP_PATH)
        issue_index = ISSUE_INDEX_PATH.read_text(encoding="utf-8")
        research_doc = RESEARCH_DOC_PATH.read_text(encoding="utf-8")
        flagship_evidence = _load_yaml(FLAGSHIP_EVIDENCE_PATH)
        claims_ledger = CLAIMS_LEDGER_PATH.read_text(encoding="utf-8")
    except (AdjudicationError, OSError) as exc:
        print(f"research-adjudication: FAIL: {exc}", file=sys.stderr)
        return 1

    errors = validate_bundle(
        artifact,
        receipt,
        program,
        issue_map,
        issue_index,
        research_doc,
        flagship_evidence,
        claims_ledger,
    )
    if args.verify_live and not errors:
        errors.extend(validate_live_identity(program))
        errors.extend(validate_live_dependencies())
    if errors:
        for error in errors:
            print(f"research-adjudication: FAIL: {error}", file=sys.stderr)
        return 1

    mode = "live" if args.verify_live else "static"
    print(
        "research-adjudication: PASS: "
        f"{len(artifact['claims'])} claims, {len(artifact['lavrea_axis_audit'])} LAVREA axes, "
        f"{artifact['repository_drift_relay']['affected_issue_body_count']} issue projections ({mode})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
