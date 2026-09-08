"""Custody regressions for the private GitHub estate census receipt."""

from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("github_estate_census", ROOT / "scripts" / "github-estate-census.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_private_receipt_replaces_permissive_file_with_owner_only_mode(tmp_path: Path):
    target = tmp_path / "private-census.json"
    target.write_text("stale", encoding="utf-8")
    target.chmod(0o644)

    MODULE._write_private_json(target, {"private_rows": 79})

    assert _mode(target) == 0o600
    assert json.loads(target.read_text(encoding="utf-8")) == {"private_rows": 79}


def test_private_receipt_replaces_symlink_without_touching_its_target(tmp_path: Path):
    external = tmp_path / "external.json"
    external.write_text("unchanged", encoding="utf-8")
    target = tmp_path / "private-census.json"
    target.symlink_to(external)

    MODULE._write_private_json(target, {"private_rows": 79})

    assert not target.is_symlink()
    assert _mode(target) == 0o600
    assert external.read_text(encoding="utf-8") == "unchanged"


def test_repository_only_check_accepts_complete_denominator_with_partial_leaf_connections(monkeypatch):
    full = {
        "source_report": {
            "exhaustive": False,
            "cursor": {
                "repository": {
                    "exhaustive": True,
                    "expected_total": 314,
                    "known_count": 314,
                }
            },
        }
    }
    tracked = {"summary": {"repository_count": 314}}
    monkeypatch.setattr(MODULE, "collect", lambda **_kwargs: (full, tracked))
    monkeypatch.setattr(sys, "argv", ["github-estate-census.py", "--check-repositories", "--json"])

    assert MODULE.main() == 0


def test_repository_only_check_rejects_incomplete_denominator(monkeypatch):
    full = {
        "source_report": {
            "exhaustive": False,
            "cursor": {
                "repository": {
                    "exhaustive": True,
                    "expected_total": 314,
                    "known_count": 313,
                }
            },
        }
    }
    tracked = {"summary": {"repository_count": 313}}
    monkeypatch.setattr(MODULE, "collect", lambda **_kwargs: (full, tracked))
    monkeypatch.setattr(sys, "argv", ["github-estate-census.py", "--check-repositories", "--json"])

    assert MODULE.main() == 1


def test_metadata_carries_live_default_commit_oid_into_generation_input():
    tip = "a" * 40

    class Gitvs:
        attempts = 0

        @classmethod
        def _gh_user(cls, args, timeout):
            assert timeout == 90
            cls.attempts += 1
            if cls.attempts == 1:
                return subprocess.CompletedProcess(
                    [],
                    1,
                    json.dumps(
                        {
                            "errors": [
                                {
                                    "message": "API rate limit exceeded",
                                    "extensions": {"code": "RATE_LIMITED"},
                                }
                            ]
                        }
                    ),
                    "",
                )
            payload = {
                "data": {
                    "repository": {
                        "id": "repository-node",
                        "nameWithOwner": "organvm/limen",
                        "isPrivate": False,
                        "issues": {"totalCount": 0},
                        "refs": {"totalCount": 1},
                        "branchProtectionRules": {
                            "totalCount": 0,
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        },
                        "rulesets": {
                            "totalCount": 0,
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        },
                        "defaultBranchRef": {
                            "name": "main",
                            "target": {
                                "oid": tip,
                                "statusCheckRollup": {"contexts": {"totalCount": 1}},
                            },
                        },
                    }
                }
            }
            return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    result = MODULE._metadata(Gitvs(), "organvm/limen")

    assert result is not None
    assert Gitvs.attempts == 2
    assert result["default_sha"] == tip
    assert result["default_check_status"] == "no_required_checks"


def test_github_api_error_classifier_separates_permanent_query_errors():
    result = subprocess.CompletedProcess(
        [],
        1,
        json.dumps(
            {
                "errors": [
                    {
                        "message": "Field 'missing' doesn't exist on type 'Repository'",
                        "extensions": {"code": "undefinedField"},
                    }
                ]
            }
        ),
        "",
    )

    error_class = MODULE._github_api_error_class(result)

    assert error_class == "github-query-invalid"
    assert MODULE._github_retry_class(error_class) == "permanent"


def test_required_check_policy_needs_both_effective_rules_and_classic_protection():
    repository = {
        "id": "repository-node",
        "nameWithOwner": "4444J99/limen",
        "isPrivate": False,
        "branchProtectionRules": {
            "totalCount": 1,
            "nodes": [
                {
                    "pattern": "main",
                    "requiresStatusChecks": True,
                    "requiredStatusCheckContexts": ["python", "worker"],
                    "requiredStatusChecks": [],
                }
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": "classic"},
        },
        "rulesets": {
            "totalCount": 1,
            "nodes": [
                {
                    "enforcement": "ACTIVE",
                    "target": "BRANCH",
                    "conditions": {
                        "refName": {"include": ["~DEFAULT_BRANCH"], "exclude": []},
                        "repositoryName": None,
                        "repositoryId": None,
                        "organizationProperty": None,
                        "repositoryProperty": None,
                    },
                    "rules": {
                        "totalCount": 1,
                        "nodes": [
                            {
                                "type": "REQUIRED_STATUS_CHECKS",
                                "parameters": {
                                    "__typename": "RequiredStatusChecksParameters",
                                    "requiredStatusChecks": [{"context": "pr-gate"}],
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": "rule"},
                    },
                }
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": "ruleset"},
        },
    }

    policy = MODULE._required_check_policy(repository, "main")

    assert policy == {
        "status": "required_checks",
        "complete": True,
        "required_check_count": 3,
        "required_check_contexts": ["pr-gate", "python", "worker"],
        "required_check_requirements": [
            {"kind": "context", "context": "pr-gate", "app_id": None},
            {"kind": "context", "context": "python", "app_id": None},
            {"kind": "context", "context": "worker", "app_id": None},
        ],
        "error": None,
    }


def test_required_check_policy_reads_app_bound_classic_check_descriptions():
    repository = {
        "id": "repository-node",
        "nameWithOwner": "4444J99/limen",
        "isPrivate": False,
        "branchProtectionRules": {
            "totalCount": 1,
            "nodes": [
                {
                    "pattern": "main",
                    "requiresStatusChecks": True,
                    "requiredStatusCheckContexts": [],
                    "requiredStatusChecks": [{"context": "pr-gate", "app": {"databaseId": 15368}}],
                }
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": "classic"},
        },
        "rulesets": {
            "totalCount": 0,
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
    }

    policy = MODULE._required_check_policy(repository, "main")

    assert policy["status"] == "required_checks"
    assert policy["complete"] is True
    assert policy["required_check_contexts"] == ["pr-gate"]
    assert policy["required_check_requirements"] == [{"kind": "context", "context": "pr-gate", "app_id": 15368}]


def test_empty_enabled_classic_check_policy_is_complete_but_invalid():
    repository = {
        "id": "repository-node",
        "nameWithOwner": "4444J99/limen",
        "isPrivate": False,
        "branchProtectionRules": {
            "totalCount": 1,
            "nodes": [
                {
                    "pattern": "main",
                    "requiresStatusChecks": True,
                    "requiredStatusCheckContexts": [],
                    "requiredStatusChecks": [],
                }
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": "classic"},
        },
        "rulesets": {
            "totalCount": 0,
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
    }

    policy = MODULE._required_check_policy(repository, "main")

    assert policy == {
        "status": "invalid_required_checks",
        "complete": True,
        "required_check_count": 0,
        "required_check_contexts": [],
        "required_check_requirements": [],
        "error": "classic-required-checks-empty",
    }


def test_repository_without_default_branch_has_complete_not_applicable_check_policy():
    policy = MODULE._required_check_policy({}, None)

    assert policy == {
        "status": "not_applicable",
        "complete": True,
        "required_check_count": 0,
        "required_check_contexts": [],
        "required_check_requirements": [],
        "error": None,
    }


def test_required_check_policy_never_promotes_incomplete_pagination_to_no_checks():
    repository = {
        "id": "repository-node",
        "nameWithOwner": "4444J99/limen",
        "isPrivate": False,
        "branchProtectionRules": {
            "totalCount": 0,
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
        "rulesets": {
            "totalCount": 101,
            "nodes": [
                {
                    "enforcement": "ACTIVE",
                    "target": "BRANCH",
                    "conditions": {"refName": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
                    "rules": {
                        "totalCount": 1,
                        "nodes": [
                            {
                                "type": "REQUIRED_STATUS_CHECKS",
                                "parameters": {
                                    "__typename": "RequiredStatusChecksParameters",
                                    "requiredStatusChecks": [{"context": "pr-gate"}],
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": "rule"},
                    },
                }
            ],
            "pageInfo": {"hasNextPage": True, "endCursor": "ruleset"},
        },
    }

    policy = MODULE._required_check_policy(repository, "main")

    assert policy["status"] == "unknown"
    assert policy["complete"] is False
    assert policy["error"] == "default-check-policy-pagination-incomplete"


def test_required_check_policy_fails_closed_for_unobservable_property_condition():
    repository = {
        "id": "repository-node",
        "nameWithOwner": "4444J99/limen",
        "isPrivate": False,
        "branchProtectionRules": {
            "totalCount": 0,
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
        "rulesets": {
            "totalCount": 1,
            "nodes": [
                {
                    "enforcement": "ACTIVE",
                    "target": "BRANCH",
                    "conditions": {
                        "refName": {"include": ["~DEFAULT_BRANCH"], "exclude": []},
                        "repositoryProperty": {"include": ["tier:critical"], "exclude": []},
                    },
                    "rules": {
                        "totalCount": 1,
                        "nodes": [
                            {
                                "type": "REQUIRED_STATUS_CHECKS",
                                "parameters": {
                                    "__typename": "RequiredStatusChecksParameters",
                                    "requiredStatusChecks": [{"context": "pr-gate"}],
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": "rule"},
                    },
                }
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": "ruleset"},
        },
    }

    policy = MODULE._required_check_policy(repository, "main")

    assert policy["status"] == "unknown"
    assert policy["complete"] is False
    assert policy["error"] == "ruleset-condition-unsupported"


def _at_default(nodes):
    return tuple({"head_oid": "a" * 40, **node} for node in nodes)


def _required_policy(*requirements):
    return {
        "status": "required_checks",
        "complete": True,
        "required_check_requirements": list(requirements),
    }


def test_required_check_status_ignores_advisory_failures():
    policy = _required_policy({"kind": "context", "context": "test", "app_id": None})
    nodes = (
        {"id": "required", "name": "test", "state": "SUCCESS", "observed_at": "2026-08-27T12:00:00Z"},
        {"id": "advisory", "name": "CodeQL", "state": "FAILURE", "observed_at": "2026-08-27T12:01:00Z"},
    )

    assert MODULE._required_check_status(policy, _at_default(nodes), default_sha="a" * 40) == "green"


def test_required_check_status_rejects_required_failure():
    policy = _required_policy({"kind": "context", "context": "test", "app_id": None})
    nodes = ({"id": "required", "name": "test", "state": "FAILURE", "observed_at": "2026-08-27T12:00:00Z"},)

    assert MODULE._required_check_status(policy, _at_default(nodes), default_sha="a" * 40) == "red"


def test_required_check_status_treats_missing_requirement_as_pending():
    policy = _required_policy({"kind": "context", "context": "test", "app_id": None})

    assert MODULE._required_check_status(policy, (), default_sha="a" * 40) == "pending"


def test_required_check_status_honors_app_binding_and_latest_observation():
    policy = _required_policy({"kind": "context", "context": "test", "app_id": 15368})
    nodes = (
        {
            "id": "wrong-app",
            "name": "test",
            "app_id": 7,
            "state": "SUCCESS",
            "observed_at": "2026-08-27T12:02:00Z",
        },
        {
            "id": "old-required",
            "name": "test",
            "app_id": 15368,
            "state": "FAILURE",
            "observed_at": "2026-08-27T12:00:00Z",
        },
        {
            "id": "new-required",
            "name": "test",
            "app_id": 15368,
            "state": "SUCCESS",
            "observed_at": "2026-08-27T12:01:00Z",
        },
    )

    assert MODULE._required_check_status(policy, _at_default(nodes), default_sha="a" * 40) == "green"


def test_required_workflow_uses_latest_run_suite_result():
    policy = _required_policy(
        {"kind": "workflow", "path": ".github/workflows/pr-gate.yml", "repository_id": 77, "ref": "refs/heads/main"}
    )
    nodes = (
        {
            "id": "old",
            "name": "test",
            "state": "SUCCESS",
            "observed_at": "2026-08-27T12:00:00Z",
            "suite_conclusion": "SUCCESS",
            "workflow_run_id": 1,
            "workflow_run_updated_at": "2026-08-27T12:00:00Z",
            "workflow_resource_path": "/4444J99/limen/actions/workflows/pr-gate.yml",
            "workflow_repository_id": 77,
            "workflow_path": ".github/workflows/pr-gate.yml",
            "workflow_source_revision": "refs/heads/main",
        },
        {
            "id": "new",
            "name": "test",
            "state": "FAILURE",
            "observed_at": "2026-08-27T12:05:00Z",
            "suite_conclusion": "FAILURE",
            "workflow_run_id": 2,
            "workflow_run_updated_at": "2026-08-27T12:05:00Z",
            "workflow_resource_path": "/4444J99/limen/actions/workflows/pr-gate.yml",
            "workflow_repository_id": 77,
            "workflow_path": ".github/workflows/pr-gate.yml",
            "workflow_source_revision": "refs/heads/main",
        },
    )

    assert MODULE._required_check_status(policy, _at_default(nodes), default_sha="a" * 40) == "red"


def test_no_required_check_policy_ignores_advisory_failures():
    policy = {"status": "no_required_checks", "complete": True, "required_check_requirements": []}
    nodes = ({"id": "advisory", "name": "CodeQL", "state": "FAILURE"},)

    assert MODULE._required_check_status(policy, _at_default(nodes), default_sha="a" * 40) == "no_required_checks"


def _check_payload(tip, *, source_repo="organvm/repo", source_ref="refs/heads/main"):
    return {
        "data": {
            "repository": {
                "databaseId": 77,
                "nameWithOwner": "organvm/repo",
                "target": {
                    "oid": tip,
                    "statusCheckRollup": {
                        "connection": {
                            "totalCount": 2,
                            "nodes": [
                                {
                                    "__typename": "CheckRun",
                                    "id": "check",
                                    "name": "test",
                                    "status": "COMPLETED",
                                    "conclusion": "SUCCESS",
                                    "checkSuite": {
                                        "id": "suite",
                                        "status": "COMPLETED",
                                        "conclusion": "SUCCESS",
                                        "app": {"databaseId": 15368},
                                        "workflowRun": {
                                            "databaseId": 42,
                                            "file": {
                                                "path": ".github/workflows/ci.yml",
                                                "repositoryName": source_repo,
                                                "repositoryFileUrl": f"https://github.com/{source_repo}/blob/{source_ref}/.github/workflows/ci.yml",
                                            },
                                            "workflow": {"name": "CI", "resourcePath": "/o/r/actions/workflows/ci.yml"},
                                        },
                                    },
                                },
                                {
                                    "__typename": "StatusContext",
                                    "id": "status",
                                    "context": "external",
                                    "state": "PENDING",
                                    "creator": {"login": "bot"},
                                },
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    },
                },
            }
        }
    }


def test_remote_check_page_normalizes_check_runs_and_status_contexts():
    tip = "b" * 40

    class Gitvs:
        @staticmethod
        def _gh_user(args, timeout):
            assert timeout == 90
            assert "target:object(oid:$commit)" in args[3]
            assert "defaultBranchRef" not in args[3]
            assert f"commit={tip}" in args
            return subprocess.CompletedProcess([], 0, json.dumps(_check_payload(tip)), "")

    page = MODULE._remote_page(Gitvs(), "organvm/repo", "checks", None, default_sha=tip)
    assert page["total_count"] == 2
    assert page["has_next_page"] is False
    assert page["nodes"][0]["head_oid"] == tip
    assert page["nodes"][0]["app_id"] == 15368
    assert page["nodes"][0]["workflow_run_id"] == 42
    assert page["nodes"][0]["workflow_repository_id"] == 77
    assert page["nodes"][0]["workflow_source_revision"] == "refs/heads/main"
    assert page["nodes"][1]["name"] == "external"
    assert page["nodes"][1]["creator_login"] == "bot"


def test_check_page_rejects_same_count_successes_for_a_different_default_head():
    class Gitvs:
        @staticmethod
        def _gh_user(args, timeout):
            return subprocess.CompletedProcess([], 0, json.dumps(_check_payload("b" * 40)), "")

    with pytest.raises(ValueError, match="default-check-head-mismatch"):
        MODULE._remote_page(Gitvs(), "organvm/repo", "checks", None, default_sha="a" * 40)


@pytest.mark.parametrize("head", [None, "b" * 40])
def test_required_status_rejects_missing_or_wrong_default_head(head):
    policy = _required_policy({"kind": "context", "context": "test", "app_id": None})
    nodes = ({"id": "check", "name": "test", "state": "SUCCESS", "head_oid": head},)
    assert MODULE._required_check_status(policy, nodes, default_sha="a" * 40) == "unknown"


def _workflow_repository(workflows):
    def connection(nodes):
        return {"nodes": nodes, "totalCount": len(nodes), "pageInfo": {"hasNextPage": False}}

    return {
        "branchProtectionRules": connection([]),
        "rulesets": connection(
            [
                {
                    "enforcement": "ACTIVE",
                    "target": "BRANCH",
                    "conditions": {},
                    "rules": connection([{"type": "WORKFLOWS", "parameters": {"workflows": workflows}}]),
                }
            ]
        ),
    }


def test_required_workflow_policy_keeps_distinct_source_repositories_and_refs():
    workflows = [
        {"path": ".github/workflows/ci.yml", "repositoryId": repo, "ref": ref, "sha": None}
        for repo, ref in ((7, "refs/heads/main"), (8, "refs/heads/main"), (7, "refs/tags/v2"))
    ]
    policy = MODULE._required_check_policy(_workflow_repository(workflows), "main")
    assert policy["required_check_count"] == 3
    assert {(r["repository_id"], r["ref"]) for r in policy["required_check_requirements"]} == {
        (7, "refs/heads/main"),
        (8, "refs/heads/main"),
        (7, "refs/tags/v2"),
    }


@pytest.mark.parametrize(
    "workflow",
    [
        {"path": ".github/workflows/ci.yml"},
        {"path": ".github/workflows/ci.yml", "repositoryId": 7},
        {"path": ".github/workflows/ci.yml", "repositoryId": True, "ref": "main"},
    ],
)
def test_required_workflow_policy_fails_closed_without_source_identity(workflow):
    policy = MODULE._required_check_policy(_workflow_repository([workflow]), "main")
    assert policy["status"] == "unknown"
    assert policy["complete"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"workflow_repository_id": 8},
        {"workflow_repository_id": None},
        {"workflow_source_revision": "refs/heads/other"},
        {"workflow_source_revision": None},
        {"workflow_path": "another/ci.yml"},
    ],
)
def test_required_workflow_rejects_success_with_wrong_or_missing_source(changes):
    requirement = {"kind": "workflow", "path": ".github/workflows/ci.yml", "repository_id": 7, "ref": "refs/heads/main"}
    node = {
        "id": "check",
        "head_oid": "a" * 40,
        "name": "test",
        "state": "SUCCESS",
        "suite_conclusion": "SUCCESS",
        "workflow_run_id": 1,
        "workflow_repository_id": 7,
        "workflow_path": requirement["path"],
        "workflow_source_revision": requirement["ref"],
    }
    policy = _required_policy(requirement)
    assert MODULE._required_check_status(policy, (node,), default_sha="a" * 40) == "green"
    assert MODULE._required_check_status(policy, ({**node, **changes},), default_sha="a" * 40) == "pending"


def test_workflow_source_repository_is_resolved_independently_of_check_target():
    calls = []

    class Gitvs:
        @staticmethod
        def _gh_user(args, timeout):
            calls.append(args)
            payload = (
                {"id": 99, "full_name": "source/policy"}
                if args[1] == "repos/source/policy"
                else _check_payload("a" * 40, source_repo="source/policy", source_ref="b" * 40)
            )
            return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    page = MODULE._remote_page(Gitvs(), "organvm/repo", "checks", None, default_sha="a" * 40)
    node = page["nodes"][0]
    requirement = {"kind": "workflow", "path": ".github/workflows/ci.yml", "repository_id": 99, "sha": "b" * 40}
    assert node["workflow_repository_id"] == 99
    assert MODULE._required_check_status(_required_policy(requirement), (node,), default_sha="a" * 40) == "green"
    assert len(calls) == 2


def test_write_refuses_to_replace_tracked_receipts_with_partial_data(tmp_path: Path, monkeypatch):
    source_report = tmp_path / "source.json"
    private_facts = tmp_path / "private.json"
    tracked_ledger = tmp_path / "tracked.json"
    baseline = tmp_path / "baseline.json"
    tracked_ledger.write_text("tracked-sentinel\n", encoding="utf-8")
    baseline.write_text("baseline-sentinel\n", encoding="utf-8")
    full = {
        "source_report": {
            "exhaustive": False,
            "cursor": {"repository": {"exhaustive": True, "expected_total": 1, "known_count": 1}},
        }
    }
    tracked = {
        "summary": {
            "repository_count": 1,
            "known_leaf_count": 0,
            "failure_count": 1,
        }
    }
    monkeypatch.setattr(MODULE, "SOURCE_REPORT", source_report)
    monkeypatch.setattr(MODULE, "PRIVATE_FACTS", private_facts)
    monkeypatch.setattr(MODULE, "TRACKED_LEDGER", tracked_ledger)
    monkeypatch.setattr(MODULE, "UNIVERSE_BASELINE_RECEIPT", baseline)
    monkeypatch.setattr(MODULE, "collect", lambda **_kwargs: (full, tracked))
    monkeypatch.setattr(sys, "argv", ["github-estate-census.py", "--write"])

    assert MODULE.main() == 1
    assert tracked_ledger.read_text(encoding="utf-8") == "tracked-sentinel\n"
    assert baseline.read_text(encoding="utf-8") == "baseline-sentinel\n"
    assert source_report.exists()
    assert private_facts.exists()


@pytest.mark.parametrize("observed_head,expected_status", [("a" * 40, "green"), ("b" * 40, "unknown")])
def test_collect_binds_commit_and_preserves_recomputable_connection_generation(
    monkeypatch, observed_head, expected_status
):
    from types import SimpleNamespace

    repo = "owner/repo"
    metadata = {
        "issues": 0,
        "branches": 1,
        "check_total": 1,
        "default_branch": "main",
        "default_sha": "a" * 40,
        "default_check_policy": "required_checks",
        "required_check_count": 1,
        "default_check_policy_receipt": _required_policy({"kind": "context", "context": "test", "app_id": None}),
    }
    gitvs = SimpleNamespace(
        load_estate=lambda: {},
        owners=lambda estate: ["owner"],
        _resolve_owner_login=lambda owner, lane: owner,
        _owner_repo_inventory=lambda owner, lane: {
            "page_count": 1,
            "repositories": [
                {"name_with_owner": repo, "private": False, "open_pr_total": 0},
            ],
        },
    )
    passed_check_heads = []

    def page(gitvs, repository, kind, cursor, *, default_sha=None):
        if kind == "checks":
            passed_check_heads.append(default_sha)
            nodes = [{"id": "check", "name": "test", "state": "SUCCESS", "head_oid": observed_head}]
        else:
            nodes = [{"name": "main", "head_oid": "a" * 40}]
        return {"total_count": 1, "nodes": nodes, "has_next_page": False, "end_cursor": None}

    monkeypatch.delenv("LIMEN_OFFLINE", raising=False)
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: "/mock/gh")
    monkeypatch.setattr(MODULE, "_gitvs", lambda: gitvs)
    monkeypatch.setattr(MODULE, "_metadata", lambda gitvs, repository: metadata)
    monkeypatch.setattr(MODULE, "_remote_page", page)
    monkeypatch.setattr(MODULE, "_load_cursor_cache", lambda generation: ("1" * 64, {}))
    monkeypatch.setattr(MODULE, "_write_cursor_cache", lambda *args, **kwargs: None)
    local = {"summary": {"failure_count": 0}, "roots": []}
    monkeypatch.setattr(MODULE, "collect_local_git_census", lambda *args, **kwargs: (local, local))

    full, _ = MODULE.collect(workers=1)

    repository = full["repositories"][0]
    assert passed_check_heads == [metadata["default_sha"]]
    assert repository["default_check_status"] == expected_status
    inputs = repository["connection_generation_inputs"]
    assert inputs["source_generation"] == full["source_report"]["source_generation"]
    assert inputs["default_sha"] == metadata["default_sha"]
    assert repository["connection_totals"] == {"pull_requests": 0, "issues": 0, "branches": 1, "checks": 1}
    assert MODULE._canonical_sha256(inputs) == repository["connection_generation"]
    assert all(cursor["source_generation"] == repository["connection_generation"] for cursor in full["cursors"])
