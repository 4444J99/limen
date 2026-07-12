from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "claim-task.py"


def load_claim_module():
    spec = importlib.util.spec_from_file_location("claim_task", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def board(budget_cost=2):
    return {
        "portal": {"budget": {"track": {"spent": 3, "per_agent": {"codex": 1}}}},
        "tasks": [
            {
                "id": "TASK-1",
                "title": "Claim me",
                "repo": "organvm/limen",
                "target_agent": "any",
                "status": "open",
                "budget_cost": budget_cost,
                "dispatch_log": [],
            }
        ],
    }


def test_claim_task_reserves_open_task_and_budget() -> None:
    claim = load_claim_module()
    data = board()

    task = claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert task["target_agent"] == "codex"
    assert task["status"] == "dispatched"
    assert data["portal"]["budget"]["track"]["spent"] == 5
    assert data["portal"]["budget"]["track"]["per_agent"]["codex"] == 3
    assert task["dispatch_log"][-1]["session_id"] == "session-1"
    assert task["predicate"] and task["receipt_target"]


def test_claim_task_rejects_unknown_agent_without_mutating() -> None:
    claim = load_claim_module()
    data = board()
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit):
        claim.claim_task(data, "TASK-1", "goose", "session-1")

    assert data == before


def test_claim_task_rejects_malformed_budget_without_mutating() -> None:
    claim = load_claim_module()
    data = board(budget_cost="not-an-int")
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_claim_task_rejects_boolean_budget_without_mutating() -> None:
    claim = load_claim_module()
    data = board(budget_cost=False)
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_claim_task_fails_closed_when_legacy_owner_cannot_be_derived() -> None:
    claim = load_claim_module()
    data = board()
    data["tasks"][0].pop("repo")
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit, match="typed intake blocked"):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before
