"""Compose remote and local censuses into one fail-closed universe receipt."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from limen.universe_recovery import (
    UniverseBaselineReceiptV1,
    UniversePartitionKind,
    UniversePartitionV1,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _partition(
    kind: UniversePartitionKind,
    *,
    terminal: int,
    protected: int,
    blocked: int,
    unaccounted: int,
) -> UniversePartitionV1:
    return UniversePartitionV1(
        kind=kind,
        total=terminal + protected + blocked + unaccounted,
        terminal=terminal,
        protected=protected,
        blocked=blocked,
        unaccounted=unaccounted,
        complete=unaccounted == 0,
    )


def _connection_total(remote: dict[str, Any], kind: str) -> tuple[int, int]:
    rows = [row for row in remote.get("cursors", ()) if row.get("kind") == kind]
    observed = sum(int(row.get("known_count") or 0) for row in rows)
    expected_values = [row.get("expected_total") for row in rows]
    expected = sum(int(value) for value in expected_values if isinstance(value, int) and not isinstance(value, bool))
    if any(not isinstance(value, int) or isinstance(value, bool) for value in expected_values):
        expected = observed
    return expected, observed


def _local_disposition(
    row: dict[str, Any],
    defaults: dict[str, tuple[str | None, str | None]],
) -> str:
    if row.get("protected"):
        return "protected"
    if row.get("custody_risk"):
        return "blocked"
    repository = row.get("repository")
    default_ref, default_sha = defaults.get(str(repository), (None, None))
    default_branch = default_ref.removeprefix("refs/heads/") if default_ref else None
    if default_branch and row.get("branch") == default_branch and default_sha and row.get("head") == default_sha:
        return "terminal"
    return "unaccounted"


def build_universe_baseline_receipt(
    remote: dict[str, Any],
    local: dict[str, Any],
) -> UniverseBaselineReceiptV1:
    """Build arithmetic partitions without promoting missing policy evidence to green."""

    report = remote["source_report"]
    observed_at = datetime.fromisoformat(str(report["generated_at"]).replace("Z", "+00:00"))
    source_generation = report.get("source_generation")
    if not isinstance(source_generation, str) or len(source_generation) != 64:
        raise ValueError("remote census lacks a content-addressed source generation")

    repository_cursor = (report.get("cursor") or {}).get("repository") or {}
    expected_repositories = repository_cursor.get("expected_total")
    receipts = list(remote.get("repository_receipts") or ())
    denominator = (
        int(expected_repositories)
        if isinstance(expected_repositories, int) and not isinstance(expected_repositories, bool)
        else len(receipts)
    )
    stable_receipts = [
        row
        for row in receipts
        if row.get("complete")
        and row.get("default_ref")
        and row.get("default_sha")
        and row.get("default_check_status") in {"green", "no_required_checks"}
    ]
    complete_receipts = sum(bool(row.get("complete")) for row in receipts)
    repositories = _partition(
        "repositories",
        terminal=len(stable_receipts),
        protected=0,
        blocked=max(0, complete_receipts - len(stable_receipts)),
        unaccounted=max(0, denominator - complete_receipts),
    )

    leaves = list(remote.get("leaves") or ())
    pull_leaves = [row for row in leaves if row.get("kind") == "pull_request"]
    pull_expected, pull_observed = _connection_total(remote, "pull_requests")
    pull_protected = sum(row.get("status") == "owned" for row in pull_leaves)
    pull_blocked = pull_observed - pull_protected
    pull_requests = _partition(
        "pull_requests",
        terminal=0,
        protected=pull_protected,
        blocked=pull_blocked,
        unaccounted=max(0, pull_expected - pull_observed),
    )

    branch_leaves = [row for row in leaves if row.get("kind") == "branch"]
    branch_expected, branch_observed = _connection_total(remote, "branches")
    branch_terminal = sum(bool(row.get("is_default")) for row in branch_leaves)
    branches = _partition(
        "branches",
        terminal=branch_terminal,
        protected=0,
        blocked=0,
        unaccounted=max(0, branch_expected - branch_observed) + max(0, branch_observed - branch_terminal),
    )

    defaults = {
        str(row["repository"]): (row.get("default_ref"), row.get("default_sha"))
        for row in receipts
        if row.get("repository")
    }
    local_rows = list(local.get("roots") or ())
    local_classes = [_local_disposition(row, defaults) for row in local_rows]
    local_roots = _partition(
        "local_roots",
        terminal=local_classes.count("terminal"),
        protected=local_classes.count("protected"),
        blocked=local_classes.count("blocked"),
        unaccounted=local_classes.count("unaccounted"),
    )
    worktree_rows = [row for row in local_rows if row.get("checkout_kind") == "linked_worktree"]
    worktree_classes = [_local_disposition(row, defaults) for row in worktree_rows]
    worktrees = _partition(
        "worktrees",
        terminal=worktree_classes.count("terminal"),
        protected=worktree_classes.count("protected"),
        blocked=worktree_classes.count("blocked"),
        unaccounted=worktree_classes.count("unaccounted"),
    )

    protection_count = int((local.get("summary") or {}).get("protection_exclusion_count") or 0)
    protections = _partition(
        "protections",
        terminal=0,
        protected=protection_count,
        blocked=0,
        unaccounted=0,
    )
    disposition_classes = (
        ["protected" if row.get("status") == "owned" else "blocked" for row in pull_leaves]
        + ["terminal" if row.get("is_default") else "unaccounted" for row in branch_leaves]
        + local_classes
    )
    terminal_dispositions = _partition(
        "terminal_dispositions",
        terminal=disposition_classes.count("terminal"),
        protected=disposition_classes.count("protected"),
        blocked=disposition_classes.count("blocked"),
        unaccounted=disposition_classes.count("unaccounted"),
    )
    partitions = (
        repositories,
        pull_requests,
        branches,
        local_roots,
        worktrees,
        protections,
        terminal_dispositions,
    )
    failure_count = int((remote.get("summary") or {}).get("failure_count") or 0) + int(
        (local.get("summary") or {}).get("failure_count") or 0
    )
    unaccounted = sum(row.unaccounted for row in partitions)
    complete = (
        len(stable_receipts) == denominator
        and failure_count == 0
        and unaccounted == 0
        and all(row.complete for row in partitions)
    )
    return UniverseBaselineReceiptV1(
        observed_at=observed_at,
        source_generation=source_generation,
        census_digest=_digest({"remote": remote, "local": local}),
        repository_denominator=denominator,
        stable_count=len(stable_receipts),
        partitions=partitions,
        failure_count=failure_count,
        unaccounted=unaccounted,
        complete=complete,
    )
