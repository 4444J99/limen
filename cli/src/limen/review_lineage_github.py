"""Exact-pagination assembly for review-lineage closure receipts.

GitHub comment bodies are deliberately outside this contract.  They are
untrusted review data; stable node identities and separately authored
correction/rejection receipts are the lifecycle evidence.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from limen.github_estate_census import ConnectionCensus, PageFetcher, paginate_exact
from limen.universe_recovery import (
    CursorReceiptV1,
    ReviewLineageClosureV2,
    ReviewThreadClosureV2,
    ThreadDisposition,
    canonical_digest,
)


def _cursor_receipt(surface: str, census: ConnectionCensus) -> CursorReceiptV1:
    return CursorReceiptV1(
        surface=surface,
        total_count=census.expected_total or 0,
        observed_count=census.known_count,
        page_count=max(1, census.page_count),
        complete=census.exhaustive,
        errors=(census.error,) if census.error else (),
    )


def build_review_lineage(
    *,
    repository: str,
    pull_request: int,
    metadata: Mapping[str, Any],
    fetch_threads: PageFetcher,
    fetch_comments: Mapping[str, PageFetcher],
    fetch_checks: PageFetcher,
) -> ReviewLineageClosureV2:
    """Build one exact-head closure or fail closed on any incomplete cursor."""

    thread_census = paginate_exact("review_threads", fetch_threads)
    check_census = paginate_exact("checks", fetch_checks)
    receipts = [
        _cursor_receipt("reviewThreads", thread_census),
        _cursor_receipt("statusCheckRollup.contexts", check_census),
    ]
    records: list[ReviewThreadClosureV2] = []
    for node in thread_census.nodes:
        thread_id = str(node["id"])
        comment_fetcher = fetch_comments.get(thread_id)
        if comment_fetcher is None:
            comment_census = ConnectionCensus(
                "review_comments",
                None,
                0,
                False,
                None,
                (),
                "comment-fetcher-missing",
            )
        else:
            comment_census = paginate_exact("review_comments", comment_fetcher)
        receipts.append(_cursor_receipt(f"reviewThreads/{thread_id}/comments", comment_census))
        records.append(
            ReviewThreadClosureV2(
                thread_id=thread_id,
                resolved=bool(node.get("isResolved")),
                outdated=bool(node.get("isOutdated")),
                disposition=cast(ThreadDisposition, str(node.get("disposition") or "pending")),
                receipt=node.get("receipt"),
                comment_ids=tuple(str(comment["id"]) for comment in comment_census.nodes),
            )
        )
    unresolved_current = sum(not row.resolved and not row.outdated for row in records)
    unresolved_outdated = sum(not row.resolved and row.outdated for row in records)
    complete = all(receipt.complete for receipt in receipts)
    terminal = (
        complete
        and unresolved_current == 0
        and unresolved_outdated == 0
        and metadata.get("review_decision") not in {"CHANGES_REQUESTED", "REVIEW_REQUIRED"}
    )
    return ReviewLineageClosureV2(
        repository=repository,
        pull_request=pull_request,
        observed_at=metadata["observed_at"],
        head_sha=metadata["head_sha"],
        base_ref=metadata["base_ref"],
        base_sha=metadata["base_sha"],
        merge_sha=metadata.get("merge_sha"),
        review_decision=metadata.get("review_decision"),
        checks_digest=canonical_digest(check_census.nodes),
        cursor_receipts=tuple(receipts),
        threads=tuple(records),
        unresolved_current=unresolved_current,
        unresolved_outdated=unresolved_outdated,
        lifecycle_stage=metadata.get("lifecycle_stage", "open"),
        corrective_owner=metadata.get("corrective_owner"),
        terminal=terminal,
    )
