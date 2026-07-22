"""Focused tests for exact, dynamically paginated GITVS estate observations."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gitvs.py"


def _load():
    spec = importlib.util.spec_from_file_location("gitvs_uut", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(payload: dict, returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, json.dumps(payload), "")


def test_owner_open_pr_counts_paginates_repository_totals(monkeypatch) -> None:
    module = _load()
    pages = [
        {
            "data": {
                "organization": {
                    "repositories": {
                        "nodes": [
                            {"nameWithOwner": "example/a", "pullRequests": {"totalCount": 2}},
                            {"nameWithOwner": "example/b", "pullRequests": {"totalCount": 0}},
                        ],
                        "pageInfo": {"hasNextPage": True, "endCursor": "next-page"},
                    }
                }
            }
        },
        {
            "data": {
                "organization": {
                    "repositories": {
                        "nodes": [{"nameWithOwner": "example/c", "pullRequests": {"totalCount": 7}}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        },
    ]
    calls: list[list[str]] = []

    def fake_gh(args, _token, timeout=60):
        calls.append(args)
        return _result(pages.pop(0))

    monkeypatch.setattr(module, "_gh", fake_gh)

    assert module._owner_open_pr_counts("example", "opaque") == {
        "example/a": 2,
        "example/b": 0,
        "example/c": 7,
    }
    assert "cursor=next-page" in calls[1]
    assert all("--author" not in call for call in calls)
    query = next(arg.removeprefix("query=") for arg in calls[0] if arg.startswith("query="))
    assert query.count("{") == query.count("}")


def test_owner_open_pr_counts_blocks_on_incomplete_remote_evidence(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(
        module,
        "_gh",
        lambda _args, _token, timeout=60: subprocess.CompletedProcess([], 1, "", "unavailable"),
    )
    assert module._owner_open_pr_counts("example", "opaque") is None


def test_owner_repo_inventory_paginates_private_repositories_and_reconciles_total(monkeypatch) -> None:
    module = _load()
    pages = [
        {
            "data": {
                "organization": {
                    "repositories": {
                        "totalCount": 2,
                        "nodes": [
                            {
                                "nameWithOwner": "renamed/private-repo",
                                "isPrivate": True,
                                "pullRequests": {"totalCount": 1001},
                            }
                        ],
                        "pageInfo": {"hasNextPage": True, "endCursor": "repos-2"},
                    }
                }
            }
        },
        {
            "data": {
                "organization": {
                    "repositories": {
                        "totalCount": 2,
                        "nodes": [
                            {
                                "nameWithOwner": "renamed/public-repo",
                                "isPrivate": False,
                                "pullRequests": {"totalCount": 0},
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        },
    ]
    calls = []
    monkeypatch.setattr(module, "_gh_user", lambda args, timeout=90: calls.append(args) or _result(pages.pop(0)))

    inventory = module._owner_repo_inventory("renamed", "opaque")

    assert inventory["repository_total"] == 2
    assert inventory["page_count"] == 2
    assert inventory["repositories"][0]["private"] is True
    assert inventory["repositories"][0]["open_pr_total"] == 1001
    assert "cursor=repos-2" in calls[1]


def test_owner_repo_inventory_falls_through_org_type_mismatch_to_user(monkeypatch) -> None:
    module = _load()
    responses = [
        subprocess.CompletedProcess([], 1, "", "Could not resolve to an Organization"),
        _result(
            {
                "data": {
                    "user": {
                        "repositories": {
                            "totalCount": 1,
                            "nodes": [
                                {
                                    "nameWithOwner": "person/profile",
                                    "isPrivate": False,
                                    "pullRequests": {"totalCount": 0},
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            }
        ),
    ]
    monkeypatch.setattr(module, "_gh_user", lambda _args, timeout=90: responses.pop(0))

    inventory = module._owner_repo_inventory("person", "opaque")

    assert inventory["repository_total"] == 1
    assert inventory["repositories"][0]["name_with_owner"] == "person/profile"


def test_repo_open_prs_pages_fixture_beyond_one_thousand(monkeypatch) -> None:
    module = _load()
    nodes = [
        {
            "number": number,
            "url": f"https://example.invalid/pull/{number}",
            "title": f"PR {number}",
            "isDraft": False,
            "updatedAt": "2026-07-21T00:00:00Z",
            "headRefName": f"branch-{number}",
            "headRefOid": f"{number:040x}",
            "body": "",
            "author": {"login": "owner"},
            "assignees": {"nodes": []},
            "labels": {"nodes": []},
        }
        for number in range(1, 1002)
    ]
    pages = []
    for offset in range(0, len(nodes), 100):
        end = min(offset + 100, len(nodes))
        pages.append(
            {
                "data": {
                    "repository": {
                        "pullRequests": {
                            "totalCount": 1001,
                            "nodes": nodes[offset:end],
                            "pageInfo": {
                                "hasNextPage": end < len(nodes),
                                "endCursor": f"pr-{end}" if end < len(nodes) else None,
                            },
                        }
                    }
                }
            }
        )
    calls = []
    monkeypatch.setattr(module, "_gh_user", lambda args, timeout=90: calls.append(args) or _result(pages.pop(0)))

    result = module._repo_open_prs("renamed/private-repo", 1001, "opaque")

    assert result["exhaustive"] is True
    assert result["page_count"] == 11
    assert len(result["rows"]) == 1001
    assert "cursor=pr-1000" in calls[-1]


def test_repo_open_prs_failed_page_is_not_exhaustive(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(
        module,
        "_gh_user",
        lambda _args, timeout=90: subprocess.CompletedProcess([], 1, "", "unavailable"),
    )

    result = module._repo_open_prs("example/repo", 1, "opaque")

    assert result["exhaustive"] is False
    assert result["error"] == "pull-request-page-failed"


def test_pr_classification_preserves_owner_and_actionable_route_contracts() -> None:
    module = _load()
    policy = {
        "active_owner_max_age_hours": 24,
        "owner_label_prefix": "owner:",
        "preservation_labels": ["custody:preservation"],
        "preservation_markers": ["preservation marker"],
    }
    now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    base = {
        "number": 7,
        "url": "https://example.invalid/pull/7",
        "title": "work",
        "isDraft": False,
        "headRefName": "topic",
        "headRefOid": "a" * 40,
        "body": "",
        "author": {"login": "claude-owner"},
        "assignees": {"nodes": []},
        "labels": {"nodes": []},
    }

    active = module._classify_open_pr("example/repo", {**base, "updatedAt": "2026-07-21T11:00:00Z"}, policy, now)
    routed = module._classify_open_pr("example/repo", {**base, "updatedAt": "2026-07-01T00:00:00Z"}, policy, now)
    preserved = module._classify_open_pr(
        "example/repo",
        {
            **base,
            "updatedAt": "2026-07-01T00:00:00Z",
            "labels": {"nodes": [{"name": "custody:preservation"}]},
        },
        policy,
        now,
    )

    assert active["classification"] == "active_custody"
    assert active["owner"] == "claude-owner"
    assert routed["classification"] == "owner_route"
    assert routed["predicate"].endswith("@" + "a" * 40)
    assert "merge-queue" in routed["merge_condition"]
    assert preserved["classification"] == "preservation"


def test_private_pr_rows_are_redacted_in_tracked_projection() -> None:
    module = _load()
    row = {
        "repository": "private-owner/secret-name",
        "number": 4,
        "url": "https://github.invalid/private-owner/secret-name/pull/4",
        "private": True,
        "owner": "private-owner",
        "head_oid": "a" * 40,
        "predicate": "secret predicate",
        "merge_condition": "secret merge condition",
        "classification": "owner_route",
    }

    redacted = module._redact_pr_row(row)

    assert redacted["repository"] is None
    assert redacted["number"] is None
    assert redacted["url"] is None
    assert redacted["owner"] is None
    assert redacted["predicate"] is None
    assert redacted["merge_condition"] is None
    assert len(redacted["pr_key"]) == 64


def test_pr_debt_census_deduplicates_renamed_owner_aliases(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "_token", lambda: "opaque")
    monkeypatch.setattr(module, "owners", lambda _estate: ["old-owner", "renamed-owner"])
    monkeypatch.setattr(module, "_resolve_owner_login", lambda _owner, _token: "renamed-owner")
    inventory_calls = []

    def inventory(owner, _token):
        inventory_calls.append(owner)
        return {
            "owner": owner,
            "repository_total": 1,
            "page_count": 1,
            "repositories": [
                {
                    "name_with_owner": "renamed-owner/repo",
                    "private": False,
                    "open_pr_total": 1,
                }
            ],
        }

    monkeypatch.setattr(module, "_owner_repo_inventory", inventory)
    monkeypatch.setattr(
        module,
        "_repo_open_prs",
        lambda _repo, _expected, _token: {
            "exhaustive": True,
            "expected_total": 1,
            "page_count": 1,
            "error": None,
            "rows": [
                {
                    "number": 1,
                    "url": "https://example.invalid/pull/1",
                    "title": "work",
                    "isDraft": False,
                    "updatedAt": "2026-07-21T11:00:00Z",
                    "headRefName": "topic",
                    "headRefOid": "a" * 40,
                    "body": "",
                    "author": {"login": "owner"},
                    "assignees": {"nodes": []},
                    "labels": {"nodes": []},
                }
            ],
        },
    )

    full, tracked = module.pr_debt_census(
        {"pr_debt_policy": {"active_owner_max_age_hours": 168}},
        now=datetime(2026, 7, 21, 12, tzinfo=UTC),
    )

    assert inventory_calls == ["renamed-owner"]
    assert full["requested_owner_count"] == 2
    assert full["canonical_owner_count"] == 1
    assert full["open_pr_count"] == 1
    assert full["exhaustive"] is True
    assert tracked["cursor_reconciliation"]["failure_count"] == 0


def test_tracked_failed_census_exposes_count_without_private_failure_names(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module, "_token", lambda: "opaque")
    monkeypatch.setattr(module, "owners", lambda _estate: ["private-owner"])
    monkeypatch.setattr(module, "_resolve_owner_login", lambda _owner, _token: "private-owner")
    monkeypatch.setattr(module, "_owner_repo_inventory", lambda _owner, _token: None)

    full, tracked = module.pr_debt_census({}, now=datetime(2026, 7, 21, 12, tzinfo=UTC))

    assert full["exhaustive"] is False
    assert full["cursor_reconciliation"]["failures"] == ["repository-cursor-failed:private-owner"]
    assert tracked["cursor_reconciliation"] == {
        "repository_pages": 0,
        "pull_request_pages": 0,
        "failure_count": 1,
    }
    assert "private-owner" not in json.dumps(tracked)
