from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.review_lineage_github import build_review_lineage
from limen.repository_identity import LIMEN_REPOSITORY_IDENTITY


def pages(nodes, *, page_size=100):
    chunks = [nodes[index : index + page_size] for index in range(0, len(nodes), page_size)] or [[]]

    def fetch(cursor):
        index = int(cursor or 0)
        return {
            "total_count": len(nodes),
            "nodes": chunks[index],
            "has_next_page": index + 1 < len(chunks),
            "end_cursor": str(index + 1) if index + 1 < len(chunks) else None,
        }

    return fetch


def metadata(**updates):
    values = {
        "observed_at": datetime(2026, 8, 23, 16, 0, tzinfo=UTC),
        "head_sha": "a" * 40,
        "base_ref": "main",
        "base_sha": "b" * 40,
        "review_decision": None,
        "lifecycle_stage": "open",
    }
    values.update(updates)
    return values


def test_more_than_one_hundred_threads_and_comments_are_exhaustive():
    threads = [
        {
            "id": f"thread-{index:03d}",
            "isResolved": True,
            "isOutdated": index % 2 == 0,
            "disposition": "corrected",
            "receipt": f"github:organvm/limen:pull-request:{index + 1}",
        }
        for index in range(101)
    ]
    comments = {
        row["id"]: pages([{"id": f"{row['id']}-comment-{index:03d}"} for index in range(101)]) for row in threads
    }

    result = build_review_lineage(
        repository_identity=LIMEN_REPOSITORY_IDENTITY,
        repository="organvm/limen",
        pull_request=2542,
        metadata=metadata(),
        fetch_threads=pages(threads),
        fetch_comments=comments,
        fetch_checks=pages([{"id": "check-1"}]),
    )

    assert result.terminal is True
    assert len(result.threads) == 101
    assert all(len(thread.comment_ids) == 101 for thread in result.threads)
    assert all(receipt.complete for receipt in result.cursor_receipts)


def test_unresolved_outdated_thread_blocks_closure():
    thread = {"id": "thread-outdated", "isResolved": False, "isOutdated": True}
    result = build_review_lineage(
        repository_identity=LIMEN_REPOSITORY_IDENTITY,
        repository="organvm/limen",
        pull_request=2542,
        metadata=metadata(),
        fetch_threads=pages([thread]),
        fetch_comments={"thread-outdated": pages([{"id": "comment-1"}])},
        fetch_checks=pages([{"id": "check-1"}]),
    )

    assert result.terminal is False
    assert result.unresolved_outdated == 1


@pytest.mark.parametrize("decision", ["REVIEW_REQUIRED", "CHANGES_REQUESTED"])
def test_outstanding_review_decisions_block_closure(decision):
    result = build_review_lineage(
        repository_identity=LIMEN_REPOSITORY_IDENTITY,
        repository="organvm/limen",
        pull_request=2542,
        metadata=metadata(review_decision=decision),
        fetch_threads=pages([]),
        fetch_comments={},
        fetch_checks=pages([{"id": "check-1"}]),
    )

    assert result.terminal is False


def test_missing_nested_comment_cursor_fails_closed():
    result = build_review_lineage(
        repository_identity=LIMEN_REPOSITORY_IDENTITY,
        repository="organvm/limen",
        pull_request=2542,
        metadata=metadata(),
        fetch_threads=pages(
            [
                {
                    "id": "thread-resolved",
                    "isResolved": True,
                    "isOutdated": False,
                    "disposition": "corrected",
                    "receipt": "github:organvm/limen:pull-request:2542",
                }
            ]
        ),
        fetch_comments={},
        fetch_checks=pages([{"id": "check-1"}]),
    )

    assert result.terminal is False
    comment_receipt = next(
        receipt for receipt in result.cursor_receipts if receipt.surface == "reviewThreads/thread-resolved/comments"
    )
    assert comment_receipt.complete is False
    assert comment_receipt.errors == ("comment-fetcher-missing",)


def test_post_merge_unresolved_review_requires_corrective_owner():
    with pytest.raises(ValueError, match="corrective owner"):
        build_review_lineage(
            repository_identity=LIMEN_REPOSITORY_IDENTITY,
            repository="organvm/limen",
            pull_request=2542,
            metadata=metadata(lifecycle_stage="merged"),
            fetch_threads=pages([{"id": "thread-new", "isResolved": False, "isOutdated": False}]),
            fetch_comments={"thread-new": pages([{"id": "comment-1"}])},
            fetch_checks=pages([{"id": "check-1"}]),
        )
