#!/usr/bin/env python3
"""Build and validate the public-safe PSP-P13-W03 technical-readiness audit.

The tracked audit is conservative by design. A missing exact-head receipt is an
owned blocker and scores zero. Private repository facts remain in memory; the
public artifact contains only the opaque identifiers accepted by PSP-P13-W01.
"""

from __future__ import annotations

import argparse
import base64
import collections
import datetime as dt
import hashlib
import json
import math
import re
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse


ROOT = Path(__file__).resolve().parents[4]
PACKAGE = ROOT / "docs/positioning/foundry/psp-c11"
AUDIT = PACKAGE / "technical-readiness-audit.json"
SNAPSHOT = PACKAGE / "product-candidate-snapshot.json"
CONTRACT = PACKAGE / "foundry-preflight-contract.json"
PREFLIGHT = ROOT / "scripts/positioning-foundry-preflight.py"

SOURCE_LOCK = {
    "w01_receipt": "https://github.com/organvm/limen/issues/2265#issuecomment-5295999920",
    "w01_accepted_head": "0239e60c68278b7f9747764b0212e8e8f1527c28",
    "w01_acceptance_sha256": "2280964c776528533bc982dadd028d99fbf80977034d48d2b99f5406654c7bbb",
    "candidate_identity_sha256": "9829f24cc353b23ab8812c8327905cec66ed4df92095552594b60caaf05bc2ca",
    "candidate_projection_sha256": "2f673c993c2334b234e97e622c361d6431042d3a11abbc9fad809e696840722b",
    "candidate_count": 62,
    "visibility": {"public": 54, "private": 8},
}

