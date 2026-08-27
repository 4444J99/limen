"""Exact GitHub-estate normalization for the work-universe source registry."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Callable, Mapping

from limen.progress_source_registry import REPORT_SCHEMA


SCHEMA = "limen.github-estate-census.v1"
SOURCE_ID = "github-estate"
CONNECTION_KINDS = (
    "pull_requests",
    "issues",
    "branches",
    "checks",
)
PAGINATED_CONNECTION_KINDS = (
    *CONNECTION_KINDS,
    "closed_pull_requests",
    "review_threads",
    "review_comments",
)
_IDENTITY_FIELD = {
    "pull_requests": "number",
    "closed_pull_requests": "number",
    "issues": "number",
    "branches": "name",
    "checks": "id",
    "review_threads": "id",
    "review_comments": "id",
}
_GREEN_CHECK_RESULTS = frozenset({"success", "neutral", "skipped"})
_CUSTODY_CLASSES = frozenset({"preservation", "active_custody", "owner_route"})


PageFetcher = Callable[[str | None], dict[str, Any]]
ConnectionFetcher = Callable[[str, str, str | None], dict[str, Any]]


def github_connection_query(kind: str) -> str:
    """Return the exact issue/branch GraphQL connection query used by the live adapter."""

    if kind == "pull_requests":
        connection = "pullRequests(states:OPEN,first:100,after:$cursor,orderBy:{field:UPDATED_AT,direction:DESC})"
        fields = (
            "number url title isDraft updatedAt headRefName headRefOid body "
            "author{login} assignees(first:10){nodes{login}} labels(first:50){nodes{name}}"
        )
    elif kind == "issues":
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
class CursorFailure:
    repository: str | None
    connection_kind: str
    cursor: str | None
    error_class: str
    attempt: int
    expected_total: int | None
    retry_class: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "repository": self.repository,
            "connection_kind": self.connection_kind,
            "cursor": self.cursor,
            "error_class": self.error_class,
            "attempt": self.attempt,
            "expected_total": self.expected_total,
            "retry_class": self.retry_class,
        }


@dataclass(frozen=True)
class ConnectionCensus:
    kind: str
    expected_total: int | None
    page_count: int
    exhaustive: bool
    end_cursor: str | None
    nodes: tuple[dict[str, Any], ...]
    error: str | None = None
    failures: tuple[CursorFailure, ...] = ()
    source_generation: str | None = None
    reused: bool = False

    @property
    def known_count(self) -> int:
        return len(self.nodes)

    def as_resume_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "expected_total": self.expected_total,
            "page_count": self.page_count,
            "exhaustive": self.exhaustive,
            "end_cursor": self.end_cursor,
            "nodes": list(self.nodes),
            "error": self.error,
            "failures": [failure.as_dict() for failure in self.failures],
            "source_generation": self.source_generation,
        }


def connection_census_from_dict(value: Mapping[str, Any]) -> ConnectionCensus:
    """Validate one private cursor-cache entry without trusting its shape."""

    kind = str(value.get("kind") or "")
    if kind not in PAGINATED_CONNECTION_KINDS:
        raise ValueError("resume-kind-invalid")
    expected = value.get("expected_total")
    if expected is not None and (isinstance(expected, bool) or not isinstance(expected, int) or expected < 0):
        raise ValueError("resume-expected-total-invalid")
    page_count = value.get("page_count")
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 0:
        raise ValueError("resume-page-count-invalid")
    exhaustive = value.get("exhaustive")
    if not isinstance(exhaustive, bool):
        raise ValueError("resume-exhaustive-invalid")
    cursor = value.get("end_cursor")
    if cursor is not None and (not isinstance(cursor, str) or not cursor):
        raise ValueError("resume-cursor-invalid")
    raw_nodes = value.get("nodes")
    if not isinstance(raw_nodes, list) or not all(isinstance(node, dict) for node in raw_nodes):
        raise ValueError("resume-nodes-invalid")
    identity_field = _IDENTITY_FIELD[kind]
    identities: set[str] = set()
    nodes: list[dict[str, Any]] = []
    for raw in raw_nodes:
        identity = raw.get(identity_field)
        if identity in {None, ""} or str(identity) in identities:
            raise ValueError("resume-node-identity-invalid")
        identities.add(str(identity))
        nodes.append(dict(raw))
    raw_failures = value.get("failures") or []
    if not isinstance(raw_failures, list):
        raise ValueError("resume-failures-invalid")
    failures: list[CursorFailure] = []
    for raw in raw_failures:
        if not isinstance(raw, dict):
            raise ValueError("resume-failure-invalid")
        attempt = raw.get("attempt")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            raise ValueError("resume-failure-attempt-invalid")
        retry_class = str(raw.get("retry_class") or "")
        if retry_class not in {"transient", "permanent", "corrupt"}:
            raise ValueError("resume-retry-class-invalid")
        failures.append(
            CursorFailure(
                repository=str(raw["repository"]) if raw.get("repository") is not None else None,
                connection_kind=str(raw.get("connection_kind") or kind),
                cursor=str(raw["cursor"]) if raw.get("cursor") is not None else None,
                error_class=str(raw.get("error_class") or "resume-error-missing"),
                attempt=attempt,
                expected_total=(int(raw["expected_total"]) if raw.get("expected_total") is not None else None),
                retry_class=retry_class,
            )
        )
    source_generation = value.get("source_generation")
    if source_generation is not None and (not isinstance(source_generation, str) or not source_generation):
        raise ValueError("resume-source-generation-invalid")
    if exhaustive and (cursor is not None or expected != len(nodes)):
        raise ValueError("resume-complete-count-invalid")
    if not exhaustive and cursor is None and nodes:
        raise ValueError("resume-partial-cursor-missing")
    return ConnectionCensus(
        kind=kind,
        expected_total=expected,
        page_count=page_count,
        exhaustive=exhaustive,
        end_cursor=cursor,
        nodes=tuple(nodes),
        error=str(value["error"]) if value.get("error") is not None else None,
        failures=tuple(failures),
        source_generation=source_generation,
    )


def _failure_retry_class(exc: BaseException) -> str:
    detail = str(exc).lower()
    if isinstance(exc, (ConnectionError, TimeoutError)) or any(
        marker in detail
        for marker in (
            "page-unavailable",
            "rate-limit",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "connection reset",
            "502",
            "503",
            "504",
        )
    ):
        return "transient"
    if any(
        marker in detail
        for marker in (
            "cursor",
            "duplicate-node",
            "node-identity",
            "total-count",
            "negative-total",
            "has-next-page",
        )
    ):
        return "corrupt"
    return "permanent"


def paginate_exact(
    kind: str,
    fetch_page: PageFetcher,
    *,
    expected_total: int | None = None,
    repository: str | None = None,
    source_generation: str | None = None,
    resume: ConnectionCensus | Mapping[str, Any] | None = None,
    max_attempts: int = 1,
) -> ConnectionCensus:
    """Page one GitHub connection and reconcile every cursor against totalCount."""

    if kind not in PAGINATED_CONNECTION_KINDS:
        raise ValueError(f"unsupported connection kind: {kind}")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    if expected_total == 0:
        return ConnectionCensus(kind, 0, 0, True, None, (), source_generation=source_generation)
    identity_field = _IDENTITY_FIELD[kind]
    cursor: str | None = None
    observed_total = expected_total
    nodes: dict[str, dict[str, Any]] = {}
    page_count = 0
    failures: list[CursorFailure] = []
    prior: ConnectionCensus | None = None
    attempt = 0
    if resume is not None:
        try:
            prior = resume if isinstance(resume, ConnectionCensus) else connection_census_from_dict(resume)
        except (KeyError, TypeError, ValueError) as exc:
            detail = f"resume-cache-corrupt:{exc}"
            failure = CursorFailure(
                repository=repository,
                connection_kind=kind,
                cursor=None,
                error_class=detail,
                attempt=1,
                expected_total=expected_total,
                retry_class="corrupt",
            )
            return ConnectionCensus(
                kind,
                expected_total,
                0,
                False,
                None,
                (),
                detail,
                (failure,),
                source_generation,
            )
        if prior is not None and (
            prior.kind != kind
            or prior.source_generation != source_generation
            or (
                expected_total is not None
                and prior.expected_total is not None
                and expected_total != prior.expected_total
            )
        ):
            prior = None
        if prior is not None and prior.exhaustive:
            return replace(prior, reused=True)
        if prior is not None:
            if not prior.failures or prior.failures[-1].retry_class != "transient":
                return replace(prior, reused=True)
            cursor = prior.end_cursor
            observed_total = prior.expected_total if prior.expected_total is not None else expected_total
            nodes = {str(node[identity_field]): dict(node) for node in prior.nodes}
            page_count = prior.page_count
            failures.extend(prior.failures)
            attempt = prior.failures[-1].attempt
    seen_cursors: set[str | None] = {cursor}
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
                return ConnectionCensus(
                    kind,
                    observed_total,
                    page_count,
                    True,
                    None,
                    ordered,
                    failures=tuple(failures),
                    source_generation=source_generation,
                )
            if not isinstance(end_cursor, str) or not end_cursor:
                raise ValueError("next-cursor-missing")
            if end_cursor in seen_cursors:
                raise ValueError("cursor-not-advanced")
            cursor = end_cursor
            seen_cursors.add(cursor)
            attempt = 0
        except (ConnectionError, KeyError, TimeoutError, TypeError, ValueError) as exc:
            attempt += 1
            retry_class = _failure_retry_class(exc)
            failures.append(
                CursorFailure(
                    repository=repository,
                    connection_kind=kind,
                    cursor=cursor,
                    error_class=str(exc),
                    attempt=attempt,
                    expected_total=observed_total,
                    retry_class=retry_class,
                )
            )
            if retry_class == "transient" and attempt < max_attempts:
                continue
            ordered = tuple(nodes[key] for key in sorted(nodes))
            return ConnectionCensus(
                kind,
                observed_total,
                page_count,
                False,
                cursor,
                ordered,
                str(exc),
                tuple(failures),
                source_generation,
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


def _repository_record(repository: dict[str, Any]) -> dict[str, Any]:
    """Normalize repository generation facts without assuming they are available."""

    name = str(repository["name_with_owner"])
    default_branch = str(repository.get("default_branch") or "") or None
    default_sha = str(repository.get("default_sha") or "") or None
    return {
        "name_with_owner": name,
        "repository_id": repository.get("repository_id"),
        "private": bool(repository.get("private")),
        "archived": bool(repository.get("archived")),
        "default_ref": f"refs/heads/{default_branch}" if default_branch else None,
        "default_sha": default_sha,
        "default_check_status": repository.get("default_check_status") or "unknown",
        "default_generation": _canonical_sha256(
            {
                "repository": name,
                "default_ref": default_branch,
                "default_sha": default_sha,
                "archived": bool(repository.get("archived")),
            }
        ),
    }


def _tracked_repository(row: dict[str, Any]) -> dict[str, Any]:
    if not row["private"]:
        return row
    return {
        "repository_key": sha256(str(row["name_with_owner"]).encode()).hexdigest(),
        "private": True,
        "archived": row["archived"],
        "default_generation": row["default_generation"],
        "default_check_status": row["default_check_status"],
    }


def _tracked_repository_receipt(row: dict[str, Any]) -> dict[str, Any]:
    if not row["private"]:
        return row
    return {
        "repository_key": sha256(str(row["repository"]).encode()).hexdigest(),
        "repository_id": row.get("repository_id"),
        "private": True,
        "archived": row["archived"],
        "default_generation": row["default_generation"],
        "source_generation": row.get("source_generation"),
        "complete": row["complete"],
        "connection_receipt_digest": row["connection_receipt_digest"],
    }


def build_github_estate_census(
    repositories: list[dict[str, Any]],
    fetch_connection: ConnectionFetcher,
    *,
    repository_cursor: dict[str, Any],
    now: datetime | None = None,
    connection_results: Mapping[tuple[str, str], ConnectionCensus] | None = None,
    resume_connections: Mapping[tuple[str, str], ConnectionCensus | Mapping[str, Any]] | None = None,
    source_generation: str | None = None,
    max_attempts: int = 1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build private full facts and a tracked redacted source projection."""

    observed = (now or datetime.now(UTC)).astimezone(UTC)
    repository_expected = repository_cursor.get("expected_total")
    repository_exhaustive = bool(repository_cursor.get("exhaustive"))
    failures: list[dict[str, Any]] = []
    if isinstance(repository_expected, int) and repository_expected != len(repositories):
        repository_exhaustive = False
        failures.append(
            {
                "repository": None,
                "connection_kind": "repositories",
                "cursor": repository_cursor.get("end_cursor"),
                "error_class": "repository-total-not-reconciled",
                "attempt": 1,
                "expected_total": repository_expected,
                "retry_class": "corrupt",
            }
        )
    for failure in repository_cursor.get("failures") or []:
        if isinstance(failure, dict):
            failures.append(dict(failure))

    seen_repositories: set[str] = set()
    repository_rows: list[dict[str, Any]] = []
    leaves: list[dict[str, Any]] = []
    cursor_rows: list[dict[str, Any]] = []
    for repository in sorted(repositories, key=lambda row: str(row.get("name_with_owner") or "")):
        repo = str(repository.get("name_with_owner") or "")
        if not repo or repo in seen_repositories:
            repository_exhaustive = False
            failures.append(
                {
                    "repository": repo or None,
                    "connection_kind": "repositories",
                    "cursor": None,
                    "error_class": "duplicate-or-missing-repository-identity",
                    "attempt": 1,
                    "expected_total": repository_expected,
                    "retry_class": "corrupt",
                }
            )
            continue
        seen_repositories.add(repo)
        repository_rows.append(_repository_record(repository))
        private = bool(repository.get("private"))
        default_branch = str(repository.get("default_branch") or "") or None
        totals = repository.get("connection_totals") or {}
        for kind in CONNECTION_KINDS:
            expected = totals.get(kind)
            expected_total = expected if isinstance(expected, int) and not isinstance(expected, bool) else None

            def fetch_page(cursor: str | None) -> dict[str, Any]:
                return fetch_connection(repo, kind, cursor)

            result = (connection_results or {}).get((repo, kind))
            if result is None:
                result = paginate_exact(
                    kind,
                    fetch_page,
                    expected_total=expected_total,
                    repository=repo,
                    source_generation=source_generation,
                    resume=(resume_connections or {}).get((repo, kind)),
                    max_attempts=max_attempts,
                )
            cursor_rows.append(
                {
                    "repository": repo,
                    "private": private,
                    "kind": kind,
                    "expected_total": result.expected_total,
                    "known_count": result.known_count,
                    "observed_total": result.known_count,
                    "page_count": result.page_count,
                    "page_cursor": result.end_cursor,
                    "exhaustive": result.exhaustive,
                    "complete": result.exhaustive,
                    "error": result.error,
                    "retry_failures": [failure.as_dict() for failure in result.failures],
                    "reused": result.reused,
                    "source_generation": result.source_generation,
                }
            )
            if not result.exhaustive:
                if result.failures:
                    failures.append(result.failures[-1].as_dict())
                else:
                    failures.append(
                        {
                            "repository": repo,
                            "connection_kind": kind,
                            "cursor": result.end_cursor,
                            "error_class": result.error or "incomplete",
                            "attempt": 1,
                            "expected_total": result.expected_total,
                            "retry_class": "permanent",
                        }
                    )
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
    unaccounted = 0
    if isinstance(repository_expected, int):
        unaccounted += max(0, repository_expected - len(seen_repositories))
    for row in cursor_rows:
        if isinstance(row["expected_total"], int):
            unaccounted += max(0, int(row["expected_total"]) - int(row["known_count"]))
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
        "source_generation": source_generation,
        "unaccounted": unaccounted,
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
            "unaccounted": unaccounted,
        },
        "failures": failures,
        "cursors": cursor_rows,
        "repositories": repository_rows,
        "leaves": leaves,
    }
    repository_receipts: list[dict[str, Any]] = []
    for repository in repository_rows:
        repo = str(repository["name_with_owner"])
        rows = [row for row in cursor_rows if row["repository"] == repo]
        repository_receipts.append(
            {
                "repository": repo,
                "repository_id": repository.get("repository_id"),
                "private": repository["private"],
                "archived": repository["archived"],
                "default_ref": repository.get("default_ref"),
                "default_sha": repository.get("default_sha"),
                "default_check_status": repository.get("default_check_status") or "unknown",
                "default_generation": repository["default_generation"],
                "source_generation": source_generation,
                "complete": len(rows) == len(CONNECTION_KINDS) and all(row["complete"] for row in rows),
                "connection_receipt_digest": _canonical_sha256(rows),
            }
        )
    full["repository_receipts"] = repository_receipts
    tracked = {
        "schema": SCHEMA,
        "source_report": source_report,
        "summary": full["summary"],
        "failure_count": len(failures),
        "repositories": [_tracked_repository(row) for row in repository_rows],
        "repository_receipts": [_tracked_repository_receipt(row) for row in repository_receipts],
        "leaves": [_tracked_leaf(row) for row in leaves],
    }
    return full, tracked
