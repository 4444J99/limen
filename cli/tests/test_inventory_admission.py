from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from limen.conduct.store import MemoryStateStore
from limen.inventory_admission import (
    InventoryAdmissionError,
    inventory_count,
    require_inventory_admission,
)


NOW = datetime(2026, 9, 8, 14, tzinfo=UTC)
GENERATION = "1" * 64
PRIOR = {"id": "GEN-org-repo-tests", "status": "open", "labels": []}
DESIRED = {**PRIOR, "status": "dispatched"}


def census(count=2):
    return {
        "schema": "limen.github-estate-census.v1",
        "source_report": {
            "exhaustive": True,
            "generated_at": NOW.isoformat(),
            "source_generation": GENERATION,
            "cursor": {
                "repository": {
                    "expected_total": 1,
                    "known_count": 1,
                    "page_count": 1,
                    "exhaustive": True,
                }
            },
        },
        "repositories": [{"name_with_owner": "organvm/example", "repository_id": "42"}],
        "failures": [],
        "cursors": [
            {
                "kind": "pull_requests",
                "repository": "organvm/example",
                "expected_total": count,
                "known_count": count,
                "page_count": 2,
                "page_cursor": None,
                "complete": True,
                "exhaustive": True,
                "source_generation": GENERATION,
            }
        ],
        "leaves": [
            {
                "kind": "pull_request",
                "repository": "organvm/example",
                "number": i + 1,
                "author_login": "4444J99",
            }
            for i in range(count)
        ],
    }


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
    assert count(snapshot) == 1


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
    snapshot["repositories"].append({"name_with_owner": "new-org/example", "repository_id": "42"})
    snapshot["source_report"]["cursor"]["repository"].update(expected_total=2, known_count=2)
    snapshot["cursors"].append({**snapshot["cursors"][0], "repository": "new-org/example"})
    snapshot["leaves"].append({**snapshot["leaves"][0], "repository": "new-org/example"})
    assert count(snapshot) == 1
    snapshot["leaves"][1]["author_login"] = "somebody-else"
    with pytest.raises(InventoryAdmissionError, match="migration_conflict"):
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
    with pytest.raises(InventoryAdmissionError, match="adapter_unavailable"):
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
