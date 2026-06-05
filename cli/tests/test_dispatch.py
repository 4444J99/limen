from __future__ import annotations

import sys
import os
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from limen.dispatch import dispatch_tasks, release_stale_tasks
from limen.doctor import qa_report, readiness_report, stale_tasks
from limen.io import load_limen_file
from limen.status import print_status


def write_board(path: Path, tasks: list[dict]) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "name": "Universal Task Intake",
                    "budget": {
                        "daily": 100,
                        "unit": "runs",
                        "per_agent": {"jules": 100, "codex": 2},
                        "track": {"date": "", "spent": 0, "per_agent": {}},
                    },
                },
                "tasks": tasks,
            },
            sort_keys=False,
        )
    )


def read_board(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def test_release_stale_dry_run_does_not_mutate(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-001",
                "title": "Stale Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-01T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "test",
                        "status": "dispatched",
                    }
                ],
            }
        ],
    )
    before = tasks_path.read_text()

    release_stale_tasks(load_limen_file(tasks_path), tasks_path, hours=24, dry_run=True)

    assert tasks_path.read_text() == before


def test_release_stale_apply_reopens_task(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-002",
                "title": "Stale Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "in_progress",
                "created": "2026-06-01",
                "dispatch_log": [],
            }
        ],
    )

    report = release_stale_tasks(load_limen_file(tasks_path), tasks_path, hours=24, dry_run=False)

    task = read_board(tasks_path)["tasks"][0]
    assert task["status"] == "open"
    assert task["dispatch_log"][-1]["status"] == "open"
    assert report["status"] == "applied"
    assert report["count"] == 1
    assert report["released"] == ["LIMEN-002"]


def test_dispatch_limit_and_per_agent_budget(tmp_path: Path, monkeypatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    dispatch_bin = tmp_path / "agent-dispatch"
    dispatch_bin.write_text("#!/bin/sh\nexit 0\n")
    dispatch_bin.chmod(0o755)
    monkeypatch.setenv("LIMEN_DISPATCH_CMD", str(dispatch_bin))
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-003",
                "title": "Open Codex task one",
                "repo": "4444J99/limen",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-004",
                "title": "Open Codex task two",
                "repo": "4444J99/limen",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-005",
                "title": "Open Codex task three",
                "repo": "4444J99/limen",
                "target_agent": "codex",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
        ],
    )

    dispatch_tasks(load_limen_file(tasks_path), tasks_path, agent="codex", dry_run=False, limit=3)

    board = read_board(tasks_path)
    statuses = {task["id"]: task["status"] for task in board["tasks"]}
    assert statuses == {"LIMEN-003": "dispatched", "LIMEN-004": "dispatched", "LIMEN-005": "open"}
    assert board["portal"]["budget"]["track"]["per_agent"]["codex"] == 2


def test_status_prints_creation_age_and_recorded_throughput(tmp_path: Path, capsys) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-AGE-001",
                "title": "Completed task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "done",
                "created": "2026-05-31",
                "dispatch_log": [
                    {
                        "timestamp": "2026-05-31T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "test",
                        "status": "dispatched",
                    },
                    {
                        "timestamp": "2026-05-31T01:00:00+00:00",
                        "agent": "jules",
                        "session_id": "test",
                        "status": "done",
                    },
                ],
            },
            {
                "id": "LIMEN-AGE-002",
                "title": "Active task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            },
        ],
    )

    print_status(load_limen_file(tasks_path))

    output = capsys.readouterr().out
    assert "Throughput: created 2026-05-31 ->" in output
    assert "capacity 100/day" in output
    assert "recorded: 2 log events, 1 starts, 1 finishes, 1 done, 1 not done" in output


