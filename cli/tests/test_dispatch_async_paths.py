import datetime
import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "cli" / "src"))

from limen.models import Budget, BudgetTrack, LimenFile, Portal, Task  # noqa: E402


def _load_script(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_async_run_paths_preserve_slash_task_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    dispatch_async = _load_script("dispatch_async_paths_test", "scripts/dispatch-async.py")
    worker = _load_script("async_run_one_paths_test", "scripts/async-run-one.py")

    task_id = "TASK-LED-rev-organvm/the-invisibl"
    agent = "opencode"

    assert "/" not in dispatch_async._run_stem(task_id)
    assert dispatch_async._run_stem(task_id) == worker._run_stem(task_id)
    assert dispatch_async._run_log_path(task_id).parent == tmp_path / "logs" / "async-runs"
    assert worker._result_path(task_id).parent == tmp_path / "logs" / "async-runs"

    dispatch_async.RUNS.mkdir(parents=True)
    marker = dispatch_async._running_marker_path(task_id, agent)
    marker.write_text(
        json.dumps(
            {
                "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "agent": agent,
                "task_id": task_id,
                "pid": 999999,
            }
        )
    )
    dispatch_async._result_path(task_id).write_text(json.dumps({"task_id": task_id, "agent": agent, "result": True}))

    assert dispatch_async._running_task_ids() == {task_id}
    assert dispatch_async._result_task_ids() == {task_id}
    assert dispatch_async._running_for(agent) == 1
    assert dispatch_async._running_local() == 1

    dispatch_async._clear_running_markers(task_id)
    assert not marker.exists()


def _task(task_id: str, agent: str) -> Task:
    return Task(
        id=task_id,
        title=task_id,
        repo="organvm/example",
        target_agent=agent,
        created=datetime.date(2026, 7, 9),
    )


def test_async_reservation_uses_live_usage_not_stale_board_caps(monkeypatch, tmp_path):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    dispatch_async = _load_script("dispatch_async_usage_math_test", "scripts/dispatch-async.py")
    dispatch_async.RUNS.mkdir(parents=True)

    board = LimenFile(
        portal=Portal(
            budget=Budget(
                daily=1,
                per_agent={"jules": 1, "opencode": 1, "agy": 1},
                track=BudgetTrack(
                    date="2026-07-09",
                    spent=1,
                    per_agent={"jules": 1, "opencode": 1, "agy": 1},
                ),
            )
        ),
        tasks=[
            *[_task(f"JULES-{i}", "jules") for i in range(3)],
            *[_task(f"OPEN-{i}", "opencode") for i in range(3)],
            *[_task(f"AGY-{i}", "agy") for i in range(3)],
        ],
    )

    picked, _reset_changed = dispatch_async._pick_reservations(
        board,
        ["jules", "opencode", "agy"],
        per_agent=3,
        cap=4,
        dry=True,
        now=datetime.datetime(2026, 7, 9, tzinfo=datetime.timezone.utc),
        usage_remaining={"jules": 2, "opencode": 999},
        weak_proxy_agents={"agy"},
    )

    counts = {
        agent: sum(1 for picked_agent, _ in picked if picked_agent == agent) for agent in ("jules", "opencode", "agy")
    }
    assert counts["jules"] == 2
    assert counts["opencode"] > 0
    assert counts["agy"] > 0
