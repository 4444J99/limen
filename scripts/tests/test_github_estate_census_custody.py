"""Custody regressions for the private GitHub estate census receipt."""

from __future__ import annotations

import importlib.util
import json
import stat
import subprocess
import sys
from pathlib import Path


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
        @staticmethod
        def _gh_user(args, timeout):
            assert timeout == 90
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
                            "target": {"oid": tip, "statusCheckRollup": {"state": "SUCCESS"}},
                        },
                    }
                }
            }
            return subprocess.CompletedProcess([], 0, json.dumps(payload), "")

    result = MODULE._metadata(Gitvs(), "organvm/limen")

    assert result is not None
    assert result["default_sha"] == tip
    assert result["default_check_status"] == "no_required_checks"


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
                    "requiredStatusChecks": [{"context": "pr-gate"}],
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
        "error": "classic-required-checks-empty",
    }


def test_repository_without_default_branch_has_complete_not_applicable_check_policy():
    policy = MODULE._required_check_policy({}, None)

    assert policy == {
        "status": "not_applicable",
        "complete": True,
        "required_check_count": 0,
        "required_check_contexts": [],
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
