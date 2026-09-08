from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from limen.conduct.store import MemoryStateStore
from limen.github_estate_census import (
    CONNECTION_KINDS,
    _canonical_sha256,
    build_github_estate_census,
    paginate_exact,
)
from limen.inventory_admission import (
    InventoryAdmissionError,
    inventory_count,
    require_inventory_admission,
)


NOW = datetime(2026, 9, 8, 14, tzinfo=UTC)
GENERATION = "1" * 64
PRIOR = {"id": "GEN-org-repo-tests", "status": "open", "labels": []}
DESIRED = {**PRIOR, "status": "dispatched"}


def census(count=2, name="organvm/example"):
    # Match the real collector: each repository hashes its own metadata under
    # the overall census generation, and proven empty partitions fetch no pages.
    inputs = {
        "source_generation": GENERATION,
        "repository": name,
        "repository_updated_at": NOW.isoformat(),
        "default_sha": "a" * 40,
        "default_check_policy": "required",
        "required_check_count": 0,
        "check_total": 0,
        "open_pr_total": count,
        "issue_total": 0,
        "branch_total": 0,
    }
    generation = _canonical_sha256(inputs)
    totals = {"pull_requests": count, "issues": 0, "branches": 0, "checks": 0}
    repository = {
        "name_with_owner": name,
        "repository_id": "42",
        "private": True,
        "default_branch": "main",
        "default_sha": inputs["default_sha"],
        "default_check_policy": inputs["default_check_policy"],
        "required_check_count": 0,
        "connection_generation": generation,
        "connection_generation_inputs": inputs,
        "connection_totals": totals,
    }

    def fetch_page(repo, kind, cursor):
        assert repo == name
        assert kind == "pull_requests"  # Empty partitions must not perform IO.
        offset = int(cursor or 0)
        end = min(offset + 100, count)
        return {
            "total_count": count,
            "nodes": [{"number": i + 1, "author_login": "4444J99"} for i in range(offset, end)],
            "has_next_page": end < count,
            "end_cursor": str(end) if end < count else None,
        }

    results = {
        (name, kind): paginate_exact(
            kind,
            lambda cursor, kind=kind: fetch_page(name, kind, cursor),
            expected_total=totals[kind],
            repository=name,
            source_generation=generation,
        )
        for kind in CONNECTION_KINDS
    }
    full, _ = build_github_estate_census(
        [repository],
        fetch_page,
        repository_cursor={"expected_total": 1, "page_count": 1, "exhaustive": True},
        now=NOW,
        source_generation=GENERATION,
        connection_results=results,
    )
    return full


def count(snapshot):
    return inventory_count(snapshot, expected_repository_ids=frozenset({"42"}), expected_generation=GENERATION, now=NOW)


def admit(snapshot, reservations=0):
    require_inventory_admission(
        PRIOR,
        DESIRED,
        observation=snapshot,
        expected_repository_ids=frozenset({"42"}),
        expected_generation=GENERATION,
        active_reservations=reservations,
        now=NOW,
    )


def test_authored_scope_is_distinct_from_all_authors():
    snapshot = census()
    snapshot["leaves"][1]["author_login"] = "dependabot[bot]"
    snapshot["source_report"]["content_sha256"] = _canonical_sha256(snapshot["leaves"])
    assert count(snapshot) == 1


def test_author_tampering_cannot_reuse_collector_receipts():
    snapshot = census()
    snapshot["leaves"][1]["author_login"] = "dependabot[bot]"
    with pytest.raises(InventoryAdmissionError, match="inventory_content_changed"):
        count(snapshot)


@pytest.mark.parametrize("leaf_count", [None, True, -1, 0, 3, "2"])
def test_collector_leaf_count_must_match_full_content(leaf_count):
    snapshot = census()
    snapshot["source_report"]["normalized_leaf_count"] = leaf_count
    with pytest.raises(InventoryAdmissionError, match="inventory_(leaf_count_invalid|content_changed)"):
        count(snapshot)


@pytest.mark.parametrize(
    "change",
    [
        lambda x: x["source_report"].update(exhaustive=False),
        lambda x: x["source_report"].update(source_generation="2" * 64),
        lambda x: x["source_report"].update(generated_at=(NOW - timedelta(minutes=16)).isoformat()),
        lambda x: x["source_report"].update(generated_at=(NOW + timedelta(seconds=1)).isoformat()),
        lambda x: x["source_report"].update(generated_at="2026-09-08T14:00:00"),
        lambda x: x.update(failures=[{"error": "private"}]),
        lambda x: x["repositories"][0].update(repository_id="43"),
        lambda x: x["source_report"]["cursor"]["repository"].update(expected_total=None),
        lambda x: x["cursors"][0].update(expected_total=None),
        lambda x: x["cursors"][0].update(page_cursor="unfinished"),
        lambda x: x["cursors"][0].update(complete=False),
        lambda x: x["cursors"][0].update(known_count=True),
        lambda x: x["cursors"][0].update(page_count=0),
        lambda x: x["cursors"].clear(),
        lambda x: x["leaves"].pop(),
        lambda x: x["leaves"][0].update(author_login=None),
        lambda x: x["leaves"][1].update(number=1),
        lambda x: x["leaves"][0].update(repository=[]),
    ],
)
def test_unknown_partial_stale_or_racing_observation_fails_closed(change):
    snapshot = census()
    change(snapshot)
    with pytest.raises(InventoryAdmissionError):
        count(snapshot)


