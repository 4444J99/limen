"""Exact GitHub-estate normalization for the work-universe source registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Callable

from limen.progress_source_registry import REPORT_SCHEMA


SCHEMA = "limen.github-estate-census.v1"
SOURCE_ID = "github-estate"
CONNECTION_KINDS = ("pull_requests", "issues", "branches", "checks")
_IDENTITY_FIELD = {
    "pull_requests": "number",
    "issues": "number",
    "branches": "name",
    "checks": "id",
}
_GREEN_CHECK_RESULTS = frozenset({"success", "neutral", "skipped"})
_CUSTODY_CLASSES = frozenset({"preservation", "active_custody", "owner_route"})


PageFetcher = Callable[[str | None], dict[str, Any]]
ConnectionFetcher = Callable[[str, str, str | None], dict[str, Any]]


def github_connection_query(kind: str) -> str:
    """Return the exact issue/branch GraphQL connection query used by the live adapter."""

    if kind == "issues":
        connection = "issues(states:OPEN,first:100,after:$cursor)"
        fields = "number url updatedAt"
    elif kind == "branches":
        connection = 'refs(refPrefix:"refs/heads/",first:100,after:$cursor)'
        fields = "name target{... on Commit{oid}}"
    else:
        raise ValueError(f"unsupported remote connection: {kind}")
    return (
        "query($owner:String!,$name:String!,$cursor:String){repository(owner:$owner,name:$name){"
        + "connection:"
        + connection
        + "{totalCount nodes{"
        + fields
        + "} pageInfo{hasNextPage endCursor}}}}"
    )


def _canonical_sha256(value: Any) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ConnectionCensus:
    kind: str
    expected_total: int | None
    page_count: int
    exhaustive: bool
    end_cursor: str | None
    nodes: tuple[dict[str, Any], ...]
    error: str | None = None

    @property
    def known_count(self) -> int:
        return len(self.nodes)


def paginate_exact(kind: str, fetch_page: PageFetcher, *, expected_total: int | None = None) -> ConnectionCensus:
    """Page one GitHub connection and reconcile every cursor against totalCount."""

    if kind not in CONNECTION_KINDS:
        raise ValueError(f"unsupported connection kind: {kind}")
    if expected_total == 0:
        return ConnectionCensus(kind, 0, 0, True, None, ())
    identity_field = _IDENTITY_FIELD[kind]
    cursor: str | None = None
    observed_total = expected_total
    nodes: dict[str, dict[str, Any]] = {}
    page_count = 0
    while True:
        try:
            page = fetch_page(cursor)
            total = int(page["total_count"])
            if total < 0:
                raise ValueError("negative-total")
            if observed_total is None:
                observed_total = total
            elif total != observed_total:
                raise ValueError("total-count-moved")
            for node in page.get("nodes") or []:
                if not isinstance(node, dict) or node.get(identity_field) in {None, ""}:
                    raise ValueError("node-identity-missing")
                identity = str(node[identity_field])
                if identity in nodes:
                    raise ValueError("duplicate-node-across-cursor")
                nodes[identity] = dict(node)
            page_count += 1
            has_next = page["has_next_page"]
            if not isinstance(has_next, bool):
                raise ValueError("has-next-page-not-boolean")
            end_cursor = page.get("end_cursor")
            if not has_next:
                if observed_total != len(nodes):
                    raise ValueError("total-count-not-reconciled")
                ordered = tuple(nodes[key] for key in sorted(nodes))
                return ConnectionCensus(kind, observed_total, page_count, True, None, ordered)
            if not isinstance(end_cursor, str) or not end_cursor:
                raise ValueError("next-cursor-missing")
            cursor = end_cursor
        except (KeyError, TypeError, ValueError) as exc:
            ordered = tuple(nodes[key] for key in sorted(nodes))
            return ConnectionCensus(
                kind,
                observed_total,
                page_count,
                False,
                cursor,
                ordered,
                str(exc),
            )


def _pr_leaf(repo: str, private: bool, node: dict[str, Any]) -> dict[str, Any]:
    number = int(node["number"])
    classification = str(node.get("classification") or "untyped")
    owner = node.get("owner")
    predicate = node.get("predicate")
    merge_condition = node.get("merge_condition")
    actionable_route = classification != "owner_route" or bool(owner and predicate and merge_condition)
    custody_debt = classification not in _CUSTODY_CLASSES or not actionable_route
    return {
        "leaf_id": f"{repo}:pull-request:{number}",
        "kind": "pull_request",
        "repository": repo,
        "private": private,
        "number": number,
        "url": node.get("url"),
        "status": "debt" if custody_debt else "owned",
        "custody_classification": classification,
        "custody_debt": custody_debt,
        "owner": owner,
        "predicate": predicate,
        "merge_condition": merge_condition,
    }


def _issue_leaf(repo: str, private: bool, node: dict[str, Any]) -> dict[str, Any]:
    number = int(node["number"])
    return {
        "leaf_id": f"{repo}:issue:{number}",
        "kind": "issue",
        "repository": repo,
        "private": private,
        "number": number,
        "url": node.get("url"),
        "status": "debt",
        "custody_debt": False,
    }


def _branch_leaf(repo: str, private: bool, default_branch: str | None, node: dict[str, Any]) -> dict[str, Any]:
    name = str(node["name"])
    is_default = bool(default_branch and name == default_branch)
    return {
        "leaf_id": f"{repo}:branch:{name}",
        "kind": "branch",
        "repository": repo,
        "private": private,
        "name": name,
        "head_oid": node.get("head_oid"),
        "is_default": is_default,
        "status": "owned" if is_default else "debt",
        "custody_debt": not is_default,
    }


def _check_leaf(repo: str, private: bool, node: dict[str, Any]) -> dict[str, Any]:
    check_id = str(node["id"])
    conclusion = str(node.get("conclusion") or node.get("state") or "unknown").lower()
    debt = conclusion not in _GREEN_CHECK_RESULTS
    return {
        "leaf_id": f"{repo}:check:{check_id}",
        "kind": "check",
        "repository": repo,
        "private": private,
        "check_id": check_id,
        "name": node.get("name"),
        "head_oid": node.get("head_oid"),
        "conclusion": conclusion,
        "url": node.get("url"),
        "status": "debt" if debt else "owned",
        "custody_debt": debt,
    }


def _normalize_nodes(
    kind: str,
    repo: str,
    private: bool,
    default_branch: str | None,
    nodes: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    if kind == "pull_requests":
        return [_pr_leaf(repo, private, node) for node in nodes]
    if kind == "issues":
        return [_issue_leaf(repo, private, node) for node in nodes]
    if kind == "branches":
        return [_branch_leaf(repo, private, default_branch, node) for node in nodes]
    return [_check_leaf(repo, private, node) for node in nodes]


def _tracked_leaf(row: dict[str, Any]) -> dict[str, Any]:
    if not row["private"]:
        return row
    return {
        "leaf_key": sha256(str(row["leaf_id"]).encode()).hexdigest(),
        "kind": row["kind"],
        "private": True,
        "status": row["status"],
        "custody_debt": row["custody_debt"],
    }


def build_github_estate_census(
    repositories: list[dict[str, Any]],
    fetch_connection: ConnectionFetcher,
    *,
    repository_cursor: dict[str, Any],
    now: datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build private full facts and a tracked redacted source projection."""

    observed = (now or datetime.now(UTC)).astimezone(UTC)
    repository_expected = repository_cursor.get("expected_total")
    repository_exhaustive = bool(repository_cursor.get("exhaustive"))
    failures: list[dict[str, str]] = []
    if isinstance(repository_expected, int) and repository_expected != len(repositories):
        repository_exhaustive = False
        failures.append({"scope": "repositories", "error": "repository-total-not-reconciled"})

    seen_repositories: set[str] = set()
    leaves: list[dict[str, Any]] = []
    cursor_rows: list[dict[str, Any]] = []
    for repository in sorted(repositories, key=lambda row: str(row.get("name_with_owner") or "")):
        repo = str(repository.get("name_with_owner") or "")
        if not repo or repo in seen_repositories:
            repository_exhaustive = False
            failures.append({"scope": "repositories", "error": "duplicate-or-missing-repository-identity"})
            continue
        seen_repositories.add(repo)
        private = bool(repository.get("private"))
        default_branch = str(repository.get("default_branch") or "") or None
        totals = repository.get("connection_totals") or {}
        for kind in CONNECTION_KINDS:
            expected = totals.get(kind)
            expected_total = expected if isinstance(expected, int) and not isinstance(expected, bool) else None

            def fetch_page(cursor: str | None) -> dict[str, Any]:
                return fetch_connection(repo, kind, cursor)

            result = paginate_exact(
                kind,
                fetch_page,
                expected_total=expected_total,
            )
            cursor_rows.append(
                {
                    "repository": repo,
                    "private": private,
                    "kind": kind,
                    "expected_total": result.expected_total,
                    "known_count": result.known_count,
                    "page_count": result.page_count,
                    "exhaustive": result.exhaustive,
                    "error": result.error,
                }
            )
            if not result.exhaustive:
                failures.append({"scope": kind, "error": result.error or "incomplete"})
            leaves.extend(_normalize_nodes(kind, repo, private, default_branch, result.nodes))

    exhaustive = repository_exhaustive and not failures
    content_sha256 = _canonical_sha256(leaves)
    debt_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for leaf in leaves:
        kind = str(leaf["kind"])
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if leaf["status"] == "debt":
            debt_counts[kind] = debt_counts.get(kind, 0) + 1
    known_leaf_count = len(leaves)
    source_report = {
        "schema": REPORT_SCHEMA,
        "source_id": SOURCE_ID,
        "cursor": {
            "repository": {
                "expected_total": repository_expected,
                "known_count": len(seen_repositories),
                "page_count": repository_cursor.get("page_count"),
                "exhaustive": repository_exhaustive,
            },
            "connection_count": len(cursor_rows),
            "failed_connection_count": len(failures),
            "known_leaf_count": known_leaf_count,
            "leaf_count_complete": exhaustive,
        },
        "exhaustive": exhaustive,
        "generated_at": observed.isoformat().replace("+00:00", "Z"),
        "content_sha256": content_sha256,
        "semantic_status": "ready" if exhaustive else "partial",
        "normalized_leaf_count": known_leaf_count,
    }
    full = {
        "schema": SCHEMA,
        "source_report": source_report,
        "summary": {
            "repository_count": len(seen_repositories),
            "private_repository_count": sum(bool(row.get("private")) for row in repositories),
            "known_leaf_count": known_leaf_count,
            "leaf_count_complete": exhaustive,
            "kind_counts": dict(sorted(kind_counts.items())),
            "debt_counts": dict(sorted(debt_counts.items())),
            "failure_count": len(failures),
        },
        "failures": failures,
        "cursors": cursor_rows,
        "leaves": leaves,
    }
    tracked = {
        "schema": SCHEMA,
        "source_report": source_report,
        "summary": full["summary"],
        "failure_count": len(failures),
        "leaves": [_tracked_leaf(row) for row in leaves],
    }
    return full, tracked
