from __future__ import annotations

from copy import deepcopy
from datetime import date

import pytest

from limen.execution_contract import (
    EXECUTION_CONTRACT_SCHEMA_VERSION,
    ExecutionContractError,
    execution_contract_hash,
    execution_contract_payload,
)
from limen.models import Task
from limen.plan_handoff import PLAN_ONLY_LABEL, build_plan_receipt
from limen.workstream_contract import packet_contract


def _task() -> dict[str, object]:
    return {
        "id": "AW-ONE",
        "title": "Bounded owner task",
        "description": "Execute one receipt-first packet",
        "repo": "organvm/limen",
        "type": "coordination",
        "target_agent": "codex",
        "workstream": "substrate",
        "priority": "high",
        "budget_cost": 1,
        "labels": ["receipt-first", "always-working"],
        "urls": ["https://github.com/organvm/limen/issues/1"],
        "context": "bounded execution context",
        "predicate": "python3 scripts/check.py",
        "receipt_target": "git:organvm/limen:logs/check.json",
        "execution_requirements": [{"kind": "mount", "path": "/runtime/volume-a"}],
        "workstream_contract": packet_contract("1h", now_epoch=1_000),
        "plan_receipt": None,
        "claude_tier": "sonnet",
        "depends_on": ["FOUNDATION-ONE"],
    }


def test_execution_contract_payload_is_versioned_and_label_order_is_canonical() -> None:
    task = _task()
    reordered = deepcopy(task)
    reordered["labels"] = list(reversed(task["labels"]))

    assert execution_contract_payload(task) == {
        "schema_version": EXECUTION_CONTRACT_SCHEMA_VERSION,
        "id": "AW-ONE",
        "title": "Bounded owner task",
        "description": "Execute one receipt-first packet",
        "repo": "organvm/limen",
        "type": "coordination",
        "target_agent": "codex",
        "workstream": "substrate",
        "priority": "high",
        "budget_cost": 1,
        "labels": ["always-working", "receipt-first"],
        "urls": ["https://github.com/organvm/limen/issues/1"],
        "context": "bounded execution context",
        "predicate": "python3 scripts/check.py",
        "receipt_target": "git:organvm/limen:logs/check.json",
        "execution_requirements": [{"kind": "mount", "path": "/runtime/volume-a"}],
        "workstream_contract": packet_contract("1h", now_epoch=1_000),
        "plan_receipt": None,
        "claude_tier": "sonnet",
        "depends_on": ["FOUNDATION-ONE"],
    }
    assert execution_contract_hash(reordered) == execution_contract_hash(task)


def test_every_execution_input_changes_the_hash() -> None:
    original = _task()
    plan_task = Task(
        id="PLAN",
        title="plan",
        repo="organvm/limen",
        target_agent="claude",
        labels=[PLAN_ONLY_LABEL],
        created=date(2026, 7, 23),
    )
    changes = {
        "id": "AW-TWO",
        "title": "Different title",
        "description": "Different description",
        "repo": "organvm/other",
        "type": "research",
        "target_agent": "jules",
        "workstream": "contributions",
        "priority": "critical",
        "budget_cost": 2,
        "labels": ["different"],
        "urls": ["https://github.com/organvm/limen/issues/2"],
        "context": "changed context",
        "predicate": "python3 scripts/other.py",
        "receipt_target": "git:organvm/limen:logs/other.json",
        "execution_requirements": [{"kind": "mount", "path": "/runtime/volume-b"}],
        "workstream_contract": packet_contract("2h", now_epoch=2_000),
        "plan_receipt": build_plan_receipt(plan_task, "Implement the accepted plan.", planner_agent="claude"),
        "claude_tier": "haiku",
        "depends_on": ["FOUNDATION-TWO"],
    }

    original_hash = execution_contract_hash(original)
    for field, value in changes.items():
        changed = deepcopy(original)
        changed[field] = value
        assert execution_contract_hash(changed) != original_hash, field


def test_type_and_workstream_are_independently_fingerprinted() -> None:
    task = _task()
    original_hash = execution_contract_hash(task)

    changed_type = deepcopy(task)
    changed_type["type"] = "research"
    assert execution_contract_hash(changed_type) != original_hash

    changed_workstream = deepcopy(task)
    changed_workstream["workstream"] = "contributions"
    assert execution_contract_hash(changed_workstream) != original_hash


def test_missing_none_and_empty_requirements_are_contract_equivalent() -> None:
    missing = _task()
    missing.pop("execution_requirements")
    explicit_none = deepcopy(missing)
    explicit_none["execution_requirements"] = None
    explicit_empty = deepcopy(missing)
    explicit_empty["execution_requirements"] = []

    assert execution_contract_payload(missing) == execution_contract_payload(explicit_none)
    assert execution_contract_payload(missing) == execution_contract_payload(explicit_empty)
    assert execution_contract_hash(missing) == execution_contract_hash(explicit_none)
    assert execution_contract_hash(missing) == execution_contract_hash(explicit_empty)


def test_missing_and_none_workstream_contract_are_equivalent() -> None:
    missing = _task()
    missing.pop("workstream_contract")
    explicit_none = deepcopy(missing)
    explicit_none["workstream_contract"] = None

    assert execution_contract_payload(missing) == execution_contract_payload(explicit_none)
    assert execution_contract_hash(missing) == execution_contract_hash(explicit_none)


@pytest.mark.parametrize("budget", [True, False, 1.0, 1.9, "1", None, 0, 1001])
def test_budget_cost_rejects_lossy_or_out_of_schema_values(budget: object) -> None:
    task = _task()
    task["budget_cost"] = budget
    with pytest.raises(ExecutionContractError, match="budget_cost"):
        execution_contract_hash(task)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", 42),
        ("description", ["not", "text"]),
        ("labels", "not-a-list"),
        ("labels", ["ok", 3]),
        ("urls", ("https://example.test",)),
        ("depends_on", [None]),
        ("execution_requirements", "not-a-list"),
        ("execution_requirements", [{"kind": "mount"}]),
        ("workstream_contract", {}),
        ("plan_receipt", {}),
    ],
)
def test_contract_rejects_unsupported_field_types(field: str, value: object) -> None:
    task = _task()
    task[field] = value
    with pytest.raises(ExecutionContractError, match=field):
        execution_contract_payload(task)


def test_contract_rejects_arbitrary_objects() -> None:
    with pytest.raises(ExecutionContractError, match="mapping or validated Task"):
        execution_contract_hash(object())