def test_readiness_report_flags_stale_claims_and_next_actions(tmp_path: Path, monkeypatch) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    dispatch_bin = tmp_path / "jules"
    dispatch_bin.write_text("#!/bin/sh\nexit 0\n")
    dispatch_bin.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-006",
                "title": "Stale Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "critical",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-007",
                "title": "Open Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "critical",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
        ],
    )
    limen = load_limen_file(tasks_path)

    report = readiness_report(limen, tasks_path, agent="jules")

    assert len(stale_tasks(limen, agent="jules")) == 1
    assert report["status"] == "degraded"
    assert report["counts"]["stale"] == 1
    assert "limen release-stale --agent jules --hours 24 --apply" in report["next_actions"]
    assert any(action.startswith("limen dispatch --agent jules") for action in report["next_actions"])


def test_release_stale_report_dry_run_does_not_mutate(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-008",
                "title": "Stale Jules task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "created": "2026-06-01",
                "dispatch_log": [],
            }
        ],
    )
    before = tasks_path.read_text()

    report = release_stale_tasks(load_limen_file(tasks_path), tasks_path, hours=24, dry_run=True, agent="jules")

    assert report["status"] == "dry_run"
    assert report["count"] == 1
    assert report["candidates"][0]["id"] == "LIMEN-008"
    assert tasks_path.read_text() == before


def test_qa_report_derives_lifecycle_without_mutation_or_private_fields(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    write_board(
        tasks_path,
        [
            {
                "id": "LIMEN-009",
                "title": "Recover task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "high",
                "budget_cost": 1,
                "status": "dispatched",
                "context": "private context must not leak",
                "urls": ["https://github.com/4444J99/limen/issues/9"],
                "created": "2026-06-01",
                "dispatch_log": [
                    {
                        "timestamp": "2026-06-01T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "private-session",
                        "status": "dispatched",
                    }
                ],
            },
            {
                "id": "LIMEN-010",
                "title": "Verify task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "medium",
                "budget_cost": 1,
                "status": "in_progress",
                "urls": ["https://github.com/4444J99/limen/pull/10"],
                "created": "2026-06-03",
                "dispatch_log": [
                    {
                        "timestamp": "2099-06-03T00:00:00+00:00",
                        "agent": "jules",
                        "session_id": "private-session",
                        "status": "in_progress",
                    }
                ],
            },
            {
                "id": "LIMEN-011",
                "title": "Assign task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "low",
                "budget_cost": 1,
                "status": "open",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
            {
                "id": "LIMEN-012",
                "title": "Archive task",
                "repo": "4444J99/limen",
                "target_agent": "jules",
                "priority": "low",
                "budget_cost": 1,
                "status": "done",
                "created": "2026-06-03",
                "dispatch_log": [],
            },
        ],
    )
    before = tasks_path.read_text()

    report = qa_report(load_limen_file(tasks_path), tasks_path, agent="jules")

    assert report["status"] == "degraded"
    assert report["lifecycle"] == {
        "total": 4,
        "assign": 1,
        "verify": 1,
        "recover": 1,
        "archive_ready": 1,
        "archived": 0,
    }
    assert [item["id"] for item in report["steering"]["next_batch"]] == ["LIMEN-009", "LIMEN-010", "LIMEN-011"]
    text = str(report)
    assert "private context must not leak" not in text
    assert "private-session" not in text
    assert "https://github.com/4444J99/limen/pull/10" not in text
    assert {mechanism["id"] for mechanism in report["mechanisms"]} == {
        "release-stale",
        "qa-verify",
        "assign-next",
        "archive-done",
    }
    mechanisms = {mechanism["id"]: mechanism for mechanism in report["mechanisms"]}
    assert mechanisms["release-stale"]["command"] == "POST /api/release-stale?hours=24&dry_run=false"
    assert mechanisms["qa-verify"]["command"] == "POST /api/tasks/{task_id}/verify"
    assert mechanisms["qa-verify"]["mode"] == "human-approved evidence gate"
    assert mechanisms["assign-next"]["command"] == "POST /api/tasks/{task_id}/assign"
    assert mechanisms["archive-done"]["command"] == "POST /api/tasks/{task_id}/archive"
    assert tasks_path.read_text() == before