def test_migration_aliases_deduplicate_stable_repository_id():
    snapshot = census(1)
    renamed = census(1, "new-org/example")
    snapshot["repositories"].extend(renamed["repositories"])
    snapshot["source_report"]["cursor"]["repository"].update(expected_total=2, known_count=2)
    snapshot["cursors"].extend(renamed["cursors"])
    snapshot["repository_receipts"].extend(renamed["repository_receipts"])
    snapshot["leaves"].extend(renamed["leaves"])
    snapshot["source_report"].update(
        content_sha256=_canonical_sha256(snapshot["leaves"]), normalized_leaf_count=len(snapshot["leaves"])
    )
    snapshot["source_report"]["cursor"]["known_leaf_count"] = len(snapshot["leaves"])
    assert count(snapshot) == 1
    snapshot["leaves"][1]["author_login"] = "somebody-else"
    snapshot["source_report"]["content_sha256"] = _canonical_sha256(snapshot["leaves"])
    with pytest.raises(InventoryAdmissionError, match="migration_conflict"):
        count(snapshot)


def test_collector_repository_generation_differs_from_census_generation():
    snapshot = census()
    assert snapshot["cursors"][0]["source_generation"] != GENERATION
    assert count(snapshot) == 2


def test_collector_proven_empty_partition_requires_no_pages():
    snapshot = census(0)
    assert snapshot["cursors"][0]["page_count"] == 0
    assert count(snapshot) == 0
    admit(snapshot)


@pytest.mark.parametrize("pr_count", [0, 2])
@pytest.mark.parametrize(
    "change",
    [
        lambda x: x["cursors"][0].update(source_generation=GENERATION),
        lambda x: x["cursors"][0].update(source_generation="2" * 64),
        lambda x: x["repositories"][0].pop("connection_generation_inputs"),
        lambda x: x["repositories"][0].update(connection_generation="2" * 64),
        lambda x: x["repositories"][0]["connection_generation_inputs"].update(source_generation="2" * 64),
        lambda x: x["repositories"][0]["connection_generation_inputs"].update(repository="other/example"),
        lambda x: x["repositories"][0].update(default_sha="b" * 40),
        lambda x: x["repositories"][0]["connection_totals"].update(pull_requests=100),
        lambda x: x["cursors"][0].update(complete=False),
        lambda x: x["cursors"][0].update(exhaustive=False),
        lambda x: x["cursors"][0].update(page_cursor="unfinished"),
    ],
)
def test_repository_generation_or_empty_partition_mismatch_fails_closed(pr_count, change):
    snapshot = census(pr_count)
    change(snapshot)
    with pytest.raises(InventoryAdmissionError):
        count(snapshot)


def test_cursor_cannot_borrow_another_repository_generation():
    snapshot = census(1)
    other = census(1, "another/example")
    snapshot["cursors"][0]["source_generation"] = other["cursors"][0]["source_generation"]
    with pytest.raises(InventoryAdmissionError, match="connection_generation_invalid"):
        count(snapshot)


@pytest.mark.parametrize(
    ("field", "value"),
    [("source_generation", "2" * 64), ("repository", "other/example"), ("default_sha", "b" * 40)],
)
def test_consistently_rehashed_cursor_still_requires_current_census_and_repository(field, value):
    snapshot = census()
    repository = snapshot["repositories"][0]
    repository["connection_generation_inputs"][field] = value
    generation = _canonical_sha256(repository["connection_generation_inputs"])
    repository["connection_generation"] = generation
    snapshot["cursors"][0]["source_generation"] = generation
    with pytest.raises(InventoryAdmissionError, match="repository_generation_invalid"):
        count(snapshot)


@pytest.mark.parametrize(
    "task",
    [
        PRIOR,
        {"id": "BLD-x", "status": "open"},
        {"id": "BLD2-x", "status": "open"},
        {"id": "old", "status": "open", "labels": ["generated", "build-out"]},
    ],
)
def test_missing_adapter_and_caller_override_flags_cannot_admit(task):
    desired = {
        **task,
        "status": "dispatched",
        "labels": ["security", "human-approved"],
        "inventory_override": True,
        "inventory_count": 0,
    }
    reason = "classification_change_unauthorized" if task["id"] == "old" else "adapter_unavailable"
    with pytest.raises(InventoryAdmissionError, match=reason):
        require_inventory_admission(task, desired)


def test_existing_execution_settlement_and_repair_are_unaffected():
    require_inventory_admission(DESIRED, {**DESIRED, "status": "in_progress"})
    require_inventory_admission(DESIRED, {**DESIRED, "status": "failed"})
    require_inventory_admission(
        {"id": "HEAL-specific", "status": "open"}, {"id": "HEAL-specific", "status": "dispatched"}
    )


def test_ceiling_includes_outstanding_growth_reservations():
    admit(census(249))
    with pytest.raises(InventoryAdmissionError, match="growth_ceiling"):
        admit(census(249), 1)
    with pytest.raises(InventoryAdmissionError, match="growth_ceiling"):
        admit(census(250))
    with pytest.raises(InventoryAdmissionError, match="reservations_unknown"):
        admit(census(0), True)


def test_two_claims_in_existing_keeper_transaction_cannot_spend_same_last_slot():
    store = MemoryStateStore()
    snapshot = census(249)

    def claim():
        try:
            with store.transaction() as state:
                held = state.get("inventory_test_growth_reservations", 0)
                admit(snapshot, held)
                state["inventory_test_growth_reservations"] = held + 1
            return True
        except InventoryAdmissionError:
            return False

    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = list(workers.map(lambda _: claim(), range(2)))
    assert sorted(outcomes) == [False, True]
    assert store.snapshot()["inventory_test_growth_reservations"] == 1


def test_census_adds_real_author_without_changing_private_projection():
    from limen.github_estate_census import _pr_leaf, _tracked_leaf

    leaf = _pr_leaf("private/example", True, {"number": 1, "author_login": "4444J99"})
    assert leaf["author_login"] == "4444J99"
    assert "author_login" not in _tracked_leaf(leaf)
