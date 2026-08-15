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
import copy
import datetime as dt
import functools
import hashlib
import json
import math
import os
import re
import runpy
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
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
    "w01_receipt_sha256": "18b9348da9f1819f43d2c11b9065cb927966482309b0c304e21bf8c03e5ca7ce",
    "w01_accepted_head": "0239e60c68278b7f9747764b0212e8e8f1527c28",
    "w01_acceptance_sha256": "2280964c776528533bc982dadd028d99fbf80977034d48d2b99f5406654c7bbb",
    "candidate_identity_sha256": "9829f24cc353b23ab8812c8327905cec66ed4df92095552594b60caaf05bc2ca",
    "candidate_projection_sha256": "53db24ccc3cc2cfd2498e7e58bd4c94a6279343b775bae95ec3d5cd8ec52d3c9",
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
    "clearance_receipt_sha256",
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
MAINTENANCE_PASS_KEYS = MAINTENANCE_KEYS | {"funding_evidence_url", "response_window_hours"}
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
PASSABLE_SECURITY_CLASSES = {"low", "moderate"}
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
OPAQUE_PRIVATE_ID = re.compile(r"^private-candidate-[0-9]{3}$")
SAFE_BLOCKER_CODE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
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
    "tested_commit",
    "dimension",
    "status",
    "exit_code",
    "run_attempt",
    "provenance_url",
    "predicate_path",
    "output_path",
    "output_sha256",
    "artifact_path",
    "artifact_sha256",
    "observed_at",
    "external_effects",
}
RESOLVED_EVIDENCE_KEYS = {
    "receipt",
    "receipt_repository",
    "receipt_commit",
    "output_sha256",
    "artifact_sha256",
    "provenance",
}
RESOLVED_MAINTENANCE_EVIDENCE_KEYS = RESOLVED_EVIDENCE_KEYS | {"funding"}
RESOLVED_SECURITY_EVIDENCE_KEYS = RESOLVED_EVIDENCE_KEYS | {"assessment"}
SECURITY_ASSESSMENT_KEYS = {
    "schema_version",
    "repository",
    "tested_commit",
    "classification",
    "observed_at",
    "external_effects",
}
MAINTENANCE_EVIDENCE_RECEIPT_KEYS = EVIDENCE_RECEIPT_KEYS | {"response_window_hours"}
FUNDING_RECEIPT_KEYS = {
    "schema_version",
    "repository",
    "tested_commit",
    "status",
    "capacity_hours_per_month",
    "run_attempt",
    "provenance_url",
    "predicate_path",
    "artifact_path",
    "artifact_sha256",
    "observed_at",
    "external_effects",
}
RESOLVED_FUNDING_KEYS = {
    "receipt",
    "receipt_repository",
    "receipt_commit",
    "artifact_sha256",
    "provenance",
}
TRUSTED_RECEIPT_REPOSITORIES = {"organvm/limen"}
EXECUTED_FAILURE_CONCLUSIONS = {"failure", "timed_out"}
HARD_FLOOR_RULE = "Any unresolved IP, data, credential, or rollback boundary makes the candidate non-transferable."
HARD_FLOOR_DIMENSIONS = {"security", "data_custody", "ip_custody", "observability_return"}
DIMENSION_BLOCKER_CODES = {dimension: f"{dimension}_evidence_missing" for dimension in DIMENSION_RECEIPT_TOKENS}
GENERIC_PRIVATE_OWNER = "portfolio_owner"
PRIVATE_CLEARANCE_SCHEMA = "limen.psp_p13_w03_private_clearances.v1"
PRIVATE_CLEARANCE_ENV = "LIMEN_P13_W03_PRIVATE_CLEARANCE_RECEIPTS"
LIVE_COLLECTION_DEADLINE_SECONDS = 270
LIVE_COLLECTION_CALL_LIMIT = 96
GOVERNED_TRANSFER_BLOCKERS = {
    "no_E3_or_stronger_primary_demand_receipt",
    "no_operator_selected_or_scored",
    "human_terms_and_contract_gates_unpulled",
    "no_observed_pilot",
}


class AuditError(RuntimeError):
    """A public-safe validation or live-observation failure."""


class LiveCollection:
    """One fail-closed deadline, call budget, and immutable-response cache per live gate."""

    def __init__(
        self,
        deadline_seconds: float = LIVE_COLLECTION_DEADLINE_SECONDS,
        call_limit: int = LIVE_COLLECTION_CALL_LIMIT,
        clock: Any = time.monotonic,
    ) -> None:
        if (
            not _is_finite_number(deadline_seconds)
            or deadline_seconds <= 0
            or not _is_nonnegative_int(call_limit)
            or call_limit <= 0
        ):
            raise AuditError("live evidence collection budget is invalid")
        self._clock = clock
        self._deadline = clock() + float(deadline_seconds)
        self._call_limit = call_limit
        self.calls = 0
        self._json_cache: dict[tuple[str, ...], dict[str, Any]] = {}

    def run_json(self, args: list[str], timeout: int) -> dict[str, Any]:
        key = tuple(args)
        if key in self._json_cache:
            return copy.deepcopy(self._json_cache[key])
        remaining = self._deadline - self._clock()
        if self.calls >= self._call_limit or remaining <= 0:
            raise AuditError("live evidence collection budget exhausted")
        self.calls += 1
        value = _run_json(args, timeout=max(1, min(timeout, math.ceil(remaining))))
        self._json_cache[key] = copy.deepcopy(value)
        return value


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


def _parse_timestamp(value: Any) -> dt.datetime | None:
    if not _is_nonblank_text(value) or not value.endswith("Z"):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _valid_timestamp(value: Any) -> bool:
    return _parse_timestamp(value) is not None


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
    """Require a dimension-named immutable receipt that can test observed_head."""
    if not _valid_https_url(value) or not SHA40.fullmatch(observed_head) or dimension not in DIMENSION_RECEIPT_TOKENS:
        return False
    parsed = urlparse(value)
    if parsed.netloc.casefold() != "github.com":
        return False
    parts = [segment for segment in parsed.path.split("/") if segment]
    if len(parts) < 5 or parts[2] != "blob" or not SHA40.fullmatch(parts[3]):
        return False
    receipt_repository = "/".join(parts[:2]).casefold()
    allowed = {repository.casefold(), *(value.casefold() for value in TRUSTED_RECEIPT_REPOSITORIES)}
    if receipt_repository not in allowed:
        return False
    receipt_path = "/".join(parts[4:]).casefold()
    if "receipt" not in receipt_path and "evidence" not in receipt_path:
        return False
    return any(token in receipt_path for token in DIMENSION_RECEIPT_TOKENS[dimension])


