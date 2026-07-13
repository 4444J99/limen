from __future__ import annotations

from copy import deepcopy

from limen.execution_contract import execution_contract_hash, execution_contract_payload


def _task() -> dict[str, object]:
    return {
        "id": "AW-ONE",
        "repo": "organvm/limen",
        "target_agent": "codex",
        "workstream": "substrate",
        "type": "coordination",
        "predicate": "python3 scripts/check.py",
        "receipt_target": "git:organvm/limen:logs/check.json",
        "context": "bounded execution context",
        "labels": ["receipt-first", "always-working"],
        "budget_cost": 1,
    }


def test_execution_contract_payload_is_canonical_and_provider_neutral() -> None:
    task = _task()
    reordered = deepcopy(task)
    reordered["labels"] = list(reversed(task["labels"]))

    assert execution_contract_payload(task) == {
        "id": "AW-ONE",
        "repo": "organvm/limen",
        "target_agent": "codex",
        "workstream_or_type": "substrate",
        "predicate": "python3 scripts/check.py",
        "receipt_target": "git:organvm/limen:logs/check.json",
        "context": "bounded execution context",
        "labels": ["always-working", "receipt-first"],
        "budget_cost": 1,
    }
    assert execution_contract_hash(reordered) == execution_contract_hash(task)


def test_every_execution_contract_field_changes_the_hash() -> None:
    original = _task()
    changes = {
        "id": "AW-TWO",
        "repo": "organvm/other",
        "target_agent": "jules",
        "workstream": "contributions",
        "predicate": "python3 scripts/other.py",
        "receipt_target": "git:organvm/limen:logs/other.json",
        "context": "changed context",
        "labels": ["different"],
        "budget_cost": 2,
    }

    original_hash = execution_contract_hash(original)
    for field, value in changes.items():
        changed = deepcopy(original)
        changed[field] = value
        assert execution_contract_hash(changed) != original_hash, field


def test_type_is_the_partition_only_when_workstream_is_absent() -> None:
    task = _task()
    with_workstream = execution_contract_hash(task)
    task["type"] = "research"
    assert execution_contract_hash(task) == with_workstream

    task["workstream"] = None
    assert execution_contract_payload(task)["workstream_or_type"] == "research"
    assert execution_contract_hash(task) != with_workstream
