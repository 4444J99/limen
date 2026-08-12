#!/usr/bin/env python3
"""Validate the PSP-P02-W03 public flagship proof-set decision.

The matrix is intentionally public-only. Static validation enforces the scoring
and reviewer contract. ``--verify-live`` additionally asks GitHub whether every
named repository is public and whether each selected live anchor still passes.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import importlib.util
import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/positioning/flagship-proof-set.yaml"
CENSUS = ROOT / "docs/github-estate-census.json"
ESTATE = ROOT / "institutio/github/estate.yaml"
ACCESS = ROOT / "institutio/github/access.yaml"
W02_RELAY = (
    ROOT
    / "docs/receipts/positioning/relays/2026-08-10-psp-p02-w02-estate-classification-preflight.md"
)
W03_RELAY = (
    ROOT
    / "docs/receipts/positioning/relays/2026-08-10-psp-p02-w03-flagship-proof-preflight.md"
)
SCHEMA = "limen.positioning_flagship_proof_set.v1"
RELAY_SCHEMA = "limen.positioning_flagship_relay_binding.v1"
WORK_ID = "PSP-P02-W03"
W02_WORK_ID = "PSP-P02-W02"
FORMAL_VERDICT = "formal_ratified_receipt_pending"
FORMAL_COMPLETION_BLOCKER = (
    "W02 is accepted; W03 still requires sanctioned merge, a marked receipt, and a passing "
    "PSP-P02-W03 receipt predicate before issue closure."
)
W01_RECEIPT = "docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json"
W02_ISSUE_URL = "https://github.com/organvm/limen/issues/2174"
W02_PULL_REQUEST_URL = "https://github.com/organvm/limen/pull/2307"
W03_ISSUE_URL = "https://github.com/organvm/limen/issues/2175"
W02_DEPENDENCY_KEYS = {
    "w01_receipt",
    "w02_branch",
    "w02_head",
    "w02_issue",
    "w02_issue_state",
    "w02_receipt",
    "w02_receipt_sha256",
    "w02_receipt_observed_head",
    "w02_pull_request",
    "w02_pull_request_state",
    "w03_issue",
    "w03_issue_state",
}
STATUSES = {"selected", "alternate", "excluded"}
REPOSITORY_MATURITY = {"active", "maintained", "dormant", "archived", "unvalidated"}
STALE_REPOSITORY_MATURITY = {"dormant", "archived", "unvalidated"}
REPOSITORY_RE = re.compile(r"[^/\s]+/[^/\s]+\Z")
WORKFLOW_API_PATH_RE = re.compile(
    r"repos/([^/\s]+/[^/\s]+)/actions/runs/([1-9][0-9]*)\Z",
    re.IGNORECASE,
)
HEAD_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
RECEIPT_BLOCK_RE = re.compile(
    r"<!--\s*positioning-receipt:(PSP-P\d{2}-W\d{2})\s*-->\s*```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)
RELAY_BINDING_RE = re.compile(
    r"<!--\s*positioning-formal-relay:start\s*-->\s*```yaml\s*(.*?)\s*```\s*"
    r"<!--\s*positioning-formal-relay:end\s*-->",
    re.DOTALL,
)
WORKFLOW_PATH_RE = re.compile(r"\.github/workflows/[^/\s]+\.(?:yml|yaml)\Z")
WORKFLOW_HEAD_BINDINGS = {"current_default_branch", "dated_default_branch_snapshot"}
DATED_SNAPSHOT_REPOSITORIES = {"organvm/limen"}
CLAIM_KEYS = {
    "statement",
    "assertion_class",
    "subject_repository",
    "includes",
    "excludes",
    "evidence_basis",
    "non_circular_exclusions",
}
CLAIM_REQUIRED_EXCLUDES = {"adoption", "customer_outcomes", "market_leadership"}
CLAIM_REQUIRED_EVIDENCE = {
    "public_source_implementation",
    "exact_head_workflow",
    "candidate_bound_public_endpoint",
}
CLAIM_REQUIRED_NON_CIRCULAR = {
    "selection_matrix",
    "portfolio_carrier",
    "private_only_material",
}
CLAIM_FORBIDDEN_ASSERTION_PATTERNS = (
    re.compile(r"\bmarket[- ]leading\b", re.IGNORECASE),
    re.compile(r"\bused by\b", re.IGNORECASE),
    re.compile(r"\b(?:customer|user) adoption\b", re.IGNORECASE),
    re.compile(r"\b(?:thousands|millions)\b", re.IGNORECASE),
)
LIVE_ENDPOINT_HOSTS = frozenset(
    {
        "limen-dashboard.pages.dev",
        "organvm-iii-ergon.github.io",
    }
)
EXPLICIT_ENDPOINT_BINDINGS = {
    "limen": {
        "deployment_identity": "cloudflare-pages:limen-dashboard",
        "url": "https://limen-dashboard.pages.dev/public-status.json",
    }
}
EXPLICIT_ADDITION_BINDINGS = {
    "limen": {
        "source_set": "manifest_primary_proof",
        "candidate_identity": "repository:organvm/limen",
    },
    "recursive_engine": {
        "source_set": "current_public_entry_point",
        "candidate_identity": "repository:organvm/recursive-engine--generative-entity",
    },
    "metasystem_master": {
        "source_set": "current_public_entry_point",
        "candidate_identity": "repository:organvm/metasystem-master",
    },
    "public_process": {
        "source_set": "current_public_entry_point",
        "candidate_identity": "repository:organvm-vi-koinonia/public-process",
    },
    "moneta": {
        "source_set": "current_front_door_endpoint",
        "candidate_identity": "endpoint:https://mint.4444j99.dev/",
    },
    "styx": {
        "source_set": "claims_ledger",
        "candidate_identity": "repository:4444J99/peer-audited--behavioral-blockchain",
    },
    "archived_landing": {
        "source_set": "legacy_entry_point",
        "candidate_identity": "repository:organvm/4444J99.github.io",
    },
}
FUTURE_OBSERVATION_SKEW = dt.timedelta(minutes=5)


class ProofSetError(RuntimeError):
    """Raised when live evidence cannot be inspected safely."""


def load_matrix(path: Path = MATRIX) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ProofSetError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProofSetError(f"{path} must contain a mapping")
    return value


def canonical_digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def canonical_receipt_digest(value: object) -> str:
    """Match the canonical digest emitted by positioning-program.py."""

    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_relay_binding(path: Path) -> tuple[dict[str, Any], str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProofSetError(f"cannot load formal relay {path.name}") from exc
    matches = RELAY_BINDING_RE.findall(text)
    if len(matches) != 1:
        raise ProofSetError(f"formal relay {path.name} must contain exactly one binding block")
    try:
        binding = yaml.safe_load(matches[0])
    except yaml.YAMLError as exc:
        raise ProofSetError(f"formal relay {path.name} has an invalid binding block") from exc
    if not isinstance(binding, dict):
        raise ProofSetError(f"formal relay {path.name} binding must be a mapping")
    return binding, text


def load_public_census_contract(path: Path = CENSUS) -> tuple[set[str], int, str]:
    """Return only the public identity projection from the redacted W01 census."""

    try:
        census = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProofSetError("cannot load the tracked public census projection") from exc
    leaves = census.get("leaves") if isinstance(census, dict) else None
    if not isinstance(leaves, list):
        raise ProofSetError("tracked public census projection has no leaf list")
    repositories = {
        str(leaf.get("repository"))
        for leaf in leaves
        if isinstance(leaf, dict)
        and leaf.get("private") is False
        and isinstance(leaf.get("repository"), str)
        and REPOSITORY_RE.fullmatch(str(leaf.get("repository")))
    }
    summary = census.get("summary") or {}
    private_count = summary.get("private_repository_count")
    repository_count = summary.get("repository_count")
    if not strict_int(private_count) or not strict_int(repository_count):
        raise ProofSetError("tracked public census projection has invalid summary counts")
    expected_public_count = repository_count - private_count
    if len(repositories) != expected_public_count:
        raise ProofSetError("tracked public census projection does not cover its public denominator")
    return repositories, expected_public_count, canonical_digest(sorted(repositories))


def load_classification_policy_contract(path: Path = ESTATE) -> tuple[dict[str, Any], str]:
    try:
        estate = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ProofSetError("cannot load the tracked W02 classification policy") from exc
    policy = estate.get("positioning_estate_classification") if isinstance(estate, dict) else None
    if not isinstance(policy, dict):
        raise ProofSetError("tracked W02 classification policy is missing")
    return policy, canonical_digest(policy)


def parse_time(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(dt.UTC)


def public_https_url(value: object) -> bool:
    if not isinstance(value, str) or value != value.strip():
        return False
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return False
    hostname = hostname.casefold()
    if "." not in hostname or hostname == "localhost" or hostname.endswith(
        (
            ".localhost",
            ".local",
            ".internal",
            ".home",
            ".lan",
            ".example",
            ".invalid",
            ".test",
        )
    ):
        return False
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return False


def validate_live_endpoint_url(url: object) -> str:
    if not public_https_url(url):
        raise ProofSetError("live endpoint must use a credential-free public HTTPS hostname")
    assert isinstance(url, str)
    if urlsplit(url).hostname not in LIVE_ENDPOINT_HOSTS:
        raise ProofSetError("live endpoint host is not in the selected-flagship allowlist")
    return url


def expected_endpoint_binding(candidate: dict[str, Any]) -> dict[str, str] | None:
    """Derive a selected candidate's exact public deployment identity."""

    candidate_id = candidate.get("id")
    if candidate_id in EXPLICIT_ENDPOINT_BINDINGS:
        return EXPLICIT_ENDPOINT_BINDINGS[candidate_id]
    repository = candidate.get("repository")
    if not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository):
        return None
    owner, name = repository.split("/", 1)
    return {
        "deployment_identity": f"github-pages:{repository}",
        "url": f"https://{owner}.github.io/{name}/",
    }