def _url_proves_maintenance_funding(value: Any, observed_head: str, repository: str) -> bool:
    if not _url_proves_dimension(value, observed_head, repository, "maintenance"):
        return False
    receipt_path = "/".join(urlparse(str(value)).path.split("/")[5:]).casefold()
    return "fund" in receipt_path


def _evidence_location(value: str) -> tuple[str, str, str]:
    parts = [segment for segment in urlparse(value).path.split("/") if segment]
    if len(parts) < 5 or parts[2] != "blob":
        raise AuditError("technical evidence URL is not an exact-head repository blob")
    return "/".join(parts[:2]), parts[3], "/".join(parts[4:])


def _safe_relative_path(value: Any) -> bool:
    if not _is_nonblank_text(value) or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and path.as_posix() == value and ".." not in path.parts and value != "."


def _actions_run_id(value: Any, repository: str) -> str | None:
    if not _valid_https_url(value):
        return None
    parsed = urlparse(value)
    parts = [segment for segment in parsed.path.split("/") if segment]
    if parsed.netloc.casefold() != "github.com" or len(parts) != 5 or parts[2:4] != ["actions", "runs"]:
        return None
    if "/".join(parts[:2]).casefold() != repository.casefold() or not parts[4].isdigit():
        return None
    return parts[4]


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
        if row["id"] in by_id:
            raise AuditError("readiness model contains duplicate dimensions")
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
    if set(by_id) != required or by_id["build_test"] % 2 or sum(by_id.values()) != 100:
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


def readiness_transfer_threshold(contract: dict[str, Any]) -> int:
    value = (
        contract.get("economics_and_kill_rules", {})
        .get("transfer_floor", {})
        .get("technical_readiness_minimum")
    )
    if not _is_nonnegative_int(value) or value > 100:
        raise AuditError("technical readiness transfer threshold is invalid")
    return value


def governed_transfer_floors_pass(candidate: dict[str, Any], contract: dict[str, Any]) -> bool:
    transfer_floor = contract.get("economics_and_kill_rules", {}).get("transfer_floor", {})
    demand_minimum = transfer_floor.get("demand_score_minimum")
    operator_minimum = transfer_floor.get("operator_score_minimum")
    tiers = contract.get("demand_model", {}).get("evidence_tiers")
    tier_ids = [row.get("id") for row in tiers] if isinstance(tiers, list) else []
    if (
        not _is_nonnegative_int(demand_minimum)
        or not _is_nonnegative_int(operator_minimum)
        or len(tier_ids) != len(set(tier_ids))
        or "E3" not in tier_ids
    ):
        raise AuditError("governed nontechnical transfer floor drifted")
    demand = candidate.get("demand")
    economics = candidate.get("economics")
    blockers = candidate.get("blocking_evidence")
    if not isinstance(demand, dict) or not isinstance(economics, dict) or not isinstance(blockers, list):
        return False
    demand_tier = demand.get("tier")
    demand_score = demand.get("score")
    allowed_tiers = set(tier_ids[tier_ids.index("E3") :])
    return (
        candidate.get("transfer_eligible") is True
        and demand_tier in allowed_tiers
        and _is_nonnegative_int(demand_score)
        and demand_score >= demand_minimum
        and economics.get("status") == "transfer_floor_passed"
        and economics.get("runway") == "approved"
        and not (set(str(value) for value in blockers) & GOVERNED_TRANSFER_BLOCKERS)
    )


def readiness_maintenance_maximum(contract: dict[str, Any]) -> float:
    value = contract.get("readiness_model", {}).get("maintenance_estimate_hours_per_month_maximum")
    if not _is_finite_number(value) or not 0 < float(value) <= 168:
        raise AuditError("maintenance estimate maximum is invalid")
    return float(value)


def readiness_maintenance_response_maximum(contract: dict[str, Any]) -> float:
    value = contract.get("readiness_model", {}).get("maintenance_response_window_hours_maximum")
    if not _is_finite_number(value) or not 0 < float(value) <= 720:
        raise AuditError("maintenance response-window maximum is invalid")
    return float(value)


def readiness_score(dimension_states: dict[str, Any], weights: dict[str, int]) -> int:
    score = sum(
        weight
        for dimension, weight in weights.items()
        if dimension not in {"build", "test"} and dimension_states.get(dimension) == "verified_pass"
    )
    if dimension_states.get("build") == dimension_states.get("test") == "verified_pass":
        score += weights["build"] + weights["test"]
    return score


def _run_json(
    args: list[str],
    timeout: int = 240,
    collection: LiveCollection | None = None,
) -> dict[str, Any]:
    if collection is not None:
        return collection.run_json(args, timeout)
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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def collect_public_heads(snapshot: dict[str, Any]) -> dict[str, str]:
    repositories = sorted(
        row["repository"]
        for row in snapshot.get("candidates", [])
        if isinstance(row, dict) and row.get("visibility") == "public" and _is_nonblank_text(row.get("repository"))
    )
    if len(repositories) != SOURCE_LOCK["visibility"]["public"] or len(repositories) != len(set(repositories)):
        raise AuditError("accepted public candidate repository set drifted")
    return _graphql_heads(repositories)


@functools.cache
def accepted_w01_acceptance_digest() -> str:
    try:
        module = runpy.run_path(str(ROOT / "scripts/positioning-program.py"))
        graph = module["index_program"](module["load_manifest"]())
        packet = graph["work_by_id"]["PSP-P13-W01"]
        return module["acceptance_digest"](packet)
    except Exception as exc:
        raise AuditError("accepted W01 acceptance digest cannot be recomputed") from exc


