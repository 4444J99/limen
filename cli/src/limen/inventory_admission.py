"""Fail-closed inventory containment for Limen #269.

This module has no production authority adapter. Callers must obtain the private
canonical census, frozen repository IDs and generation through a trusted keeper
integration; task fields, local files and supplied receipts are not authority.
The default claim boundary rejects routine growth while that adapter is absent.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Mapping

from limen.github_estate_census import CONNECTION_KINDS, _canonical_sha256


POLICY_ISSUE = "https://github.com/4444J99/limen/issues/269"
INVENTORY_CEILING = 250
MAX_AGE_SECONDS = 900
_GENERATION = re.compile(r"[0-9a-f]{64}")


class InventoryAdmissionError(ValueError):
    """A safe public denial code; never include private census contents."""


def routine_inventory_growth(task: Mapping[str, Any]) -> bool:
    """Use stable generated IDs as well as the established build-out labels."""
    task_id = str(task.get("id") or "")
    labels = task.get("labels") or []
    return task_id.startswith(("GEN-", "BLD-", "BLD2-")) or (
        isinstance(labels, list) and "generated" in labels and "build-out" in labels
    )


def require_inventory_classification(prior: Mapping[str, Any], desired: Mapping[str, Any]) -> None:
    """Keep established routine classification until an authorized migration exists."""
    if routine_inventory_growth(prior) and not routine_inventory_growth(desired):
        raise InventoryAdmissionError("inventory_classification_change_unauthorized")


def _integer(value: Any, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InventoryAdmissionError(reason)
    return value


def _validate_connection_receipts(
    observation: Mapping[str, Any],
    cursors: list[Any],
    aliases: Mapping[str, str],
    expected_generation: str,
) -> None:
    """Use the emitter's existing global-to-repository receipt binding."""
    receipts = observation.get("repository_receipts")
    if not isinstance(receipts, list):
        raise InventoryAdmissionError("inventory_repository_receipts_required")
    rows_by_name: dict[str, list[dict[str, Any]]] = {name: [] for name in aliases}
    for cursor in cursors:
        if not isinstance(cursor, dict):
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        name = cursor.get("repository")
        if not isinstance(name, str) or name not in rows_by_name:
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        rows_by_name[name].append(cursor)
    seen: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        name = receipt.get("repository")
        if not isinstance(name, str) or name not in aliases or name in seen:
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        seen.add(name)
        if (
            str(receipt.get("repository_id")) != aliases[name]
            or receipt.get("source_generation") != expected_generation
            or receipt.get("complete") is not True
        ):
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
        rows = rows_by_name[name]
        kinds = [row.get("kind") for row in rows]
        if len(rows) != len(CONNECTION_KINDS) or any(kinds.count(kind) != 1 for kind in CONNECTION_KINDS):
            raise InventoryAdmissionError("inventory_connection_partition_missing")
        if any(row.get("complete") is not True or row.get("exhaustive") is not True for row in rows):
            raise InventoryAdmissionError("inventory_connection_partition_incomplete")
        generations = [row.get("source_generation") for row in rows]
        if any(not isinstance(value, str) or not _GENERATION.fullmatch(value) for value in generations):
            raise InventoryAdmissionError("inventory_connection_generation_invalid")
        if any(value != generations[0] for value in generations[1:]):
            raise InventoryAdmissionError("inventory_connection_generation_invalid")
        try:
            digest = _canonical_sha256(rows)
        except (TypeError, ValueError):
            raise InventoryAdmissionError("inventory_connection_receipt_invalid") from None
        if receipt.get("connection_receipt_digest") != digest:
            raise InventoryAdmissionError("inventory_connection_receipt_invalid")
    if seen != aliases.keys():
        raise InventoryAdmissionError("inventory_repository_receipts_required")


