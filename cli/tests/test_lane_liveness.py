from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("lane_liveness", ROOT / "scripts" / "lane-liveness.py")
assert SPEC and SPEC.loader
lane_liveness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lane_liveness)


def write_tasks(path: Path, tasks: list[dict]) -> None:
    if not tasks:
        path.joinpath("tasks.yaml").write_text("tasks: []\n")
        return
    path.joinpath("tasks.yaml").write_text("tasks:\n" + "\n".join(f"  - {task!r}" for task in tasks) + "\n")


def test_idle_catalog_lanes_are_not_failures(tmp_path, monkeypatch):
    write_tasks(tmp_path, [])
    monkeypatch.setattr(lane_liveness, "ROOT", tmp_path)
    monkeypatch.setattr(lane_liveness, "VENDORS", (SimpleNamespace(name="codex"),))

    report = lane_liveness.evaluate(tmp_path, "codex", datetime(2026, 9, 15, tzinfo=timezone.utc), 24)

    assert report["status"] == "pass"
    assert report["lanes"][0]["state"] == "idle"


def test_recent_and_stale_tasks_are_distinguished(tmp_path, monkeypatch):
    # Use YAML rather than Python repr so this fixture matches the production projection.
    tmp_path.joinpath("tasks.yaml").write_text(
        "tasks:\n"
        "  - id: recent\n"
        "    target_agent: codex\n"
        "    status: in_progress\n"
        "    dispatch_log:\n"
        "      - timestamp: '2026-09-15T12:00:00Z'\n"
        "  - id: old\n"
        "    target_agent: claude\n"
        "    status: dispatched\n"
        "    dispatch_log:\n"
        "      - timestamp: '2026-09-13T00:00:00Z'\n"
    )
    monkeypatch.setattr(lane_liveness, "ROOT", tmp_path)
    monkeypatch.setattr(
        lane_liveness,
        "VENDORS",
        (SimpleNamespace(name="codex"), SimpleNamespace(name="claude")),
    )
    now = datetime(2026, 9, 15, 13, 0, tzinfo=timezone.utc)

    recent = lane_liveness.evaluate(tmp_path, "codex", now, 24)
    stale = lane_liveness.evaluate(tmp_path, "claude", now, 24)

    assert recent["status"] == "pass"
    assert recent["lanes"][0]["state"] == "active"
    assert stale["status"] == "fail"
    assert stale["lanes"][0]["state"] == "stalled"


def test_unreadable_projection_is_unmeasured(tmp_path, monkeypatch):
    monkeypatch.setattr(lane_liveness, "ROOT", tmp_path)
    monkeypatch.setattr(lane_liveness, "VENDORS", (SimpleNamespace(name="codex"),))
    tmp_path.joinpath("tasks.yaml").write_text("tasks: [")

    report = lane_liveness.evaluate(tmp_path, "codex", datetime.now(timezone.utc), 24)

    assert report["status"] == "fail"
    assert report["unmeasured"] is True
    assert report["lanes"][0]["state"] == "unmeasured"


@pytest.fixture(autouse=True)
def broker(monkeypatch, tmp_path):
    class Broker:
        def capabilities(self):
            return {"available": True}

        def task_run(self, task_id):
            return {"found": True, "root_run_id": task_id, "run_id": task_id}

        def graph(self, task_id):
            tasks = yaml.safe_load((tmp_path / "tasks.yaml").read_text())["tasks"]
            task = next(t for t in tasks if t["id"] == task_id)
            return {
                "nodes": [
                    {
                        "run_id": task_id,
                        "lease": {
                            "executor": {"agent": task.get("executor", task["target_agent"])},
                            "state": "active",
                            "heartbeat_at": task.get("heartbeat_at", task["dispatch_log"][0]["timestamp"]),
                            "hard_deadline": task.get("hard_deadline", "2099-01-01T00:00:00Z"),
                        },
                    }
                ]
            }

    monkeypatch.setattr("limen.conduct.client.client_from_env", Broker)


def test_unknown_lane_is_unmeasured(tmp_path):
    write_tasks(tmp_path, [])
    report = lane_liveness.evaluate(tmp_path, "invented", datetime.now(timezone.utc), 24)
    assert report["unmeasured"]


def test_stale_sibling_cannot_hide_behind_fresh_task(tmp_path):
    tasks = [
        {
            "id": name,
            "target_agent": "any",
            "executor": "codex",
            "status": "in_progress",
            "dispatch_log": [{"timestamp": stamp}],
        }
        for name, stamp in [("old", "2026-09-10T00:00:00Z"), ("new", "2026-09-15T12:00:00Z")]
    ]
    (tmp_path / "tasks.yaml").write_text(yaml.safe_dump({"tasks": tasks}))
    report = lane_liveness.evaluate(tmp_path, "codex", datetime(2026, 9, 15, 13, tzinfo=timezone.utc), 24)
    assert report["lanes"][0]["state"] == "stalled"
    assert report["lanes"][0]["active_tasks"] == 2


def test_receipt_replacement(tmp_path):
    path = tmp_path / "receipt.json"
    lane_liveness.write_receipt(path, {"status": "pass"})
    lane_liveness.write_receipt(path, {"status": "fail"})
    import json

    assert json.loads(path.read_text()) == {"status": "fail"}
    assert list(tmp_path.iterdir()) == [path]


def test_missing_private_custody_is_unmeasured(tmp_path, monkeypatch):
    def missing(_path):
        raise lane_liveness.PrivateCustodyUnavailable("missing")

    monkeypatch.setattr(lane_liveness, "board_path", missing)
    report = lane_liveness.evaluate(tmp_path, "codex", datetime.now(timezone.utc), 24)
    assert report["unmeasured"]
    assert report["status"] == "fail"


def test_broker_failure_is_unmeasured(tmp_path, monkeypatch):
    write_tasks(tmp_path, [])

    def unavailable():
        raise RuntimeError("offline")

    monkeypatch.setattr("limen.conduct.client.client_from_env", unavailable)
    assert lane_liveness.evaluate(tmp_path, "codex", datetime.now(timezone.utc), 24)["unmeasured"]


def test_doctor_uses_configured_runtime_root(tmp_path, monkeypatch):
    from limen.doctor import _lane_liveness

    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "lane-liveness.py").write_text("print(" + repr('{"status":"pass","source":"configured"}') + ")")
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    assert _lane_liveness(tmp_path / "tasks.yaml", "codex")["source"] == "configured"


def test_long_running_lease_uses_heartbeat_not_initial_transition(tmp_path):
    task = {
        "id": "long",
        "target_agent": "any",
        "executor": "codex",
        "status": "in_progress",
        "dispatch_log": [{"timestamp": "2026-08-01T00:00:00Z"}],
        "heartbeat_at": "2026-09-15T12:00:00Z",
    }
    (tmp_path / "tasks.yaml").write_text(yaml.safe_dump({"tasks": [task]}))
    report = lane_liveness.evaluate(tmp_path, "codex", datetime(2026, 9, 15, 13, tzinfo=timezone.utc), 24)
    assert report["lanes"][0]["state"] == "active"


@pytest.mark.parametrize(
    "tasks",
    [
        [{"id": "bad", "status": "invented", "target_agent": "codex"}],
        [{"id": "dup", "status": "open", "target_agent": "codex"}] * 2,
    ],
)
def test_malformed_projection_is_not_idle(tmp_path, tasks):
    (tmp_path / "tasks.yaml").write_text(yaml.safe_dump({"tasks": tasks}))
    assert lane_liveness.evaluate(tmp_path, "codex", datetime.now(timezone.utc), 24)["unmeasured"]
