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
SCHEMA = "limen.positioning_flagship_proof_set.v1"
STATUSES = {"selected", "alternate", "excluded"}
REPOSITORY_RE = re.compile(r"[^/\s]+/[^/\s]+\Z")
WORKFLOW_API_PATH_RE = re.compile(r"repos/([^/\s]+/[^/\s]+)/actions/runs/[1-9][0-9]*\Z")
HEAD_RE = re.compile(r"[0-9a-f]{40}\Z")
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
    if hostname == "localhost" or hostname.endswith((".localhost", ".local")):
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


def repository_workflow_api_path(value: object, repository: object) -> str | None:
    match = WORKFLOW_API_PATH_RE.fullmatch(str(value or ""))
    if match is None or match.group(1) != repository:
        return None
    return str(value)


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


def validate_matrix(
    matrix: dict[str, Any],
    *,
    now: dt.datetime | None = None,
    enforce_freshness: bool = False,
) -> list[str]:
    errors: list[str] = []
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
    if not strict_int(minimum_total):
        errors.append("selection_policy.minimum_weighted_total must be an integer")

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
        for anchor in anchors:
            if not isinstance(anchor, dict) or anchor.get("kind") != "public_endpoint":
                continue
            identity = anchor.get("deployment_identity")
            endpoint_url = anchor.get("url")
            if isinstance(identity, str) and identity:
                endpoint_identities.append(identity)
            if isinstance(endpoint_url, str) and endpoint_url:
                endpoint_urls.append(endpoint_url)

        if status == "selected":
            claim = candidate.get("flagship_claim")
            if not isinstance(claim, str) or not claim.strip():
                errors.append(f"{prefix}: selected candidate needs a nonempty flagship_claim")
            role = candidate.get("story_role")
            if not isinstance(role, str) or not role:
                errors.append(f"{prefix}: selected candidate needs a story_role")
            else:
                selected_roles[role].append(candidate_id)
            if candidate.get("eligible") is not True:
                errors.append(f"{prefix}: selected candidate is marked excluded/ineligible")
            if candidate.get("stale") is not False:
                errors.append(f"{prefix}: selected candidate is stale")
            if dependencies:
                errors.append(f"{prefix}: selected candidate has a private-only dependency")
            if candidate.get("hard_gate_failures"):
                errors.append(f"{prefix}: selected candidate has hard-gate failures")
            if strict_int(minimum_total) and candidate.get("weighted_total", -1) < minimum_total:
                errors.append(f"{prefix}: selected score is below the minimum")
            if isinstance(scores, dict):
                for dimension, minimum in dimension_minima.items():
                    if not strict_int(minimum) or scores.get(dimension, -1) < minimum:
                        errors.append(f"{prefix}: {dimension} is below the selected minimum")

            live_anchors = [anchor for anchor in anchors if isinstance(anchor, dict) and anchor.get("live") is True]
            if not live_anchors:
                errors.append(f"{prefix}: selected candidate is missing a live evidence anchor")
            for anchor_index, anchor in enumerate(live_anchors):
                anchor_prefix = f"{prefix}.evidence_anchors[{anchor_index}]"
                if anchor.get("status") != "pass":
                    errors.append(f"{anchor_prefix}: live anchor must be passing")
                if anchor.get("kind") == "public_endpoint" and not endpoint_matches_candidate(anchor, candidate):
                    errors.append(f"{anchor_prefix}: endpoint identity is not bound to this candidate")
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
    duplicate_repositories = sorted(
        name for name, count in collections.Counter(repositories).items() if count > 1
    )
    if duplicate_repositories:
        errors.append(f"duplicate candidate repositories: {', '.join(duplicate_repositories)}")
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


def validate_live(matrix: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    candidates = matrix.get("candidates") or []
    current_heads: dict[str, str] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("kind") != "repository":
            continue
        candidate_id = str(candidate.get("id") or "unknown")
        repository = str(candidate.get("repository") or "")
        try:
            metadata = command_json(["gh", "api", f"repos/{repository}"])
        except ProofSetError as exc:
            errors.append(f"{candidate_id}: cannot inspect public repository: {exc}")
            continue
        if bool(metadata.get("private")):
            errors.append(f"{candidate_id}: public matrix names a private repository")
        if candidate.get("status") == "selected" and bool(metadata.get("archived")):
            errors.append(f"{candidate_id}: selected repository is archived")
        if candidate.get("status") == "selected":
            default_branch = metadata.get("default_branch")
            if not isinstance(default_branch, str) or not default_branch:
                errors.append(f"{candidate_id}: repository has no readable default branch")
                continue
            try:
                commit = command_json(["gh", "api", f"repos/{repository}/commits/{default_branch}"])
            except ProofSetError as exc:
                errors.append(f"{candidate_id}: cannot inspect current default-branch head: {exc}")
                continue
            current_head = commit.get("sha") if isinstance(commit, dict) else None
            if not isinstance(current_head, str) or not HEAD_RE.fullmatch(current_head):
                errors.append(f"{candidate_id}: current default-branch head is invalid")
                continue
            current_heads[repository] = current_head

    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("status") != "selected":
            continue
        candidate_id = str(candidate.get("id") or "unknown")
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
                except ProofSetError as exc:
                    errors.append(f"{candidate_id}: workflow anchor unavailable: {exc}")
                    continue
                if run.get("status") != "completed" or run.get("conclusion") != "success":
                    errors.append(f"{candidate_id}: workflow anchor is not a completed success")
                if run.get("head_sha") != anchor.get("observed_head"):
                    errors.append(f"{candidate_id}: workflow anchor head does not match the matrix")
                if run.get("head_sha") != current_heads.get(str(candidate.get("repository") or "")):
                    errors.append(f"{candidate_id}: workflow anchor is not on the current default-branch head")
            elif kind == "public_endpoint":
                if not endpoint_matches_candidate(anchor, candidate):
                    errors.append(f"{candidate_id}: endpoint identity is not bound to this candidate")
                    continue
                expected = anchor.get("expected_http_status")
                try:
                    observed = http_status(str(anchor.get("url") or ""))
                except ProofSetError as exc:
                    errors.append(f"{candidate_id}: endpoint anchor unavailable: {exc}")
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
