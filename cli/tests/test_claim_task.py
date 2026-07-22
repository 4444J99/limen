from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import limen.tabularius as tabularius
import pytest
import yaml
from limen.conduct.client import BrokerUnavailable


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "claim-task.py"


def load_claim_module():
    spec = importlib.util.spec_from_file_location("claim_task", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def board(budget_cost=2):
    return {
        "portal": {
            "budget": {
                "track": {
                    "date": "2026-07-18",
                    "spent": 3,
                    "per_agent": {"codex": 1},
                }
            }
        },
        "tasks": [
            {
                "id": "TASK-1",
                "title": "Claim me",
                "repo": "organvm/limen",
                "target_agent": "any",
                "status": "open",
                "budget_cost": budget_cost,
                "origin": "human_prompt",
                "horizon": "present",
                "value_case": "Reserve one bounded claim through the authenticated broker",
                "owner_surface": "organvm/limen",
                "predicate": "pytest -q cli/tests/test_claim_task.py",
                "receipt_target": "github:organvm/limen:pull-request:TASK-1",
                "created": "2026-07-18",
                "dispatch_log": [],
            }
        ],
    }


class FakeClaimBroker:
    def __init__(self, task):
        self.task = dict(task)
        self.sessions = []
        self.packets = []

    def register(self, session):
        self.sessions.append(session)
        return {"status": "registered"}

    def submit(self, packet):
        self.packets.append(packet)
        intent = dict(packet.intent)
        projected = {**self.task, **dict(intent["patch"])}
        projected["id"] = intent["task_id"]
        self.task = projected
        return {
            "status": "accepted",
            "projection_receipts": [{"task_id": projected["id"], "task": projected}],
        }


def write_tasks(path: Path) -> bytes:
    path.write_text(yaml.safe_dump(board(), sort_keys=False))
    return path.read_bytes()


def test_claim_task_reserves_open_task_and_budget() -> None:
    claim = load_claim_module()
    data = board()

    task = claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert task["target_agent"] == "any"
    assert task["status"] == "dispatched"
    assert data["portal"]["budget"]["track"]["spent"] == 5
    assert data["portal"]["budget"]["track"]["per_agent"]["codex"] == 3
    assert task["dispatch_log"][-1]["session_id"] == "session-1"
    assert task["dispatch_log"][-1]["agent"] == "codex"
    assert task["predicate"] and task["receipt_target"]


def test_claim_task_rejects_unknown_agent_without_mutating() -> None:
    claim = load_claim_module()
    data = board()
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit):
        claim.claim_task(data, "TASK-1", "goose", "session-1")

    assert data == before


def test_claim_task_uses_latest_route_receipt_without_rewriting_owner() -> None:
    claim = load_claim_module()
    data = board()
    data["tasks"][0]["target_agent"] = "codex"
    data["tasks"][0]["dispatch_log"] = [
        {
            "timestamp": "2026-07-18T12:00:00Z",
            "agent": "codex",
            "session_id": "prior",
            "status": "open",
            "route_to": "opencode",
        }
    ]

    task = claim.claim_task(data, "TASK-1", "opencode", "session-2")

    assert task["target_agent"] == "codex"
    assert task["status"] == "dispatched"
    assert task["dispatch_log"][-1]["agent"] == "opencode"


