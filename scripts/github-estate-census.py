#!/usr/bin/env python3
"""Produce the exhaustive GitHub-estate source report without GitHub search."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.github_estate_census import (  # noqa: E402
    build_github_estate_census,
    github_connection_query,
    paginate_exact,
)


SOURCE_REPORT = ROOT / "logs" / "progress-sources" / "github-estate.json"
PRIVATE_FACTS = ROOT / "logs" / "github-estate-census-facts.json"
TRACKED_LEDGER = ROOT / "docs" / "github-estate-census.json"


def _gitvs():
    path = ROOT / "scripts" / "gitvs.py"
    spec = importlib.util.spec_from_file_location("limen_gitvs_estate_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("gitvs adapter unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metadata(gitvs, repo: str) -> dict[str, Any] | None:
    try:
        owner, name = repo.split("/", 1)
    except ValueError:
        return None
    query = (
        "query($owner:String!,$name:String!){repository(owner:$owner,name:$name){"
        'issues(states:OPEN){totalCount} refs(refPrefix:"refs/heads/"){totalCount} '
        "defaultBranchRef{name target{... on Commit{oid statusCheckRollup{state}}}}}}"
    )
    result = gitvs._gh_user(
        [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
        ],
        timeout=90,
    )
    if result.returncode != 0:
        return None
    try:
        repository = (json.loads(result.stdout or "{}").get("data") or {}).get("repository")
        if not isinstance(repository, dict):
            return None
        default_ref = repository.get("defaultBranchRef") or {}
        target = default_ref.get("target") or {}
        rollup = target.get("statusCheckRollup") or {}
        check_state = rollup.get("state")
        check_nodes = []
        if check_state:
            check_nodes.append(
                {
                    "id": f"default:{target.get('oid') or 'unknown'}",
                    "name": "default-branch-rollup",
                    "state": str(check_state),
                    "head_oid": target.get("oid"),
                    "url": None,
                }
            )
        return {
            "issues": int((repository.get("issues") or {})["totalCount"]),
            "branches": int((repository.get("refs") or {})["totalCount"]),
            "default_branch": default_ref.get("name"),
            "checks": check_nodes,
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _remote_page(gitvs, repo: str, kind: str, cursor: str | None) -> dict[str, Any]:
    owner, name = repo.split("/", 1)
    query = github_connection_query(kind)
    args = [
        "api",
        "graphql",
        "-f",
        f"query={query}",
        "-F",
        f"owner={owner}",
        "-F",
        f"name={name}",
    ]
    if cursor:
        args.extend(["-F", f"cursor={cursor}"])
    result = gitvs._gh_user(args, timeout=90)
    if result.returncode != 0:
        raise ValueError("github-page-unavailable")
    try:
        repository = (json.loads(result.stdout or "{}").get("data") or {}).get("repository")
        block = repository["connection"]
        nodes = []
        for raw in block.get("nodes") or []:
            node = dict(raw)
            if kind == "branches":
                node["head_oid"] = (node.pop("target", None) or {}).get("oid")
            nodes.append(node)
        page = block["pageInfo"]
        return {
            "total_count": int(block["totalCount"]),
            "nodes": nodes,
            "has_next_page": bool(page["hasNextPage"]),
            "end_cursor": page.get("endCursor"),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("github-page-invalid") from exc


def collect(*, workers: int = 8) -> tuple[dict[str, Any], dict[str, Any]]:
    gitvs = _gitvs()
    estate = gitvs.load_estate()
    requested = gitvs.owners(estate)
    online = not os.environ.get("LIMEN_OFFLINE") and shutil.which("gh") is not None
    canonical: list[str] = []
    owner_failures = 0
    if online:
        for owner in requested:
            resolved = gitvs._resolve_owner_login(owner, "user-native")
            if not resolved:
                owner_failures += 1
            elif resolved not in canonical:
                canonical.append(resolved)
    else:
        owner_failures = len(requested)

    repositories: dict[str, dict[str, Any]] = {}
    repository_pages = 0
    for owner in canonical:
        inventory = gitvs._owner_repo_inventory(owner, "user-native")
        if inventory is None:
            owner_failures += 1
            continue
        repository_pages += int(inventory["page_count"])
        for row in inventory["repositories"]:
            repositories[str(row["name_with_owner"])] = dict(row)

    now = datetime.now(UTC)

    def collect_repository(repo: str) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]] | None]]:
        row = repositories[repo]
        metadata = _metadata(gitvs, repo)
        pr_result = gitvs._repo_open_prs(repo, int(row["open_pr_total"]), "user-native")
        if not pr_result["exhaustive"]:
            pr_nodes: list[dict[str, Any]] | None = None
        else:
            pr_nodes = [
                gitvs._classify_open_pr(repo, pr, estate.get("pr_debt_policy") or {}, now) for pr in pr_result["rows"]
            ]
        local: dict[str, list[dict[str, Any]] | None] = {"pull_requests": pr_nodes}
        if metadata is None:
            local.update({"issues": None, "branches": None, "checks": None})
            totals: dict[str, int] = {"pull_requests": int(row["open_pr_total"])}
            default_branch = None
        else:
            issue_result = paginate_exact(
                "issues",
                lambda cursor: _remote_page(gitvs, repo, "issues", cursor),
                expected_total=int(metadata["issues"]),
            )
            branch_result = paginate_exact(
                "branches",
                lambda cursor: _remote_page(gitvs, repo, "branches", cursor),
                expected_total=int(metadata["branches"]),
            )
            local.update(
                {
                    "issues": list(issue_result.nodes) if issue_result.exhaustive else None,
                    "branches": list(branch_result.nodes) if branch_result.exhaustive else None,
                    "checks": list(metadata["checks"]),
                }
            )
            totals = {
                "pull_requests": int(row["open_pr_total"]),
                "issues": int(metadata["issues"]),
                "branches": int(metadata["branches"]),
                "checks": len(metadata["checks"]),
            }
            default_branch = metadata["default_branch"]
        return (
            {
                "name_with_owner": repo,
                "private": bool(row["private"]),
                "default_branch": default_branch,
                "connection_totals": totals,
            },
            local,
        )

    evidence: list[dict[str, Any]] = []
    cached: dict[tuple[str, str], list[dict[str, Any]] | None] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="github-estate") as executor:
        for repository, local in executor.map(collect_repository, sorted(repositories)):
            repo = str(repository["name_with_owner"])
            evidence.append(repository)
            for kind, nodes in local.items():
                cached[(repo, kind)] = nodes

    def fetch(repo: str, kind: str, cursor: str | None) -> dict[str, Any]:
        local = cached.get((repo, kind), "remote")
        if local is None:
            raise ValueError("upstream-connection-incomplete")
        if isinstance(local, list):
            if cursor is not None:
                raise ValueError("unexpected-local-cursor")
            return {
                "total_count": len(local),
                "nodes": local,
                "has_next_page": False,
                "end_cursor": None,
            }
        return _remote_page(gitvs, repo, kind, cursor)

    return build_github_estate_census(
        evidence,
        fetch,
        repository_cursor={
            "expected_total": len(repositories) if owner_failures == 0 else None,
            "page_count": repository_pages,
            "exhaustive": owner_failures == 0,
        },
        now=now,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 unless every cursor is exhaustive")
    parser.add_argument("--json", action="store_true", help="print the redacted report summary")
    parser.add_argument("--write", action="store_true", help="write owner, source, and tracked receipts")
    parser.add_argument("--workers", type=int, default=8, help="bounded concurrent repository packets (1-32)")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 32:
        parser.error("--workers must be between 1 and 32")
    full, tracked = collect(workers=args.workers)
    report = full["source_report"]
    if args.write:
        SOURCE_REPORT.parent.mkdir(parents=True, exist_ok=True)
        SOURCE_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        PRIVATE_FACTS.parent.mkdir(parents=True, exist_ok=True)
        PRIVATE_FACTS.write_text(json.dumps(full, indent=2, sort_keys=True) + "\n")
        TRACKED_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        TRACKED_LEDGER.write_text(json.dumps(tracked, indent=2, sort_keys=True) + "\n")
    if args.json:
        print(json.dumps({"source_report": report, "summary": tracked["summary"]}, indent=2, sort_keys=True))
    else:
        mark = "✓" if report["exhaustive"] else "✗"
        print(
            f"{mark} github-estate-census: repositories={tracked['summary']['repository_count']} "
            f"known_leaves={tracked['summary']['known_leaf_count']} "
            f"exhaustive={str(report['exhaustive']).lower()} failures={tracked['summary']['failure_count']}"
        )
    return 1 if args.check and not report["exhaustive"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
