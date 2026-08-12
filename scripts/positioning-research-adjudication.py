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
from urllib.parse import quote, unquote, urlsplit

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
CREDENTIAL_METADATA_RE = re.compile(
    r"(?:authorization\s*:|bearer\s+[A-Za-z0-9._~-]+|(?:access[-_]?token|token|api[-_]?key|password|passwd|secret)\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
EXPECTED_CLAIM_COUNT = 13
EXPECTED_API_RECEIPT_IDS = {
    "profile_metadata",
    "public_organization_repository_counts",
    "public_original_organization_repository_counts",
    "contribution_calendar_fresh_observation",
    "w01_public_safe_census",
}
EXPECTED_ORGANIZATION_KEYS = {
    "a-organvm",
    "meta-organvm",
    "organvm",
    "organvm-i-theoria",
    "organvm-ii-poiesis",
    "organvm-iii-ergon",
    "organvm-iv-taxis",
    "organvm-v-logos",
    "organvm-vi-koinonia",
    "organvm-vii-kerygma",
}
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
        "flagship_evidence_path": "docs/positioning/evidence/flagship-evidence.yaml",
        "flagship_evidence_blob": "ce59d44794f44e0511436cbabbcd4fba1a938891",
    },
}
RECEIPT_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
PROFILE_RENDERED_CONTRIBUTIONS = 33130
PROFILE_FRESH_CONTRIBUTIONS = 33168
PROFILE_CONTRIBUTION_WORDING = "33,130 contributions in the last year"
EXPECTED_PROFILE_METADATA_RESULT = {
    "login": "4444J99",
    "id": 24796448,
    "type": "User",
    "public_repos": 8,
    "followers": 41,
    "following": 61,
    "created_at": "2016-12-27T17:24:06Z",
    "updated_at": "2026-08-09T16:58:24Z",
    "blog": "https://organvm.github.io/portfolio/",
}
LIVE_REFERENCE_ISSUE_NUMBER = 1245
LIVE_REFERENCE_URL = f"https://github.com/organvm/limen/issues/{LIVE_REFERENCE_ISSUE_NUMBER}"
LIVE_REFERENCE_API_URL = (
    f"https://api.github.com/repos/organvm/limen/issues/{LIVE_REFERENCE_ISSUE_NUMBER}"
)
EXPECTED_LIVE_REFERENCE = {
    "issue": LIVE_REFERENCE_URL,
    "issue_state": "open",
    "role": "profile-engine follow-up owner; it does not replace the post-merge projection gate",
}
EXPECTED_HTTP_RECEIPTS = {
    "current_profile_blog_field": ("https://organvm.github.io/portfolio/", 404),
    "canonical_transferred_portfolio_pages": (
        "https://organvm-vii-kerygma.github.io/portfolio/",
        200,
    ),
}
EXPECTED_PUBLIC_SOURCES: dict[str, dict[str, object]] = {
    "PROFILE_README": {
        "repository": "4444J99/4444J99",
        "path": "README.md",
        "head": "f198b37e3161121e7c198e21bd18b87e29b6bc4f",
        "blob": "b006a06c2a7e9f84166b0fd7fad638a5c36c356f",
        "url": "https://github.com/4444J99/4444J99/blob/f198b37e3161121e7c198e21bd18b87e29b6bc4f/README.md",
    },
    "PROFILE_MANIFEST": {
        "repository": "4444J99/4444J99",
        "path": "assets/stats-manifest.json",
        "head": "f198b37e3161121e7c198e21bd18b87e29b6bc4f",
        "blob": "668c09daab5f63882e9fd6b848ab9d0017a65ae5",
        "url": "https://github.com/4444J99/4444J99/blob/f198b37e3161121e7c198e21bd18b87e29b6bc4f/assets/stats-manifest.json",
    },
    "PROFILE_WORKFLOW": {
        "repository": "4444J99/4444J99",
        "path": ".github/workflows/profile.yml",
        "head": "f198b37e3161121e7c198e21bd18b87e29b6bc4f",
        "url": "https://github.com/4444J99/4444J99/blob/f198b37e3161121e7c198e21bd18b87e29b6bc4f/.github/workflows/profile.yml",
    },
    "PROFILE_API_RECEIPT": {"url": "https://api.github.com/users/4444J99"},
    "PROFILE_RUNS": {
        "repository": "4444J99/4444J99",
        "path": ".github/workflows/profile.yml",
        "url": "https://github.com/4444J99/4444J99/actions/workflows/profile.yml",
    },
    "W01_CENSUS_RECEIPT": {
        "repository": "organvm/limen",
        "path": "docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json",
        "head": ACCEPTED_DEPENDENCIES["PSP-P02-W01"]["accepted_head"],
        "blob": ACCEPTED_DEPENDENCIES["PSP-P02-W01"]["tracked_receipt_blob"],
        "url": "https://github.com/organvm/limen/blob/10cf8476d5e88309c71d5fac25167ec7b7af59c4/docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json",
    },
    "W03_PROOF_SET": {
        "repository": "organvm/limen",
        "path": "docs/positioning/flagship-proof-set.yaml",
        "head": "0de48d3f5dc15b9bae61cbf49eeba9a9eed59ba2",
        "blob": "120529ab75d797c2e28c693d8bfc2d042428dd49",
        "url": "https://github.com/organvm/limen/blob/0de48d3f5dc15b9bae61cbf49eeba9a9eed59ba2/docs/positioning/flagship-proof-set.yaml",
    },
    "CLAIMS_LEDGER": {
        "repository": "organvm/limen",
        "path": ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["claims_ledger_path"],
        "head": ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["accepted_head"],
        "blob": ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["claims_ledger_blob"],
        "url": "https://github.com/organvm/limen/blob/d8b44e60e404b044436addf8108732cc28c06371/docs/positioning/claims-ledger.md",
    },
    "W05_FLAGSHIP_EVIDENCE": {
        "repository": "organvm/limen",
        "path": ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["flagship_evidence_path"],
        "head": ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["accepted_head"],
        "blob": ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["flagship_evidence_blob"],
        "url": "https://github.com/organvm/limen/blob/d8b44e60e404b044436addf8108732cc28c06371/docs/positioning/evidence/flagship-evidence.yaml",
    },
    "LAVREA_METHODOLOGY": {
        "repository": "organvm/laurea",
        "path": "METHODOLOGY.md",
        "head": "02e360c9828336ac95ce8223c65d127ffea27661",
        "blob": "b671568236f386041a416d28964b50820249ac2a",
        "url": "https://github.com/organvm/laurea/blob/02e360c9828336ac95ce8223c65d127ffea27661/METHODOLOGY.md",
    },
    "LAVREA_BASELINES": {
        "repository": "organvm/laurea",
        "path": "src/laurea/baselines.py",
        "head": "02e360c9828336ac95ce8223c65d127ffea27661",
        "blob": "c66c496a9b0c647876bbe09a5d10dde80708c689",
        "url": "https://github.com/organvm/laurea/blob/02e360c9828336ac95ce8223c65d127ffea27661/src/laurea/baselines.py",
    },
    "GITHUB_CONTRIBUTIONS": {
        "url": "https://docs.github.com/en/account-and-profile/reference/profile-contributions-reference"
    },
    "GITHUB_GRAPHQL": {
        "url": "https://docs.github.com/en/graphql/reference/users#contributioncalendar"
    },
    "GITHUB_REPOSITORIES": {"url": "https://docs.github.com/en/rest/repos/repos"},
    "GITHUB_TRANSFER": {
        "url": "https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository"
    },
    "GITHUB_OCTOVERSE_2023": {
        "url": "https://github.blog/news-insights/research/the-state-of-open-source-and-ai/"
    },
    "PORTFOLIO_IDENTITY": {
        "repository": PORTFOLIO_CANONICAL_SLUG,
        "repository_id": PORTFOLIO_REPOSITORY_ID,
        "url": f"https://api.github.com/repositories/{PORTFOLIO_REPOSITORY_ID}",
    },
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
EXPECTED_LAVREA_AXIS_CONTRACTS = {
    "contributions_year": {
        "measurement_disposition": "retain_dated_measurement",
        "inference_disposition": "withhold_percentile",
        "primary_source_result": "GitHub defines contribution-calendar counts; Octoverse account totals do not establish the 5,000 or 20,000 percentile thresholds.",
        "citations": [
            "GITHUB_CONTRIBUTIONS",
            "GITHUB_GRAPHQL",
            "GITHUB_OCTOVERSE_2023",
            "LAVREA_BASELINES",
        ],
    },
    "pull_requests_year": {
        "measurement_disposition": "retain_dated_measurement",
        "inference_disposition": "withhold_percentile",
        "primary_source_result": "The public sources inspected do not supply a sampled active-developer distribution supporting the 500 or 2,000 thresholds.",
        "citations": ["LAVREA_BASELINES", "GITHUB_OCTOVERSE_2023"],
    },
    "repos_owned": {
        "measurement_disposition": "refresh_from_public_safe_census",
        "inference_disposition": "withhold_percentile",
        "primary_source_result": "GitHub's repository APIs support counts, not the claimed 50/200 percentile placement; W01 is the safe current count authority.",
        "citations": ["GITHUB_REPOSITORIES", "W01_CENSUS_RECEIPT", "LAVREA_BASELINES"],
    },
    "language_breadth": {
        "measurement_disposition": "retain_rule_labeled_measurement",
        "inference_disposition": "withhold_percentile",
        "primary_source_result": "Primary-language counts are reproducible under a declared rule, but no cited primary distribution establishes the 6/10 thresholds.",
        "citations": ["LAVREA_METHODOLOGY", "LAVREA_BASELINES"],
    },
    "orgs_operated": {
        "measurement_disposition": "narrow_to_membership_and_owned_repository_facts",
        "inference_disposition": "withhold_percentile",
        "primary_source_result": "W01 establishes ten memberships and repository ownership counts; 'operated' and the 3/8 percentile thresholds require separate definitions and population evidence.",
        "citations": ["W01_CENSUS_RECEIPT", "LAVREA_BASELINES"],
    },
    "full_stack_coverage": {
        "measurement_disposition": "retain_rule_labeled_measurement",
        "inference_disposition": "withhold_percentile",
        "primary_source_result": "The language-to-layer mapping is a local working definition, not a primary population ranking.",
        "citations": ["LAVREA_METHODOLOGY"],
    },
    "composite_python_full_stack": {
        "measurement_disposition": "retain_constituent_measurements",
        "inference_disposition": "withhold_percentile",
        "primary_source_result": "The conjunction cannot inherit an unproven percentile floor; constituent percentile premises must be validated first.",
        "citations": ["LAVREA_METHODOLOGY", "LAVREA_BASELINES"],
    },
    "tenure": {
        "measurement_disposition": "retain_dated_measurement",
        "inference_disposition": "no_percentile_claim",
        "primary_source_result": "Account creation time is a direct public API fact and LAVREA does not assign it a percentile.",
        "citations": ["PROFILE_API_RECEIPT", "LAVREA_METHODOLOGY"],
    },
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


def _string_token_list(value: object) -> bool:
    """Return whether value is a nonempty list of nonempty string tokens."""

    return isinstance(value, list) and bool(value) and all(_text(item) for item in value)


def _exact_typed_mapping(value: object, expected: dict[str, object]) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == set(expected)
        and all(type(value[key]) is type(expected[key]) and value[key] == expected[key] for key in expected)
    )


def _mapping(value: object, label: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} must be a mapping")
        return {}
    return value


def _list(value: object, label: str, errors: list[str]) -> list[Any]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    return value


def _safe_public_metadata(value: object) -> bool:
    return _text(value) and CREDENTIAL_METADATA_RE.search(str(value)) is None


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


def _git_blob_oid_bytes(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _git_blob_oid(path: Path) -> str:
    return _git_blob_oid_bytes(path.read_bytes())


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
    flagship_evidence_text: str,
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
    formalization = _mapping(artifact.get("formalization"), "artifact.formalization", errors)
    if formalization.get("readiness") != "formal_ready":
        errors.append("artifact formalization must be formal-ready")
    if formalization.get("projection_status") != PROJECTION_STATUS:
        errors.append("artifact must remain projection_pending")
    formalization_dependencies = _list(
        formalization.get("accepted_dependencies"),
        "artifact.formalization.accepted_dependencies",
        errors,
    )
    for index, dependency in enumerate(formalization_dependencies):
        _mapping(dependency, f"artifact.formalization.accepted_dependencies[{index}]", errors)
    if formalization_dependencies != expected_dependencies:
        errors.append("artifact must bind the exact accepted W01 and W05 receipts")
    if formalization.get("post_merge_projection_command") != "python3 scripts/positioning-program.py --sync --apply":
        errors.append("artifact must retain the authorized post-merge projection command")
    if formalization.get("post_merge_verify_command") != "python3 scripts/positioning-program.py --verify-remote":
        errors.append("artifact must retain the post-merge remote-parity predicate")

    formal = _mapping(receipt.get("formal_completion"), "receipt.formal_completion", errors)
    if formal.get("allowed") is not False:
        errors.append("formal completion must remain false until post-merge projection parity")
    if formal.get("readiness") != "formal_ready":
        errors.append("receipt must record formal readiness")
    if formal.get("projection_status") != PROJECTION_STATUS:
        errors.append("receipt must remain projection_pending")
    dependencies = _list(formal.get("dependencies"), "receipt.formal_completion.dependencies", errors)
    if dependencies != expected_dependencies:
        errors.append("receipt must bind the exact accepted W01 and W05 receipts")
    for index, dependency_value in enumerate(dependencies):
        dependency = _mapping(
            dependency_value,
            f"receipt.formal_completion.dependencies[{index}]",
            errors,
        )
        if not dependency:
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
    if not isinstance(flagship_evidence_text, str):
        errors.append("flagship evidence source bytes must be text")
    else:
        if _git_blob_oid_bytes(flagship_evidence_text.encode()) != ACCEPTED_DEPENDENCIES[
            "PSP-P02-W05"
        ]["flagship_evidence_blob"]:
            errors.append("flagship-evidence blob differs from the accepted W05 binding")
        try:
            parsed_flagship_evidence = yaml.safe_load(flagship_evidence_text)
        except yaml.YAMLError:
            parsed_flagship_evidence = None
        if parsed_flagship_evidence != flagship_evidence:
            errors.append("flagship evidence mapping must match its tracked source bytes")
    live_reference = _mapping(
        formal.get("live_reference"),
        "receipt.formal_completion.live_reference",
        errors,
    )
    if live_reference != EXPECTED_LIVE_REFERENCE:
        errors.append("the profile-engine live reference must bind the exact open organvm/limen#1245 contract")

    privacy = _mapping(receipt.get("privacy_review"), "receipt.privacy_review", errors)
    if privacy.get("public_only") is not True:
        errors.append("receipt must be public-only")
    if privacy.get("private_repository_names") != 0 or privacy.get("private_only_sources") != 0:
        errors.append("receipt must declare zero private repository names and private-only sources")

    coverage = _mapping(artifact.get("coverage"), "artifact.coverage", errors)
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

    vocabularies = _mapping(
        artifact.get("disposition_vocabularies"),
        "artifact.disposition_vocabularies",
        errors,
    )
    disposition_tokens: dict[str, frozenset[str]] = {}
    for layer in LAYERS:
        vocabulary = vocabularies.get(layer)
        expected_vocabulary = list(DISPOSITION_VOCABULARIES[layer])
        if vocabulary != expected_vocabulary:
            errors.append(f"{layer} disposition vocabulary must match the canonical ordered vocabulary")
        disposition_tokens[layer] = (
            frozenset(vocabulary) if _string_token_list(vocabulary) else frozenset()
        )

    sources = artifact.get("sources")
    if not isinstance(sources, dict) or not sources:
        errors.append("sources must be a nonempty mapping")
        sources = {}
    if set(sources) != set(EXPECTED_PUBLIC_SOURCES):
        errors.append("sources must contain the exact expected public source ID set")
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
    for source_id, expected_source in EXPECTED_PUBLIC_SOURCES.items():
        source = _mapping(
            sources.get(source_id),
            f"artifact.sources.{source_id}",
            errors,
        )
        for key, expected in expected_source.items():
            if source.get(key) != expected:
                errors.append(f"source {source_id} must bind its exact public {key}")

    w01_source = _mapping(
        sources.get("W01_CENSUS_RECEIPT"),
        "artifact.sources.W01_CENSUS_RECEIPT",
        errors,
    )
    if (
        w01_source.get("head") != ACCEPTED_DEPENDENCIES["PSP-P02-W01"]["accepted_head"]
        or w01_source.get("blob") != ACCEPTED_DEPENDENCIES["PSP-P02-W01"]["tracked_receipt_blob"]
    ):
        errors.append("W01 source must bind the accepted head and tracked receipt blob")
    ledger_source = _mapping(
        sources.get("CLAIMS_LEDGER"),
        "artifact.sources.CLAIMS_LEDGER",
        errors,
    )
    if (
        ledger_source.get("head") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["accepted_head"]
        or ledger_source.get("blob") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["claims_ledger_blob"]
    ):
        errors.append("claims-ledger source must bind the accepted W05 head and blob")
    flagship_source = _mapping(
        sources.get("W05_FLAGSHIP_EVIDENCE"),
        "artifact.sources.W05_FLAGSHIP_EVIDENCE",
        errors,
    )
    if (
        flagship_source.get("head") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["accepted_head"]
        or flagship_source.get("blob")
        != ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["flagship_evidence_blob"]
    ):
        errors.append("flagship-evidence source must bind the accepted W05 head and blob")

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
            disposition = value.get("disposition")
            if not _text(disposition) or disposition not in disposition_tokens[layer]:
                errors.append(f"{prefix}.{layer} uses an unknown disposition")
            if not _text(value.get("rationale")):
                errors.append(f"{prefix}.{layer} needs a rationale")
            citations = value.get("citations")
            if not isinstance(citations, list) or not citations:
                errors.append(f"{prefix}.{layer} needs at least one citation")
            elif not _string_token_list(citations):
                errors.append(f"{prefix}.{layer} citations must be nonempty string source IDs")
            else:
                unknown = sorted(citation for citation in citations if citation not in sources)
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

        measurement = _mapping(claim.get("measurement"), f"{prefix}.measurement", errors)
        prominence = _mapping(claim.get("prominence"), f"{prefix}.prominence", errors)
        measurement_disposition = measurement.get("disposition")
        if (
            isinstance(measurement_disposition, str)
            and measurement_disposition in {"verified", "partially_verified"}
            and prominence.get("disposition") == "withhold"
        ):
            wording = str(integration.get("public_wording") if isinstance(integration, dict) else "").lower()
            if not any(token in wording for token in ("measurement", "github", "python", "language", "output")):
                errors.append(f"{prefix} withholds prominence without preserving its verified measurement")

    duplicates = sorted({claim_id for claim_id in claim_ids if claim_ids.count(claim_id) > 1})
    if duplicates:
        errors.append(f"duplicate claim ids: {', '.join(duplicates)}")

    artifact_projection = _artifact_claim_projection(claims)
    w05_import = _mapping(
        flagship_evidence.get("w08_research_import"),
        "flagship_evidence.w08_research_import",
        errors,
    )
    imported_claims = w05_import.get("claims")
    expected_import_keys = {
        "id",
        "layers",
        "publishable_status",
        "public_wording",
        "required_receipts",
    }
    if not isinstance(imported_claims, list):
        errors.append("flagship_evidence.w08_research_import.claims must be a list")
        imported_claims = []
    for index, imported_claim in enumerate(imported_claims):
        if not isinstance(imported_claim, dict):
            errors.append(f"flagship_evidence.w08_research_import.claims[{index}] must be a mapping")
    if len(imported_claims) != EXPECTED_CLAIM_COUNT:
        errors.append("accepted W05 import must contain exactly 13 claims")
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
    axis_tokens = [
        row.get("axis")
        for row in axes
        if isinstance(row, dict) and _text(row.get("axis"))
    ]
    axis_names = set(axis_tokens)
    if axis_names != LAVREA_AXES or len(axes) != len(LAVREA_AXES):
        errors.append("LAVREA audit must cover each of the eight axes exactly once")
    for index, row in enumerate(axes):
        if not isinstance(row, dict):
            continue
        axis = row.get("axis")
        if not _text(axis):
            errors.append(f"lavrea_axis_audit[{index}].axis must be a nonempty string token")
            axis = f"row[{index}]"
        if not _text(row.get("measurement_disposition")) or not _text(row.get("inference_disposition")):
            errors.append(f"LAVREA axis {axis} needs distinct measurement and inference dispositions")
        if not _text(row.get("primary_source_result")):
            errors.append(f"LAVREA axis {axis} needs a primary-source result")
        citations = row.get("citations")
        if not _string_token_list(citations) or any(citation not in sources for citation in citations):
            errors.append(f"LAVREA axis {axis} needs valid citations")
        expected_axis = EXPECTED_LAVREA_AXIS_CONTRACTS.get(axis) if isinstance(axis, str) else None
        if expected_axis is not None and any(row.get(key) != value for key, value in expected_axis.items()):
            errors.append(f"LAVREA axis {axis} must match its accepted exact conclusion contract")

    w05 = _mapping(artifact.get("w05_import_contract"), "artifact.w05_import_contract", errors)
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
    if w05.get("accepted_projection_blob") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"][
        "flagship_evidence_blob"
    ]:
        errors.append("W05 contract must bind the accepted flagship-evidence blob")
    if w05.get("source_claim_ids") != claim_ids:
        errors.append("W05 contract claim IDs must match adjudicated claim order")
    if "must not collapse" not in str(w05.get("import_rule") or ""):
        errors.append("W05 contract must forbid collapsing measurements into inferences")
    if "PSP-P02-W01" not in str(w05.get("completion_gate") or "") or "PSP-P02-W05" not in str(
        w05.get("completion_gate") or ""
    ):
        errors.append("W08 completion gate must name W01 and W05")

    identities = _mapping(program.get("repository_identities"), "program.repository_identities", errors)
    identity_rows = _mapping(
        identities.get("repositories"),
        "program.repository_identities.repositories",
        errors,
    )
    identity = _mapping(
        identity_rows.get("portfolio"),
        "program.repository_identities.repositories.portfolio",
        errors,
    )
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

    relay = _mapping(
        artifact.get("repository_drift_relay"),
        "artifact.repository_drift_relay",
        errors,
    )
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

    receipt_identity = _mapping(
        receipt.get("portfolio_repository_identity"),
        "receipt.portfolio_repository_identity",
        errors,
    )
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

    issues = _mapping(issue_map.get("issues"), "issue_map.issues", errors)
    expected_issue_rows = []
    for work_id in canonical_work_ids:
        mapped = _mapping(issues.get(work_id), f"issue_map.issues.{work_id}", errors)
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

    public_profile = _mapping(receipt.get("public_profile"), "receipt.public_profile", errors)
    profile_readme = _mapping(
        public_profile.get("readme"),
        "receipt.public_profile.readme",
        errors,
    )
    manifest = _mapping(
        public_profile.get("stats_manifest"),
        "receipt.public_profile.stats_manifest",
        errors,
    )
    rendered = _mapping(
        manifest.get("rendered_values"),
        "receipt.public_profile.stats_manifest.rendered_values",
        errors,
    )
    profile_head = public_profile.get("head")
    if not HEAD_RE.fullmatch(str(profile_head or "")):
        errors.append("public-profile receipt needs an exact 40-character head")
    profile_readme_source = _mapping(
        sources.get("PROFILE_README"),
        "artifact.sources.PROFILE_README",
        errors,
    )
    profile_manifest_source = _mapping(
        sources.get("PROFILE_MANIFEST"),
        "artifact.sources.PROFILE_MANIFEST",
        errors,
    )
    if profile_head != profile_readme_source.get("head") or profile_head != profile_manifest_source.get("head"):
        errors.append("public-profile head must exactly match the cited README and manifest heads")
    if profile_readme.get("blob") != profile_readme_source.get("blob"):
        errors.append("public-profile README blob must exactly match its cited source blob")
    if manifest.get("blob") != profile_manifest_source.get("blob"):
        errors.append("public-profile manifest blob must exactly match its cited source blob")
    if rendered.get("personal_public_repositories") != 8:
        errors.append("profile manifest personal public repository count must be 8")
    if rendered.get("ecosystem_public_repositories") != 227:
        errors.append("profile manifest organization public repository count must be 227")
    if rendered.get("ecosystem_original_repositories") != 198:
        errors.append("profile manifest original repository count must be 198")

    api_rows = _list(receipt.get("api_query_receipts"), "receipt.api_query_receipts", errors)
    api_receipts: dict[str, dict[str, Any]] = {}
    for index, row_value in enumerate(api_rows):
        row = _mapping(row_value, f"receipt.api_query_receipts[{index}]", errors)
        if not row:
            continue
        receipt_id = row.get("id")
        if not isinstance(receipt_id, str) or not receipt_id:
            errors.append(f"receipt.api_query_receipts[{index}] needs a nonempty id")
            continue
        if receipt_id in api_receipts:
            errors.append(f"API query receipt id {receipt_id} is duplicated")
        else:
            api_receipts[receipt_id] = row
        if not _credential_free_https_url(row.get("source")):
            errors.append(f"API query receipt {receipt_id} needs a credential-free HTTPS source")
        if _rfc3339(row.get("observed_at")) is None:
            errors.append(f"API query receipt {receipt_id} needs an RFC3339 observation time")
        metadata = [row[key] for key in ("reproduction", "query") if key in row]
        if not metadata or any(not _safe_public_metadata(value) for value in metadata):
            errors.append(
                f"API query receipt {receipt_id} needs safe nonempty reproduction or query metadata"
            )
    if len(api_rows) != len(EXPECTED_API_RECEIPT_IDS) or set(api_receipts) != EXPECTED_API_RECEIPT_IDS:
        errors.append("API query receipts must contain the exact unique expected ID set")

    profile_metadata = _mapping(
        api_receipts.get("profile_metadata"),
        "API query receipt profile_metadata",
        errors,
    )
    profile_metadata_result = profile_metadata.get("result")
    if not _exact_typed_mapping(profile_metadata_result, EXPECTED_PROFILE_METADATA_RESULT):
        errors.append("profile metadata result must match the exact typed public observation")
        profile_metadata_result = {}
    profile_claim = next(
        (
            claim
            for claim in claims
            if isinstance(claim, dict) and claim.get("id") == "profile-portfolio-link"
        ),
        {},
    )
    if (
        profile_metadata_result.get("login") != "4444J99"
        or profile_metadata_result.get("public_repos") != rendered.get("personal_public_repositories")
        or profile_metadata_result.get("blog") != EXPECTED_HTTP_RECEIPTS["current_profile_blog_field"][0]
        or profile_claim.get("exact_public_wording") != profile_metadata_result.get("blog")
        or _rfc3339(profile_metadata_result.get("created_at")) is None
        or _rfc3339(profile_metadata_result.get("updated_at")) is None
    ):
        errors.append("profile metadata result must reconcile identity, repository count, blog claim, and tenure inputs")

    org_public = _mapping(
        api_receipts.get("public_organization_repository_counts"),
        "API query receipt public_organization_repository_counts",
        errors,
    )
    org_original = _mapping(
        api_receipts.get("public_original_organization_repository_counts"),
        "API query receipt public_original_organization_repository_counts",
        errors,
    )
    for receipt_id, row, expected_total in (
        ("public_organization_repository_counts", org_public, 227),
        ("public_original_organization_repository_counts", org_original, 198),
    ):
        counts = _mapping(row.get("counts"), f"API query receipt {receipt_id}.counts", errors)
        if set(counts) != EXPECTED_ORGANIZATION_KEYS:
            errors.append(f"API query receipt {receipt_id} must contain the exact ten organization keys")
        if any(not _nonnegative_integer(count) for count in counts.values()):
            errors.append(f"API query receipt {receipt_id} counts must be non-negative integers")
        elif sum(counts.values()) != expected_total:
            errors.append(f"API query receipt {receipt_id} counts must sum to {expected_total}")
        if row.get("organization_count") != len(EXPECTED_ORGANIZATION_KEYS):
            errors.append(f"API query receipt {receipt_id} organization_count must be 10")
        if row.get("total") != expected_total:
            errors.append(f"API query receipt {receipt_id} total must be {expected_total}")

    contribution_receipt = _mapping(
        api_receipts.get("contribution_calendar_fresh_observation"),
        "API query receipt contribution_calendar_fresh_observation",
        errors,
    )
    contributions = _mapping(
        contribution_receipt.get("result"),
        "API query receipt contribution_calendar_fresh_observation.result",
        errors,
    )
    w01_receipt = _mapping(
        api_receipts.get("w01_public_safe_census"),
        "API query receipt w01_public_safe_census",
        errors,
    )
    w01_result = _mapping(
        w01_receipt.get("result"),
        "API query receipt w01_public_safe_census.result",
        errors,
    )
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
    contribution_integration = _mapping(
        contribution_claim.get("w05_integration"),
        "profile-contributions-last-year.w05_integration",
        errors,
    )
    if contribution_claim.get("exact_public_wording") != PROFILE_CONTRIBUTION_WORDING or (
        f"{PROFILE_RENDERED_CONTRIBUTIONS:,}"
        not in str(contribution_integration.get("public_wording") or "")
    ):
        errors.append("contribution claim wording must remain bound to the rendered observation")
    if w01_result.get("public_repository_count") != 8 + 227:
        errors.append("W01 public count must reconcile 8 personal plus 227 organization repositories")

    http_rows = _list(receipt.get("http_receipts"), "receipt.http_receipts", errors)
    http: dict[str, dict[str, Any]] = {}
    for index, row_value in enumerate(http_rows):
        row = _mapping(row_value, f"receipt.http_receipts[{index}]", errors)
        if not row:
            continue
        receipt_id = row.get("id")
        if not _text(receipt_id):
            errors.append(f"receipt.http_receipts[{index}] needs a nonempty string id")
            continue
        if receipt_id in http:
            errors.append(f"HTTP receipt id {receipt_id} is duplicated")
            continue
        http[receipt_id] = row
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

    daily = _mapping(
        receipt.get("daily_generation_receipt"),
        "receipt.daily_generation_receipt",
        errors,
    )
    runs = _list(daily.get("runs"), "receipt.daily_generation_receipt.runs", errors)
    if daily.get("scheduled_runs_observed") != 8 or daily.get("successful_runs") != 8 or len(runs) != 8:
        errors.append("daily generation receipt must contain eight observed successful runs")
    window_start = _rfc3339(daily.get("window_start"))
    window_end = _rfc3339(daily.get("window_end"))
    if window_start is None or window_end is None or window_start > window_end:
        errors.append("daily generation receipt needs a valid bounded observation window")
    run_ids: set[int] = set()
    run_urls: set[str] = set()
    run_times: list[datetime] = []
    run_observations: list[tuple[datetime, dict[str, Any]]] = []
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
            run_observations.append((created_at, row))
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
    if run_observations:
        latest_run = max(run_observations, key=lambda item: item[0])[1]
        if latest_run.get("resulting_head") != profile_head:
            errors.append("public-profile head must exactly match the latest scheduled run resulting_head")

    ledger = _mapping(
        receipt.get("claims_ledger_integration"),
        "receipt.claims_ledger_integration",
        errors,
    )
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
    if ledger.get("accepted_projection_blob") != ACCEPTED_DEPENDENCIES["PSP-P02-W05"][
        "flagship_evidence_blob"
    ]:
        errors.append("claims-ledger integration must bind the accepted flagship-evidence projection blob")

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
        ACCEPTED_DEPENDENCIES["PSP-P02-W05"]["flagship_evidence_blob"],
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
    try:
        result = subprocess.run(
            ["gh", *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise AdjudicationError("GitHub query timed out after 60 seconds") from exc
    except OSError as exc:
        raise AdjudicationError(f"cannot start GitHub query: {exc}") from exc
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
    repository_identities = program.get("repository_identities")
    if not isinstance(repository_identities, dict):
        return ["cannot verify live identity without a repository-identities mapping"]
    repositories = repository_identities.get("repositories")
    if not isinstance(repositories, dict):
        return ["cannot verify live identity without a repository-identities repository mapping"]
    identity = repositories.get("portfolio")
    if not isinstance(identity, dict):
        return ["cannot verify live identity without a portfolio repository-identity mapping"]
    repository_id = identity.get("github_repository_id")
    if repository_id != PORTFOLIO_REPOSITORY_ID:
        return ["cannot verify live identity without the expected stable repository ID"]
    try:
        live = fetch(["api", f"repositories/{repository_id}"])
    except AdjudicationError as exc:
        return [f"cannot resolve stable repository identity: {exc}"]
    if not isinstance(live, dict):
        return ["stable repository identity response must be a mapping"]
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
    permissions = live.get("permissions")
    if not isinstance(permissions, dict):
        errors.append("stable repository identity permissions must be a mapping")
    elif permissions.get("admin") is not True:
        errors.append("authenticated live identity receipt no longer has admin access")
    return errors


def validate_live_sources(
    artifact: dict[str, Any],
    fetch: Callable[[list[str]], Any] = _gh_json,
) -> list[str]:
    """Verify repository-backed accepted sources remain public and path-addressable."""

    sources = artifact.get("sources")
    if not isinstance(sources, dict):
        return ["cannot verify public sources without a source mapping"]
    errors: list[str] = []
    repositories = sorted(
        {
            str(expected["repository"])
            for expected in EXPECTED_PUBLIC_SOURCES.values()
            if "repository" in expected
        }
    )
    for repository in repositories:
        try:
            live_repository = fetch(["api", f"repos/{repository}"])
        except AdjudicationError as exc:
            errors.append(f"cannot verify public source repository {repository}: {exc}")
            continue
        if not isinstance(live_repository, dict):
            errors.append(f"public source repository {repository} response must be a mapping")
            continue
        if (
            live_repository.get("full_name") != repository
            or live_repository.get("private") is not False
            or live_repository.get("visibility") != "public"
        ):
            errors.append(f"public source repository {repository} must resolve as that exact public repository")

    for source_id, expected in EXPECTED_PUBLIC_SOURCES.items():
        repository = expected.get("repository")
        path = expected.get("path")
        head = expected.get("head")
        if not all(isinstance(value, str) for value in (repository, path, head)):
            continue
        endpoint = f"repos/{repository}/contents/{quote(path, safe='/')}?ref={head}"
        try:
            live_content = fetch(["api", endpoint])
        except AdjudicationError as exc:
            errors.append(f"cannot verify public source {source_id}: {exc}")
            continue
        if not isinstance(live_content, dict):
            errors.append(f"public source {source_id} content response must be a mapping")
            continue
        if (
            live_content.get("type") != "file"
            or live_content.get("path") != path
            or live_content.get("html_url") != expected.get("url")
        ):
            errors.append(f"public source {source_id} must resolve its exact accepted repository path")
        expected_blob = expected.get("blob")
        if expected_blob is not None and live_content.get("sha") != expected_blob:
            errors.append(f"public source {source_id} live blob differs from its accepted binding")
    return errors


def validate_live_reference(
    fetch: Callable[[list[str]], Any] = _gh_json,
) -> list[str]:
    """Verify the exact organvm/limen follow-up issue remains an open issue."""

    try:
        issue = fetch(["api", f"repos/organvm/limen/issues/{LIVE_REFERENCE_ISSUE_NUMBER}"])
    except AdjudicationError as exc:
        return [f"cannot resolve profile-engine live reference: {exc}"]
    if not isinstance(issue, dict):
        return ["profile-engine live reference response must be a mapping"]
    errors: list[str] = []
    expected = {
        "number": LIVE_REFERENCE_ISSUE_NUMBER,
        "html_url": LIVE_REFERENCE_URL,
        "url": LIVE_REFERENCE_API_URL,
        "repository_url": "https://api.github.com/repos/organvm/limen",
        "state": "open",
    }
    for key, value in expected.items():
        if issue.get(key) != value:
            errors.append(f"profile-engine live reference {key} must remain {value!r}")
    if issue.get("pull_request") is not None:
        errors.append("profile-engine live reference must remain an issue, not a pull request")
    if issue.get("transferred_to") is not None:
        errors.append("profile-engine live reference must not be a transferred substitute")
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
            comment_pages = fetch(
                [
                    "api",
                    "--paginate",
                    "--slurp",
                    f"repos/organvm/limen/issues/{issue_number}/comments?per_page=100",
                ]
            )
        except AdjudicationError as exc:
            errors.append(f"cannot resolve accepted {work_id} receipt: {exc}")
            continue
        if not isinstance(issue, dict) or issue.get("state") != "closed":
            errors.append(f"accepted dependency {work_id} issue must remain closed")
        if not isinstance(comment_pages, list):
            errors.append(f"accepted dependency {work_id} comment pagination must be a list of pages")
            continue
        comments: list[dict[str, Any]] = []
        for page_index, page in enumerate(comment_pages):
            if not isinstance(page, list):
                errors.append(f"accepted dependency {work_id} comment page[{page_index}] must be a list")
                continue
            for row_index, row in enumerate(page):
                if not isinstance(row, dict):
                    errors.append(
                        f"accepted dependency {work_id} comment page[{page_index}][{row_index}] must be a mapping"
                    )
                    continue
                comment_id = row.get("id")
                if (
                    not isinstance(comment_id, int)
                    or isinstance(comment_id, bool)
                    or comment_id <= 0
                ):
                    errors.append(
                        f"accepted dependency {work_id} comment page[{page_index}][{row_index}] needs a positive integer id"
                    )
                    continue
                comments.append(row)
        marker = f"<!-- positioning-receipt:{work_id} -->"
        marked = [row for row in comments if marker in str(row.get("body") or "")]
        if not marked:
            errors.append(f"accepted dependency {work_id} has no marked receipt")
            continue
        latest = max(marked, key=lambda row: row["id"])
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
        observed_heads = receipt.get("observed_heads")
        if not isinstance(observed_heads, dict):
            errors.append(f"accepted dependency {work_id} observed_heads must be a mapping")
            continue
        observed_head = observed_heads.get("organvm/limen")
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
        flagship_evidence_text = FLAGSHIP_EVIDENCE_PATH.read_text(encoding="utf-8")
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
        flagship_evidence_text,
        claims_ledger,
    )
    if args.verify_live and not errors:
        errors.extend(validate_live_identity(program))
        errors.extend(validate_live_sources(artifact))
        errors.extend(validate_live_reference())
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
