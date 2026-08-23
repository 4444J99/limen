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


def test_terminal_human_levers_cannot_be_current_gitvs_owners(tmp_path, monkeypatch) -> None:
    module = _load()
    rows = [{"id": "L-OPEN", "status": "open", "issue": 1}]
    rows.extend(
        {"id": f"L-{status.upper()}", "status": status, "issue": 2} for status in module.TERMINAL_LEVER_STATUSES
    )
    rows.append({"id": "L-LEGACY", "discharged": "2026-07-17", "issue": 3})
    (tmp_path / "his-hand-levers.json").write_text(json.dumps({"levers": rows}), encoding="utf-8")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    assert module._homed_levers() == {"L-OPEN"}
    assert set(module._lever_index()) == {"L-OPEN"}
    assert module._cite("L-DISCHARGED", module._lever_index()) == "L-DISCHARGED (cited)"


def test_usage_projects_actions_product_not_all_github_products(tmp_path, monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module.shutil, "which", lambda _command: "/usr/bin/gh")
    monkeypatch.setattr(module, "owners", lambda _estate: ["organvm"])
    monkeypatch.setattr(
        module,
        "_usage_month",
        lambda *_args: {
            "by_product": {
                "actions": {"net_usd": 0.5},
                "code_quality": {"net_usd": 100.0},
            },
            "net_usd_total": 100.5,
        },
    )
    monkeypatch.setattr(module, "_runner_admission_observation", lambda _repo: (False, "annotation absent"))
    monkeypatch.setattr(module, "USAGE_DOC", tmp_path / "usage.json")
    monkeypatch.setattr(module, "USAGE_STAMP", tmp_path / "usage-stamp.json")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    estate = {"budgets": {"actions_spend": {"monthly_net_usd_max": 25}}}
    assert module.usage(estate, check=True, print_json=False) == 0
    doc = json.loads(module.USAGE_DOC.read_text(encoding="utf-8"))
    assert doc["schema"] == "limen.github_actions_usage.v2"
    assert doc["actions_net_usd_mtd"] == 0.5
    assert doc["net_usd_total"] == 100.5
    assert doc["actions_net_usd_projected_month_end"] < doc["budget_net_usd"]


def test_usage_no_write_preserves_immutable_observer_source(tmp_path, monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(module.shutil, "which", lambda _command: "/usr/bin/gh")
    monkeypatch.setattr(module, "owners", lambda _estate: ["organvm"])
    monkeypatch.setattr(
        module,
        "_usage_month",
        lambda *_args: {"by_product": {"actions": {"net_usd": 0.0}}, "net_usd_total": 0.0},
    )
    monkeypatch.setattr(module, "_runner_admission_observation", lambda _repo: (False, "annotation absent"))
    monkeypatch.setattr(module, "USAGE_DOC", tmp_path / "usage.json")
    monkeypatch.setattr(module, "USAGE_STAMP", tmp_path / "usage-stamp.json")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    assert module.usage({}, check=True, print_json=False, write=False) == 0
    assert not module.USAGE_DOC.exists()
    assert not module.USAGE_STAMP.exists()


def test_runner_admission_observation_paginates_and_preserves_unreadable_evidence(monkeypatch) -> None:
    module = _load()
    calls: list[list[str]] = []
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, '{"id": 77, "conclusion": "failure"}', ""),
            subprocess.CompletedProcess(
                [],
                0,
                '[{"id": 101, "conclusion": "failure", "steps": []}, '
                '{"id": 102, "conclusion": "failure", "steps": []}]',
                "",
            ),
            subprocess.CompletedProcess([], 0, "ordinary failure\n", ""),
            subprocess.CompletedProcess([], 0, "spending limit reached\n", ""),
        ]
    )

    def fake_gh(args, timeout=30):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(module, "_gh_user", fake_gh)
    assert module._runner_admission_observation("example/repo")[0] is True
    assert all("--paginate" in call for call in calls[1:])
    assert "--slurp" in calls[1]

    responses = iter(
        [
            subprocess.CompletedProcess([], 0, '{"id": 77, "conclusion": "failure"}', ""),
            subprocess.CompletedProcess([], 1, "", "unavailable"),
        ]
    )
    assert module._runner_admission_observation("example/repo") == (None, "jobs unreadable")