ROOT_KEYS = {
    "schema_version",
    "work_id",
    "status",
    "observed_at",
    "source_lock",
    "candidates",
    "summary",
    "external_effects",
    "owner_custody_unchanged",
}
PUBLIC_KEYS = {
    "candidate_id",
    "visibility",
    "repository",
    "observed_head",
    "build",
    "test",
    "deploy",
    "documentation",
    "security",
    "data_custody",
    "ip_custody",
    "observability_return",
    "maintenance",
    "readiness_score",
    "blockers",
    "transfer_eligible",
}
PRIVATE_KEYS = {
    "candidate_id",
    "visibility",
    "readiness_status",
    "blocker",
    "readiness_score",
    "transfer_eligible",
}
SIMPLE_DIMENSION_KEYS = {"state", "evidence_url"}
SECURITY_KEYS = {"class", "state", "evidence_url"}
MAINTENANCE_KEYS = {
    "state",
    "owner",
    "estimate_hours_per_month",
    "evidence_url",
    "blocker",
}
BLOCKER_KEYS = {"code", "owner", "next_action", "predicate"}
SUMMARY_KEYS = {
    "candidate_count",
    "visibility",
    "status_counts",
    "score_distribution",
    "blocker_owner_counts",
    "transfer_eligible",
}
STATES = {"verified_pass", "verified_fail", "not_applicable", "blocked_unverified"}
SECURITY_CLASSES = {"unassessed", "low", "moderate", "high", "critical"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_PRIVATE_ID = re.compile(r"^private-candidate-[0-9]{3}$")
FORBIDDEN_EVIDENCE_HINTS = {
    "homepage",
    "default_branch",
    "default-branch",
    "recent_push",
    "recent-push",
    "pushed_at",
}
DIMENSION_RECEIPT_TOKENS = {
    "build": ("build",),
    "test": ("test",),
    "deploy": ("deploy", "runtime"),
    "documentation": ("documentation", "operator-doc", "recovery-doc"),
    "security": ("security", "secret-boundary"),
    "data_custody": ("data-custody", "data_custody", "privacy-custody"),
    "ip_custody": ("ip-custody", "ip_custody", "ownership-custody"),
    "observability_return": ("observability-return", "observability_return", "rollback-return"),
    "maintenance": ("maintenance",),
}
EVIDENCE_RECEIPT_KEYS = {
    "schema_version",
    "repository",
    "commit",
    "dimension",
    "status",
    "observed_at",
    "command",
    "external_effects",
}
HARD_FLOOR_RULE = "Any unresolved IP, data, credential, or rollback boundary makes the candidate non-transferable."
HARD_FLOOR_DIMENSIONS = {"security", "data_custody", "ip_custody", "observability_return"}
DIMENSION_BLOCKER_CODES = {dimension: f"{dimension}_evidence_missing" for dimension in DIMENSION_RECEIPT_TOKENS}
GENERIC_PRIVATE_OWNER = "portfolio_owner"


class AuditError(RuntimeError):
    """A public-safe validation or live-observation failure."""


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AuditError(f"duplicate JSON member: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_without_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError, AuditError) as exc:
        raise AuditError(f"cannot load {display_path(path)}: {exc}") from exc
    if not isinstance(value, dict):
        raise AuditError(f"{display_path(path)} must contain an object")
    return value


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def _is_nonblank_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _valid_timestamp(value: Any) -> bool:
    if not _is_nonblank_text(value) or not value.endswith("Z"):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _valid_https_url(value: Any) -> bool:
    if not _is_nonblank_text(value):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def _url_pins_head(value: Any, observed_head: str) -> bool:
    if not _valid_https_url(value) or not SHA40.fullmatch(observed_head):
        return False
    parsed = urlparse(value)
    path_values = {segment for segment in parsed.path.split("/") if segment}
    query_values = {item for values in parse_qs(parsed.query, keep_blank_values=True).values() for item in values}
    return observed_head in path_values or observed_head in query_values


def _url_proves_dimension(value: Any, observed_head: str, repository: str, dimension: str) -> bool:
    """Require a dimension-named technical receipt in the candidate tree at the exact head."""
    if not _url_pins_head(value, observed_head) or dimension not in DIMENSION_RECEIPT_TOKENS:
        return False
    parsed = urlparse(value)
    if parsed.netloc.casefold() != "github.com":
        return False
    parts = [segment for segment in parsed.path.split("/") if segment]
    expected_repository = repository.split("/", 1)
    if len(parts) < 5 or len(expected_repository) != 2:
        return False
    if [part.casefold() for part in parts[:2]] != [part.casefold() for part in expected_repository]:
        return False
    if parts[2] != "blob" or parts[3] != observed_head:
        return False
    receipt_path = "/".join(parts[4:]).casefold()
    if "receipt" not in receipt_path and "evidence" not in receipt_path:
        return False
    return any(token in receipt_path for token in DIMENSION_RECEIPT_TOKENS[dimension])


def _evidence_location(value: str) -> tuple[str, str, str]:
    parts = [segment for segment in urlparse(value).path.split("/") if segment]
    if len(parts) < 5 or parts[2] != "blob":
        raise AuditError("technical evidence URL is not an exact-head repository blob")
    return "/".join(parts[:2]), parts[3], "/".join(parts[4:])


def _exact_keys(value: Any, expected: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == expected


def readiness_weights(contract: dict[str, Any]) -> dict[str, int]:
    dimensions = contract.get("readiness_model", {}).get("dimensions")
    if not isinstance(dimensions, list):
        raise AuditError("readiness model dimensions are missing")
    by_id: dict[str, int] = {}
    for row in dimensions:
        if not isinstance(row, dict) or not _is_nonblank_text(row.get("id")):
            raise AuditError("readiness model contains an invalid dimension")
        weight = row.get("weight")
        if not _is_nonnegative_int(weight):
            raise AuditError("readiness model contains an invalid weight")
        by_id[row["id"]] = weight
    required = {
        "build_test",
        "deploy_runtime",
        "documentation",
        "security",
        "data_privacy",
        "ip_custody",
        "observability_return",
        "maintenance",
    }
    if set(by_id) != required or by_id["build_test"] % 2:
        raise AuditError("readiness model dimension set or build/test allocation drifted")
    return {
        "build": by_id["build_test"] // 2,
        "test": by_id["build_test"] // 2,
        "deploy": by_id["deploy_runtime"],
        "documentation": by_id["documentation"],
        "security": by_id["security"],
        "data_custody": by_id["data_privacy"],
        "ip_custody": by_id["ip_custody"],
        "observability_return": by_id["observability_return"],
        "maintenance": by_id["maintenance"],
    }


def readiness_hard_floors(contract: dict[str, Any]) -> set[str]:
    rules = contract.get("readiness_model", {}).get("rules")
    if not isinstance(rules, list) or HARD_FLOOR_RULE not in rules:
        raise AuditError("readiness hard-floor rule drifted")
    return set(HARD_FLOOR_DIMENSIONS)


def readiness_score(dimension_states: dict[str, Any], weights: dict[str, int]) -> int:
    score = sum(
        weight
        for dimension, weight in weights.items()
        if dimension not in {"build", "test"} and dimension_states.get(dimension) == "verified_pass"
    )
    if dimension_states.get("build") == dimension_states.get("test") == "verified_pass":
        score += weights["build"] + weights["test"]
    return score


def _run_json(args: list[str], timeout: int = 240) -> dict[str, Any]:
    try:
        result = subprocess.run(
            args,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuditError("live GitHub observation failed closed") from exc
    if result.returncode != 0:
        raise AuditError("live GitHub observation failed closed")
    try:
        value = json.loads(result.stdout, object_pairs_hook=_object_without_duplicate_keys)
    except (json.JSONDecodeError, AuditError) as exc:
        raise AuditError("live GitHub observation returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise AuditError("live GitHub observation returned a non-object")
    return value


def _graphql_heads(repositories: list[str]) -> dict[str, str]:
    selections: list[str] = []
    for index, repository in enumerate(repositories):
        owner, name = repository.split("/", 1)
        selections.append(
            f"r{index}:repository(owner:{json.dumps(owner)},name:{json.dumps(name)})"
            "{isPrivate defaultBranchRef{target{... on Commit{oid}}}}"
        )
    response = _run_json(["gh", "api", "graphql", "-f", "query=query{" + "".join(selections) + "}"])
    data = response.get("data")
    if not isinstance(data, dict):
        raise AuditError("live GitHub head response is missing data")
    heads: dict[str, str] = {}
    for index, repository in enumerate(repositories):
        row = data.get(f"r{index}")
        target = ((row or {}).get("defaultBranchRef") or {}).get("target") if isinstance(row, dict) else None
        head = target.get("oid") if isinstance(target, dict) else None
        if (
            not isinstance(row, dict)
            or row.get("isPrivate") is not False
            or not isinstance(head, str)
            or not SHA40.fullmatch(head)
        ):
            raise AuditError(f"public candidate head observation failed for {repository}")
        heads[repository] = head
    return heads


def _private_identity_leaks(private_names: set[str], private_bare_names: set[str]) -> list[str]:
    names = {name.casefold() for name in private_names | private_bare_names if name}
    repository_character = r"A-Za-z0-9_.-"
    leaks: set[str] = set()
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            relative = path
        haystacks = [relative.as_posix().casefold(), *(part.casefold() for part in relative.parts)]
        try:
            haystacks.append(path.read_text(encoding="utf-8").casefold())
        except UnicodeDecodeError:
            pass
        for name in names:
            pattern = rf"(?<![{repository_character}]){re.escape(name)}(?![{repository_character}])"
            if any(re.search(pattern, haystack) for haystack in haystacks):
                leaks.add(display_path(path))
    return sorted(leaks)


def candidate_projection_digest(snapshot: dict[str, Any]) -> str:
    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list):
        raise AuditError("accepted candidate snapshot candidates are missing")
    identities: list[str] = []
    bindings: list[dict[str, str]] = []
    for row in candidates:
        candidate_id = row.get("candidate_id") if isinstance(row, dict) else None
        if not _is_nonblank_text(candidate_id):
            raise AuditError("accepted candidate snapshot contains an invalid identity")
        identities.append(candidate_id)
        visibility = row.get("visibility")
        repository = row.get("repository")
        if visibility == "public" and not _is_nonblank_text(repository):
            raise AuditError("accepted public candidate binding is invalid")
        if visibility == "private" and repository is not None:
            raise AuditError("accepted private candidate binding is not opaque")
        if visibility not in {"public", "private"}:
            raise AuditError("accepted candidate visibility is invalid")
        bindings.append(
            {
                "candidate_id": candidate_id,
                "repository": repository if isinstance(repository, str) else "",
                "visibility": visibility,
            }
        )
    if len(identities) != len(set(identities)):
        raise AuditError("accepted candidate snapshot contains duplicate identities")
    public_repositories = [
        binding["repository"].casefold() for binding in bindings if binding["visibility"] == "public"
    ]
    if len(public_repositories) != len(set(public_repositories)):
        raise AuditError("accepted public candidate bindings contain duplicate repositories")
    payload = json.dumps(
        sorted(bindings, key=lambda binding: binding["candidate_id"]), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _live_candidate_identity_digest(module: dict[str, Any], repositories: list[dict[str, Any]]) -> str:
    estate = module["load_yaml"](module["ESTATE"])
    product_names = [str(value) for value in ((estate.get("product_ledger") or {}).get("repos") or [])]
    by_name: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in repositories:
        by_name[str(row.get("name") or "")].append(row)
    resolved = [by_name.get(name, []) for name in product_names]
    if len(product_names) != SOURCE_LOCK["candidate_count"] or any(len(rows) != 1 for rows in resolved):
        raise AuditError("live accepted candidate identity resolution drifted")
    identities = sorted(str(rows[0].get("full_name") or "") for rows in resolved)
    if any(not identity for identity in identities):
        raise AuditError("live accepted candidate identity resolution drifted")
    return hashlib.sha256("\n".join(identities).encode("utf-8")).hexdigest()


def collect_live_context(snapshot: dict[str, Any]) -> tuple[dict[str, str], list[str], str]:
    module = runpy.run_path(str(PREFLIGHT))
    _, repositories = module["collect_live_repositories"]()
    public_repositories = sorted(
        row["repository"]
        for row in snapshot.get("candidates", [])
        if isinstance(row, dict) and row.get("visibility") == "public" and _is_nonblank_text(row.get("repository"))
    )
    by_name = {str(row.get("full_name") or ""): row for row in repositories if isinstance(row, dict)}
    if len(by_name) != len(repositories):
        raise AuditError("live owner census contains duplicate repository identities")
    for repository in public_repositories:
        if repository not in by_name or bool(by_name[repository].get("private")):
            raise AuditError(f"accepted public candidate is missing or private: {repository}")
    private_names = {name for name, row in by_name.items() if bool(row.get("private"))}
    public_bare_names = {
        str(row.get("name") or "") for row in repositories if isinstance(row, dict) and not bool(row.get("private"))
    }
    private_bare_names = {
        str(row.get("name") or "")
        for row in repositories
        if isinstance(row, dict) and bool(row.get("private")) and str(row.get("name") or "") not in public_bare_names
    }
    return (
        _graphql_heads(public_repositories),
        _private_identity_leaks(private_names, private_bare_names),
        _live_candidate_identity_digest(module, repositories),
    )


def collect_live_evidence_receipts(audit: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    receipts: dict[tuple[str, str], dict[str, Any]] = {}
    for row in audit.get("candidates", []):
        if not isinstance(row, dict) or row.get("visibility") != "public":
            continue
        candidate_id = row.get("candidate_id")
        for dimension in DIMENSION_RECEIPT_TOKENS:
            value = row.get(dimension)
            if not isinstance(value, dict) or value.get("state") not in {"verified_pass", "verified_fail"}:
                continue
            evidence_url = value.get("evidence_url")
            if not isinstance(candidate_id, str) or not isinstance(evidence_url, str):
                continue
            repository, commit, path = _evidence_location(evidence_url)
            response = _run_json(
                ["gh", "api", f"repos/{repository}/contents/{quote(path, safe='/')}?ref={quote(commit, safe='')}"]
            )
            encoded = response.get("content")
            if response.get("encoding") != "base64" or not isinstance(encoded, str):
                raise AuditError("live technical evidence blob is not decodable")
            try:
                decoded = base64.b64decode("".join(encoded.split()), validate=True).decode("utf-8")
                receipt = json.loads(decoded, object_pairs_hook=_object_without_duplicate_keys)
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError, AuditError) as exc:
                raise AuditError("live technical evidence receipt is invalid") from exc
            if not isinstance(receipt, dict):
                raise AuditError("live technical evidence receipt is not an object")
            receipts[(candidate_id, dimension)] = receipt
    return receipts


def _blocker(candidate_id: str, code: str, next_action: str) -> dict[str, str]:
    predicate = (
        "python3 -B docs/positioning/foundry/psp-c11/verify_technical_readiness.py "
        "--audit docs/positioning/foundry/psp-c11/technical-readiness-audit.json "
        f"--live --require-cleared {candidate_id}:{code} --json"
    )
    return {"code": code, "owner": GENERIC_PRIVATE_OWNER, "next_action": next_action, "predicate": predicate}


def _blocked_dimension() -> dict[str, Any]:
    return {"state": "blocked_unverified", "evidence_url": None}


def build_audit(snapshot: dict[str, Any], heads: dict[str, str], observed_at: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for source in snapshot.get("candidates", []):
        if not isinstance(source, dict):
            raise AuditError("accepted candidate snapshot contains a non-object row")
        candidate_id = source.get("candidate_id")
        visibility = source.get("visibility")
        if not _is_nonblank_text(candidate_id):
            raise AuditError("accepted candidate snapshot contains an invalid identity")
        if visibility == "private":
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "visibility": "private",
                    "readiness_status": "restricted",
                    "blocker": _blocker(
                        candidate_id,
                        "restricted_private_evidence",
                        "Complete the restricted technical audit under owner-controlled custody.",
                    ),
                    "readiness_score": 0,
                    "transfer_eligible": False,
                }
            )
            continue
        repository = source.get("repository")
        if not _is_nonblank_text(repository) or repository not in heads:
            raise AuditError("accepted public candidate is missing an observed head")
        blockers = [
            _blocker(
                candidate_id,
                "build_evidence_missing",
                "Run the reproducible build at the observed head and attach its receipt.",
            ),
            _blocker(candidate_id, "test_evidence_missing", "Run the exact-head test suite and attach its receipt."),
            _blocker(
                candidate_id,
                "deploy_evidence_missing",
                "Attach a dated exact-head runtime or deployment receipt.",
            ),
            _blocker(
                candidate_id,
                "documentation_evidence_missing",
                "Audit operator, recovery, and maintenance documentation.",
            ),
            _blocker(
                candidate_id,
                "security_evidence_missing",
                "Complete the exact-head security and secret-boundary review.",
            ),
            _blocker(
                candidate_id,
                "data_custody_evidence_missing",
                "Document data classes, retention, deletion, and processing custody.",
            ),
            _blocker(
                candidate_id,
                "ip_custody_evidence_missing",
                "Verify ownership, licensing, contributor, and repository custody.",
            ),
            _blocker(
                candidate_id,
                "observability_return_evidence_missing",
                "Prove telemetry, rollback, revocation, and restore at the observed head.",
            ),
            _blocker(
                candidate_id,
                "maintenance_evidence_missing",
                "Name a maintainer and record a bounded maintenance estimate.",
            ),
        ]
        candidates.append(
            {
                "candidate_id": candidate_id,
                "visibility": "public",
                "repository": repository,
                "observed_head": heads[repository],
                "build": _blocked_dimension(),
                "test": _blocked_dimension(),
                "deploy": _blocked_dimension(),
                "documentation": _blocked_dimension(),
                "security": {"class": "unassessed", **_blocked_dimension()},
                "data_custody": _blocked_dimension(),
                "ip_custody": _blocked_dimension(),
                "observability_return": _blocked_dimension(),
                "maintenance": {
                    "state": "blocked_unverified",
                    "owner": None,
                    "estimate_hours_per_month": None,
                    "evidence_url": None,
                    "blocker": blockers[-1],
                },
                "readiness_score": 0,
                "blockers": blockers,
                "transfer_eligible": False,
            }
        )
    result = {
        "schema_version": "limen.psp_p13_w03_technical_readiness.v1",
        "work_id": "PSP-P13-W03",
        "status": "ACCEPTANCE_EVIDENCE",
        "observed_at": observed_at,
        "source_lock": SOURCE_LOCK,
        "candidates": candidates,
        "summary": {},
        "external_effects": [],
        "owner_custody_unchanged": True,
    }
    result["summary"] = compute_summary(candidates)
    return result


def _evidence_receipt_errors(
    receipt: Any,
    repository: str,
    observed_head: str,
    dimension: str,
    state: str,
    label: str,
) -> list[str]:
    if not _exact_keys(receipt, EVIDENCE_RECEIPT_KEYS):
        return [f"{label} live receipt must use the exact evidence schema"]
    errors: list[str] = []
    expected_status = "pass" if state == "verified_pass" else "fail"
    if receipt.get("schema_version") != "limen.psp_p13_w03_technical_evidence.v1":
        errors.append(f"{label} live receipt schema version drift")
    if receipt.get("repository") != repository or receipt.get("commit") != observed_head:
        errors.append(f"{label} live receipt repository or commit drift")
    if receipt.get("dimension") != dimension or receipt.get("status") != expected_status:
        errors.append(f"{label} live receipt dimension or result drift")
    if not _valid_timestamp(receipt.get("observed_at")) or not _is_nonblank_text(receipt.get("command")):
        errors.append(f"{label} live receipt needs a timestamp and executable command")
    if receipt.get("external_effects") != []:
        errors.append(f"{label} live receipt must record zero external effects")
    return errors


def _evidence_errors(
    value: Any,
    observed_head: str,
    repository: str,
    dimension: str,
    label: str,
    expected_keys: set[str],
    live_receipt: dict[str, Any] | None = None,
    require_live_receipt: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not _exact_keys(value, expected_keys):
        return [f"{label} must use the exact dimension schema"]
    state = value.get("state")
    evidence_url = value.get("evidence_url")
    if not isinstance(state, str) or state not in STATES:
        errors.append(f"{label}.state is invalid")
    if isinstance(state, str) and state in {"verified_pass", "verified_fail"}:
        if not _url_pins_head(evidence_url, observed_head):
            errors.append(f"{label} evidence must be an HTTPS URL pinned to observed_head")
        elif not _url_proves_dimension(evidence_url, observed_head, repository, dimension):
            errors.append(f"{label} requires a dimension-specific exact-head technical receipt")
        elif require_live_receipt:
            errors.extend(_evidence_receipt_errors(live_receipt, repository, observed_head, dimension, state, label))
        lowered = str(evidence_url).lower()
        if any(token in lowered for token in FORBIDDEN_EVIDENCE_HINTS):
            errors.append(f"{label} cannot use metadata as technical proof")
    elif evidence_url is not None:
        errors.append(f"{label} without a verified result must not carry evidence")
    return errors


def _blocker_errors(value: Any, label: str, candidate_id: str) -> list[str]:
    if not _exact_keys(value, BLOCKER_KEYS):
        return [f"{label} must use the exact blocker schema"]
    errors: list[str] = []
    for key in sorted(BLOCKER_KEYS):
        if not _is_nonblank_text(value.get(key)):
            errors.append(f"{label}.{key} must be nonblank text")
    code = value.get("code")
    if _is_nonblank_text(code) and value.get("predicate") != _blocker(candidate_id, code, "unused")["predicate"]:
        errors.append(f"{label}.predicate must be the exact trusted live clearance command")
    return errors


def _public_candidate_errors(
    row: dict[str, Any],
    expected: dict[str, Any],
    weights: dict[str, int],
    hard_floors: set[str],
    live_receipts: dict[tuple[str, str], dict[str, Any]] | None,
) -> list[str]:
    candidate_id = str(expected.get("candidate_id") or "unknown")
    label = f"candidate {candidate_id}"
    if set(row) != PUBLIC_KEYS:
        return [f"{label} must use the exact public row schema"]
    errors: list[str] = []
    if row.get("candidate_id") != expected.get("candidate_id") or row.get("visibility") != "public":
        errors.append(f"{label} identity or visibility drift")
    if row.get("repository") != expected.get("repository"):
        errors.append(f"{label} repository drift")
    repository = str(expected.get("repository") or "")
    head = row.get("observed_head")
    if not isinstance(head, str) or not SHA40.fullmatch(head):
        errors.append(f"{label} observed_head must be a 40-hex commit")
        head = ""
    dimension_states: dict[str, Any] = {}
    for dimension in ("build", "test", "deploy", "documentation", "data_custody", "ip_custody", "observability_return"):
        value = row.get(dimension)
        errors.extend(
            _evidence_errors(
                value,
                head,
                repository,
                dimension,
                f"{label}.{dimension}",
                SIMPLE_DIMENSION_KEYS,
                (live_receipts or {}).get((candidate_id, dimension)),
                live_receipts is not None,
            )
        )
        dimension_states[dimension] = value.get("state") if isinstance(value, dict) else None
    security = row.get("security")
    errors.extend(
        _evidence_errors(
            security,
            head,
            repository,
            "security",
            f"{label}.security",
            SECURITY_KEYS,
            (live_receipts or {}).get((candidate_id, "security")),
            live_receipts is not None,
        )
    )
    if isinstance(security, dict):
        if not isinstance(security.get("class"), str) or security.get("class") not in SECURITY_CLASSES:
            errors.append(f"{label}.security.class is invalid")
        if security.get("state") == "verified_pass" and security.get("class") == "unassessed":
            errors.append(f"{label}.security cannot pass while unassessed")
        dimension_states["security"] = security.get("state")
    maintenance = row.get("maintenance")
    errors.extend(
        _evidence_errors(
            maintenance,
            head,
            repository,
            "maintenance",
            f"{label}.maintenance",
            MAINTENANCE_KEYS,
            (live_receipts or {}).get((candidate_id, "maintenance")),
            live_receipts is not None,
        )
    )
    if isinstance(maintenance, dict):
        state = maintenance.get("state")
        dimension_states["maintenance"] = state
        if state == "verified_pass":
            estimate = maintenance.get("estimate_hours_per_month")
            if (
                not _is_nonblank_text(maintenance.get("owner"))
                or not _is_finite_number(estimate)
                or float(estimate) <= 0
            ):
                errors.append(f"{label}.maintenance pass requires an owner and bounded positive estimate")
            if maintenance.get("blocker") is not None:
                errors.append(f"{label}.maintenance pass cannot retain a blocker")
        else:
            if maintenance.get("owner") is not None or maintenance.get("estimate_hours_per_month") is not None:
                errors.append(f"{label}.maintenance unresolved state must not claim owner or estimate")
            errors.extend(_blocker_errors(maintenance.get("blocker"), f"{label}.maintenance.blocker", candidate_id))
    blockers = row.get("blockers")
    if not isinstance(blockers, list):
        errors.append(f"{label}.blockers must be a list")
        blockers = []
    blocker_codes: list[str] = []
    for index, blocker in enumerate(blockers):
        errors.extend(_blocker_errors(blocker, f"{label}.blockers[{index}]", candidate_id))
        if isinstance(blocker, dict) and isinstance(blocker.get("code"), str):
            blocker_codes.append(blocker["code"])
    if len(blocker_codes) != len(set(blocker_codes)):
        errors.append(f"{label}.blocker codes must be unique")
    unresolved_dimensions = {
        dimension
        for dimension, state in dimension_states.items()
        if isinstance(state, str) and state in {"verified_fail", "blocked_unverified"}
    }
    expected_dimension_blockers = {DIMENSION_BLOCKER_CODES[dimension] for dimension in unresolved_dimensions}
    observed_dimension_blockers = set(blocker_codes) & set(DIMENSION_BLOCKER_CODES.values())
    if observed_dimension_blockers != expected_dimension_blockers:
        errors.append(f"{label}.blockers must exactly cover every unresolved dimension")
    expected_score = readiness_score(dimension_states, weights)
    score = row.get("readiness_score")
    if not _is_nonnegative_int(score) or score > 100 or score != expected_score:
        errors.append(f"{label}.readiness_score drift")
    all_hard_floors_pass = hard_floors <= dimension_states.keys() and all(
        dimension_states[dimension] == "verified_pass" for dimension in hard_floors
    )
    if not blockers and not all_hard_floors_pass:
        errors.append(f"{label}.blockers may be empty only after every hard floor passes")
    hard_blocker_codes = {DIMENSION_BLOCKER_CODES[dimension] for dimension in hard_floors}
    hard_unresolved = not all_hard_floors_pass or bool(set(blocker_codes) & hard_blocker_codes)
    accepted_lifecycle = expected.get("current_state") != "archived" and expected.get("preflight_disposition") != "park"
    expected_transfer = expected_score >= 75 and not hard_unresolved and accepted_lifecycle
    if row.get("transfer_eligible") is not expected_transfer:
        errors.append(f"{label}.transfer_eligible drift")
    if row.get("transfer_eligible") is True and hard_unresolved:
        errors.append(f"{label} cannot be transferable with unresolved hard blockers")
    if row.get("transfer_eligible") is True and not accepted_lifecycle:
        errors.append(f"{label} accepted archived or parked lifecycle cannot be transferable")
    return errors


def _private_candidate_errors(row: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    candidate_id = str(expected.get("candidate_id") or "unknown")
    label = f"candidate {candidate_id}"
    if set(row) != PRIVATE_KEYS:
        return [f"{label} must use the exact private row schema"]
    errors: list[str] = []
    if row.get("candidate_id") != candidate_id or not OPAQUE_PRIVATE_ID.fullmatch(candidate_id):
        errors.append(f"{label} must retain its opaque accepted identity")
    if row.get("visibility") != "private" or row.get("readiness_status") != "restricted":
        errors.append(f"{label} private status drift")
    errors.extend(_blocker_errors(row.get("blocker"), f"{label}.blocker", candidate_id))
    blocker = row.get("blocker")
    if isinstance(blocker, dict) and blocker.get("owner") != GENERIC_PRIVATE_OWNER:
        errors.append(f"{label} must expose only the generic accountable owner role")
    if row.get("readiness_score") != 0 or row.get("transfer_eligible") is not False:
        errors.append(f"{label} private readiness must remain zero and non-transferable")
    return errors


def compute_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    visibility = collections.Counter(
        row.get("visibility") if isinstance(row.get("visibility"), str) else "<invalid>"
        for row in candidates
        if isinstance(row, dict)
    )
    status_counts = collections.Counter(
        (
            "restricted"
            if row.get("visibility") == "private"
            else "transfer_ready"
            if row.get("transfer_eligible") is True
            else "blocked_unverified"
        )
        for row in candidates
        if isinstance(row, dict)
    )
    scores = collections.Counter(
        str(row.get("readiness_score")) if _is_nonnegative_int(row.get("readiness_score")) else "<invalid>"
        for row in candidates
        if isinstance(row, dict)
    )
    blocker_owners: collections.Counter[str] = collections.Counter()
    for row in candidates:
        if not isinstance(row, dict):
            continue
        if row.get("visibility") == "private":
            blocker = row.get("blocker")
            if isinstance(blocker, dict) and isinstance(blocker.get("owner"), str):
                blocker_owners[blocker["owner"]] += 1
        else:
            for blocker in row.get("blockers", []):
                if isinstance(blocker, dict) and isinstance(blocker.get("owner"), str):
                    blocker_owners[blocker["owner"]] += 1
    return {
        "candidate_count": len(candidates),
        "visibility": {"public": visibility.get("public", 0), "private": visibility.get("private", 0)},
        "status_counts": dict(sorted(status_counts.items())),
        "score_distribution": dict(sorted(scores.items())),
        "blocker_owner_counts": dict(sorted(blocker_owners.items())),
        "transfer_eligible": sum(row.get("transfer_eligible") is True for row in candidates if isinstance(row, dict)),
    }


def validate_audit(
    audit: dict[str, Any],
    snapshot: dict[str, Any],
    contract: dict[str, Any],
    *,
    live_heads: dict[str, str] | None = None,
    private_leaks: list[str] | None = None,
    live_candidate_identity_sha256: str | None = None,
    live_receipts: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[str]:
    errors: list[str] = []
    if set(audit) != ROOT_KEYS:
        return ["audit must use the exact root schema"]
    if audit.get("schema_version") != "limen.psp_p13_w03_technical_readiness.v1":
        errors.append("audit schema_version drift")
    if audit.get("work_id") != "PSP-P13-W03" or audit.get("status") != "ACCEPTANCE_EVIDENCE":
        errors.append("audit work_id or status drift")
    if not _valid_timestamp(audit.get("observed_at")):
        errors.append("audit observed_at must be an RFC3339 UTC timestamp")
    if audit.get("source_lock") != SOURCE_LOCK:
        errors.append("audit source_lock drift")
    denominator = snapshot.get("candidate_denominator")
    if not isinstance(denominator, dict):
        errors.append("accepted candidate denominator is missing")
    else:
        if denominator.get("count") != SOURCE_LOCK["candidate_count"]:
            errors.append("accepted candidate count drift")
        if denominator.get("visibility") != {"private": 8, "public": 54}:
            errors.append("accepted candidate visibility drift")
        if denominator.get("identity_sha256") != SOURCE_LOCK["candidate_identity_sha256"]:
            errors.append("accepted candidate identity digest drift")
    try:
        projection_digest = candidate_projection_digest(snapshot)
    except AuditError as exc:
        errors.append(str(exc))
    else:
        if projection_digest != SOURCE_LOCK["candidate_projection_sha256"]:
            errors.append("accepted candidate projection digest drift")
    if (
        live_candidate_identity_sha256 is not None
        and live_candidate_identity_sha256 != SOURCE_LOCK["candidate_identity_sha256"]
    ):
        errors.append("live accepted candidate identity digest drift")
    candidates = audit.get("candidates")
    expected_candidates = snapshot.get("candidates")
    if not isinstance(candidates, list) or not isinstance(expected_candidates, list):
        return errors + ["audit and accepted snapshot candidates must be lists"]
    if len(candidates) != len(expected_candidates):
        errors.append("audit candidate count drift")
    expected_ids = [row.get("candidate_id") if isinstance(row, dict) else None for row in expected_candidates]
    observed_ids = [row.get("candidate_id") if isinstance(row, dict) else None for row in candidates]
    observed_ids_are_text = all(isinstance(candidate_id, str) for candidate_id in observed_ids)
    if observed_ids != expected_ids or not observed_ids_are_text or len(set(observed_ids)) != len(observed_ids):
        errors.append("audit candidate identity set or order drift")
    weights = readiness_weights(contract)
    hard_floors = readiness_hard_floors(contract)
    for index, expected in enumerate(expected_candidates):
        if index >= len(candidates) or not isinstance(expected, dict):
            continue
        row = candidates[index]
        if not isinstance(row, dict):
            errors.append(f"candidate {expected.get('candidate_id')} must be an object")
            continue
        if expected.get("visibility") == "public":
            errors.extend(_public_candidate_errors(row, expected, weights, hard_floors, live_receipts))
            if live_heads is not None:
                repository = expected.get("repository")
                if live_heads.get(repository) != row.get("observed_head"):
                    errors.append(f"candidate {expected.get('candidate_id')} observed_head drifted live")
        elif expected.get("visibility") == "private":
            errors.extend(_private_candidate_errors(row, expected))
        else:
            errors.append(f"candidate {expected.get('candidate_id')} has invalid accepted visibility")
    summary = audit.get("summary")
    if not _exact_keys(summary, SUMMARY_KEYS) or summary != compute_summary(candidates):
        errors.append("audit summary drift")
    if audit.get("external_effects") != []:
        errors.append("audit validation must have zero external effects")
    if audit.get("owner_custody_unchanged") is not True:
        errors.append("audit must preserve owner custody")
    if private_leaks:
        errors.append("private repository identity leaked into public C11 paths")
    return errors


def required_blocker_errors(audit: dict[str, Any], requirement: str | None) -> list[str]:
    if requirement is None:
        return []
    candidate_id, separator, code = requirement.partition(":")
    if not separator or not _is_nonblank_text(candidate_id) or not _is_nonblank_text(code):
        return ["--require-cleared must be CANDIDATE_ID:BLOCKER_CODE"]
    row = next(
        (
            item
            for item in audit.get("candidates", [])
            if isinstance(item, dict) and item.get("candidate_id") == candidate_id
        ),
        None,
    )
    if row is None:
        return ["--require-cleared candidate is not in the accepted denominator"]
    blockers: list[Any] = []
    if row.get("visibility") == "private":
        blockers.append(row.get("blocker"))
    else:
        blockers.extend(row.get("blockers", []))
        maintenance = row.get("maintenance")
        if isinstance(maintenance, dict):
            blockers.append(maintenance.get("blocker"))
    if any(isinstance(blocker, dict) and blocker.get("code") == code for blocker in blockers):
        return ["required blocker remains uncleared"]
    return []


def _result(audit_path: Path, errors: list[str], audit: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "status": "pass" if not errors else "fail",
        "work_id": "PSP-P13-W03",
        "audit": display_path(audit_path),
        "errors": errors,
        "summary": audit.get("summary") if audit is not None and not errors else None,
        "external_effects": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, default=AUDIT)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--write", type=Path)
    parser.add_argument("--require-cleared")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit_path = args.audit if args.audit.is_absolute() else ROOT / args.audit
    write_path = args.write if args.write is None or args.write.is_absolute() else ROOT / args.write
    try:
        snapshot = load_json(SNAPSHOT)
        contract = load_json(CONTRACT)
        heads: dict[str, str] | None = None
        leaks: list[str] | None = None
        live_identity_digest: str | None = None
        live_receipts: dict[tuple[str, str], dict[str, Any]] | None = None
        if args.require_cleared and not args.live:
            raise AuditError("--require-cleared requires --live")
        if args.live:
            heads, leaks, live_identity_digest = collect_live_context(snapshot)
        if write_path is not None:
            if not args.live or heads is None:
                raise AuditError("--write requires --live")
            generated = build_audit(
                snapshot,
                heads,
                dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            )
            live_receipts = collect_live_evidence_receipts(generated)
            errors = validate_audit(
                generated,
                snapshot,
                contract,
                live_heads=heads,
                private_leaks=leaks,
                live_candidate_identity_sha256=live_identity_digest,
                live_receipts=live_receipts,
            )
            errors.extend(required_blocker_errors(generated, args.require_cleared))
            if errors:
                payload = _result(write_path, errors, generated)
                print(json.dumps(payload, sort_keys=True) if args.json else "\n".join(errors))
                return 1
            write_path.write_text(json.dumps(generated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            payload = _result(write_path, [], generated)
            print(json.dumps(payload, sort_keys=True) if args.json else "technical-readiness: PASS")
            return 0
        audit = load_json(audit_path)
        if args.live:
            live_receipts = collect_live_evidence_receipts(audit)
        errors = validate_audit(
            audit,
            snapshot,
            contract,
            live_heads=heads,
            private_leaks=leaks,
            live_candidate_identity_sha256=live_identity_digest,
            live_receipts=live_receipts,
        )
        errors.extend(required_blocker_errors(audit, args.require_cleared))
        payload = _result(audit_path, errors, audit)
        print(
            json.dumps(payload, sort_keys=True)
            if args.json
            else ("technical-readiness: PASS" if not errors else "\n".join(errors))
        )
        return 0 if not errors else 1
    except AuditError as exc:
        payload = _result(audit_path, [str(exc)], None)
        print(json.dumps(payload, sort_keys=True) if args.json else str(exc))
        return 1
    except Exception:
        payload = _result(audit_path, ["technical-readiness validation failed closed"], None)
        print(json.dumps(payload, sort_keys=True) if args.json else payload["errors"][0])
        return 1


if __name__ == "__main__":
    sys.exit(main())
