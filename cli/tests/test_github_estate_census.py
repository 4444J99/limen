from __future__ import annotations

import json
from datetime import UTC, datetime

from limen.github_estate_census import build_github_estate_census, github_connection_query, paginate_exact

NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)


def test_live_connection_queries_close_every_graphql_scope() -> None:
    issues = github_connection_query("issues")
    branches = github_connection_query("branches")

    assert "connection:issues(states:OPEN,first:100,after:$cursor)" in issues
    assert 'connection:refs(refPrefix:"refs/heads/",first:100,after:$cursor)' in branches
    assert issues.endswith("}}}}")
    assert branches.endswith("}}}}")


def test_exact_connection_paginates_beyond_one_thousand() -> None:
    nodes = [{"number": number} for number in range(1, 1002)]
    calls = []

    def fetch(cursor):
        offset = int(cursor or 0)
        calls.append(cursor)
        page = nodes[offset : offset + 100]
        end = offset + len(page)
        return {
            "total_count": len(nodes),
            "nodes": page,
            "has_next_page": end < len(nodes),
            "end_cursor": str(end) if end < len(nodes) else None,
        }

    result = paginate_exact("issues", fetch)

    assert result.exhaustive is True
    assert result.expected_total == 1001
    assert result.known_count == 1001
    assert result.page_count == 11
    assert calls[-1] == "1000"


def test_census_normalizes_distinct_work_kinds_and_registry_report() -> None:
    nodes = {
        "pull_requests": [
            {
                "number": 4,
                "url": "https://example.invalid/pull/4",
                "classification": "owner_route",
                "owner": "agent",
                "predicate": "checks@head",
                "merge_condition": "queue-when-green",
            }
        ],
        "issues": [{"number": 8, "url": "https://example.invalid/issues/8"}],
        "branches": [
            {"name": "main", "head_oid": "a" * 40},
            {"name": "topic", "head_oid": "b" * 40},
        ],
        "checks": [
            {"id": "green", "name": "ci", "conclusion": "success", "head_oid": "a" * 40},
            {"id": "red", "name": "lint", "conclusion": "failure", "head_oid": "b" * 40},
        ],
    }

    def fetch(_repo, kind, cursor):
        assert cursor is None
        return {
            "total_count": len(nodes[kind]),
            "nodes": nodes[kind],
            "has_next_page": False,
            "end_cursor": None,
        }

    full, tracked = build_github_estate_census(
        [
            {
                "name_with_owner": "renamed-owner/repo",
                "private": False,
                "default_branch": "main",
                "connection_totals": {kind: len(value) for kind, value in nodes.items()},
            }
        ],
        fetch,
        repository_cursor={"expected_total": 1, "page_count": 1, "exhaustive": True},
        now=NOW,
    )

    assert full["source_report"]["exhaustive"] is True
    assert full["source_report"]["normalized_leaf_count"] == 6
    assert full["summary"]["kind_counts"] == {"branch": 2, "check": 2, "issue": 1, "pull_request": 1}
    assert full["summary"]["debt_counts"] == {"branch": 1, "check": 1, "issue": 1}
    assert tracked["source_report"]["semantic_status"] == "ready"


def test_failed_page_is_partial_with_known_subtotal_not_complete_zero() -> None:
    calls = 0

    def fetch(_repo, kind, cursor):
        nonlocal calls
        calls += 1
        if kind == "issues" and cursor == "next":
            raise ValueError("page unavailable")
        if kind == "issues":
            return {
                "total_count": 2,
                "nodes": [{"number": 1}],
                "has_next_page": True,
                "end_cursor": "next",
            }
        return {"total_count": 0, "nodes": [], "has_next_page": False, "end_cursor": None}

    full, _ = build_github_estate_census(
        [{"name_with_owner": "owner/repo", "private": False, "connection_totals": {}}],
        fetch,
        repository_cursor={"expected_total": 1, "page_count": 1, "exhaustive": True},
        now=NOW,
    )

    assert calls == 5
    assert full["source_report"]["exhaustive"] is False
    assert full["source_report"]["semantic_status"] == "partial"
    assert full["source_report"]["normalized_leaf_count"] == 1
    assert full["source_report"]["cursor"]["leaf_count_complete"] is False
    assert full["summary"]["known_leaf_count"] == 1


def test_moved_total_and_duplicate_cursor_rows_fail_closed() -> None:
    pages = [
        {
            "total_count": 2,
            "nodes": [{"name": "main"}],
            "has_next_page": True,
            "end_cursor": "next",
        },
        {
            "total_count": 3,
            "nodes": [{"name": "main"}],
            "has_next_page": False,
            "end_cursor": None,
        },
    ]

    result = paginate_exact("branches", lambda _cursor: pages.pop(0), expected_total=2)

    assert result.exhaustive is False
    assert result.known_count == 1
    assert result.error == "total-count-moved"


def test_private_repository_names_never_enter_tracked_projection() -> None:
    private_name = "private-owner/secret-repository"
    nodes = {
        "pull_requests": [{"number": 1, "classification": "active_custody", "owner": "owner"}],
        "issues": [{"number": 2}],
        "branches": [{"name": "main", "head_oid": "a" * 40}],
        "checks": [{"id": "ci", "conclusion": "success"}],
    }

    def fetch(_repo, kind, _cursor):
        return {
            "total_count": 1,
            "nodes": nodes[kind],
            "has_next_page": False,
            "end_cursor": None,
        }

    full, tracked = build_github_estate_census(
        [
            {
                "name_with_owner": private_name,
                "private": True,
                "default_branch": "main",
                "connection_totals": {kind: 1 for kind in nodes},
            }
        ],
        fetch,
        repository_cursor={"expected_total": 1, "page_count": 1, "exhaustive": True},
        now=NOW,
    )

    assert private_name in json.dumps(full)
    assert private_name not in json.dumps(tracked)
    assert all(set(row) == {"leaf_key", "kind", "private", "status", "custody_debt"} for row in tracked["leaves"])


def test_repository_count_mismatch_prevents_exhaustive_claim() -> None:
    def fetch(_repo, _kind, _cursor):
        return {"total_count": 0, "nodes": [], "has_next_page": False, "end_cursor": None}

    full, _ = build_github_estate_census(
        [{"name_with_owner": "owner/one", "private": False, "connection_totals": {}}],
        fetch,
        repository_cursor={"expected_total": 2, "page_count": 1, "exhaustive": True},
        now=NOW,
    )

    assert full["source_report"]["exhaustive"] is False
    assert full["summary"]["failure_count"] == 1
