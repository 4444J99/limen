import datetime
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relpath)
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
