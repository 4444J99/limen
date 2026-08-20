"""Read-only GitHub adapters for recovery reacceptance evidence."""

from __future__ import annotations

import copy
import json
import re
import subprocess
from collections.abc import Callable
from typing import Any

from limen.reacceptance_contract import (
    FULL_HEAD,
    REVIEW_GATE_CONTEXT,
    LedgerError,
    _base_row,
    _source_ask,
    _strict_json_loads,
)


GRAPHQL = """
query ReacceptancePullRequest($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number url state isDraft headRefOid baseRefName mergedAt closedAt reviewDecision
      author { login }
      mergeCommit { oid }
      statusCheckRollup {
        contexts(first: 100) {
          pageInfo { hasNextPage }
          nodes {
            __typename
            ... on CheckRun {
              name status conclusion detailsUrl
              checkSuite { app { slug } }
            }
            ... on StatusContext {
              context state targetUrl
            }
          }
        }
      }
      reviewThreads(first: 100) {
        pageInfo { hasNextPage }
        nodes {
          isResolved isOutdated
          comments(first: 100) {
            pageInfo { hasNextPage }
            nodes { body url author { login } }
          }
        }
      }
    }
  }
}
"""

PullRequestReader = Callable[[str, int], dict[str, Any]]


def _gh_graphql(repository: str, number: int) -> dict[str, Any]:
    owner, name = repository.split("/", 1)
    command = [
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={GRAPHQL}",
        "-F",
        f"owner={owner}",
        "-F",
        f"name={name}",
        "-F",
        f"number={number}",
    ]
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LedgerError(f"cannot inspect {repository}#{number}: {exc}") from exc
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or "gh graphql failed"
        raise LedgerError(f"cannot inspect {repository}#{number}: {message}")
    try:
        payload = _strict_json_loads(process.stdout)
        pr = payload["data"]["repository"]["pullRequest"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise LedgerError(f"invalid GitHub response for {repository}#{number}") from exc
    if not isinstance(pr, dict):
        raise LedgerError(f"GitHub returned no pull request for {repository}#{number}")
    return pr


def _complete_connection(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        raise LedgerError(f"{label} is unavailable")
    page_info = value.get("pageInfo")
    nodes = value.get("nodes")
    if not isinstance(page_info, dict) or not isinstance(nodes, list):
        raise LedgerError(f"{label} is malformed")
    if page_info.get("hasNextPage") is True:
        raise LedgerError(f"{label} pagination is incomplete")
    if any(not isinstance(node, dict) for node in nodes):
        raise LedgerError(f"{label} contains a malformed node")
    return nodes


def _remedy_remote_snapshot(
    pr: dict[str, Any],
    *,
    repository: str,
    review_gate_app_slug: str | None,
) -> dict[str, Any]:
    rollup = pr.get("statusCheckRollup")
    contexts = _complete_connection(
        rollup.get("contexts") if isinstance(rollup, dict) else None,
        label=f"{repository} remedy status checks",
    )
    authoritative: list[dict[str, Any]] = []
    if isinstance(review_gate_app_slug, str) and review_gate_app_slug:
        for context in contexts:
            suite = context.get("checkSuite")
            app = suite.get("app") if isinstance(suite, dict) else None
            if (
                context.get("__typename") == "CheckRun"
                and context.get("name") == REVIEW_GATE_CONTEXT
                and isinstance(app, dict)
                and app.get("slug") == review_gate_app_slug
            ):
                authoritative.append(
                    {
                        "name": context.get("name"),
                        "status": str(context.get("status") or "").upper(),
                        "conclusion": str(context.get("conclusion") or "").upper(),
                        "details_url": context.get("detailsUrl"),
                        "app_slug": app.get("slug"),
                    }
                )
    if len(authoritative) > 1:
        raise LedgerError(
            f"{repository} remedy has multiple current {REVIEW_GATE_CONTEXT} results from {review_gate_app_slug}"
        )
    return {
        "url": pr.get("url"),
        "state": str(pr.get("state") or "").upper(),
        "draft": pr.get("isDraft"),
        "head_sha": pr.get("headRefOid"),
        "merge_commit": (pr.get("mergeCommit") or {}).get("oid"),
        "merged_at": pr.get("mergedAt"),
        "closed_at": pr.get("closedAt"),
        "review_gate_check": authoritative[0] if authoritative else None,
    }


def _refresh_remedy(
    remedy: dict[str, Any],
    *,
    fetch_pr: PullRequestReader | None = None,
) -> dict[str, Any]:
    refreshed = copy.deepcopy(remedy)
    repository = remedy.get("repository")
    pull_request = remedy.get("pull_request")
    if (
        not isinstance(repository, str)
        or "/" not in repository
        or not isinstance(pull_request, int)
        or isinstance(pull_request, bool)
        or pull_request <= 0
    ):
        return refreshed
    pr = (fetch_pr or _gh_graphql)(repository, pull_request)
    remote = _remedy_remote_snapshot(
        pr,
        repository=repository,
        review_gate_app_slug=remedy.get("review_gate_app_slug"),
    )
    old_head = remedy.get("exact_head")
    new_head = remote.get("head_sha")
    if remedy.get("status") in {"accepted", "reverted"} and old_head != new_head:
        raise LedgerError(
            f"adjudicated remedy {remedy.get('id')} is stale: exact head changed from {old_head} to {new_head}"
        )
    if remedy.get("status") == "repair_required" and isinstance(new_head, str) and FULL_HEAD.fullmatch(new_head):
        refreshed["exact_head"] = new_head
    refreshed["remote"] = remote
    return refreshed


def _severity(body: str) -> str:
    if re.search(r"(?:^|[^a-z0-9])p1(?:[^a-z0-9]|$)", body, flags=re.IGNORECASE):
        return "p1"
    if re.search(r"(?:^|[^a-z0-9])p2(?:[^a-z0-9]|$)", body, flags=re.IGNORECASE):
        return "p2"
    return "unclassified"


def _thread_snapshot(pr: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    threads = _complete_connection(pr.get("reviewThreads"), label="reviewThreads")
    live: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for index, thread in enumerate(threads):
        comments = _complete_connection(
            thread.get("comments"),
            label=f"reviewThreads[{index}].comments",
        )
        body = "\n".join(str(comment.get("body") or "") for comment in comments)
        url = next((str(comment.get("url")) for comment in comments if comment.get("url")), "")
        if not url:
            raise LedgerError(f"reviewThreads[{index}] has no durable discussion URL")
        record = {
            "discussion_url": url,
            "severity": _severity(body),
            "resolved": bool(thread.get("isResolved")),
            "outdated": bool(thread.get("isOutdated")),
        }
        records.append(record)
        if not record["resolved"] and not record["outdated"]:
            live.append(record)
    counts = {severity: sum(item["severity"] == severity for item in live) for severity in ("p1", "p2", "unclassified")}
    return (
        {
            "status": "current_remote_snapshot",
            **counts,
            "unresolved_current": len(live),
            "urls": [item["discussion_url"] for item in live],
        },
        records,
    )


def _pr_row(
    item: tuple[str, int],
    *,
    known_side_effects: dict[str, list[str]],
    fetch_pr: PullRequestReader | None = None,
) -> dict[str, Any]:
    repository, number = item
    pr = (fetch_pr or _gh_graphql)(repository, number)
    findings, threads = _thread_snapshot(pr)
    row = _base_row("pull_request", f"{repository}#{number}")
    row_id = f"pull_request:{repository}#{number}"
    row.update(
        {
            "id": row_id,
            "session": None,
            "source_ask": _source_ask(f"private_prompt_corpus:pr:{repository}#{number}:unreconciled"),
            "exact_head": pr.get("headRefOid"),
            "side_effects": {
                "status": "unreconciled",
                "attempt_ids": [],
                "observed": copy.deepcopy(known_side_effects.get(row_id, [])),
                "replay_authorized": False,
                "receipt": None,
            },
            "owner_surfaces": [repository],
            "review_findings": findings,
            "review_threads": threads,
            "receipt": {
                "status": str(pr.get("state") or "UNKNOWN").lower(),
                "url": pr.get("url"),
                "merge_commit": (pr.get("mergeCommit") or {}).get("oid"),
                "review_decision": pr.get("reviewDecision"),
                "draft": bool(pr.get("isDraft")),
                "merged_at": pr.get("mergedAt"),
                "closed_at": pr.get("closedAt"),
            },
            "keeper": {
                "executing_keeper": "claude",
                "reviewing_keeper": None,
                "provider_route": "claude",
                "github_author": (pr.get("author") or {}).get("login"),
                "owner_surface": repository,
            },
        }
    )
    return row
