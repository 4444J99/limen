import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))
from limen.io import load_limen_file

# Add scripts dir to path to import the script for testing
sys.path.insert(0, str(ROOT / "scripts"))

import importlib.util

spec = importlib.util.spec_from_file_location("insight_route", str(ROOT / "scripts" / "insight-route.py"))
insight_route = importlib.util.module_from_spec(spec)
# Add to sys.modules so patch can find it
sys.modules["insight_route"] = insight_route
spec.loader.exec_module(insight_route)


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    # Isolate from the fleet env: a leaked LIMEN_TICKETS_PRODUCE=1 would silently
    # flip the repo route onto the keeper path and break the legacy-path asserts.
    monkeypatch.delenv("LIMEN_TICKETS_PRODUCE", raising=False)
    monkeypatch.delenv("LIMEN_INSIGHT_ROUTE_APPLY", raising=False)
    monkeypatch.delenv("LIMEN_INSIGHT_ROUTE_MAX", raising=False)
    # Setup test environment with paths inside tmp_path
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    cadence_dir = logs_dir / "insight-cadence"
    cadence_dir.mkdir()

    tasks_yaml = tmp_path / "tasks.yaml"
    # Seed tasks.yaml
    tasks_yaml.write_text("""
version: '1.0'
portal:
  name: Universal Task Intake
  description: ''
  budget:
    daily: 100
    unit: runs
    per_agent: {}
    track:
      date: ''
      spent: 0
      per_agent: {}
      per_agent_reset: {}
tasks: []
""")

    his_hand_file = tmp_path / "his-hand-levers.json"
    his_hand_file.write_text('{"levers": []}')

    return {"logs": logs_dir, "cadence": cadence_dir, "tasks": tasks_yaml, "his_hand": his_hand_file, "root": tmp_path}


def test_insight_routing_repo(test_env):
    insight = {
        "id": "INS-REPO-1",
        "severity": "warning",
        "title": "Repo Insight",
        "detail": "Some detail",
        "owner": "test-org/test-repo",
        "source": "test",
        "suggested_action": "Fix it",
        "healable": True,
    }

    report = {
        "tier": "hourly",
        "generated_at": "2024-01-01T00:00:00Z",
        "window_start": "2024-01-01T00:00:00Z",
        "insights": [insight],
    }

    report_file = test_env["cadence"] / "hourly-test.json"
    report_file.write_text(json.dumps(report))

    with (
        patch("insight_route.TASKS_YAML", test_env["tasks"]),
        patch("insight_route.HIS_HAND_FILE", test_env["his_hand"]),
        patch("insight_route.LOGS_DIR", test_env["logs"]),
    ):
        insight_route.process_report(report_file, apply=True)

        limen_file = load_limen_file(test_env["tasks"])
        assert len(limen_file.tasks) == 0
        inbox = test_env["root"] / "logs" / "tickets" / "inbox"
        tickets = list(inbox.glob("*.json"))
        assert len(tickets) == 1
        ticket = json.loads(tickets[0].read_text())
        assert ticket["task_id"] == "TASK-INS-REPO-1"
        assert ticket["intent"] == "task.upsert"
        assert ticket["patch"]["repo"] == "test-org/test-repo"
        assert ticket["patch"]["title"] == "Heal insight: Repo Insight"

        # Test idempotency
        insight_route.process_report(report_file, apply=True)
        assert len(list(inbox.glob("*.json"))) == 1


def test_insight_routing_organ(test_env):
    insight = {
        "id": "INS-ORG-1",
        "severity": "info",
        "title": "Organ Insight",
        "detail": "Detail",
        "owner": "test-organ",
        "source": "test",
        "suggested_action": "Action",
    }

    report = {"insights": [insight]}

    report_file = test_env["cadence"] / "daily-test.json"
    report_file.write_text(json.dumps(report))

    with (
        patch("insight_route.TASKS_YAML", test_env["tasks"]),
        patch("insight_route.HIS_HAND_FILE", test_env["his_hand"]),
        patch("insight_route.LOGS_DIR", test_env["logs"]),
    ):
        insight_route.process_report(report_file, apply=True)

        residual_file = test_env["logs"] / "test-organ-residual.json"
        assert residual_file.exists()

        data = json.loads(residual_file.read_text())
        assert len(data) == 1
        assert data[0]["id"] == "INS-ORG-1"

        # Idempotency
        insight_route.process_report(report_file, apply=True)
        data = json.loads(residual_file.read_text())
        assert len(data) == 1


@patch("subprocess.run")
def test_insight_routing_anthony(mock_run, test_env):
    insight = {
        "id": "INS-ANTHONY-1",
        "severity": "high",
        "title": "Human Insight",
        "detail": "Requires human",
        "owner": "anthony",
        "source": "test",
        "suggested_action": "Do something",
    }

    report = {"insights": [insight]}

    report_file = test_env["cadence"] / "weekly-test.json"
    report_file.write_text(json.dumps(report))

    with (
        patch("insight_route.TASKS_YAML", test_env["tasks"]),
        patch("insight_route.HIS_HAND_FILE", test_env["his_hand"]),
        patch("insight_route.LOGS_DIR", test_env["logs"]),
    ):
        insight_route.process_report(report_file, apply=True)

        data = json.loads(test_env["his_hand"].read_text())
        assert len(data["levers"]) == 1
        lever = data["levers"][0]
        assert lever["id"] == "INS-ANTHONY-1"
        assert lever["owner"] == "yours"
        assert mock_run.called

        # Idempotency
        mock_run.reset_mock()
        insight_route.process_report(report_file, apply=True)
        data = json.loads(test_env["his_hand"].read_text())
        assert len(data["levers"]) == 1
        assert not mock_run.called