def test_runner_admission_preserves_executed_step_evidence(monkeypatch) -> None:
    module = _load()
    responses = iter(
        [
            subprocess.CompletedProcess([], 0, '{"id": 77, "conclusion": "failure"}', ""),
            subprocess.CompletedProcess(
                [],
                0,
                '[{"id": 101, "conclusion": "failure", "steps": [{"name": "pytest"}]}]',
                "",
            ),
            subprocess.CompletedProcess([], 0, "spending limit reached\n", ""),
        ]
    )
    monkeypatch.setattr(module, "_gh_user", lambda *_args, **_kwargs: next(responses))
    present, detail = module._runner_admission_observation("example/repo")
    assert present is False
    assert "without the matching admission annotation" in detail


def test_usage_strict_prefers_unreadable_admission_over_budget_failure(tmp_path, monkeypatch, capsys) -> None:
    module = _load()
    monkeypatch.setattr(module.shutil, "which", lambda _command: "/usr/bin/gh")
    monkeypatch.setattr(module, "owners", lambda _estate: ["organvm"])
    monkeypatch.setattr(
        module,
        "_usage_month",
        lambda *_args: {"by_product": {"actions": {"net_usd": 100.0}}, "net_usd_total": 100.0},
    )
    monkeypatch.setattr(module, "_runner_admission_observation", lambda _repo: (None, "jobs unreadable"))
    monkeypatch.setattr(module, "USAGE_DOC", tmp_path / "usage.json")
    monkeypatch.setattr(module, "USAGE_STAMP", tmp_path / "usage-stamp.json")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    assert module.usage({}, check=True, print_json=False, strict=True) == 77
    assert "observation unreadable" in capsys.readouterr().out


def test_usage_reports_provider_admission_text_without_account_diagnosis(tmp_path, monkeypatch, capsys) -> None:
    module = _load()
    monkeypatch.setattr(module.shutil, "which", lambda _command: "/usr/bin/gh")
    monkeypatch.setattr(module, "owners", lambda _estate: ["organvm"])
    monkeypatch.setattr(
        module,
        "_usage_month",
        lambda *_args: {"by_product": {"actions": {"net_usd": 0.0}}, "net_usd_total": 0.0},
    )
    monkeypatch.setattr(
        module,
        "_runner_admission_observation",
        lambda _repo: (True, "provider billing-related admission annotation present; cause unverified"),
    )
    monkeypatch.setattr(module, "USAGE_DOC", tmp_path / "usage.json")
    monkeypatch.setattr(module, "USAGE_STAMP", tmp_path / "usage-stamp.json")
    monkeypatch.setattr(module, "ROOT", tmp_path)

    assert module.usage({}, check=True, print_json=False) == 1
    output = capsys.readouterr().out.lower()
    assert "account cause and remediation are unverified" in output
    assert "account is locked" not in output
    doc = json.loads(module.USAGE_DOC.read_text(encoding="utf-8"))
    observation = doc["runner_admission_observation"]
    assert observation["annotation_present"] is True
    assert observation["account_cause_verified"] is False
    assert observation["remediation_verified"] is False


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


def test_owner_repos_preserves_successful_empty_owner(monkeypatch) -> None:
    module = _load()
    calls: list[list[str]] = []

    def fake_gh(args, _token, timeout=60):
        calls.append(args)
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr(module, "_gh", fake_gh)

    assert module._owner_repos("empty-owner", "opaque") == []
    assert len(calls) == 1