def _repository_connection_generation(repository: dict[str, Any], expected_generation: str) -> str:
    """Bind collector connection facts to this repository and census generation.

    This checks consistency within the trusted private observation; the keeper
    still owns authentication of the observation and the expected generation.
    """
    inputs = repository.get("connection_generation_inputs")
    totals = repository.get("connection_totals")
    if not isinstance(inputs, dict) or not isinstance(totals, dict):
        raise InventoryAdmissionError("inventory_repository_generation_invalid")
    fields = {
        "source_generation",
        "repository",
        "repository_updated_at",
        "default_sha",
        "default_check_policy",
        "required_check_count",
        "check_total",
        "open_pr_total",
        "issue_total",
        "branch_total",
    }
    if (
        inputs.keys() != fields
        or inputs.get("source_generation") != expected_generation
        or inputs.get("repository") != repository.get("name_with_owner")
        or any(
            inputs.get(field) != repository.get(field)
            for field in ("default_sha", "default_check_policy", "required_check_count")
        )
    ):
        raise InventoryAdmissionError("inventory_repository_generation_invalid")
    for field, kind in (
        ("open_pr_total", "pull_requests"),
        ("issue_total", "issues"),
        ("branch_total", "branches"),
        ("check_total", "checks"),
    ):
        if _integer(inputs.get(field), "inventory_repository_generation_invalid") != _integer(
            totals.get(kind), "inventory_repository_generation_invalid"
        ):
            raise InventoryAdmissionError("inventory_repository_generation_invalid")
    try:
        generation = _canonical_sha256(inputs)
    except (TypeError, ValueError):
        raise InventoryAdmissionError("inventory_repository_generation_invalid") from None
    if repository.get("connection_generation") != generation:
        raise InventoryAdmissionError("inventory_repository_generation_invalid")
    return generation


def inventory_count(
    observation: Mapping[str, Any],
    *,
    expected_repository_ids: frozenset[str],
    expected_generation: str,
    now: datetime,
) -> int:
    """Validate the existing full census; count authored PRs by stable repo ID.

    Expected scope/generation must come from the keeper's authenticated collector
    state, never from the candidate observation. Redacted/truncated projections
    deliberately cannot satisfy this predicate.
    """
    if observation.get("schema") != "limen.github-estate-census.v1":
        raise InventoryAdmissionError("inventory_schema_invalid")
    report = observation.get("source_report")
    if not isinstance(report, dict) or report.get("exhaustive") is not True:
        raise InventoryAdmissionError("inventory_partial_or_unknown")
    if not isinstance(expected_generation, str) or not _GENERATION.fullmatch(expected_generation):
        raise InventoryAdmissionError("inventory_generation_changed")
    if report.get("source_generation") != expected_generation:
        raise InventoryAdmissionError("inventory_generation_changed")
    try:
        observed = datetime.fromisoformat(str(report["generated_at"]).replace("Z", "+00:00"))
        if observed.tzinfo is None or now.tzinfo is None:
            raise ValueError("timezone missing")
        age = (now.astimezone(UTC) - observed.astimezone(UTC)).total_seconds()
    except (KeyError, TypeError, ValueError):
        raise InventoryAdmissionError("inventory_timestamp_invalid") from None
    if age < 0 or age > MAX_AGE_SECONDS:
        raise InventoryAdmissionError("inventory_stale")
    repositories = observation.get("repositories")
    cursors = observation.get("cursors")
    leaves = observation.get("leaves")
    if not isinstance(repositories, list) or not isinstance(cursors, list) or not isinstance(leaves, list):
        raise InventoryAdmissionError("inventory_private_full_facts_required")
    if observation.get("failures") != []:
        raise InventoryAdmissionError("inventory_partial_or_unknown")
    aliases: dict[str, str] = {}
    generations: dict[str, str] = {}
    repository_pr_totals: dict[str, int] = {}
    for repository in repositories:
        if not isinstance(repository, dict):
            raise InventoryAdmissionError("inventory_repository_identity_invalid")
        identity = repository.get("repository_id")
        name = repository.get("name_with_owner")
        if isinstance(identity, bool) or not isinstance(identity, (int, str)) or not str(identity):
            raise InventoryAdmissionError("inventory_repository_identity_invalid")
        if not isinstance(name, str) or name.count("/") != 1 or name in aliases:
            raise InventoryAdmissionError("inventory_repository_identity_invalid")
        aliases[name] = str(identity)
        generations[name] = _repository_connection_generation(repository, expected_generation)
        repository_pr_totals[name] = repository["connection_totals"]["pull_requests"]
    if not expected_repository_ids or set(aliases.values()) != expected_repository_ids:
        raise InventoryAdmissionError("inventory_scope_changed")
    cursor_summary = report.get("cursor")
    if not isinstance(cursor_summary, dict):
        raise InventoryAdmissionError("inventory_repository_pagination_incomplete")
    if (
        _integer(report.get("normalized_leaf_count"), "inventory_leaf_count_invalid") != len(leaves)
        or _integer(cursor_summary.get("known_leaf_count"), "inventory_leaf_count_invalid") != len(leaves)
        or cursor_summary.get("leaf_count_complete") is not True
    ):
        raise InventoryAdmissionError("inventory_leaf_count_invalid")
    try:
        content_digest = _canonical_sha256(leaves)
    except (TypeError, ValueError):
        raise InventoryAdmissionError("inventory_content_digest_invalid") from None
    if report.get("content_sha256") != content_digest:
        raise InventoryAdmissionError("inventory_content_digest_invalid")
    repository_cursor = cursor_summary.get("repository")
    if not isinstance(repository_cursor, dict) or repository_cursor.get("exhaustive") is not True:
        raise InventoryAdmissionError("inventory_repository_pagination_incomplete")
    if (
        _integer(repository_cursor.get("expected_total"), "inventory_repository_total_unknown") != len(repositories)
        or _integer(repository_cursor.get("known_count"), "inventory_repository_total_unknown") != len(repositories)
        or _integer(repository_cursor.get("page_count"), "inventory_repository_pagination_incomplete") == 0
    ):
        raise InventoryAdmissionError("inventory_repository_pagination_incomplete")
    _validate_connection_receipts(observation, cursors, aliases, expected_generation)
    counts: dict[str, int] = {}
    for cursor in cursors:
        if not isinstance(cursor, dict) or cursor.get("kind") != "pull_requests":
            continue
        name = cursor.get("repository")
        if not isinstance(name, str) or name not in aliases or name in counts:
            raise InventoryAdmissionError("inventory_pr_pagination_invalid")
        count = _integer(cursor.get("expected_total"), "inventory_pr_total_unknown")
        if (
            cursor.get("complete") is not True
            or cursor.get("exhaustive") is not True
            or _integer(cursor.get("known_count"), "inventory_pr_total_unknown") != count
            or repository_pr_totals[name] != count
            or cursor.get("page_cursor") is not None
            or cursor.get("source_generation") != generations[name]
            or (_integer(cursor.get("page_count"), "inventory_pr_pagination_invalid") == 0 and count != 0)
        ):
            raise InventoryAdmissionError("inventory_pr_pagination_incomplete")
        counts[name] = count
    if counts.keys() != aliases.keys():
        raise InventoryAdmissionError("inventory_pr_partition_missing")
    seen: dict[tuple[str, int], str] = {}
    observed_counts = dict.fromkeys(aliases, 0)
    seen_named: set[tuple[str, int]] = set()
    for leaf in leaves:
        if not isinstance(leaf, dict) or leaf.get("kind") != "pull_request":
            continue
        name = leaf.get("repository")
        number = _integer(leaf.get("number"), "inventory_pr_identity_invalid")
        author = leaf.get("author_login")
        if not isinstance(name, str) or name not in aliases or number == 0 or not isinstance(author, str) or not author:
            raise InventoryAdmissionError("inventory_pr_identity_or_author_unknown")
        if (name, number) in seen_named:
            raise InventoryAdmissionError("inventory_pr_duplicate")
        seen_named.add((name, number))
        observed_counts[name] += 1
        key = (aliases[name], number)
        if key in seen and seen[key] != author.lower():
            raise InventoryAdmissionError("inventory_migration_conflict")
        seen[key] = author.lower()
    if observed_counts != counts:
        raise InventoryAdmissionError("inventory_pr_total_changed")
    return sum(author == "4444j99" for author in seen.values())


