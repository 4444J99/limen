from __future__ import annotations

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