def test_claim_task_rejects_successor_required_open_row_without_mutating() -> None:
    claim = load_claim_module()
    data = board()
    data["tasks"][0]["labels"] = ["workstream:successor-required"]
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit, match="separately admitted successor"):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_claim_task_rejects_malformed_budget_without_mutating() -> None:
    claim = load_claim_module()
    data = board(budget_cost="not-an-int")
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_claim_task_rejects_missing_underwriting_in_stable_order_without_mutating() -> None:
    claim = load_claim_module()
    data = board()
    for field in ("origin", "horizon", "value_case"):
        data["tasks"][0].pop(field)
    before = copy.deepcopy(data)

    with pytest.raises(
        SystemExit,
        match="^task-not-underwritten:source_origin,horizon,value_case$",
    ):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_claim_task_rejects_boolean_budget_without_mutating() -> None:
    claim = load_claim_module()
    data = board(budget_cost=False)
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_claim_task_rejects_unavailable_runtime_without_mutating(monkeypatch) -> None:
    claim = load_claim_module()
    data = board()
    data["tasks"][0]["execution_requirements"] = [{"kind": "mount", "path": "/runtime/unavailable"}]
    before = copy.deepcopy(data)
    monkeypatch.setattr(claim.runtime_requirements.os.path, "ismount", lambda _path: False)

    with pytest.raises(SystemExit, match="runtime requirements blocked TASK-1"):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_claim_task_accepts_available_explicit_mount(monkeypatch) -> None:
    claim = load_claim_module()
    data = board()
    data["tasks"][0]["execution_requirements"] = [{"kind": "mount", "path": "/runtime/available"}]
    monkeypatch.setattr(
        claim.runtime_requirements.os.path,
        "ismount",
        lambda path: path == "/runtime/available",
    )

    task = claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert task["status"] == "dispatched"
    assert data["portal"]["budget"]["track"]["spent"] == 5


def test_claim_task_fails_closed_when_legacy_owner_cannot_be_derived() -> None:
    claim = load_claim_module()
    data = board()
    data["tasks"][0].pop("repo")
    data["tasks"][0].pop("owner_surface")
    before = copy.deepcopy(data)

    with pytest.raises(SystemExit, match="task-not-underwritten:owner_surface"):
        claim.claim_task(data, "TASK-1", "codex", "session-1")

    assert data == before


def test_live_claim_uses_broker_receipt_and_keeps_local_projection_byte_identical(
    tmp_path, monkeypatch, capsys
) -> None:
    claim = load_claim_module()
    tasks_path = tmp_path / "tasks.yaml"
    before = write_tasks(tasks_path)
    owner = FakeClaimBroker(board()["tasks"][0])
    monkeypatch.setattr(tabularius, "client_from_env", lambda: owner)
    monkeypatch.setattr(
        claim.sys,
        "argv",
        [
            "claim-task.py",
            "TASK-1",
            "codex",
            "--tasks",
            str(tasks_path),
            "--session-id",
            "live-session",
            "--live",
        ],
    )

    assert claim.main() == 0

    assert tasks_path.read_bytes() == before
    assert len(owner.sessions) == 1
    assert len(owner.packets) == 1
    intent = owner.packets[0].intent
    assert intent["kind"] == "task.claim"
    assert intent["expected_status"] == "open"
    assert "target_agent" not in intent["patch"]
    assert intent["patch"]["status"] == "dispatched"
    assert "budget_debit" not in intent
    assert owner.task["status"] == "dispatched"
    assert "canonical conduct broker" in capsys.readouterr().out


def test_live_claim_fails_closed_when_broker_is_unavailable(tmp_path, monkeypatch) -> None:
    claim = load_claim_module()
    tasks_path = tmp_path / "tasks.yaml"
    before = write_tasks(tasks_path)

    def unavailable():
        raise BrokerUnavailable("test broker unavailable")

    monkeypatch.setattr(tabularius, "client_from_env", unavailable)
    monkeypatch.setattr(
        claim.sys,
        "argv",
        [
            "claim-task.py",
            "TASK-1",
            "codex",
            "--tasks",
            str(tasks_path),
            "--session-id",
            "blocked-session",
            "--live",
        ],
    )

    with pytest.raises(BrokerUnavailable, match="test broker unavailable"):
        claim.main()

    assert tasks_path.read_bytes() == before


def test_dry_run_remains_a_local_preview_without_contacting_broker(tmp_path, monkeypatch, capsys) -> None:
    claim = load_claim_module()
    tasks_path = tmp_path / "tasks.yaml"
    before = write_tasks(tasks_path)

    def unexpected_broker():
        raise AssertionError("dry-run must not contact the conduct broker")

    monkeypatch.setattr(tabularius, "client_from_env", unexpected_broker)
    monkeypatch.setattr(
        claim.sys,
        "argv",
        [
            "claim-task.py",
            "TASK-1",
            "codex",
            "--tasks",
            str(tasks_path),
            "--session-id",
            "preview-session",
        ],
    )

    assert claim.main() == 0

    assert tasks_path.read_bytes() == before
    assert "DRY-RUN claim" in capsys.readouterr().out