def test_dry_run(test_env):
    insight = {
        "id": "INS-DRY-1",
        "severity": "info",
        "title": "Dry Insight",
        "detail": "Detail",
        "owner": "test-organ",
        "source": "test",
        "suggested_action": "Action",
    }

    report = {"insights": [insight]}

    report_file = test_env["cadence"] / "daily-test.json"
    report_file.write_text(json.dumps(report))

    with (
        patch("insight_route.TASKS_YAML", test_env["tasks"]),
        patch("insight_route.HIS_HAND_FILE", test_env["his_hand"]),
        patch("insight_route.LOGS_DIR", test_env["logs"]),
    ):
        insight_route.process_report(report_file, apply=False)

        residual_file = test_env["logs"] / "test-organ-residual.json"
        assert not residual_file.exists()


def _repo_insight(iid, source="test"):
    return {
        "id": iid,
        "severity": "warning",
        "title": f"Insight {iid}",
        "detail": "Detail",
        "owner": "test-org/test-repo",
        "source": source,
        "suggested_action": "Fix it",
    }


def test_board_echo_skipped(test_env):
    # An insight sourced from the board itself is an echo of a task the board
    # already records — it must never become a heal-twin task.
    report = {"insights": [_repo_insight("INS-ECHO-1", source="tasks.yaml")]}
    report_file = test_env["cadence"] / "hourly-echo.json"
    report_file.write_text(json.dumps(report))

    stats = {"cap_left": 5, "created": 0, "echo": 0, "deferred": 0}
    with (
        patch("insight_route.TASKS_YAML", test_env["tasks"]),
        patch("insight_route.HIS_HAND_FILE", test_env["his_hand"]),
        patch("insight_route.LOGS_DIR", test_env["logs"]),
    ):
        insight_route.process_report(report_file, apply=True, stats=stats)

    limen_file = load_limen_file(test_env["tasks"])
    assert len(limen_file.tasks) == 0
    assert stats["echo"] == 1
    assert stats["created"] == 0


def test_cap_defers_overflow(test_env, monkeypatch):
    report = {"insights": [_repo_insight(f"INS-CAP-{i}") for i in range(3)]}
    report_file = test_env["cadence"] / "hourly-cap.json"
    report_file.write_text(json.dumps(report))

    stats = {"cap_left": 1, "created": 0, "echo": 0, "deferred": 0}
    with (
        patch("insight_route.TASKS_YAML", test_env["tasks"]),
        patch("insight_route.HIS_HAND_FILE", test_env["his_hand"]),
        patch("insight_route.LOGS_DIR", test_env["logs"]),
    ):
        insight_route.process_report(report_file, apply=True, stats=stats)

    limen_file = load_limen_file(test_env["tasks"])
    assert len(limen_file.tasks) == 0
    inbox = test_env["root"] / "logs" / "tickets" / "inbox"
    assert len(list(inbox.glob("*.json"))) == 1
    from limen.tabularius import drain_once

    drain_once(test_env["tasks"])
    limen_file = load_limen_file(test_env["tasks"])
    assert len(limen_file.tasks) == 1
    assert stats["created"] == 1
    assert stats["deferred"] == 2


def test_keeper_path_submits_ticket_not_board_write(test_env, monkeypatch):
    # With the TABVLARIVS producer flag on, a repo insight becomes an upsert
    # ticket in the inbox and the board file itself stays untouched.
    monkeypatch.setenv("LIMEN_TICKETS_PRODUCE", "1")
    report = {"insights": [_repo_insight("INS-KEEPER-1")]}
    report_file = test_env["cadence"] / "hourly-keeper.json"
    report_file.write_text(json.dumps(report))

    with (
        patch("insight_route.TASKS_YAML", test_env["tasks"]),
        patch("insight_route.HIS_HAND_FILE", test_env["his_hand"]),
        patch("insight_route.LOGS_DIR", test_env["logs"]),
    ):
        insight_route.process_report(report_file, apply=True)

    limen_file = load_limen_file(test_env["tasks"])
    assert len(limen_file.tasks) == 0
    inbox = test_env["root"] / "logs" / "tickets" / "inbox"
    tickets = list(inbox.glob("*.json"))
    assert len(tickets) == 1
    ticket = json.loads(tickets[0].read_text())
    assert ticket["task_id"] == "TASK-INS-KEEPER-1"
    assert ticket["intent"] == "task.upsert"


def test_latest_reports_picks_true_latest_per_tier(test_env):
    # Stamp formats changed over time; lexical sort would pick 20260626T135356
    # over 2026-07-03T133909+0000. The selector must order on the digit prefix.
    cadence = test_env["cadence"]
    for name in (
        "hourly-20260626T135356.json",
        "hourly-2026-07-03T133909+0000.json",
        "daily-20260625T223909.json",
    ):
        (cadence / name).write_text(json.dumps({"insights": []}))

    picked = {p.name for p in insight_route.latest_reports(cadence)}
    assert picked == {
        "hourly-2026-07-03T133909+0000.json",
        "daily-20260625T223909.json",
    }