def require_inventory_admission(
    prior: Mapping[str, Any],
    desired: Mapping[str, Any],
    *,
    observation: Mapping[str, Any] | None = None,
    expected_repository_ids: frozenset[str] | None = None,
    expected_generation: str | None = None,
    active_reservations: int = 0,
    now: datetime | None = None,
) -> None:
    """Guard new claims inside the existing keeper transaction, before debit.

    Settlement and existing launches must remain possible. Exceptions/overrides
    need an authenticated owner decision in the future adapter; mutable task
    labels, supplied receipt fields and environment variables cannot override.
    Outstanding growth reservations must be counted in the same transaction.
    """
    require_inventory_classification(prior, desired)
    if prior.get("status") != "open" or desired.get("status") not in {"dispatched", "in_progress"}:
        return
    if not (routine_inventory_growth(prior) or routine_inventory_growth(desired)):
        return
    if observation is None or expected_repository_ids is None or expected_generation is None:
        raise InventoryAdmissionError("inventory_admission_adapter_unavailable")
    count = inventory_count(
        observation,
        expected_repository_ids=expected_repository_ids,
        expected_generation=expected_generation,
        now=now or datetime.now(UTC),
    )
    reservations = _integer(active_reservations, "inventory_reservations_unknown")
    if count + reservations >= INVENTORY_CEILING:
        raise InventoryAdmissionError("inventory_growth_ceiling")
