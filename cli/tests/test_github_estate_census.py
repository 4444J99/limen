from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

from limen.github_estate_census import build_github_estate_census, github_connection_query, paginate_exact


NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)


def _load_script():
    path = Path(__file__).resolve().parents[2] / "scripts" / "github-estate-census.py"
    spec = importlib.util.spec_from_file_location("github_estate_census_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recording_digest_ignores_observation_identity_but_not_estate_state() -> None:
    module = _load_script()
    first = {
        "source_report": {"generated_at": "2026-08-27T12:00:00Z", "source_generation": "1" * 64},
        "repository_receipts": [{"connection_receipt_digest": "2" * 64}],
        "universe_baseline": {"observed_at": "2026-08-27T12:00:00Z", "census_digest": "3" * 64},
        "summary": {"repository_count": 320},
    }
    second = json.loads(json.dumps(first))
    second["source_report"]["generated_at"] = "2026-08-27T13:00:00Z"
    second["source_report"]["source_generation"] = "4" * 64
    second["repository_receipts"][0]["connection_receipt_digest"] = "5" * 64
    second["universe_baseline"]["observed_at"] = "2026-08-27T13:00:00Z"
    second["universe_baseline"]["census_digest"] = "6" * 64

    assert module._stable_digest(json.dumps(first)) == module._stable_digest(json.dumps(second))
    second["summary"]["repository_count"] = 321
    assert module._stable_digest(json.dumps(first)) != module._stable_digest(json.dumps(second))


def test_live_connection_queries_close_every_graphql_scope() -> None:
    pull_requests = github_connection_query("pull_requests")
    issues = github_connection_query("issues")
    branches = github_connection_query("branches")

    assert "connection:pullRequests(states:OPEN,first:100,after:$cursor" in pull_requests
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
                "default_sha": "a" * 40,
                "repository_id": "R_repo_1",
                "archived": True,
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
    assert full["repositories"][0]["repository_id"] == "R_repo_1"
    assert full["repositories"][0]["default_ref"] == "refs/heads/main"
    assert full["repositories"][0]["default_sha"] == "a" * 40
    assert full["repositories"][0]["archived"] is True
    assert len(full["repositories"][0]["default_generation"]) == 64
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


def test_transient_failed_cursor_resumes_without_restarting_completed_page() -> None:
    generation = "generation-1"
    first_calls: list[str | None] = []

    def first_fetch(cursor):
        first_calls.append(cursor)
        if cursor == "next":
            raise ValueError("github-page-unavailable")
        return {
            "total_count": 2,
            "nodes": [{"number": 1}],
            "has_next_page": True,
            "end_cursor": "next",
        }

    partial = paginate_exact(
        "issues",
        first_fetch,
        expected_total=2,
        repository="owner/repo",
        source_generation=generation,
    )
    resumed_calls: list[str | None] = []

    def resumed_fetch(cursor):
        resumed_calls.append(cursor)
        assert cursor == "next"
        return {
            "total_count": 2,
            "nodes": [{"number": 2}],
            "has_next_page": False,
            "end_cursor": None,
        }

    complete = paginate_exact(
        "issues",
        resumed_fetch,
        expected_total=2,
        repository="owner/repo",
        source_generation=generation,
        resume=partial.as_resume_dict(),
    )

    assert first_calls == [None, "next"]
    assert resumed_calls == ["next"]
    assert complete.exhaustive is True
    assert complete.known_count == 2
    assert complete.page_count == 2
    assert complete.failures[-1].repository == "owner/repo"
    assert complete.failures[-1].connection_kind == "issues"
    assert complete.failures[-1].cursor == "next"
    assert complete.failures[-1].attempt == 1
    assert complete.failures[-1].expected_total == 2
    assert complete.failures[-1].retry_class == "transient"


def test_complete_connection_is_reused_without_fetch() -> None:
    complete = paginate_exact(
        "branches",
        lambda _cursor: {
            "total_count": 1,
            "nodes": [{"name": "main"}],
            "has_next_page": False,
            "end_cursor": None,
        },
        expected_total=1,
        source_generation="generation-1",
    )

    reused = paginate_exact(
        "branches",
        lambda _cursor: (_ for _ in ()).throw(AssertionError("fetch must not run")),
        expected_total=1,
        source_generation="generation-1",
        resume=complete.as_resume_dict(),
    )

    assert reused.exhaustive is True
    assert reused.reused is True


def test_cursor_corruption_and_corrupt_resume_cache_fail_closed() -> None:
    repeated = paginate_exact(
        "branches",
        lambda _cursor: {
            "total_count": 2,
            "nodes": [{"name": "main"}],
            "has_next_page": True,
            "end_cursor": "same",
        },
        expected_total=2,
    )
    assert repeated.exhaustive is False
    assert repeated.error == "duplicate-node-across-cursor"
    assert repeated.failures[-1].retry_class == "corrupt"

    complete_cache = {
        "kind": "issues",
        "expected_total": 1,
        "page_count": 1,
        "exhaustive": True,
        "end_cursor": None,
        "nodes": [{"number": 1}, {"number": 1}],
        "source_generation": "generation-1",
    }
    refused = paginate_exact(
        "issues",
        lambda _cursor: (_ for _ in ()).throw(AssertionError("fetch must not run")),
        expected_total=1,
        repository="owner/repo",
        source_generation="generation-1",
        resume=complete_cache,
    )
    assert refused.exhaustive is False
    assert refused.error.startswith("resume-cache-corrupt:")
    assert refused.failures[-1].retry_class == "corrupt"


def test_changed_source_generation_restarts_instead_of_reusing_stale_pages() -> None:
    cached = paginate_exact(
        "issues",
        lambda _cursor: {
            "total_count": 1,
            "nodes": [{"number": 1}],
            "has_next_page": False,
            "end_cursor": None,
        },
        expected_total=1,
        source_generation="generation-1",
    )
    calls: list[str | None] = []

    refreshed = paginate_exact(
        "issues",
        lambda cursor: (
            calls.append(cursor)
            or {
                "total_count": 1,
                "nodes": [{"number": 2}],
                "has_next_page": False,
                "end_cursor": None,
            }
        ),
        expected_total=1,
        source_generation="generation-2",
        resume=cached.as_resume_dict(),
    )

    assert calls == [None]
    assert refreshed.reused is False
    assert refreshed.nodes == ({"number": 2},)


def test_transient_page_retries_are_bounded() -> None:
    calls = 0

    def fetch(_cursor):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise TimeoutError("temporary timeout")
        return {
            "total_count": 1,
            "nodes": [{"number": 1}],
            "has_next_page": False,
            "end_cursor": None,
        }

    result = paginate_exact("issues", fetch, expected_total=1, max_attempts=3)

    assert result.exhaustive is True
    assert calls == 3
    assert [failure.attempt for failure in result.failures] == [1, 2]


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