def verify_w01_live_receipt(collection: LiveCollection | None = None) -> None:
    verification = _run_json(
        ["python3", "scripts/positioning-program.py", "--verify-work", "PSP-P13-W01", "--json"],
        collection=collection,
    )
    if (
        verification.get("status") != "pass"
        or verification.get("work_id") != "PSP-P13-W01"
        or verification.get("receipt_url") != SOURCE_LOCK["w01_receipt"]
        or verification.get("receipt_sha256") != SOURCE_LOCK["w01_receipt_sha256"]
    ):
        raise AuditError("accepted W01 marked receipt verification drifted")
    comment = _run_json(
        ["gh", "api", "repos/organvm/limen/issues/comments/5295999920"],
        collection=collection,
    )
    body = comment.get("body")
    if comment.get("html_url") != SOURCE_LOCK["w01_receipt"] or not isinstance(body, str):
        raise AuditError("accepted W01 marked receipt resolution drifted")
    match = re.search(
        r"<!--\s*positioning-receipt:PSP-P13-W01\s*-->\s*```json\s*(\{.*?\})\s*```",
        body,
        re.DOTALL,
    )
    if match is None:
        raise AuditError("accepted W01 marked receipt block is missing")
    try:
        receipt = json.loads(match.group(1), object_pairs_hook=_object_without_duplicate_keys)
    except (json.JSONDecodeError, AuditError) as exc:
        raise AuditError("accepted W01 marked receipt block is invalid") from exc
    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if (
        not isinstance(receipt, dict)
        or receipt.get("acceptance_sha256") != SOURCE_LOCK["w01_acceptance_sha256"]
        or (receipt.get("observed_heads") or {}).get("organvm/limen") != SOURCE_LOCK["w01_accepted_head"]
        or hashlib.sha256(canonical).hexdigest() != SOURCE_LOCK["w01_receipt_sha256"]
    ):
        raise AuditError("accepted W01 marked receipt binding drifted")


