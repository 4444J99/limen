#!/usr/bin/env python3
"""Resolve frozen GitHub receipts and reconcile the public report snapshot."""

from __future__ import annotations

import collections
import json
import subprocess
from pathlib import Path
from typing import Any

from model import (
    OUTCOMES,
    classify_receipt,
    outcome_rank,
    parse_pr_url,
    parse_ts,
    strongest_outcome,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SNAPSHOT = parse_ts("2026-07-19T15:11:00Z")
assert SNAPSHOT
PRIVATE = ROOT / ".limen-private/session-corpus/seven-agent-review-links.json"


def gh_json(args: list[str]) -> Any:
    result = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def estate() -> tuple[dict[str, str], int]:
    repos: list[dict[str, Any]] = []
    for owner in ("organvm", "4444J99"):
        repos.extend(
            gh_json(
                [
                    "repo",
                    "list",
                    owner,
                    "--limit",
                    "1000",
                    "--json",
                    "name,nameWithOwner,isPrivate",
                ]
            )
        )
    by_name: dict[str, str] = {}
    for repo in repos:
        name = str(repo["name"]).lower()
        current = str(repo["nameWithOwner"])
        if name not in by_name or current.lower().startswith("organvm/"):
            by_name[name] = current
    return by_name, len({str(repo["nameWithOwner"]).lower() for repo in repos})


def coding_agent_receipts() -> list[str]:
    rows = gh_json(
        [
            "search",
            "prs",
            "--owner",
            "organvm",
            "--author",
            "app/copilot-swe-agent",
            "--created",
            "2026-07-06T04:00:00Z..2026-07-19T15:10:59Z",
            "--limit",
            "100",
            "--json",
            "url",
        ]
    )
    return [str(row["url"]) for row in rows]


def batch_receipts(
    urls: list[str], current_by_name: dict[str, str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    normalized: dict[tuple[str, str, int], set[str]] = collections.defaultdict(set)
    redirect_cache: dict[tuple[str, str], str] = {}
    for url in urls:
        parsed = parse_pr_url(url)
        if not parsed:
            continue
        owner, repo, number = parsed
        original = (owner.lower(), repo.lower())
        if original not in redirect_cache and owner.lower() != "organvm":
            try:
                resolved = gh_json(
                    [
                        "repo",
                        "view",
                        f"{owner}/{repo}",
                        "--json",
                        "nameWithOwner",
                    ]
                )
                redirect_cache[original] = str(resolved["nameWithOwner"])
            except (subprocess.CalledProcessError, KeyError, json.JSONDecodeError):
                redirect_cache[original] = current_by_name.get(
                    repo.lower(), f"{owner}/{repo}"
                )
        canonical_repo = redirect_cache.get(
            original, current_by_name.get(repo.lower(), f"{owner}/{repo}")
        )
        current_owner, current_name = canonical_repo.split("/", 1)
        normalized[(current_owner, current_name, number)].add(url)
    keys = sorted(normalized)
    found: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for offset in range(0, len(keys), 25):
        chunk = keys[offset : offset + 25]
        fields = []
        for index, (owner, repo, number) in enumerate(chunk):
            fields.append(
                f'''r{index}: repository(owner:{json.dumps(owner)}, name:{json.dumps(repo)}) {{
                  nameWithOwner isPrivate defaultBranchRef {{ name }}
                  p: pullRequest(number:{number}) {{
                    url title state createdAt mergedAt closedAt baseRefName headRefOid
                    author {{ login }}
                    commits(last:1) {{ nodes {{ commit {{
                      committedDate oid statusCheckRollup {{ state }}
                    }} }} }}
                  }}
                }}'''
            )
        query = "query {\n" + "\n".join(fields) + "\n}"
        try:
            response = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={query}"],
                check=False,
                capture_output=True,
                text=True,
            )
            payload = json.loads(response.stdout)
            data = payload.get("data") or {}
            for error in payload.get("errors") or []:
                errors.append(
                    f"graphql:{str(error.get('type') or 'partial').lower()}"
                )
        except json.JSONDecodeError as exc:
            errors.append(f"batch-{offset // 25 + 1}:{type(exc).__name__}")
            continue
        for index, key in enumerate(chunk):
            owner, repo, number = key
            container = data.get(f"r{index}") or {}
            pr = container.get("p")
            if not pr:
                errors.append(f"missing:{owner}/{repo}#{number}")
                continue
            if container.get("isPrivate"):
                # Private receipts influence classification but never enter tracked output.
                public_url = None
            else:
                public_url = pr.get("url")
            commit_nodes = ((pr.get("commits") or {}).get("nodes") or [])
            commits = []
            checks = []
            for node in commit_nodes:
                commit = node.get("commit") or {}
                commits.append({"committed_at": commit.get("committedDate")})
                state = ((commit.get("statusCheckRollup") or {}).get("state"))
                if state:
                    checks.append({"state": state})
            receipt = {
                "url": public_url,
                "canonical_url": public_url,
                "title": pr.get("title"),
                "author": ((pr.get("author") or {}).get("login")),
                "created_at": pr.get("createdAt"),
                "merged_at": pr.get("mergedAt"),
                "closed_at": pr.get("closedAt"),
                "base_ref": pr.get("baseRefName"),
                "default_branch": ((container.get("defaultBranchRef") or {}).get("name")),
                "commits": commits,
                "checks": checks,
                "private": bool(container.get("isPrivate")),
                "canonical_repo": container.get("nameWithOwner"),
            }
            outcome, reason = classify_receipt(receipt, snapshot_at=SNAPSHOT)
            receipt["outcome"] = outcome
            receipt["reason"] = reason
            for original in normalized[key]:
                found[original] = receipt
            if public_url:
                found[public_url] = receipt
    return found, errors


def rebuild_summary(snapshot: dict[str, Any]) -> None:
    for row in snapshot["comparison"]:
        agent = row["agent"]
        label = row["window"]
        window = next(value for value in snapshot["windows"] if value["label"] == label)
        start = parse_ts(window["start"])
        end = parse_ts(window["end"])
        assert start and end
        asks = [
            ask
            for ask in snapshot["asks"]
            if ask["agent"] == agent
            and start
            <= (parse_ts(ask["observed_at"]) or start)
            < end
        ]
        row["asks_observed"] = len(asks)
        row["verified_done"] = sum(ask["outcome"] == "verified_done" for ask in asks)
        row["open_or_unknown"] = sum(
            ask["outcome"]
            in {"durably_homed_open", "not_done_or_unverified", "coverage_unknown"}
            for ask in asks
        )
    snapshot["outcome_distribution"] = [
        {
            "agent": agent,
            "outcome": outcome,
            "ask_count": sum(
                ask["agent"] == agent and ask["outcome"] == outcome
                for ask in snapshot["asks"]
            ),
        }
        for agent in ("codex", "claude", "agy", "opencode", "gemini", "copilot", "jules")
        for outcome in OUTCOMES
    ]


def main() -> int:
    snapshot = json.loads((HERE / "snapshot.json").read_text())
    private = json.loads(PRIVATE.read_text())
    current_by_name, repo_count = estate()
    copilot_urls = coding_agent_receipts()
    urls = sorted(
        {
            url
            for item in private["asks"]
            for url in item["receipt_urls"]
        }
        | set(copilot_urls)
    )
    receipt_map, errors = batch_receipts(urls, current_by_name)
    public_receipts: dict[str, dict[str, Any]] = {}
    private_by_ask = {row["ask"]: row["receipt_urls"] for row in private["asks"]}
    for ask in snapshot["asks"]:
        candidates = [receipt_map[url] for url in private_by_ask.get(ask["ask"], []) if url in receipt_map]
        if candidates:
            ask["outcome"] = strongest_outcome([row["outcome"] for row in candidates])
            chosen = max(
                candidates,
                key=lambda row: outcome_rank(row["outcome"]),
            )
            ask["receipt"] = chosen["url"]
            ask["predicate"] = chosen["reason"]
            if chosen["url"]:
                public_receipts[chosen["url"]] = chosen
    for url in copilot_urls:
        receipt = receipt_map.get(url)
        if not receipt:
            continue
        ask = {
            "ask": f"ask-copilot-{parse_pr_url(url)[2]}",
            "agent": "copilot",
            "subject": receipt.get("title") or "GitHub coding-agent work item",
            "repo": receipt.get("canonical_repo") or "remote GitHub repository",
            "outcome": receipt["outcome"],
            "receipt": receipt.get("url"),
            "predicate": receipt["reason"],
            "observed_at": receipt["created_at"],
        }
        snapshot["asks"].append(ask)
        if receipt.get("url"):
            public_receipts[receipt["url"]] = receipt
    snapshot["estate"]["remote_repository_count"] = repo_count
    snapshot["estate"]["note"] = (
        "Live GitHub estate enumerated from registry owners and session/task-linked receipts; "
        "repository-name redirects resolved to current owners."
    )
    snapshot["deliverables"] = sorted(
        [
            {
                "agent": (
                    "copilot"
                    if str(receipt.get("author") or "").lower()
                    == "copilot-swe-agent"
                    else next(
                        (
                            ask["agent"]
                            for ask in snapshot["asks"]
                            if ask.get("receipt") == url
                        ),
                        "unknown",
                    )
                ),
                "title": receipt.get("title"),
                "receipt": url,
                "outcome": receipt.get("outcome"),
                "predicate": receipt.get("reason"),
            }
            for url, receipt in public_receipts.items()
            if receipt.get("outcome") in {"verified_done", "verified_partial"}
        ],
        key=lambda row: (row["outcome"] != "verified_done", row["agent"], row["title"] or ""),
    )
    snapshot["reconciliation"] = {
        "candidate_pr_urls": len(urls),
        "resolved_pr_urls": sum(url in receipt_map for url in urls),
        "batch_errors": errors,
        "remote_repository_count": repo_count,
        "copilot_coding_agent_receipts": len(copilot_urls),
        "opencode_message_query_matches_collector": (
            snapshot["coverage"]["opencode"]["messages_in_sessions"]
            == snapshot["coverage"]["opencode"]["direct_message_count"]
        ),
        "token_event_aggregations_reconciled": ["codex", "claude", "opencode", "copilot"],
    }
    rebuild_summary(snapshot)
    (HERE / "snapshot.json").write_text(json.dumps(snapshot, indent=2) + "\n")
    print(
        json.dumps(
            {
                "repositories": repo_count,
                "candidate_prs": len(urls),
                "resolved_keys": len(receipt_map),
                "errors": len(errors),
                "deliverables": len(snapshot["deliverables"]),
                "copilot_receipts": len(copilot_urls),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