def test_owner_repos_keeps_failures_distinct_from_empty_success(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(
        module,
        "_gh",
        lambda _args, _token, timeout=60: subprocess.CompletedProcess([], 1, "", "unavailable"),
    )

    assert module._owner_repos("unavailable-owner", "opaque") is None


def test_owner_repos_fails_closed_on_malformed_success(monkeypatch) -> None:
    module = _load()
    monkeypatch.setattr(
        module,
        "_gh",
        lambda _args, _token, timeout=60: subprocess.CompletedProcess([], 0, "not-json\n", ""),
    )

    assert module._owner_repos("malformed-owner", "opaque") is None


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
                                "isArchived": True,
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
                                "isArchived": False,
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
    assert inventory["repositories"][0]["archived"] is True
    assert inventory["repositories"][0]["open_pr_total"] == 1001
    assert "isArchived" in calls[0][3]
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
    routed = module._classify_open_pr(
        "example/repo",
        {
            **base,
            "updatedAt": "2026-07-01T00:00:00Z",
            "labels": {"nodes": [{"name": "lifecycle:delivery"}]},
        },
        policy,
        now,
    )
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
    assert active["lifecycle_complete"] is False
    assert active["lifecycle_disposition"] is None
    assert routed["classification"] == "owner_route"
    assert routed["lifecycle_disposition"] == "lifecycle:delivery"
    assert routed["lifecycle_complete"] is True
    assert routed["exact_head_owner"]["head_oid"] == "a" * 40
    assert routed["predicate"].endswith("@" + "a" * 40)
    assert "merge-queue" in routed["merge_condition"]
    assert preserved["classification"] == "preservation"
    assert preserved["lifecycle_disposition"] == "lifecycle:preservation"
    assert preserved["lifecycle_disposition_source"] == "legacy-preservation-marker"


def test_pr_lifecycle_conflicts_and_unowned_supersession_fail_closed() -> None:
    module = _load()
    now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    base = {
        "number": 8,
        "url": "https://example.invalid/pull/8",
        "title": "work",
        "isDraft": False,
        "updatedAt": "2026-07-21T11:00:00Z",
        "headRefName": "topic",
        "headRefOid": "b" * 40,
        "body": "",
        "author": {"login": "owner"},
        "assignees": {"nodes": []},
    }
    conflicting = module._classify_open_pr(
        "example/repo",
        {
            **base,
            "labels": {
                "nodes": [
                    {"name": "lifecycle:delivery"},
                    {"name": "lifecycle:blocked"},
                ]
            },
        },
        {},
        now,
    )
    superseded = module._classify_open_pr(
        "example/repo",
        {
            **base,
            "labels": {"nodes": [{"name": "lifecycle:superseded"}]},
        },
        {},
        now,
    )
    held = module._classify_open_pr(
        "example/repo",
        {
            **base,
            "body": "Superseded by: example/repo#9",
            "labels": {"nodes": [{"name": "lifecycle:superseded"}]},
        },
        {},
        now,
    )

    assert conflicting["lifecycle_disposition"] is None
    assert conflicting["lifecycle_disposition_source"] == "conflicting-labels"
    assert conflicting["lifecycle_complete"] is False
    assert superseded["lifecycle_debt_reasons"] == ["missing-supersession-target"]
    assert held["supersession_target"] == "example/repo#9"
    assert held["lifecycle_complete"] is True


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
    assert redacted["head_oid"] is None
    assert redacted["exact_head_owner"] is None
    assert redacted["predicate"] is None
    assert redacted["receipt_target"] is None
    assert redacted["merge_condition"] is None
    assert redacted["dependencies"] is None
    assert redacted["supersession_target"] is None
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
    assert full["classification_untyped_count"] == 0
    assert full["lifecycle_untyped_count"] == 1
    assert full["untyped_count"] == 1
    assert full["lifecycle_disposition_counts"] == {"untyped": 1}
    assert tracked["cursor_reconciliation"]["failure_count"] == 0


def test_archived_repository_owns_missing_disposition_as_blocked() -> None:
    module = _load()
    row = {
        "private": False,
        "lifecycle_disposition": None,
        "lifecycle_disposition_source": "missing-label",
        "lifecycle_label_matches": [],
        "exact_head_owner": {"owner": "owner", "head_oid": "a" * 40},
        "lifecycle_debt_reasons": ["missing-or-conflicting-lifecycle-disposition"],
        "lifecycle_complete": False,
    }

    result = module._apply_repository_state(
        row,
        {"private": False, "archived": True},
    )

    assert result["lifecycle_disposition"] == "lifecycle:blocked"
    assert result["lifecycle_disposition_source"] == "repository-archived-immutable"
    assert result["lifecycle_debt_reasons"] == []
    assert result["lifecycle_complete"] is True


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


def test_custody_drift_flags_live_partnered_product_org_side() -> None:
    module = _load()
    ledger = ["peer-audited--behavioral-blockchain", "hokage-chess"]
    grants = {
        "organvm/peer-audited--behavioral-blockchain": [{"login": "jt", "role": "push"}],
        "organvm/hokage-chess": [{"login": "rb", "role": "push"}],
    }
    by_repo = {
        "organvm/peer-audited--behavioral-blockchain": {"outside": [{"login": "jt", "role": "push"}]},
        "organvm/hokage-chess": {"outside": []},  # staged, never sent — class N's cite, not custody drift
    }

    drifts = module.custody_drift(ledger, grants, by_repo, {"organvm"})

    assert len(drifts) == 1
    assert "peer-audited--behavioral-blockchain" in drifts[0]
    assert "jt" in drifts[0]


def test_owners_enumerates_declared_shelf_orgs() -> None:
    module = _load()
    estate = {
        "classes": {"g": {"match": ["organvm/**"]}},
        "shelf_assignments": {"shelves": {"organvm-iii-ergon": ["mesh"]}},
    }

    assert module.owners(estate) == ["organvm", "organvm-iii-ergon"]


def test_shelf_drift_reports_both_directions_and_absences() -> None:
    module = _load()
    shelves = {"organvm-iii-ergon": ["mesh", "prima", "ghost-repo"]}
    rows = [
        {"full_name": "organvm-iii-ergon/mesh"},  # declared + placed — clean
        {"full_name": "organvm/prima"},  # declared but still org-side — transfer owed
        {"full_name": "organvm-iii-ergon/squatter"},  # undeclared in the shelf org
        {"full_name": "organvm/limen"},  # unrelated engine-room repo — silent
    ]

    drifts = module.shelf_drift(shelves, rows)

    assert any("ghost-repo" in d and "absent" in d for d in drifts)
    assert any(d.startswith("prima: declared shelf organvm-iii-ergon") for d in drifts)
    assert any("squatter" in d and "undeclared" in d for d in drifts)
    assert len(drifts) == 3


def test_shelf_drift_clean_when_declared_matches_census() -> None:
    module = _load()
    shelves = {"organvm-iii-ergon": ["mesh"]}
    rows = [{"full_name": "organvm-iii-ergon/mesh"}, {"full_name": "organvm/limen"}]

    assert module.shelf_drift(shelves, rows) == []


def test_custody_drift_ignores_personal_estate_undeclared_and_unreadable() -> None:
    module = _load()
    ledger = ["victoroff-os", "mesh", "prima"]
    grants = {"4444J99/victoroff-os": [{"login": "dv", "role": "push"}]}
    by_repo = {
        "4444J99/victoroff-os": {"outside": [{"login": "dv", "role": "push"}]},  # personal — right home
        "organvm/mesh": {"outside": [{"login": "stranger", "role": "push"}]},  # undeclared — class N's
        "organvm/prima": {"outside": None},  # unreadable roll — custody never guesses
    }

    assert module.custody_drift(ledger, grants, by_repo, {"organvm"}) == []


def test_permission_over_grant_flags_unlisted_repo_and_over_rank_only() -> None:
    module = _load()
    personal_full = {
        "4444J99/victoroff-os": [{"login": "dv", "role": "admin"}],  # probed — class N's finding
        "4444J99/mystery-repo": [{"login": "stranger", "role": "read"}],  # unlisted in ACCESS
        "4444J99/hokage-chess": [{"login": "jt", "role": "admin"}],  # over declared push
        "4444J99/micro-tato-play": [{"login": "rb", "role": "write"}],  # equal to declared push
        "4444J99/unreadable": None,  # caller's SKIP, never a guess
    }
    grants = {
        "4444J99/hokage-chess": [{"login": "jt", "role": "push"}],
        "4444J99/micro-tato-play": [{"login": "rb", "role": "push"}],
    }

    drifts = module.permission_over_grant(personal_full, grants, probed={"4444J99/victoroff-os"})

    assert any("mystery-repo" in d and "NO grant row" in d for d in drifts)
    assert any("hokage-chess" in d and "exceeds declared" in d for d in drifts)
    assert not any("victoroff-os" in d for d in drifts)
    assert not any("micro-tato-play" in d for d in drifts)
    assert len(drifts) == 2


def test_posture_window_is_deterministic_and_cycles_full_coverage() -> None:
    module = _load()
    eligible = [f"o/r{i}" for i in range(7)]

    assert module.posture_window(eligible, 3, 100) == module.posture_window(eligible, 3, 100)
    assert module.posture_window(eligible, 10, 5) == sorted(eligible)  # window ≥ n probes all
    assert module.posture_window([], 3, 1) == []
    covered: set[str] = set()
    for ordinal in range(4):  # ceil(7/3) = 3 rotations cover everything; 4 is safety margin
        covered |= set(module.posture_window(eligible, 3, ordinal))
    assert covered == set(eligible)


def test_visibility_drift_cites_ungated_public_candidate_instead_of_silence() -> None:
    module = _load()
    estate = {
        "classes": {"operation_private": {"match": [], "visibility": "private"}},
        "repo_overrides": {
            "4444J99/micro-tato": {"class": "operation_private", "publish_candidate": True},
            "4444J99/mirror-mirror": {"class": "operation_private", "publish_candidate": True},
        },
    }
    rows = [
        {"full_name": "4444J99/micro-tato", "private": False},  # candidate riding public un-gated
        {"full_name": "4444J99/mirror-mirror", "private": True},  # candidate at resting posture
    ]

    fails, cites = module.visibility_drift(rows, estate)

    assert fails == []
    assert any("micro-tato" in c and "observed public" in c for c in cites)
    assert not any("mirror-mirror" in c and "observed public" in c for c in cites)


def test_visibility_drift_receipt_lens_clears_a_swept_public_candidate() -> None:
    """A green+fresh sweep receipt legitimately OWNS the public posture, so the rung must fall
    silent on that repo. Without the lens class G cites all 32 swept-clean publics on every run,
    and a rung that always cites is a rung nobody reads."""
    module = _load()
    estate = {
        "classes": {"operation_private": {"match": [], "visibility": "private"}},
        "repo_overrides": {
            "organvm/swept": {"class": "operation_private", "publish_candidate": True},
            "organvm/unswept": {"class": "operation_private", "publish_candidate": True},
        },
    }
    rows = [
        {"full_name": "organvm/swept", "private": False},
        {"full_name": "organvm/unswept", "private": False},
    ]
    lens = lambda repo: (True, "green+fresh") if repo == "organvm/swept" else (False, "no receipt")  # noqa: E731

    fails, cites = module.visibility_drift(rows, estate, receipt_ok=lens)

    assert fails == []
    assert not any("swept" in c and "unswept" not in c for c in cites), "a receipt-owned public must not be cited"
    assert any("unswept" in c and "no receipt" in c for c in cites)

    # Omitting the lens must stay the over-citing (safe) direction, not silently pass everything.
    _, unlensed = module.visibility_drift(rows, estate)
    assert len(unlensed) == 2


def test_owner_repos_user_scoped_authenticated_owner_sees_private_estate(monkeypatch) -> None:
    module = _load()
    routes: list[str] = []
    lines = "\n".join(
        json.dumps(r)
        for r in [
            {"full_name": "4444J99/mirror-mirror", "private": True},
            {"full_name": "someorg/not-mine", "private": False},  # affiliation row outside the namespace
        ]
    )

    def fake_gh_user(args, timeout=30):
        routes.append(args[1])
        return subprocess.CompletedProcess(args, 0, lines, "")

    monkeypatch.setattr(module, "_gh_user", fake_gh_user)
    monkeypatch.setattr(module, "_gh_login", lambda: "4444J99")

    rows = module._owner_repos("4444J99", None, user_scoped=True)

    assert routes[0] == "/user/repos?affiliation=owner"
    assert [r["full_name"] for r in rows] == ["4444J99/mirror-mirror"]


def test_audience_lens_imports_the_law_instead_of_recopying_it() -> None:
    """Rung Q must DERIVE from check-audience.py, never carry its own copy of the audience law.

    A second copy inside the doctor is exactly the drift every registry in this estate exists to
    prevent — and it would rot in the direction that matters, since the doctor is the thing people
    read. The lens returns the (derive, assess) pair or None; it never stubs an answer.
    """
    module = _load()
    lens = module._audience_lens()
    assert lens is not None, "check-audience.py should be importable from the doctor"
    derive, assess = lens
    assert callable(derive) and callable(assess)


def test_audience_rung_ships_disarmed() -> None:
    """Observable before autonomous: the ratchet stays false until the rung has been quiet."""
    import yaml

    estate = yaml.safe_load(
        (SCRIPT.parent.parent / "institutio" / "github" / "estate.yaml").read_text(encoding="utf-8")
    )
    assert estate["ratchets"]["audience_parity_armed"] is False


def test_audience_rung_never_demands_a_visibility_flip() -> None:
    """`world` is "public, SOLO", so public-AND-granted is a fourth state the enum cannot express —
    NOT drift. If the rung ever read it as drift it would demand a public→private flip of a
    traction repo and sit permanently at war with class G, which reads portal_public and demands
    public. The finding must name the state and stop.
    """
    module = _load()
    derive, assess = module._audience_lens()
    estate = {
        "classes": {"portal_public": {"visibility": "public"}},
        "repo_overrides": {"o/traction": {"class": "portal_public"}},
    }
    access = {"grants": {"o/traction": [{"login": "someone", "role": "push"}]}, "policy": {}}
    breaks, owed = assess(derive(estate, access, {}))

    assert breaks == [], "a deliberate public collaboration is not a structural break"
    assert len(owed) == 1 and "world+guest" in owed[0]
    # Suggesting a private TWIN is the split doctrine and is fine; demanding this repo be flipped
    # or demoted is the thing that would put Q at war with class G forever.
    for verb in ("flip", "demote", "make it private", "should be private"):
        assert verb not in owed[0].lower(), f"the rung must not demand a visibility change ({verb!r})"


def test_parity_accepts_declared_audience_and_rejects_a_bad_value() -> None:
    """`audience` is declared INTENT on the rows where it disagrees with the derivation. Parity
    owns the value; check-audience owns the softer judgments."""
    module = _load()
    base = {
        "classes": {"operation_private": {"visibility": "private"}},
        "resource_types": {},
    }
    ok = module.parity(
        {**base, "repo_overrides": {"o/lane": {"class": "operation_private", "audience": "collab", "why": "w"}}}
    )
    assert not [f for f in ok if "audience" in f]

    bad = module.parity(
        {**base, "repo_overrides": {"o/lane": {"class": "operation_private", "audience": "wrold", "why": "w"}}}
    )
    assert any("audience 'wrold' is not one of" in f for f in bad)


def test_parity_rejects_collab_that_is_also_a_publish_candidate() -> None:
    """A shared operation and a solo publication are contradictory FUTURES, not a soft judgment —
    the one audience combination that is structurally impossible rather than merely unmet."""
    module = _load()
    fails = module.parity(
        {
            "classes": {"operation_private": {"visibility": "private"}},
            "resource_types": {},
            "repo_overrides": {
                "o/lane": {"class": "operation_private", "audience": "collab", "publish_candidate": True, "why": "w"}
            },
        }
    )
    assert any("contradictory futures" in f for f in fails)