def load_private_clearance_receipts() -> dict[str, str]:
    configured = os.environ.get(PRIVATE_CLEARANCE_ENV)
    if not configured:
        return {}
    path = Path(os.path.abspath(Path(configured).expanduser()))
    try:
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise AuditError("private clearance custody receipt must be a regular non-symlink file")
        if before.st_uid != os.getuid() or stat.S_IMODE(before.st_mode) != 0o600:
            raise AuditError("private clearance custody receipt must use owner-only mode 0600")
        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            relative = None
        if relative is not None:
            tracked = subprocess.run(
                ["git", "ls-files", "--error-unmatch", "--", relative.as_posix()],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            ignored = subprocess.run(
                ["git", "check-ignore", "--quiet", "--", relative.as_posix()],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            if tracked.returncode != 1 or ignored.returncode != 0:
                raise AuditError("private clearance custody receipt is not in an untracked private-safe path")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
            os.close(descriptor)
            raise AuditError("private clearance custody receipt changed during validation")
        with os.fdopen(descriptor, encoding="utf-8") as handle:
            payload = json.load(handle, object_pairs_hook=_object_without_duplicate_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, subprocess.TimeoutExpired, AuditError) as exc:
        raise AuditError("private clearance custody receipt cannot be loaded") from exc
    if not isinstance(payload, dict):
        raise AuditError("private clearance custody receipt must be an object")
    if set(payload) != {"schema_version", "receipts"} or payload.get("schema_version") != PRIVATE_CLEARANCE_SCHEMA:
        raise AuditError("private clearance custody receipt schema drifted")
    receipts = payload.get("receipts")
    if not isinstance(receipts, dict) or any(
        not OPAQUE_PRIVATE_ID.fullmatch(str(candidate_id)) or not SHA64.fullmatch(str(digest))
        for candidate_id, digest in receipts.items()
    ):
        raise AuditError("private clearance custody receipt bindings are invalid")
    return {str(candidate_id): str(digest) for candidate_id, digest in receipts.items()}


def _private_identity_leaks(private_names: set[str], private_bare_names: set[str]) -> list[str]:
    full_names = {name.casefold() for name in private_names if name}
    bare_names = {name.casefold() for name in private_bare_names if name}
    repository_character = r"A-Za-z0-9_.-"
    leaks: set[str] = set()
    try:
        package_path = str(PACKAGE.relative_to(ROOT))
    except ValueError:
        package_path = str(PACKAGE)
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", package_path],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=240,
        )
    except subprocess.TimeoutExpired as exc:
        raise AuditError("tracked public C11 path listing timed out") from exc
    if result.returncode != 0:
        raise AuditError("tracked public C11 path listing failed")
    tracked = [ROOT / line for line in result.stdout.splitlines() if line.strip()]
    for path in tracked:
        try:
            relative = path.relative_to(ROOT)
        except ValueError:
            relative = path
        path_haystacks = [relative.as_posix().casefold(), *(part.casefold() for part in relative.parts)]
        content = ""
        try:
            content = path.read_text(encoding="utf-8").casefold()
        except UnicodeDecodeError:
            pass
        for name in full_names:
            pattern = rf"(?<![{repository_character}]){re.escape(name)}(?:\.git)?(?![{repository_character}])"
            if re.search(pattern, content) or any(re.search(pattern, haystack) for haystack in path_haystacks):
                leaks.add(display_path(path))
        for name in bare_names:
            pattern = rf"(?<![{repository_character}]){re.escape(name)}(?:\.git)?(?![{repository_character}])"
            if any(re.search(pattern, haystack) for haystack in path_haystacks):
                leaks.add(display_path(path))
    return sorted(leaks)


def candidate_projection_digest(snapshot: dict[str, Any]) -> str:
    candidates = snapshot.get("candidates")
    if not isinstance(candidates, list):
        raise AuditError("accepted candidate snapshot candidates are missing")
    identities: list[str] = []
    bindings: list[dict[str, Any]] = []
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
        demand = row.get("demand")
        economics = row.get("economics")
        blocking_evidence = row.get("blocking_evidence")
        transfer_eligible = row.get("transfer_eligible")
        if (
            not isinstance(demand, dict)
            or not isinstance(economics, dict)
            or not isinstance(blocking_evidence, list)
            or not all(_is_nonblank_text(value) for value in blocking_evidence)
            or not isinstance(transfer_eligible, bool)
        ):
            raise AuditError("accepted candidate nontechnical decision basis is invalid")
        current_state = row.get("current_state")
        preflight_disposition = row.get("preflight_disposition")
        if visibility == "public" and (current_state, preflight_disposition) not in {
            ("active_repository", "park"),
            ("active_repository", "experiment"),
            ("archived", "park"),
        }:
            raise AuditError("accepted public candidate lifecycle binding is invalid")
        bindings.append(
            {
                "candidate_id": candidate_id,
                "repository": repository if isinstance(repository, str) else "",
                "visibility": visibility,
                "current_state": current_state if isinstance(current_state, str) else "",
                "preflight_disposition": preflight_disposition if isinstance(preflight_disposition, str) else "",
                "fork": row.get("fork") if isinstance(row.get("fork"), bool) else None,
                "demand": demand,
                "economics": economics,
                "blocking_evidence": blocking_evidence,
                "transfer_eligible": transfer_eligible,
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


def _fetch_repository_blob(
    repository: str,
    commit: str,
    path: str,
    collection: LiveCollection | None = None,
) -> bytes:
    if not SHA40.fullmatch(commit) or not _safe_relative_path(path):
        raise AuditError("technical evidence blob location is invalid")
    response = _run_json(
        ["gh", "api", f"repos/{repository}/contents/{quote(path, safe='/')}?ref={quote(commit, safe='')}"],
        collection=collection,
    )
    encoded = response.get("content")
    if response.get("encoding") != "base64" or not isinstance(encoded, str):
        raise AuditError("live technical evidence blob is not decodable")
    try:
        return base64.b64decode("".join(encoded.split()), validate=True)
    except ValueError as exc:
        raise AuditError("live technical evidence blob is invalid") from exc


def _fetch_exact_head_blob(
    value: Any,
    repository: str,
    commit: str,
    collection: LiveCollection | None = None,
) -> bytes:
    if not isinstance(value, str) or not _valid_https_url(value):
        raise AuditError("technical evidence artifact URL is invalid")
    parsed = urlparse(value)
    if parsed.netloc.casefold() != "github.com":
        raise AuditError("technical evidence artifact URL is not a GitHub blob")
    resolved_repository, resolved_commit, path = _evidence_location(value)
    if resolved_repository.casefold() != repository.casefold() or resolved_commit != commit:
        raise AuditError("technical evidence artifact is not bound to the candidate exact head")
    return _fetch_repository_blob(resolved_repository, resolved_commit, path, collection)


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


def collect_live_evidence_receipts(
    audit: dict[str, Any],
    collection: LiveCollection | None = None,
) -> dict[tuple[str, str], dict[str, Any]]:
    collection = collection or LiveCollection()
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
            receipt_repository, receipt_commit, _ = _evidence_location(evidence_url)
            try:
                decoded = _fetch_exact_head_blob(
                    evidence_url,
                    receipt_repository,
                    receipt_commit,
                    collection,
                ).decode("utf-8")
                receipt = json.loads(decoded, object_pairs_hook=_object_without_duplicate_keys)
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError, AuditError) as exc:
                raise AuditError("live technical evidence receipt is invalid") from exc
            if not isinstance(receipt, dict):
                raise AuditError("live technical evidence receipt is not an object")
            output = _fetch_repository_blob(
                receipt_repository,
                receipt_commit,
                receipt.get("output_path"),
                collection,
            )
            artifact = _fetch_repository_blob(
                receipt_repository,
                receipt_commit,
                receipt.get("artifact_path"),
                collection,
            )
            run_id = _actions_run_id(receipt.get("provenance_url"), str(row.get("repository") or ""))
            run_attempt = receipt.get("run_attempt")
            if run_id is None or not _is_nonnegative_int(run_attempt) or run_attempt < 1:
                raise AuditError("live technical evidence provenance URL is invalid")
            provenance = _run_json(
                [
                    "gh",
                    "api",
                    f"repos/{row['repository']}/actions/runs/{run_id}/attempts/{run_attempt}",
                ],
                collection=collection,
            )
            resolved: dict[str, Any] = {
                "receipt": receipt,
                "receipt_repository": receipt_repository,
                "receipt_commit": receipt_commit,
                "output_sha256": hashlib.sha256(output).hexdigest(),
                "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
                "provenance": provenance,
            }
            if dimension == "security":
                try:
                    assessment = json.loads(
                        artifact.decode("utf-8"),
                        object_pairs_hook=_object_without_duplicate_keys,
                    )
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError, AuditError) as exc:
                    raise AuditError("live security assessment artifact is invalid") from exc
                if not isinstance(assessment, dict):
                    raise AuditError("live security assessment artifact is not an object")
                resolved["assessment"] = assessment
            if dimension == "maintenance" and value.get("state") == "verified_pass":
                funding_url = value.get("funding_evidence_url")
                if not isinstance(funding_url, str):
                    raise AuditError("live maintenance funding evidence URL is invalid")
                funding_repository, funding_commit, _ = _evidence_location(funding_url)
                try:
                    funding_decoded = _fetch_exact_head_blob(
                        funding_url,
                        funding_repository,
                        funding_commit,
                        collection,
                    ).decode("utf-8")
                    funding_receipt = json.loads(
                        funding_decoded,
                        object_pairs_hook=_object_without_duplicate_keys,
                    )
                except (ValueError, UnicodeDecodeError, json.JSONDecodeError, AuditError) as exc:
                    raise AuditError("live maintenance funding receipt is invalid") from exc
                if not isinstance(funding_receipt, dict):
                    raise AuditError("live maintenance funding receipt is not an object")
                funding_artifact = _fetch_repository_blob(
                    funding_repository,
                    funding_commit,
                    funding_receipt.get("artifact_path"),
                    collection,
                )
                funding_run_id = _actions_run_id(
                    funding_receipt.get("provenance_url"),
                    str(row.get("repository") or ""),
                )
                funding_run_attempt = funding_receipt.get("run_attempt")
                if (
                    funding_run_id is None
                    or not _is_nonnegative_int(funding_run_attempt)
                    or funding_run_attempt < 1
                ):
                    raise AuditError("live maintenance funding provenance URL is invalid")
                funding_provenance = _run_json(
                    [
                        "gh",
                        "api",
                        f"repos/{row['repository']}/actions/runs/{funding_run_id}/attempts/{funding_run_attempt}",
                    ],
                    collection=collection,
                )
                resolved["funding"] = {
                    "receipt": funding_receipt,
                    "receipt_repository": funding_repository,
                    "receipt_commit": funding_commit,
                    "artifact_sha256": hashlib.sha256(funding_artifact).hexdigest(),
                    "provenance": funding_provenance,
                }
            receipts[(candidate_id, dimension)] = resolved
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


def build_audit(
    snapshot: dict[str, Any],
    heads: dict[str, str],
    observed_at: str,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    previous_rows = {
        row.get("candidate_id"): row
        for row in (previous or {}).get("candidates", [])
        if isinstance(row, dict) and _is_nonblank_text(row.get("candidate_id"))
    }
    candidates: list[dict[str, Any]] = []
    for source in snapshot.get("candidates", []):
        if not isinstance(source, dict):
            raise AuditError("accepted candidate snapshot contains a non-object row")
        candidate_id = source.get("candidate_id")
        visibility = source.get("visibility")
        if not _is_nonblank_text(candidate_id):
            raise AuditError("accepted candidate snapshot contains an invalid identity")
        if visibility == "private":
            previous_row = previous_rows.get(candidate_id)
            if isinstance(previous_row, dict) and previous_row.get("visibility") == "private":
                candidates.append(copy.deepcopy(previous_row))
            else:
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
                        "clearance_receipt_sha256": None,
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
        fresh = {
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
        previous_row = previous_rows.get(candidate_id)
        if (
            isinstance(previous_row, dict)
            and previous_row.get("visibility") == "public"
            and previous_row.get("repository") == repository
            and previous_row.get("observed_head") == heads[repository]
        ):
            candidates.append(copy.deepcopy(previous_row))
        else:
            candidates.append(fresh)
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
    result["summary"] = compute_summary(candidates, snapshot)
    return result


def _evidence_receipt_errors(
    resolved_evidence: Any,
    repository: str,
    observed_head: str,
    dimension: str,
    state: str,
    label: str,
    expected_value: dict[str, Any] | None = None,
) -> list[str]:
    if dimension == "maintenance" and state == "verified_pass":
        expected_resolved_keys = RESOLVED_MAINTENANCE_EVIDENCE_KEYS
        expected_receipt_keys = MAINTENANCE_EVIDENCE_RECEIPT_KEYS
    elif dimension == "security":
        expected_resolved_keys = RESOLVED_SECURITY_EVIDENCE_KEYS
        expected_receipt_keys = EVIDENCE_RECEIPT_KEYS
    else:
        expected_resolved_keys = RESOLVED_EVIDENCE_KEYS
        expected_receipt_keys = EVIDENCE_RECEIPT_KEYS
    if not _exact_keys(resolved_evidence, expected_resolved_keys):
        return [f"{label} live receipt must resolve immutable output and artifact evidence"]
    receipt = resolved_evidence.get("receipt")
    if not _exact_keys(receipt, expected_receipt_keys):
        return [f"{label} live receipt must use the exact evidence schema"]
    errors: list[str] = []
    expected_status = "pass" if state == "verified_pass" else "fail"
    if receipt.get("schema_version") != "limen.psp_p13_w03_technical_evidence.v2":
        errors.append(f"{label} live receipt schema version drift")
    if receipt.get("repository") != repository or receipt.get("tested_commit") != observed_head:
        errors.append(f"{label} live receipt repository or tested_commit drift")
    receipt_repository = resolved_evidence.get("receipt_repository")
    receipt_commit = resolved_evidence.get("receipt_commit")
    allowed_receipt_repositories = {repository.casefold(), *(value.casefold() for value in TRUSTED_RECEIPT_REPOSITORIES)}
    if (
        not isinstance(receipt_repository, str)
        or receipt_repository.casefold() not in allowed_receipt_repositories
        or not isinstance(receipt_commit, str)
        or not SHA40.fullmatch(receipt_commit)
    ):
        errors.append(f"{label} live receipt immutable location drift")
    if receipt.get("dimension") != dimension or receipt.get("status") != expected_status:
        errors.append(f"{label} live receipt dimension or result drift")
    exit_code = receipt.get("exit_code")
    valid_exit = isinstance(exit_code, int) and not isinstance(exit_code, bool)
    if not valid_exit or (state == "verified_pass" and exit_code != 0) or (state == "verified_fail" and exit_code == 0):
        errors.append(f"{label} live receipt exit_code drift")
    output_path = receipt.get("output_path")
    artifact_path = receipt.get("artifact_path")
    if not _safe_relative_path(output_path) or not _safe_relative_path(artifact_path) or output_path == artifact_path:
        errors.append(f"{label} live receipt needs distinct safe output and artifact paths")
    if (
        receipt.get("output_sha256") != resolved_evidence.get("output_sha256")
        or receipt.get("artifact_sha256") != resolved_evidence.get("artifact_sha256")
        or resolved_evidence.get("output_sha256") == resolved_evidence.get("artifact_sha256")
    ):
        errors.append(f"{label} live receipt must bind independently distinct output and artifact evidence")
    provenance = resolved_evidence.get("provenance")
    run_id = _actions_run_id(receipt.get("provenance_url"), repository)
    run_attempt = receipt.get("run_attempt")
    expected_conclusion = "success" if state == "verified_pass" else None
    predicate_path = receipt.get("predicate_path")
    if (
        not isinstance(provenance, dict)
        or run_id is None
        or not _is_nonnegative_int(run_attempt)
        or run_attempt < 1
    ):
        errors.append(f"{label} live receipt must resolve trusted execution provenance")
    else:
        conclusion = provenance.get("conclusion")
        if (
            provenance.get("html_url") != receipt.get("provenance_url")
            or provenance.get("head_sha") != observed_head
            or provenance.get("run_attempt") != receipt.get("run_attempt")
            or provenance.get("status") != "completed"
            or (state == "verified_pass" and conclusion != expected_conclusion)
            or (state == "verified_fail" and conclusion not in EXECUTED_FAILURE_CONCLUSIONS)
        ):
            errors.append(f"{label} live receipt trusted result semantics drift")
        if provenance.get("path") != predicate_path or not _is_nonblank_text(predicate_path) or not any(
            token in str(predicate_path).casefold() for token in DIMENSION_RECEIPT_TOKENS[dimension]
        ):
            errors.append(f"{label} live receipt predicate provenance drift")
        observed = _parse_timestamp(receipt.get("observed_at"))
        completed = _parse_timestamp(provenance.get("updated_at"))
        started = _parse_timestamp(provenance.get("run_started_at") or provenance.get("created_at"))
        now = dt.datetime.now(dt.UTC)
        if observed is None or completed is None or started is None or observed != completed or not started <= completed <= now:
            errors.append(f"{label} live receipt chronology drift")
    if receipt.get("external_effects") != []:
        errors.append(f"{label} live receipt must record zero external effects")
    if dimension == "security":
        assessment = resolved_evidence.get("assessment")
        if not _exact_keys(assessment, SECURITY_ASSESSMENT_KEYS):
            errors.append(f"{label} must resolve the exact security assessment artifact")
        elif (
            assessment.get("schema_version") != "limen.psp_p13_w03_security_assessment.v1"
            or assessment.get("repository") != repository
            or assessment.get("tested_commit") != observed_head
            or assessment.get("classification") != (expected_value or {}).get("class")
            or assessment.get("observed_at") != receipt.get("observed_at")
            or assessment.get("external_effects") != []
        ):
            errors.append(f"{label} recorded class is not bound to the independently resolved assessment")
    if dimension == "maintenance" and state == "verified_pass":
        if receipt.get("response_window_hours") != (expected_value or {}).get("response_window_hours"):
            errors.append(f"{label} response window is not bound to the independently resolved receipt")
    return errors


def _maintenance_funding_errors(
    resolved_funding: Any,
    repository: str,
    observed_head: str,
    required_hours: Any,
    technical_evidence: Any,
    label: str,
) -> list[str]:
    if not _exact_keys(resolved_funding, RESOLVED_FUNDING_KEYS):
        return [f"{label} must independently resolve immutable funding evidence"]
    receipt = resolved_funding.get("receipt")
    if not _exact_keys(receipt, FUNDING_RECEIPT_KEYS):
        return [f"{label} must use the exact funding receipt schema"]
    errors: list[str] = []
    if receipt.get("schema_version") != "limen.psp_p13_w03_maintenance_funding.v1":
        errors.append(f"{label} schema version drift")
    if (
        receipt.get("repository") != repository
        or receipt.get("tested_commit") != observed_head
        or receipt.get("status") != "funded"
    ):
        errors.append(f"{label} repository, tested_commit, or status drift")
    capacity = receipt.get("capacity_hours_per_month")
    if (
        not _is_finite_number(capacity)
        or not _is_finite_number(required_hours)
        or float(capacity) < float(required_hours)
    ):
        errors.append(f"{label} capacity does not fund the bounded maintenance estimate")
    receipt_repository = resolved_funding.get("receipt_repository")
    receipt_commit = resolved_funding.get("receipt_commit")
    allowed_repositories = {repository.casefold(), *(value.casefold() for value in TRUSTED_RECEIPT_REPOSITORIES)}
    if (
        not isinstance(receipt_repository, str)
        or receipt_repository.casefold() not in allowed_repositories
        or not isinstance(receipt_commit, str)
        or not SHA40.fullmatch(receipt_commit)
    ):
        errors.append(f"{label} immutable location drift")
    artifact_path = receipt.get("artifact_path")
    artifact_sha256 = resolved_funding.get("artifact_sha256")
    technical_digests = {
        technical_evidence.get("output_sha256"),
        technical_evidence.get("artifact_sha256"),
    } if isinstance(technical_evidence, dict) else set()
    if (
        not _safe_relative_path(artifact_path)
        or receipt.get("artifact_sha256") != artifact_sha256
        or artifact_sha256 in technical_digests
    ):
        errors.append(f"{label} must bind an independently distinct funding artifact")
    provenance = resolved_funding.get("provenance")
    run_id = _actions_run_id(receipt.get("provenance_url"), repository)
    run_attempt = receipt.get("run_attempt")
    predicate_path = receipt.get("predicate_path")
    if (
        not isinstance(provenance, dict)
        or run_id is None
        or not _is_nonnegative_int(run_attempt)
        or run_attempt < 1
    ):
        errors.append(f"{label} must resolve trusted execution provenance")
    else:
        if (
            provenance.get("html_url") != receipt.get("provenance_url")
            or provenance.get("head_sha") != observed_head
            or provenance.get("run_attempt") != receipt.get("run_attempt")
            or provenance.get("status") != "completed"
            or provenance.get("conclusion") != "success"
        ):
            errors.append(f"{label} trusted result semantics drift")
        lowered_path = str(predicate_path).casefold()
        if (
            provenance.get("path") != predicate_path
            or not _is_nonblank_text(predicate_path)
            or "maintenance" not in lowered_path
            or "fund" not in lowered_path
        ):
            errors.append(f"{label} predicate provenance drift")
        observed = _parse_timestamp(receipt.get("observed_at"))
        completed = _parse_timestamp(provenance.get("updated_at"))
        started = _parse_timestamp(provenance.get("run_started_at") or provenance.get("created_at"))
        now = dt.datetime.now(dt.UTC)
        if observed is None or completed is None or started is None or observed != completed or not started <= completed <= now:
            errors.append(f"{label} chronology drift")
    if receipt.get("external_effects") != []:
        errors.append(f"{label} must record zero external effects")
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
        if not _url_proves_dimension(evidence_url, observed_head, repository, dimension):
            errors.append(f"{label} requires a dimension-specific immutable technical receipt")
        elif require_live_receipt:
            errors.extend(
                _evidence_receipt_errors(
                    live_receipt,
                    repository,
                    observed_head,
                    dimension,
                    state,
                    label,
                    value,
                )
            )
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
    if not isinstance(code, str) or not SAFE_BLOCKER_CODE.fullmatch(code):
        errors.append(f"{label}.code must be a safe lowercase identifier")
    elif value.get("predicate") != _blocker(candidate_id, code, "unused")["predicate"]:
        errors.append(f"{label}.predicate must be the exact trusted live clearance command")
    return errors


def _public_candidate_errors(
    row: dict[str, Any],
    expected: dict[str, Any],
    contract: dict[str, Any],
    weights: dict[str, int],
    hard_floors: set[str],
    transfer_threshold: int,
    maintenance_maximum: float,
    maintenance_response_maximum: float,
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
        security_class = security.get("class")
        security_state = security.get("state")
        if not isinstance(security_class, str) or security_class not in SECURITY_CLASSES:
            errors.append(f"{label}.security.class is invalid")
        if security_state == "verified_pass" and security_class not in PASSABLE_SECURITY_CLASSES:
            errors.append(f"{label}.security verified_pass requires a low or moderate class")
            security_state = "blocked_unverified"
        dimension_states["security"] = security_state
    maintenance = row.get("maintenance")
    maintenance_keys = (
        MAINTENANCE_PASS_KEYS
        if isinstance(maintenance, dict) and maintenance.get("state") == "verified_pass"
        else MAINTENANCE_KEYS
    )
    errors.extend(
        _evidence_errors(
            maintenance,
            head,
            repository,
            "maintenance",
            f"{label}.maintenance",
            maintenance_keys,
            (live_receipts or {}).get((candidate_id, "maintenance")),
            live_receipts is not None,
        )
    )
    funded_maintenance = False
    if isinstance(maintenance, dict):
        state = maintenance.get("state")
        if state == "verified_pass":
            estimate = maintenance.get("estimate_hours_per_month")
            valid_estimate = _is_finite_number(estimate) and 0 < float(estimate) <= maintenance_maximum
            response_window = maintenance.get("response_window_hours")
            valid_response = (
                _is_finite_number(response_window)
                and 0 < float(response_window) <= maintenance_response_maximum
            )
            valid_pass = _is_nonblank_text(maintenance.get("owner")) and valid_estimate and valid_response
            if not valid_pass:
                errors.append(
                    f"{label}.maintenance pass requires an owner, bounded positive estimate, and bounded response window"
                )
            if _is_finite_number(estimate) and float(estimate) > maintenance_maximum:
                errors.append(f"{label}.maintenance estimate exceeds the contract maximum")
            if maintenance.get("blocker") is not None:
                errors.append(f"{label}.maintenance pass cannot retain a blocker")
                valid_pass = False
            funding_evidence_url = maintenance.get("funding_evidence_url")
            funded_maintenance = (
                funding_evidence_url != maintenance.get("evidence_url")
                and _url_proves_maintenance_funding(funding_evidence_url, head, repository)
            )
            if not funded_maintenance:
                errors.append(f"{label}.maintenance pass requires distinct immutable funded-maintenance evidence")
            if live_receipts is not None:
                technical_evidence = live_receipts.get((candidate_id, "maintenance"))
                funding_errors = _maintenance_funding_errors(
                    technical_evidence.get("funding") if isinstance(technical_evidence, dict) else None,
                    repository,
                    head,
                    estimate,
                    technical_evidence,
                    f"{label}.maintenance.funding",
                )
                errors.extend(funding_errors)
                funded_maintenance = funded_maintenance and not funding_errors
            dimension_states["maintenance"] = state if valid_pass else "blocked_unverified"
        else:
            dimension_states["maintenance"] = state
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
    if isinstance(maintenance, dict) and maintenance.get("state") != "verified_pass":
        canonical_maintenance_blocker = next(
            (
                blocker
                for blocker in blockers
                if isinstance(blocker, dict) and blocker.get("code") == DIMENSION_BLOCKER_CODES["maintenance"]
            ),
            None,
        )
        if maintenance.get("blocker") != canonical_maintenance_blocker:
            errors.append(f"{label}.maintenance.blocker must equal the canonical top-level maintenance blocker")
    unresolved_dimensions = {
        dimension
        for dimension, state in dimension_states.items()
        if isinstance(state, str) and state in {"verified_fail", "blocked_unverified", "not_applicable"}
    }
    expected_dimension_blockers = {DIMENSION_BLOCKER_CODES[dimension] for dimension in unresolved_dimensions}
    observed_blocker_codes = set(blocker_codes)
    if observed_blocker_codes != expected_dimension_blockers:
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
    unclassified_blockers = observed_blocker_codes - set(DIMENSION_BLOCKER_CODES.values())
    hard_unresolved = (
        not all_hard_floors_pass or bool(observed_blocker_codes & hard_blocker_codes) or bool(unclassified_blockers)
    )
    accepted_lifecycle = expected.get("current_state") != "archived" and expected.get("preflight_disposition") != "park"
    governed_floors_pass = governed_transfer_floors_pass(expected, contract)
    expected_transfer = (
        expected_score >= transfer_threshold
        and not hard_unresolved
        and accepted_lifecycle
        and funded_maintenance
        and governed_floors_pass
    )
    if row.get("transfer_eligible") is not expected_transfer:
        errors.append(f"{label}.transfer_eligible drift")
    if row.get("transfer_eligible") is True and hard_unresolved:
        errors.append(f"{label} cannot be transferable with unresolved hard blockers")
    if row.get("transfer_eligible") is True and not accepted_lifecycle:
        errors.append(f"{label} accepted archived or parked lifecycle cannot be transferable")
    if row.get("transfer_eligible") is True and not governed_floors_pass:
        errors.append(f"{label} cannot be transferable before every governed nontechnical floor passes")
    return errors


def _private_candidate_errors(
    row: dict[str, Any],
    expected: dict[str, Any],
    private_clearance_receipts: dict[str, str] | None,
) -> list[str]:
    candidate_id = str(expected.get("candidate_id") or "unknown")
    label = f"candidate {candidate_id}"
    if set(row) != PRIVATE_KEYS:
        return [f"{label} must use the exact private row schema"]
    errors: list[str] = []
    if row.get("candidate_id") != candidate_id or not OPAQUE_PRIVATE_ID.fullmatch(candidate_id):
        errors.append(f"{label} must retain its opaque accepted identity")
    status = row.get("readiness_status")
    if row.get("visibility") != "private" or status not in {"restricted", "clearance_pending_live"}:
        errors.append(f"{label} private status drift")
    blocker = row.get("blocker")
    clearance_digest = row.get("clearance_receipt_sha256")
    if status == "restricted":
        errors.extend(_blocker_errors(blocker, f"{label}.blocker", candidate_id))
        if isinstance(blocker, dict) and blocker.get("owner") != GENERIC_PRIVATE_OWNER:
            errors.append(f"{label} must expose only the generic accountable owner role")
        if isinstance(blocker, dict) and blocker.get("code") != "restricted_private_evidence":
            errors.append(f"{label} must retain the restricted private evidence blocker")
        if clearance_digest is not None:
            errors.append(f"{label} restricted status cannot claim a clearance receipt")
    elif status == "clearance_pending_live":
        errors.extend(_blocker_errors(blocker, f"{label}.blocker", candidate_id))
        if isinstance(blocker, dict) and (
            blocker.get("owner") != GENERIC_PRIVATE_OWNER or blocker.get("code") != "restricted_private_evidence"
        ):
            errors.append(f"{label} pending clearance must retain the generic private evidence blocker")
        if not SHA64.fullmatch(str(clearance_digest or "")):
            errors.append(f"{label} pending clearance requires an opaque custody receipt digest")
        if private_clearance_receipts is not None and private_clearance_receipts.get(candidate_id) != clearance_digest:
            errors.append(f"{label} clearance receipt is not confirmed in owner-controlled custody")
    if row.get("readiness_score") != 0 or row.get("transfer_eligible") is not False:
        errors.append(f"{label} private readiness must remain zero and non-transferable")
    return errors


def _public_dimensions_verified(row: dict[str, Any]) -> bool:
    return all(
        isinstance(row.get(dimension), dict) and row[dimension].get("state") == "verified_pass"
        for dimension in DIMENSION_RECEIPT_TOKENS
    )


def compute_summary(candidates: list[dict[str, Any]], snapshot: dict[str, Any]) -> dict[str, Any]:
    lifecycle_by_id = {
        row.get("candidate_id"): row
        for row in snapshot.get("candidates", [])
        if isinstance(row, dict) and row.get("visibility") == "public"
    }
    visibility = collections.Counter(
        row.get("visibility") if isinstance(row.get("visibility"), str) else "<invalid>"
        for row in candidates
        if isinstance(row, dict)
    )
    status_counts: collections.Counter[str] = collections.Counter()
    for row in candidates:
        if not isinstance(row, dict):
            continue
        if row.get("visibility") == "private":
            status_counts[str(row.get("readiness_status") or "restricted")] += 1
            continue
        if row.get("transfer_eligible") is True:
            status_counts["transfer_ready"] += 1
            continue
        candidate_id = row.get("candidate_id")
        expected = lifecycle_by_id.get(candidate_id, {}) if isinstance(candidate_id, str) else {}
        if _public_dimensions_verified(row):
            if expected.get("current_state") == "archived" or expected.get("preflight_disposition") == "park":
                status_counts["verified_nontransferable_lifecycle"] += 1
            else:
                status_counts["technical_ready_governance_pending"] += 1
        else:
            status_counts["blocked_unverified"] += 1
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
    private_clearance_receipts: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    if set(audit) != ROOT_KEYS:
        return ["audit must use the exact root schema"]
    if audit.get("schema_version") != "limen.psp_p13_w03_technical_readiness.v1":
        errors.append("audit schema_version drift")
    if audit.get("work_id") != "PSP-P13-W03" or audit.get("status") != "ACCEPTANCE_EVIDENCE":
        errors.append("audit work_id or status drift")
    observed_at = _parse_timestamp(audit.get("observed_at"))
    if observed_at is None or observed_at > dt.datetime.now(dt.UTC):
        errors.append("audit observed_at must be a non-future RFC3339 UTC timestamp")
    if audit.get("source_lock") != SOURCE_LOCK:
        errors.append("audit source_lock drift")
    try:
        w01_acceptance_digest = accepted_w01_acceptance_digest()
    except AuditError as exc:
        errors.append(str(exc))
    else:
        if w01_acceptance_digest != SOURCE_LOCK["w01_acceptance_sha256"]:
            errors.append("accepted W01 acceptance digest drift")
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
    transfer_threshold = readiness_transfer_threshold(contract)
    maintenance_maximum = readiness_maintenance_maximum(contract)
    maintenance_response_maximum = readiness_maintenance_response_maximum(contract)
    for index, expected in enumerate(expected_candidates):
        if index >= len(candidates) or not isinstance(expected, dict):
            continue
        row = candidates[index]
        if not isinstance(row, dict):
            errors.append(f"candidate {expected.get('candidate_id')} must be an object")
            continue
        if expected.get("visibility") == "public":
            errors.extend(
                _public_candidate_errors(
                    row,
                    expected,
                    contract,
                    weights,
                    hard_floors,
                    transfer_threshold,
                    maintenance_maximum,
                    maintenance_response_maximum,
                    live_receipts,
                )
            )
            if live_heads is not None:
                repository = expected.get("repository")
                if live_heads.get(repository) != row.get("observed_head"):
                    errors.append(f"candidate {expected.get('candidate_id')} observed_head drifted live")
        elif expected.get("visibility") == "private":
            errors.extend(_private_candidate_errors(row, expected, private_clearance_receipts))
        else:
            errors.append(f"candidate {expected.get('candidate_id')} has invalid accepted visibility")
    summary = audit.get("summary")
    if not _exact_keys(summary, SUMMARY_KEYS) or summary != compute_summary(candidates, snapshot):
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
    live_mode = parser.add_mutually_exclusive_group()
    live_mode.add_argument("--live", action="store_true")
    live_mode.add_argument("--public-live", action="store_true")
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
        private_clearance_receipts: dict[str, str] | None = None
        live_collection = LiveCollection() if args.live or args.public_live else None
        if args.require_cleared and not args.live:
            raise AuditError("--require-cleared requires --live")
        if args.live:
            heads, leaks, live_identity_digest = collect_live_context(snapshot)
            private_clearance_receipts = load_private_clearance_receipts()
            verify_w01_live_receipt(live_collection)
        elif args.public_live:
            verify_w01_live_receipt(live_collection)
        if write_path is not None:
            if not args.live or heads is None:
                raise AuditError("--write requires --live")
            previous_path = write_path if write_path.exists() else audit_path
            previous = load_json(previous_path) if previous_path.exists() else None
            generated = build_audit(
                snapshot,
                heads,
                dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
                previous,
            )
            live_receipts = collect_live_evidence_receipts(generated, live_collection)
            errors = validate_audit(
                generated,
                snapshot,
                contract,
                live_heads=heads,
                private_leaks=leaks,
                live_candidate_identity_sha256=live_identity_digest,
                live_receipts=live_receipts,
                private_clearance_receipts=private_clearance_receipts,
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
        if args.live or args.public_live:
            live_receipts = collect_live_evidence_receipts(audit, live_collection)
        errors = validate_audit(
            audit,
            snapshot,
            contract,
            live_heads=heads,
            private_leaks=leaks,
            live_candidate_identity_sha256=live_identity_digest,
            live_receipts=live_receipts,
            private_clearance_receipts=private_clearance_receipts,
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