def endpoint_matches_candidate(anchor: dict[str, Any], candidate: dict[str, Any]) -> bool:
    binding = expected_endpoint_binding(candidate)
    return binding is not None and all(anchor.get(key) == value for key, value in binding.items())


def candidate_public_identity(candidate: dict[str, Any]) -> str | None:
    repository = candidate.get("repository")
    if isinstance(repository, str) and REPOSITORY_RE.fullmatch(repository):
        return f"repository:{repository}"
    public_url = candidate.get("public_url")
    if candidate.get("kind") == "endpoint" and public_https_url(public_url):
        return f"endpoint:{public_url}"
    return None


def github_repository_from_anchor_url(value: object) -> str | None:
    """Return the repository identity encoded by a GitHub/Pages evidence URL."""

    if not public_https_url(value):
        return None
    assert isinstance(value, str)
    parsed = urlsplit(value)
    hostname = str(parsed.hostname or "").casefold()
    parts = [part for part in parsed.path.split("/") if part]
    if hostname == "github.com" and len(parts) >= 2:
        return f"{parts[0]}/{parts[1].removesuffix('.git')}"
    if hostname.endswith(".github.io") and parts:
        owner = hostname.removesuffix(".github.io")
        return f"{owner}/{parts[0]}"
    return None


def validate_public_anchor_custody(
    anchor: object,
    public_canonical: dict[str, str],
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(anchor, dict):
        return [f"{prefix}: evidence anchor must be a mapping"]
    url = anchor.get("url")
    if not public_https_url(url):
        return [f"{prefix}: evidence URL must use a credential-free public HTTPS hostname"]
    assert isinstance(url, str)
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment:
        errors.append(f"{prefix}: evidence URL must not contain query or fragment data")
    repository = github_repository_from_anchor_url(url)
    if repository is not None and repository.casefold() not in public_canonical:
        errors.append(f"{prefix}: evidence repository is not present in the tracked public census")
    return errors


def repository_workflow_api_path(value: object, repository: object) -> str | None:
    match = WORKFLOW_API_PATH_RE.fullmatch(str(value or ""))
    if (
        match is None
        or not isinstance(repository, str)
        or match.group(1).casefold() != repository.casefold()
    ):
        return None
    return str(value)


def workflow_run_id(api_path: object, repository: object) -> str | None:
    path = repository_workflow_api_path(api_path, repository)
    if path is None:
        return None
    match = WORKFLOW_API_PATH_RE.fullmatch(path)
    assert match is not None
    return match.group(2)


def validate_selected_claim(claim: object, repository: object, prefix: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(claim, dict) or set(claim) != CLAIM_KEYS:
        return [f"{prefix}: selected candidate needs the complete structured flagship_claim contract"]
    statement = claim.get("statement")
    if not isinstance(statement, str) or not statement.strip() or len(statement) > 240:
        errors.append(f"{prefix}: flagship_claim.statement must contain 1-240 characters")
    elif any(pattern.search(statement) for pattern in CLAIM_FORBIDDEN_ASSERTION_PATTERNS):
        errors.append(f"{prefix}: flagship_claim.statement exceeds the bounded public assertion class")
    if claim.get("assertion_class") != "implemented_capability":
        errors.append(f"{prefix}: flagship_claim.assertion_class must be implemented_capability")
    if claim.get("subject_repository") != repository:
        errors.append(f"{prefix}: flagship_claim subject must be the candidate repository")

    list_contracts = {
        "includes": None,
        "excludes": CLAIM_REQUIRED_EXCLUDES,
        "evidence_basis": CLAIM_REQUIRED_EVIDENCE,
        "non_circular_exclusions": CLAIM_REQUIRED_NON_CIRCULAR,
    }
    for name, required in list_contracts.items():
        values = claim.get(name)
        valid_values = (
            isinstance(values, list)
            and 1 <= len(values) <= 8
            and all(isinstance(value, str) and value.strip() and len(value) <= 80 for value in values)
            and len({value.casefold() for value in values}) == len(values)
        )
        if not valid_values:
            errors.append(f"{prefix}: flagship_claim.{name} must be a bounded unique string list")
            continue
        if required is not None and set(values) != required:
            errors.append(f"{prefix}: flagship_claim.{name} must match the required public claim boundary")
    return errors


def validate_workflow_anchor(
    anchor: dict[str, Any], candidate: dict[str, Any], anchor_prefix: str
) -> list[str]:
    errors: list[str] = []
    repository = candidate.get("repository")
    run_id = workflow_run_id(anchor.get("github_api_path"), repository)
    if run_id is None:
        errors.append(f"{anchor_prefix}: workflow API path must be bound to the candidate repository")
        return errors
    expected_url = f"https://github.com/{repository}/actions/runs/{run_id}"
    if anchor.get("url") != expected_url:
        errors.append(f"{anchor_prefix}: workflow display URL must match its repository-bound run")
    identity = anchor.get("workflow_identity")
    if not isinstance(identity, dict) or set(identity) != {"id", "path", "name"}:
        errors.append(f"{anchor_prefix}: workflow identity must pin id, path, and name")
    else:
        if not strict_int(identity.get("id")) or identity.get("id", 0) <= 0:
            errors.append(f"{anchor_prefix}: workflow identity id must be a positive integer")
        if not isinstance(identity.get("path"), str) or not WORKFLOW_PATH_RE.fullmatch(identity["path"]):
            errors.append(f"{anchor_prefix}: workflow identity path must name a workflow file")
        if not isinstance(identity.get("name"), str) or not identity["name"].strip():
            errors.append(f"{anchor_prefix}: workflow identity name must be nonempty")
    if not isinstance(anchor.get("observed_head"), str) or not HEAD_RE.fullmatch(anchor["observed_head"]):
        errors.append(f"{anchor_prefix}: workflow anchor needs a valid observed head")
    default_branch = anchor.get("observed_default_branch")
    if not isinstance(default_branch, str) or not default_branch.strip():
        errors.append(f"{anchor_prefix}: workflow anchor needs the observed default branch")
    head_binding = anchor.get("head_binding")
    if head_binding not in WORKFLOW_HEAD_BINDINGS:
        errors.append(f"{anchor_prefix}: workflow anchor needs a supported head binding")
    elif (
        head_binding == "dated_default_branch_snapshot"
        and isinstance(repository, str)
        and repository.casefold() not in DATED_SNAPSHOT_REPOSITORIES
    ):
        errors.append(f"{anchor_prefix}: dated snapshot binding is not allowed for this repository")
    return errors


def weighted_total(scores: dict[str, Any], dimensions: dict[str, Any]) -> int | None:
    total = 0
    for name, spec in dimensions.items():
        score = scores.get(name)
        weight = spec.get("weight") if isinstance(spec, dict) else None
        if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 5:
            return None
        if not isinstance(weight, int) or isinstance(weight, bool) or weight < 0:
            return None
        total += score * weight
    if total % 5:
        return None
    return total // 5


def strict_int(value: Any) -> bool:
    """Return true for YAML integers while rejecting booleans."""

    return isinstance(value, int) and not isinstance(value, bool)


def receipt_comment_url(value: object) -> bool:
    if not isinstance(value, str) or not public_https_url(value):
        return False
    parsed = urlsplit(value)
    return (
        parsed.hostname == "github.com"
        and parsed.path == "/organvm/limen/issues/2174"
        and not parsed.query
        and re.fullmatch(r"issuecomment-[1-9][0-9]*", parsed.fragment or "") is not None
    )


def expected_relay_bindings(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    dependency = matrix.get("dependency_snapshot")
    if not isinstance(dependency, dict):
        dependency = {}
    candidates = matrix.get("candidates")
    if not isinstance(candidates, list):
        candidates = []
    selected = [
        candidate.get("id")
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("status") == "selected"
    ]
    alternates = [
        candidate.get("id")
        for candidate in candidates
        if isinstance(candidate, dict) and candidate.get("status") == "alternate"
    ]
    excluded_count = sum(
        isinstance(candidate, dict) and candidate.get("status") == "excluded"
        for candidate in candidates
    )
    candidate_screen = matrix.get("candidate_screen")
    if not isinstance(candidate_screen, dict):
        candidate_screen = {}
    return {
        "w02": {
            "schema_version": RELAY_SCHEMA,
            "work_id": W02_WORK_ID,
            "state": "closed",
            "accepted_head": dependency.get("w02_head"),
            "issue": dependency.get("w02_issue"),
            "issue_state": dependency.get("w02_issue_state"),
            "marked_receipt": dependency.get("w02_receipt"),
            "receipt_sha256": dependency.get("w02_receipt_sha256"),
            "receipt_observed_head": dependency.get("w02_receipt_observed_head"),
            "pull_request": dependency.get("w02_pull_request"),
            "pull_request_state": dependency.get("w02_pull_request_state"),
            "next_work": WORK_ID,
        },
        "w03": {
            "schema_version": RELAY_SCHEMA,
            "work_id": WORK_ID,
            "state": matrix.get("verdict"),
            "dependency_work_id": W02_WORK_ID,
            "dependency_head": dependency.get("w02_head"),
            "dependency_issue_state": dependency.get("w02_issue_state"),
            "dependency_marked_receipt": dependency.get("w02_receipt"),
            "dependency_receipt_sha256": dependency.get("w02_receipt_sha256"),
            "dependency_receipt_observed_head": dependency.get("w02_receipt_observed_head"),
            "dependency_pull_request_state": dependency.get("w02_pull_request_state"),
            "candidate_count": candidate_screen.get("candidate_count"),
            "selected_ids": selected,
            "alternate_ids": alternates,
            "excluded_count": excluded_count,
        },
    }


def validate_relay_consistency(
    matrix: dict[str, Any],
    *,
    relay_bindings: dict[str, dict[str, Any]] | None = None,
    relay_documents: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if relay_bindings is None or relay_documents is None:
        try:
            w02_binding, w02_document = load_relay_binding(W02_RELAY)
            w03_binding, w03_document = load_relay_binding(W03_RELAY)
        except ProofSetError as exc:
            return [str(exc)]
        relay_bindings = {"w02": w02_binding, "w03": w03_binding}
        relay_documents = {"w02": w02_document, "w03": w03_document}

    expected = expected_relay_bindings(matrix)
    for relay_id in ("w02", "w03"):
        observed = relay_bindings.get(relay_id)
        wanted = expected[relay_id]
        if not isinstance(observed, dict):
            errors.append(f"{relay_id.upper()} formal relay binding must be a mapping")
            continue
        if set(observed) != set(wanted):
            errors.append(f"{relay_id.upper()} formal relay binding has an incorrect exact schema")
        for key, value in wanted.items():
            if observed.get(key) != value:
                errors.append(f"{relay_id.upper()} formal relay {key} does not match the matrix")

    dependency = matrix.get("dependency_snapshot")
    if not isinstance(dependency, dict):
        dependency = {}
    screen = matrix.get("candidate_screen")
    if not isinstance(screen, dict):
        screen = {}
    required_snippets = {
        "w02": (
            "W02 is formally closed",
            str(dependency.get("w02_head") or ""),
            str(dependency.get("w02_receipt") or ""),
            str(dependency.get("w02_receipt_sha256") or ""),
            "PR #2307 is merged",
            "issue #2174 is closed",
        ),
        "w03": (
            str(dependency.get("w02_head") or ""),
            str(dependency.get("w02_receipt") or ""),
            str(dependency.get("w02_receipt_sha256") or ""),
            f"{screen.get('candidate_count')} public candidates",
        ),
    }
    for relay_id, snippets in required_snippets.items():
        document = relay_documents.get(relay_id, "")
        if any(not snippet or snippet not in document for snippet in snippets):
            errors.append(f"{relay_id.upper()} formal relay prose does not match its binding")

    stale_w02_phrases = (
        "#2307 is not yet merged",
        "#2174 has no marked receipt",
        "No W02 receipt and no issue comment posted",
        "Adopt PR #2307",
        "no W02 issue receipt exists yet",
    )
    w02_document = relay_documents.get("w02", "")
    if any(phrase in w02_document for phrase in stale_w02_phrases):
        errors.append("W02 formal relay retains stale pre-integration instructions")
    return errors


def validate_formal_contract(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if matrix.get("work_id") != WORK_ID:
        errors.append(f"work_id must be {WORK_ID}")
    if parse_time(matrix.get("generated_at")) is None:
        errors.append("generated_at must be a valid timestamp")
    if matrix.get("verdict") != FORMAL_VERDICT:
        errors.append(f"verdict must be {FORMAL_VERDICT}")
    if matrix.get("formal_completion_blocker") != FORMAL_COMPLETION_BLOCKER:
        errors.append("formal_completion_blocker does not match the W03 pending-receipt boundary")

    dependency = matrix.get("dependency_snapshot")
    if not isinstance(dependency, dict):
        errors.append("dependency_snapshot must be the exact W02 formal dependency mapping")
        return [*errors, *validate_relay_consistency(matrix)]
    if set(dependency) != W02_DEPENDENCY_KEYS:
        errors.append("dependency_snapshot has an incorrect exact schema")
    exact_values = {
        "w01_receipt": W01_RECEIPT,
        "w02_branch": "main",
        "w02_issue": W02_ISSUE_URL,
        "w02_issue_state": "closed",
        "w02_pull_request": W02_PULL_REQUEST_URL,
        "w02_pull_request_state": "merged",
        "w03_issue": W03_ISSUE_URL,
        "w03_issue_state": "open",
    }
    for key, value in exact_values.items():
        if dependency.get(key) != value:
            errors.append(f"dependency_snapshot.{key} must be {value}")
    for key in ("w02_head", "w02_receipt_observed_head"):
        value = dependency.get(key)
        if not isinstance(value, str) or HEAD_RE.fullmatch(value) is None:
            errors.append(f"dependency_snapshot.{key} must be a lowercase exact Git head")
    if dependency.get("w02_receipt_observed_head") != dependency.get("w02_head"):
        errors.append("dependency receipt observed head must equal the accepted W02 main head")
    if not receipt_comment_url(dependency.get("w02_receipt")):
        errors.append("dependency_snapshot.w02_receipt must be the marked W02 issue comment URL")
    receipt_sha256 = dependency.get("w02_receipt_sha256")
    if not isinstance(receipt_sha256, str) or DIGEST_RE.fullmatch(receipt_sha256) is None:
        errors.append("dependency_snapshot.w02_receipt_sha256 must be a lowercase SHA-256 digest")
    errors.extend(validate_relay_consistency(matrix))
    return errors


def validate_source_projection(
    matrix: dict[str, Any], candidates: list[dict[str, Any]]
) -> tuple[list[str], set[str]]:
    """Bind the candidate denominator to the tracked W01/W02 public sources."""

    errors: list[str] = []
    try:
        public_repositories, public_count, public_digest = load_public_census_contract()
        _, policy_digest = load_classification_policy_contract()
    except ProofSetError as exc:
        return [str(exc)], set()

    screen = matrix.get("candidate_screen") or {}
    projection = screen.get("source_projection") if isinstance(screen, dict) else None
    if not isinstance(projection, dict):
        return ["candidate_screen.source_projection must bind the W01/W02 public denominator"], public_repositories
    if projection.get("w01_public_repository_count") != public_count:
        errors.append("source projection W01 public repository count does not match the tracked census")
    if projection.get("w01_public_repository_identity_sha256") != public_digest:
        errors.append("source projection W01 public identity digest does not match the tracked census")
    if projection.get("w02_classification_policy_sha256") != policy_digest:
        errors.append("source projection W02 policy digest does not match the tracked classification policy")
    if parse_time(projection.get("observed_at")) is None:
        errors.append("candidate source projection needs a valid observation timestamp")

    w02_repositories = projection.get("w02_front_door_proof_repositories")
    if not isinstance(w02_repositories, list) or not w02_repositories:
        errors.append("source projection needs the authoritative W02 front-door repository list")
        w02_repositories = []
    elif not all(isinstance(value, str) and REPOSITORY_RE.fullmatch(value) for value in w02_repositories):
        errors.append("source projection W02 repository identities are invalid")
        w02_repositories = []
    w02_keys = [repository.casefold() for repository in w02_repositories]
    if len(set(w02_keys)) != len(w02_keys):
        errors.append("source projection contains case-insensitive duplicate W02 repositories")
    public_canonical = {repository.casefold(): repository for repository in public_repositories}
    noncanonical_w02_count = sum(
        public_canonical.get(repository.casefold()) != repository for repository in w02_repositories
    )
    if noncanonical_w02_count:
        errors.append(
            "source projection contains "
            f"{noncanonical_w02_count} W02 repository identities absent from the canonical public census"
        )

    additions = projection.get("explicit_additions")
    if not isinstance(additions, list):
        errors.append("source projection explicit_additions must be a list")
        additions = []
    addition_ids: list[str] = []
    addition_source_sets: collections.Counter[str] = collections.Counter()
    for addition in additions:
        if not isinstance(addition, dict) or set(addition) != {
            "candidate_id",
            "source_set",
            "candidate_identity",
        }:
            errors.append(
                "every source projection addition must bind one candidate id, source set, and public identity"
            )
            continue
        candidate_id = addition.get("candidate_id")
        source_set = addition.get("source_set")
        candidate_identity = addition.get("candidate_identity")
        if (
            not isinstance(candidate_id, str)
            or not candidate_id
            or not isinstance(source_set, str)
            or not source_set
            or not isinstance(candidate_identity, str)
            or not candidate_identity
        ):
            errors.append(
                "every source projection addition needs nonempty candidate, source-set, and public identities"
            )
            continue
        addition_ids.append(candidate_id)
        addition_source_sets[source_set] += 1
        if addition != {"candidate_id": candidate_id, **EXPLICIT_ADDITION_BINDINGS.get(candidate_id, {})}:
            errors.append("an explicit candidate addition differs from its pinned source-registry identity")
    if len(set(addition_ids)) != len(addition_ids):
        errors.append("source projection contains duplicate explicit candidate additions")

    candidate_by_id = {
        str(candidate.get("id")): candidate for candidate in candidates if isinstance(candidate, dict)
    }
    actual_w02_repositories = sorted(
        str(candidate.get("repository"))
        for candidate in candidates
        if isinstance(candidate, dict)
        and "w02_front_door_proof" in (candidate.get("source_sets") or [])
        and isinstance(candidate.get("repository"), str)
    )
    if sorted(w02_repositories) != actual_w02_repositories:
        errors.append("matrix W02 rows do not match the authoritative source projection")
    for addition in additions:
        if not isinstance(addition, dict):
            continue
        candidate = candidate_by_id.get(str(addition.get("candidate_id")))
        if (
            candidate is None
            or addition.get("source_set") not in (candidate.get("source_sets") or [])
            or candidate_public_identity(candidate) != addition.get("candidate_identity")
        ):
            errors.append("an explicit candidate addition is not bound to its declared source set")

    projected_ids = {
        str(candidate.get("id"))
        for candidate in candidates
        if isinstance(candidate, dict)
        and isinstance(candidate.get("repository"), str)
        and candidate["repository"].casefold() in set(w02_keys)
    } | set(addition_ids)
    actual_ids = {
        str(candidate.get("id")) for candidate in candidates if isinstance(candidate, dict)
    }
    if projected_ids != actual_ids or len(projected_ids) != len(candidates):
        errors.append("candidate matrix does not equal the authoritative source projection")

    count_fields = {
        "manifest_primary_proof": "manifest_primary_proof_additions",
        "current_public_entry_point": "current_public_entry_point_additions",
        "current_front_door_endpoint": "current_front_door_endpoint_additions",
        "claims_ledger": "claims_ledger_additions",
        "legacy_entry_point": "legacy_entry_point_additions",
    }
    if screen.get("w02_front_door_proof_repositories") != len(w02_repositories):
        errors.append("candidate screen W02 count does not match its source projection")
    for source_set, field in count_fields.items():
        if screen.get(field) != addition_source_sets[source_set]:
            errors.append(f"candidate screen {field} does not match its source projection")
    if screen.get("candidate_count") != len(w02_repositories) + len(addition_ids):
        errors.append("candidate screen count does not match the authoritative source projection")
    return errors, public_repositories


def validate_matrix(
    matrix: dict[str, Any],
    *,
    now: dt.datetime | None = None,
    enforce_freshness: bool = False,
) -> list[str]:
    errors = validate_formal_contract(matrix)
    if matrix.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA}")

    rubric = matrix.get("rubric") or {}
    dimensions = rubric.get("dimensions") if isinstance(rubric, dict) else None
    if not isinstance(dimensions, dict) or not dimensions:
        errors.append("rubric.dimensions must be a nonempty mapping")
        dimensions = {}
    weights = [spec.get("weight") for spec in dimensions.values() if isinstance(spec, dict)]
    if len(weights) != len(dimensions) or any(not strict_int(weight) for weight in weights):
        errors.append("every rubric dimension needs an integer weight")
    elif sum(weights) != 100:
        errors.append("rubric weights must sum to 100")

    candidates = matrix.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append("candidates must be a nonempty list")
        return errors
    source_errors, public_repositories = validate_source_projection(matrix, candidates)
    errors.extend(source_errors)
    public_canonical = {repository.casefold(): repository for repository in public_repositories}

    screen = matrix.get("candidate_screen") or {}
    if screen.get("candidate_count") != len(candidates):
        errors.append("candidate_screen.candidate_count must equal the matrix row count")
    privacy = matrix.get("privacy_split") or {}
    if privacy.get("public_candidates_scored") != len(candidates):
        errors.append("privacy_split.public_candidates_scored must equal the matrix row count")
    if privacy.get("private_repository_names_in_this_artifact") != 0:
        errors.append("the public matrix must declare zero private repository names")

    policy = matrix.get("selection_policy") or {}
    minimum_selected = policy.get("minimum_selected")
    maximum_selected = policy.get("maximum_selected")
    minimum_total = policy.get("minimum_weighted_total")
    dimension_minima = policy.get("minimum_dimension_scores")
    if not isinstance(dimension_minima, dict) or not dimension_minima:
        errors.append("selection_policy.minimum_dimension_scores must be a nonempty mapping")
        dimension_minima = {}
    if not strict_int(minimum_selected) or not strict_int(maximum_selected):
        errors.append("selection_policy needs integer selected bounds")
    elif not (1 <= minimum_selected <= maximum_selected <= len(candidates)):
        errors.append("selection_policy selected bounds must be positive, ordered, and within the matrix")
    if not strict_int(minimum_total):
        errors.append("selection_policy.minimum_weighted_total must be an integer")
    elif not 0 <= minimum_total <= 100:
        errors.append("selection_policy.minimum_weighted_total must be within the score range")
    if set(dimension_minima) - set(dimensions):
        errors.append("selection_policy.minimum_dimension_scores names an unknown rubric dimension")
    if any(not strict_int(value) or not 0 <= value <= 5 for value in dimension_minima.values()):
        errors.append("selection_policy.minimum_dimension_scores must stay within the 0-5 score range")

    ids: list[str] = []
    repositories: list[str] = []
    endpoint_identities: list[str] = []
    endpoint_urls: list[str] = []
    status_ids: dict[str, list[str]] = collections.defaultdict(list)
    selected_roles: dict[str, list[str]] = collections.defaultdict(list)
    check_now = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC)

    for index, candidate in enumerate(candidates):
        prefix = f"candidate[{index}]"
        if not isinstance(candidate, dict):
            errors.append(f"{prefix} must be a mapping")
            continue
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str) or not candidate_id:
            errors.append(f"{prefix}.id must be a nonempty string")
            candidate_id = prefix
        ids.append(candidate_id)
        prefix = candidate_id

        status = candidate.get("status")
        if status not in STATUSES:
            errors.append(f"{prefix}: invalid status {status!r}")
            continue
        status_ids[status].append(candidate_id)

        public_url = candidate.get("public_url")
        if not public_https_url(public_url):
            errors.append(f"{prefix}: public_url must use a credential-free public HTTPS hostname")
        repository = candidate.get("repository")
        if candidate.get("kind") == "repository" and (
            not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository)
        ):
            errors.append(f"{prefix}: repository candidates need a valid owner/repository slug")
        elif isinstance(repository, str) and repository:
            repositories.append(repository)
            if public_canonical.get(repository.casefold()) != repository:
                errors.append(f"{prefix}: repository identity is not present in the tracked public census")
            if public_url != f"https://github.com/{repository}":
                errors.append(f"{prefix}: public_url must be the canonical public GitHub repository URL")
        source_sets = candidate.get("source_sets")
        if not isinstance(source_sets, list) or not source_sets or not all(
            isinstance(source_set, str) and source_set for source_set in source_sets
        ):
            errors.append(f"{prefix}: source_sets must be a nonempty string list")
        repository_maturity = candidate.get("repository_maturity")
        if candidate.get("kind") == "repository" and repository_maturity not in REPOSITORY_MATURITY:
            errors.append(f"{prefix}: repository_maturity must use the W02 maturity taxonomy")

        scores = candidate.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(dimensions):
            errors.append(f"{prefix}: scores must name every rubric dimension exactly")
        else:
            calculated = weighted_total(scores, dimensions)
            if calculated is None:
                errors.append(f"{prefix}: scores or weights are invalid")
            elif calculated != candidate.get("weighted_total"):
                errors.append(
                    f"{prefix}: weighted_total {candidate.get('weighted_total')!r} does not equal {calculated}"
                )

        dependencies = candidate.get("private_only_dependencies")
        if not isinstance(dependencies, list):
            errors.append(f"{prefix}: private_only_dependencies must be a list")
            dependencies = []
        anchors = candidate.get("evidence_anchors")
        if not isinstance(anchors, list):
            errors.append(f"{prefix}: evidence_anchors must be a list")
            anchors = []
        for anchor_index, anchor in enumerate(anchors):
            errors.extend(
                validate_public_anchor_custody(
                    anchor,
                    public_canonical,
                    f"{prefix}.evidence_anchors[{anchor_index}]",
                )
            )
            if not isinstance(anchor, dict) or anchor.get("kind") != "public_endpoint":
                continue
            identity = anchor.get("deployment_identity")
            endpoint_url = anchor.get("url")
            if isinstance(identity, str) and identity:
                endpoint_identities.append(identity)
            if isinstance(endpoint_url, str) and endpoint_url:
                endpoint_urls.append(endpoint_url)

        if status == "selected":
            errors.extend(validate_selected_claim(candidate.get("flagship_claim"), repository, prefix))
            role = candidate.get("story_role")
            if not isinstance(role, str) or not role.strip():
                errors.append(f"{prefix}: selected candidate needs a story_role")
            else:
                selected_roles[role.strip().casefold()].append(candidate_id)
            if candidate.get("eligible") is not True:
                errors.append(f"{prefix}: selected candidate is marked excluded/ineligible")
            if candidate.get("stale") is not False:
                errors.append(f"{prefix}: selected candidate is stale")
            if repository_maturity in STALE_REPOSITORY_MATURITY:
                errors.append(f"{prefix}: selected repository maturity is stale or unvalidated")
            if dependencies:
                errors.append(f"{prefix}: selected candidate has a private-only dependency")
            if candidate.get("hard_gate_failures"):
                errors.append(f"{prefix}: selected candidate has hard-gate failures")
            candidate_total = candidate.get("weighted_total")
            if strict_int(minimum_total) and (
                not strict_int(candidate_total) or candidate_total < minimum_total
            ):
                errors.append(f"{prefix}: selected score is below the minimum")
            if isinstance(scores, dict):
                for dimension, minimum in dimension_minima.items():
                    dimension_score = scores.get(dimension)
                    if (
                        not strict_int(minimum)
                        or not strict_int(dimension_score)
                        or dimension_score < minimum
                    ):
                        errors.append(f"{prefix}: {dimension} is below the selected minimum")

            live_anchors = [anchor for anchor in anchors if isinstance(anchor, dict) and anchor.get("live") is True]
            live_kinds = collections.Counter(anchor.get("kind") for anchor in live_anchors)
            if live_kinds != {"workflow_run": 1, "public_endpoint": 1}:
                errors.append(
                    f"{prefix}: selected candidate needs exactly one live workflow_run and one live public_endpoint"
                )
            for anchor_index, anchor in enumerate(live_anchors):
                anchor_prefix = f"{prefix}.evidence_anchors[{anchor_index}]"
                if anchor.get("status") != "pass":
                    errors.append(f"{anchor_prefix}: live anchor must be passing")
                if anchor.get("kind") == "public_endpoint":
                    if not endpoint_matches_candidate(anchor, candidate):
                        errors.append(f"{anchor_prefix}: endpoint identity is not bound to this candidate")
                    if anchor.get("expected_http_status") != 200:
                        errors.append(f"{anchor_prefix}: endpoint must require exact HTTP 200 success")
                if anchor.get("kind") == "workflow_run":
                    errors.extend(validate_workflow_anchor(anchor, candidate, anchor_prefix))
                url = anchor.get("url")
                if not public_https_url(url):
                    errors.append(
                        f"{anchor_prefix}: live anchor URL must use a credential-free public HTTPS hostname"
                    )
                if not anchor.get("reproduction"):
                    errors.append(f"{anchor_prefix}: live anchor needs a reproduction command")
                observed = parse_time(anchor.get("observed_at"))
                max_age = anchor.get("max_age_days")
                if observed is None or not strict_int(max_age) or max_age <= 0:
                    errors.append(f"{anchor_prefix}: live anchor needs a valid observation and max age")
                else:
                    if observed > check_now + FUTURE_OBSERVATION_SKEW:
                        errors.append(f"{anchor_prefix}: live anchor observation is future-dated")
                    elif enforce_freshness and check_now - observed > dt.timedelta(days=max_age):
                        errors.append(f"{anchor_prefix}: live anchor is stale")
        elif status == "alternate":
            if not candidate.get("verdict_reason"):
                errors.append(f"{prefix}: alternate needs a verdict_reason")
            if not candidate.get("promotion_condition"):
                errors.append(f"{prefix}: alternate needs a promotion_condition")
        elif not candidate.get("exclusion_reason"):
            errors.append(f"{prefix}: excluded candidate needs an exclusion_reason")

    duplicate_ids = sorted(name for name, count in collections.Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate candidate ids: {', '.join(duplicate_ids)}")
    duplicate_repository_count = sum(
        count - 1 for count in collections.Counter(name.casefold() for name in repositories).values() if count > 1
    )
    if duplicate_repository_count:
        errors.append(
            f"duplicate candidate repositories: {duplicate_repository_count} case-insensitive duplicate identities"
        )
    duplicate_endpoint_identities = sorted(
        name for name, count in collections.Counter(endpoint_identities).items() if count > 1
    )
    if duplicate_endpoint_identities:
        errors.append(f"duplicate endpoint identities: {', '.join(duplicate_endpoint_identities)}")
    duplicate_endpoint_urls = sorted(
        name for name, count in collections.Counter(endpoint_urls).items() if count > 1
    )
    if duplicate_endpoint_urls:
        errors.append(f"duplicate endpoint URLs: {', '.join(duplicate_endpoint_urls)}")
    duplicate_roles = sorted(role for role, members in selected_roles.items() if len(members) > 1)
    if duplicate_roles:
        errors.append(f"duplicate selected story roles: {', '.join(duplicate_roles)}")

    verdict = matrix.get("reviewer_verdict") or {}
    if verdict.get("selected_ids") != status_ids["selected"]:
        errors.append("reviewer_verdict.selected_ids must match selected matrix rows in order")
    if verdict.get("alternate_ids") != status_ids["alternate"]:
        errors.append("reviewer_verdict.alternate_ids must match alternate matrix rows in order")
    selected_count = len(status_ids["selected"])
    if strict_int(minimum_selected) and selected_count < minimum_selected:
        errors.append("selected set is smaller than selection_policy.minimum_selected")
    if strict_int(maximum_selected) and selected_count > maximum_selected:
        errors.append("selected set is larger than selection_policy.maximum_selected")
    return errors


def command_json(args: list[str]) -> Any:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False, timeout=60)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise ProofSetError(detail)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProofSetError("live query returned invalid JSON") from exc


def github_pages(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        separator = "&" if "?" in path else "?"
        value = command_json(
            ["gh", "api", f"{path}{separator}per_page=100&page={page}"]
        )
        if not isinstance(value, list):
            raise ProofSetError("GitHub receipt query returned a non-list")
        rows.extend(row for row in value if isinstance(row, dict))
        if len(value) < 100:
            return rows
        page += 1


def load_positioning_program_module() -> Any:
    path = ROOT / "scripts/positioning-program.py"
    spec = importlib.util.spec_from_file_location("flagship_positioning_program", path)
    if spec is None or spec.loader is None:
        raise ProofSetError("cannot load the positioning receipt verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def live_w02_dependency_snapshot() -> dict[str, Any]:
    """Resolve the accepted W02 issue, PR, and latest canonical marked receipt."""

    try:
        pull_request = command_json(["gh", "api", "repos/organvm/limen/pulls/2307"])
        issue = command_json(["gh", "api", "repos/organvm/limen/issues/2174"])
        w03_issue = command_json(["gh", "api", "repos/organvm/limen/issues/2175"])
        comments = github_pages("repos/organvm/limen/issues/2174/comments")
        current_main = command_json(["gh", "api", "repos/organvm/limen/commits/main"])
    except ProofSetError as exc:
        raise ProofSetError("accepted W02 formal state is unavailable") from exc
    if not all(isinstance(value, dict) for value in (pull_request, issue, w03_issue, current_main)):
        raise ProofSetError("accepted W02 formal state has an invalid GitHub response")

    marker = f"<!-- positioning-receipt:{W02_WORK_ID} -->"
    marked = [row for row in comments if marker in str(row.get("body") or "")]
    if not marked:
        raise ProofSetError("accepted W02 has no marked receipt")
    latest = max(marked, key=lambda row: int(row.get("id") or 0))
    body = str(latest.get("body") or "")
    matches = [match for match in RECEIPT_BLOCK_RE.findall(body) if match[0] == W02_WORK_ID]
    if len(matches) != 1:
        raise ProofSetError("accepted W02 latest marked comment has no unique receipt block")
    try:
        receipt = json.loads(matches[0][1])
        positioning = load_positioning_program_module()
        graph = positioning.index_program(positioning.load_manifest())
        receipt = positioning.validate_work_receipt(receipt, W02_WORK_ID, graph)
    except Exception as exc:
        raise ProofSetError("accepted W02 latest marked receipt is invalid") from exc

    merge_head = pull_request.get("merge_commit_sha")
    current_main_head = current_main.get("sha")
    if not isinstance(merge_head, str) or HEAD_RE.fullmatch(merge_head) is None:
        raise ProofSetError("accepted W02 pull request has no valid merge commit")
    if not isinstance(current_main_head, str) or HEAD_RE.fullmatch(current_main_head) is None:
        raise ProofSetError("current main has no valid exact head")
    try:
        comparison = command_json(
            [
                "gh",
                "api",
                f"repos/organvm/limen/compare/{merge_head}...{current_main_head}",
            ]
        )
    except ProofSetError as exc:
        raise ProofSetError("accepted W02 main-line ancestry is unavailable") from exc
    if not isinstance(comparison, dict):
        raise ProofSetError("accepted W02 main-line ancestry is invalid")

    observed_heads = receipt.get("observed_heads")
    receipt_head = observed_heads.get("organvm/limen") if isinstance(observed_heads, dict) else None
    return {
        "issue_state": str(issue.get("state") or "").lower(),
        "w03_issue_state": str(w03_issue.get("state") or "").lower(),
        "pull_request_state": "merged"
        if pull_request.get("merged_at") and pull_request.get("merged") is True
        else str(pull_request.get("state") or "").lower(),
        "pull_request_merge_head": merge_head,
        "receipt_url": str(latest.get("html_url") or ""),
        "receipt_sha256": canonical_receipt_digest(receipt),
        "receipt_observed_head": receipt_head,
        "current_main_head": current_main_head,
        "main_contains_pull_request_head": comparison.get("status") in {"ahead", "identical"},
    }


def validate_live_formal_dependency(
    matrix: dict[str, Any], observed: dict[str, Any] | None = None
) -> list[str]:
    dependency = matrix.get("dependency_snapshot")
    if not isinstance(dependency, dict):
        return ["live W02 binding requires the formal dependency snapshot"]
    if observed is None:
        try:
            observed = live_w02_dependency_snapshot()
        except ProofSetError as exc:
            return [str(exc)]
    errors: list[str] = []
    comparisons = {
        "issue_state": "w02_issue_state",
        "w03_issue_state": "w03_issue_state",
        "pull_request_state": "w02_pull_request_state",
        "pull_request_merge_head": "w02_head",
        "receipt_url": "w02_receipt",
        "receipt_sha256": "w02_receipt_sha256",
        "receipt_observed_head": "w02_receipt_observed_head",
    }
    labels = {
        "issue_state": "issue state",
        "w03_issue_state": "W03 issue state",
        "pull_request_state": "pull request state",
        "pull_request_merge_head": "merged pull request head",
        "receipt_url": "latest marked receipt URL",
        "receipt_sha256": "canonical receipt SHA-256",
        "receipt_observed_head": "receipt observed head",
    }
    for observed_key, dependency_key in comparisons.items():
        if observed.get(observed_key) != dependency.get(dependency_key):
            errors.append(f"accepted W02 {labels[observed_key]} differs from the formal snapshot")
    if observed.get("receipt_observed_head") != observed.get("pull_request_merge_head"):
        errors.append("accepted W02 receipt observed head differs from its merged pull request head")
    current_main_head = observed.get("current_main_head")
    if not isinstance(current_main_head, str) or HEAD_RE.fullmatch(current_main_head) is None:
        errors.append("accepted W02 live binding has no valid current main head")
    if observed.get("main_contains_pull_request_head") is not True:
        errors.append("current main does not contain the accepted W02 merge commit")
    return errors


def http_status(url: str) -> int:
    url = validate_live_endpoint_url(url)
    result = subprocess.run(
        [
            "curl",
            "--proto",
            "=https",
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            url,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        raise ProofSetError((result.stderr or f"HTTP probe failed for {url}").strip())
    try:
        return int(result.stdout.strip())
    except ValueError as exc:
        raise ProofSetError(f"HTTP probe returned an invalid status for {url}") from exc


def load_estate_classification_module() -> Any:
    path = ROOT / "scripts/estate-classification.py"
    spec = importlib.util.spec_from_file_location("flagship_estate_classification", path)
    if spec is None or spec.loader is None:
        raise ProofSetError("cannot load the W02 classification verifier")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def live_w02_snapshot() -> dict[str, Any]:
    """Derive W02 relevance and maturity from the current authoritative estate."""

    try:
        classification = load_estate_classification_module()
        estate = classification.load_yaml(ESTATE)
        access = classification.load_yaml(ACCESS)
        rows = classification.collect_live_repositories()
        classified = classification.classify(rows, estate, access, dt.datetime.now(dt.UTC))
    except Exception as exc:  # The public caller must not echo private live identities.
        raise ProofSetError("authoritative W02 live projection is unavailable") from exc
    if len(rows) != len(classified):
        raise ProofSetError("authoritative W02 live projection has inconsistent coverage")
    public_pairs = [
        (row, result)
        for row, result in zip(rows, classified, strict=True)
        if row.get("private") is False
    ]
    return {
        "front_door_repositories": sorted(
            str(row.get("full_name"))
            for row, result in public_pairs
            if result.get("public_relevance") == "front_door_proof"
        ),
        "metadata": {
            str(row.get("full_name")).casefold(): row for row, _ in public_pairs
        },
        "maturity": {
            str(row.get("full_name")).casefold(): result.get("maturity")
            for row, result in public_pairs
        },
    }


def validate_live(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    candidates = matrix.get("candidates") or []
    if isinstance(matrix.get("dependency_snapshot"), dict):
        errors.extend(validate_live_formal_dependency(matrix))
    try:
        w02 = live_w02_snapshot()
    except ProofSetError as exc:
        return [str(exc)]

    projection = ((matrix.get("candidate_screen") or {}).get("source_projection") or {})
    expected_w02 = projection.get("w02_front_door_proof_repositories")
    observed_w02 = w02.get("front_door_repositories") or []
    if isinstance(expected_w02, list) and sorted(expected_w02) != sorted(observed_w02):
        errors.append(
            "authoritative W02 live denominator differs from the pinned public projection "
            f"(expected {len(expected_w02)}, observed {len(observed_w02)})"
        )

    metadata_by_repository = w02.get("metadata") or {}
    maturity_by_repository = w02.get("maturity") or {}
    default_branches: dict[str, str] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("kind") != "repository":
            continue
        candidate_id = str(candidate.get("id") or "unknown")
        repository = str(candidate.get("repository") or "")
        repository_key = repository.casefold()
        metadata = metadata_by_repository.get(repository_key)
        if not isinstance(metadata, dict):
            errors.append(f"{candidate_id}: repository is absent from the current public estate projection")
            continue
        observed_maturity = maturity_by_repository.get(repository_key)
        if candidate.get("repository_maturity") != observed_maturity:
            errors.append(f"{candidate_id}: repository maturity differs from current W02 metadata")
        if candidate.get("status") == "selected" and bool(metadata.get("archived")):
            errors.append(f"{candidate_id}: selected repository is archived")
        if candidate.get("status") == "selected":
            default_branch = metadata.get("default_branch")
            if not isinstance(default_branch, str) or not default_branch:
                errors.append(f"{candidate_id}: repository has no readable default branch")
                continue
            default_branches[repository_key] = default_branch

    current_heads: dict[str, str] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("status") != "selected":
            continue
        candidate_id = str(candidate.get("id") or "unknown")
        repository = str(candidate.get("repository") or "")
        repository_key = repository.casefold()
        for anchor in candidate.get("evidence_anchors") or []:
            if not isinstance(anchor, dict) or anchor.get("live") is not True:
                continue
            kind = anchor.get("kind")
            if kind == "workflow_run":
                api_path = repository_workflow_api_path(
                    anchor.get("github_api_path"), candidate.get("repository")
                )
                if api_path is None:
                    errors.append(f"{candidate_id}: workflow anchor needs its repository-bound API path")
                    continue
                try:
                    run = command_json(["gh", "api", api_path])
                except ProofSetError:
                    errors.append(f"{candidate_id}: workflow anchor is unavailable")
                    continue
                if not isinstance(run, dict):
                    errors.append(f"{candidate_id}: workflow anchor returned an invalid response")
                    continue
                if run.get("status") != "completed" or run.get("conclusion") != "success":
                    errors.append(f"{candidate_id}: workflow anchor is not a completed success")
                if run.get("head_sha") != anchor.get("observed_head"):
                    errors.append(f"{candidate_id}: workflow anchor head does not match the matrix")
                run_id = workflow_run_id(api_path, repository)
                expected_url = f"https://github.com/{repository}/actions/runs/{run_id}"
                if anchor.get("url") != expected_url or run.get("html_url") != expected_url:
                    errors.append(f"{candidate_id}: workflow display URL does not match the pinned run")
                identity = anchor.get("workflow_identity") or {}
                if (
                    run.get("workflow_id") != identity.get("id")
                    or run.get("path") != identity.get("path")
                    or run.get("name") != identity.get("name")
                ):
                    errors.append(f"{candidate_id}: workflow identity differs from the pinned workflow")
                default_branch = default_branches.get(repository_key)
                if (
                    run.get("head_branch") != default_branch
                    or anchor.get("observed_default_branch") != default_branch
                ):
                    errors.append(f"{candidate_id}: workflow run is not bound to the repository default branch")
                if anchor.get("head_binding") == "current_default_branch":
                    if repository_key not in current_heads and default_branch:
                        try:
                            commit = command_json(
                                ["gh", "api", f"repos/{repository}/commits/{default_branch}"]
                            )
                        except ProofSetError:
                            errors.append(f"{candidate_id}: current default-branch head is unavailable")
                            continue
                        current_head = commit.get("sha") if isinstance(commit, dict) else None
                        if not isinstance(current_head, str) or not HEAD_RE.fullmatch(current_head):
                            errors.append(f"{candidate_id}: current default-branch head is invalid")
                            continue
                        current_heads[repository_key] = current_head
                    if run.get("head_sha") != current_heads.get(repository_key):
                        errors.append(f"{candidate_id}: workflow anchor is not on the current default-branch head")
            elif kind == "public_endpoint":
                if not endpoint_matches_candidate(anchor, candidate):
                    errors.append(f"{candidate_id}: endpoint identity is not bound to this candidate")
                    continue
                expected = anchor.get("expected_http_status")
                try:
                    observed = http_status(str(anchor.get("url") or ""))
                except ProofSetError:
                    errors.append(f"{candidate_id}: endpoint anchor is unavailable")
                    continue
                if observed != expected:
                    errors.append(f"{candidate_id}: endpoint returned {observed}, expected {expected}")
            else:
                errors.append(f"{candidate_id}: unsupported live anchor kind {kind!r}")
    return errors


def public_summary(matrix: dict[str, Any]) -> dict[str, Any]:
    candidates = matrix.get("candidates") or []
    statuses = collections.Counter(candidate.get("status") for candidate in candidates if isinstance(candidate, dict))
    return {
        "candidate_count": len(candidates),
        "selected": [candidate["id"] for candidate in candidates if candidate.get("status") == "selected"],
        "alternates": [candidate["id"] for candidate in candidates if candidate.get("status") == "alternate"],
        "status_counts": dict(sorted(statuses.items())),
        "formal_completion_blocker": matrix.get("formal_completion_blocker"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the static public decision contract")
    parser.add_argument(
        "--verify-live", action="store_true", help="also verify public visibility and selected live anchors"
    )
    parser.add_argument("--json", action="store_true", help="emit a public-safe result summary")
    args = parser.parse_args()
    if not args.check and not args.verify_live:
        parser.error("one of --check or --verify-live is required")

    try:
        matrix = load_matrix()
    except ProofSetError as exc:
        print(f"flagship-proof-set: FAIL: {exc}", file=sys.stderr)
        return 1
    errors = validate_matrix(matrix, enforce_freshness=args.verify_live)
    if args.verify_live and not errors:
        errors.extend(validate_live(matrix))
    if errors:
        for error in errors:
            print(f"flagship-proof-set: FAIL: {error}", file=sys.stderr)
        return 1
    summary = public_summary(matrix)
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        mode = "live" if args.verify_live else "static"
        print(
            "flagship-proof-set: PASS: "
            f"{summary['candidate_count']} public candidates, "
            f"{len(summary['selected'])} selected, {len(summary['alternates'])} alternates ({mode})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
