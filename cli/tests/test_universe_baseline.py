from __future__ import annotations

import pytest

from limen.github_estate_census import build_github_estate_census
from limen.universe_baseline import build_universe_baseline_receipt


def _remote(*, check_status: str = "green", failures: int = 0):
    source_generation = "1" * 64
    return {
        "source_report": {
            "generated_at": "2026-08-27T12:00:00Z",
            "source_generation": source_generation,
            "cursor": {"repository": {"expected_total": 1}},
        },
        "summary": {"failure_count": failures},
        "repository_receipts": [
            {
                "repository": "owner/repo",
                "complete": True,
                "default_ref": "refs/heads/main",
                "default_sha": "a" * 40,
                "default_check_status": check_status,
            }
        ],
        "cursors": [
            {"kind": "pull_requests", "expected_total": 0, "known_count": 0},
            {"kind": "branches", "expected_total": 1, "known_count": 1},
        ],
        "leaves": [
            {
                "kind": "branch",
                "repository": "owner/repo",
                "name": "main",
                "is_default": True,
                "status": "owned",
            }
        ],
    }


def _local(*, dirty: bool = False):
    return {
        "summary": {"failure_count": 0, "protection_exclusion_count": 0},
        "roots": [
            {
                "repository": "owner/repo",
                "branch": "main",
                "head": "a" * 40,
                "checkout_kind": "primary_clone",
                "protected": False,
                "custody_risk": dirty,
            }
        ],
    }


def test_complete_baseline_requires_green_exact_defaults_and_terminal_partitions() -> None:
    receipt = build_universe_baseline_receipt(_remote(), _local())

    assert receipt.repository_denominator == 1
    assert receipt.stable_count == 1
    assert receipt.failure_count == 0
    assert receipt.unaccounted == 0
    assert receipt.complete is True


def test_unknown_no_check_policy_is_not_promoted_to_stable() -> None:
    receipt = build_universe_baseline_receipt(_remote(check_status="unknown"), _local())

    repositories = next(row for row in receipt.partitions if row.kind == "repositories")
    assert receipt.stable_count == 0
    assert repositories.blocked == 1
    assert receipt.complete is False


def test_topic_branches_and_dirty_roots_remain_visible_debt() -> None:
    remote = _remote()
    remote["cursors"][-1] = {"kind": "branches", "expected_total": 2, "known_count": 2}
    remote["leaves"].append(
        {
            "kind": "branch",
            "repository": "owner/repo",
            "name": "topic",
            "is_default": False,
            "status": "debt",
        }
    )

    receipt = build_universe_baseline_receipt(remote, _local(dirty=True))

    branches = next(row for row in receipt.partitions if row.kind == "branches")
    roots = next(row for row in receipt.partitions if row.kind == "local_roots")
    assert branches.unaccounted == 1
    assert roots.blocked == 1
    assert receipt.complete is False


def test_open_owned_pull_request_is_debt_not_automatic_protection() -> None:
    remote = _remote()
    remote["cursors"].insert(0, {"kind": "pull_requests", "expected_total": 1, "known_count": 1})
    remote["leaves"].append(
        {
            "kind": "pull_request",
            "repository": "owner/repo",
            "number": 9,
            "status": "owned",
        }
    )

    receipt = build_universe_baseline_receipt(remote, _local())
    pulls = next(row for row in receipt.partitions if row.kind == "pull_requests")

    assert pulls.protected == 0
    assert pulls.unaccounted == 1
    assert receipt.unique_debt_count == 1


def test_unique_debt_does_not_double_count_a_linked_worktree_or_aggregate_partition() -> None:
    local = _local(dirty=True)
    local["roots"][0]["checkout_kind"] = "linked_worktree"

    receipt = build_universe_baseline_receipt(_remote(), local)
    roots = next(row for row in receipt.partitions if row.kind == "local_roots")
    worktrees = next(row for row in receipt.partitions if row.kind == "worktrees")
    dispositions = next(row for row in receipt.partitions if row.kind == "terminal_dispositions")

    assert roots.blocked == 1
    assert worktrees.blocked == 1
    assert dispositions.blocked == 1
    assert receipt.unique_debt_count == 1
    assert receipt.unaccounted == 1


def test_observation_completeness_is_separate_from_lifecycle_closure() -> None:
    remote = _remote()
    remote["cursors"][-1] = {"kind": "branches", "expected_total": 2, "known_count": 2}
    remote["leaves"].append(
        {
            "kind": "branch",
            "repository": "owner/repo",
            "name": "topic",
            "is_default": False,
            "status": "debt",
        }
    )

    receipt = build_universe_baseline_receipt(remote, _local())
    branches = next(row for row in receipt.partitions if row.kind == "branches")

    assert branches.observation_complete is True
    assert branches.closure_complete is False
    assert receipt.observation_complete is True
    assert receipt.closure_complete is False


@pytest.mark.parametrize("classification", ["preservation", "active_custody", "owner_route"])
def test_actual_census_custody_output_is_protected_without_claiming_landing(classification):
    nodes = {
        "pull_requests": [
            {
                "number": 9,
                "classification": classification,
                "owner": "maintainer",
                "predicate": "pytest",
                "merge_condition": "exact head verified",
            }
        ],
        "issues": [],
        "branches": [{"name": "main", "head_oid": "a" * 40}],
        "checks": [],
    }

    def fetch(repo, kind, cursor):
        return {"nodes": nodes[kind], "total_count": len(nodes[kind]), "has_next_page": False, "end_cursor": None}

    remote, _ = build_github_estate_census(
        [
            {
                "name_with_owner": "owner/repo",
                "default_branch": "main",
                "default_sha": "a" * 40,
                "default_check_status": "no_required_checks",
                "connection_totals": {k: len(v) for k, v in nodes.items()},
            }
        ],
        fetch,
        repository_cursor={"expected_total": 1, "exhaustive": True},
        source_generation="1" * 64,
    )
    receipt = build_universe_baseline_receipt(remote, _local())
    pulls = next(row for row in receipt.partitions if row.kind == "pull_requests")
    dispositions = next(row for row in receipt.partitions if row.kind == "terminal_dispositions")
    assert pulls.protected == 1
    assert pulls.terminal == 0
    assert pulls.unaccounted == 0
    assert dispositions.protected == 1


@pytest.mark.parametrize(
    "change",
    [
        {"custody_debt": True},
        {"custody_debt": None},
        {"status": "debt"},
        {"custody_classification": "untyped"},
        {"predicate": None},
    ],
)
def test_incomplete_custody_fields_cannot_be_promoted_by_legacy_disposition(change):
    remote = _remote()
    remote["cursors"][0] = {"kind": "pull_requests", "expected_total": 1, "known_count": 1}
    remote["leaves"].append(
        {
            "kind": "pull_request",
            "status": "owned",
            "custody_debt": False,
            "custody_classification": "owner_route",
            "owner": "maintainer",
            "predicate": "pytest",
            "merge_condition": "verified",
            "disposition": "landed",
            **change,
        }
    )
    receipt = build_universe_baseline_receipt(remote, _local())
    pulls = next(row for row in receipt.partitions if row.kind == "pull_requests")
    assert pulls.terminal == 0
    assert pulls.protected == 0
    assert pulls.unaccounted == 1
