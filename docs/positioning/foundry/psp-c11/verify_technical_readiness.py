#!/usr/bin/env python3
"""Build and validate the public-safe PSP-P13-W03 technical-readiness audit.

The tracked audit is conservative by design. A missing exact-head receipt is an
owned blocker and scores zero. Private repository facts remain in memory; the
public artifact contains only the opaque identifiers accepted by PSP-P13-W01.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import math
import re
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


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
BLOCKER_KEYS = {"code", "owner", "next_action"}
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
    names = {name for name in private_names | private_bare_names if name}
    repository_character = r"A-Za-z0-9_.-"
    leaks: set[str] = set()
    for path in sorted(PACKAGE.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name in names:
            if re.search(rf"(?<![{repository_character}]){re.escape(name)}(?![{repository_character}])", text):
                leaks.add(display_path(path))
    return sorted(leaks)


def collect_live_context(snapshot: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
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
    return _graphql_heads(public_repositories), _private_identity_leaks(private_names, private_bare_names)


def _blocker(code: str, next_action: str) -> dict[str, str]:
    return {"code": code, "owner": GENERIC_PRIVATE_OWNER, "next_action": next_action}


def _blocked_dimension() -> dict[str, Any]:
    return {"state": "blocked_unverified", "evidence_url": None}


def build_audit(snapshot: dict[str, Any], heads: dict[str, str], observed_at: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for source in snapshot.get("candidates", []):
        if not isinstance(source, dict):
            raise AuditError("accepted candidate snapshot contains a non-object row")
        candidate_id = source.get("candidate_id")
        visibility = source.get("visibility")
        if visibility == "private":
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "visibility": "private",
                    "readiness_status": "restricted",
                    "blocker": _blocker(
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
                "build_evidence_missing", "Run the reproducible build at the observed head and attach its receipt."
            ),
            _blocker("test_evidence_missing", "Run the exact-head test suite and attach its receipt."),
            _blocker("deploy_evidence_missing", "Attach a dated exact-head runtime or deployment receipt."),
            _blocker("documentation_evidence_missing", "Audit operator, recovery, and maintenance documentation."),
            _blocker("security_evidence_missing", "Complete the exact-head security and secret-boundary review."),
            _blocker(
                "data_custody_evidence_missing", "Document data classes, retention, deletion, and processing custody."
            ),
            _blocker(
                "ip_custody_evidence_missing", "Verify ownership, licensing, contributor, and repository custody."
            ),
            _blocker(
                "observability_return_evidence_missing",
                "Prove telemetry, rollback, revocation, and restore at the observed head.",
            ),
            _blocker("maintenance_evidence_missing", "Name a maintainer and record a bounded maintenance estimate."),
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


def _evidence_errors(value: Any, observed_head: str, label: str, expected_keys: set[str]) -> list[str]:
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
        lowered = str(evidence_url).lower()
        if any(token in lowered for token in FORBIDDEN_EVIDENCE_HINTS):
            errors.append(f"{label} cannot use metadata as technical proof")
    elif evidence_url is not None:
        errors.append(f"{label} without a verified result must not carry evidence")
    return errors


def _blocker_errors(value: Any, label: str) -> list[str]:
    if not _exact_keys(value, BLOCKER_KEYS):
        return [f"{label} must use the exact blocker schema"]
    errors: list[str] = []
    for key in sorted(BLOCKER_KEYS):
        if not _is_nonblank_text(value.get(key)):
            errors.append(f"{label}.{key} must be nonblank text")
    return errors


def _public_candidate_errors(row: dict[str, Any], expected: dict[str, Any], weights: dict[str, int]) -> list[str]:
    candidate_id = str(expected.get("candidate_id") or "unknown")
    label = f"candidate {candidate_id}"
    if set(row) != PUBLIC_KEYS:
        return [f"{label} must use the exact public row schema"]
    errors: list[str] = []
    if row.get("candidate_id") != expected.get("candidate_id") or row.get("visibility") != "public":
        errors.append(f"{label} identity or visibility drift")
    if row.get("repository") != expected.get("repository"):
        errors.append(f"{label} repository drift")
    head = row.get("observed_head")
    if not isinstance(head, str) or not SHA40.fullmatch(head):
        errors.append(f"{label} observed_head must be a 40-hex commit")
        head = ""
    dimension_states: dict[str, Any] = {}
    for dimension in ("build", "test", "deploy", "documentation", "data_custody", "ip_custody", "observability_return"):
        value = row.get(dimension)
        errors.extend(_evidence_errors(value, head, f"{label}.{dimension}", SIMPLE_DIMENSION_KEYS))
        dimension_states[dimension] = value.get("state") if isinstance(value, dict) else None
    security = row.get("security")
    errors.extend(_evidence_errors(security, head, f"{label}.security", SECURITY_KEYS))
    if isinstance(security, dict):
        if not isinstance(security.get("class"), str) or security.get("class") not in SECURITY_CLASSES:
            errors.append(f"{label}.security.class is invalid")
        if security.get("state") == "verified_pass" and security.get("class") == "unassessed":
            errors.append(f"{label}.security cannot pass while unassessed")
        dimension_states["security"] = security.get("state")
    maintenance = row.get("maintenance")
    errors.extend(_evidence_errors(maintenance, head, f"{label}.maintenance", MAINTENANCE_KEYS))
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
            errors.extend(_blocker_errors(maintenance.get("blocker"), f"{label}.maintenance.blocker"))
    blockers = row.get("blockers")
    if not isinstance(blockers, list) or not blockers:
        errors.append(f"{label}.blockers must be a nonempty list until every hard floor passes")
        blockers = []
    blocker_codes: list[str] = []
    for index, blocker in enumerate(blockers):
        errors.extend(_blocker_errors(blocker, f"{label}.blockers[{index}]"))
        if isinstance(blocker, dict) and isinstance(blocker.get("code"), str):
            blocker_codes.append(blocker["code"])
    if len(blocker_codes) != len(set(blocker_codes)):
        errors.append(f"{label}.blocker codes must be unique")
    expected_score = sum(
        weight for dimension, weight in weights.items() if dimension_states.get(dimension) == "verified_pass"
    )
    score = row.get("readiness_score")
    if not _is_nonnegative_int(score) or score > 100 or score != expected_score:
        errors.append(f"{label}.readiness_score drift")
    hard_unresolved = any(
        not isinstance(state, str) or state in {"verified_fail", "blocked_unverified"}
        for state in dimension_states.values()
    )
    expected_transfer = expected_score >= 75 and not hard_unresolved and not blockers
    if row.get("transfer_eligible") is not expected_transfer:
        errors.append(f"{label}.transfer_eligible drift")
    if row.get("transfer_eligible") is True and (hard_unresolved or blockers):
        errors.append(f"{label} cannot be transferable with unresolved hard blockers")
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
    errors.extend(_blocker_errors(row.get("blocker"), f"{label}.blocker"))
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
        "restricted" if row.get("visibility") == "private" else "blocked_unverified"
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
    for index, expected in enumerate(expected_candidates):
        if index >= len(candidates) or not isinstance(expected, dict):
            continue
        row = candidates[index]
        if not isinstance(row, dict):
            errors.append(f"candidate {expected.get('candidate_id')} must be an object")
            continue
        if expected.get("visibility") == "public":
            errors.extend(_public_candidate_errors(row, expected, weights))
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
        if args.live:
            heads, leaks = collect_live_context(snapshot)
        if write_path is not None:
            if not args.live or heads is None:
                raise AuditError("--write requires --live")
            generated = build_audit(
                snapshot,
                heads,
                dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            )
            errors = validate_audit(
                generated,
                snapshot,
                contract,
                live_heads=heads,
                private_leaks=leaks,
            )
            if errors:
                payload = _result(write_path, errors, generated)
                print(json.dumps(payload, sort_keys=True) if args.json else "\n".join(errors))
                return 1
            write_path.write_text(json.dumps(generated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            payload = _result(write_path, [], generated)
            print(json.dumps(payload, sort_keys=True) if args.json else "technical-readiness: PASS")
            return 0
        audit = load_json(audit_path)
        errors = validate_audit(audit, snapshot, contract, live_heads=heads, private_leaks=leaks)
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
