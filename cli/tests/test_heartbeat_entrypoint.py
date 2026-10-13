import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from limen import entrypoint

ROOT = Path(__file__).resolve().parents[2]


def test_scheduled_console_path_avoids_unrelated_cli_import(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["limen", "heartbeat", "--once"])
    monkeypatch.setattr(entrypoint, "_scheduled_heartbeat", lambda **_kwargs: 7)
    assert entrypoint.main() == 7


def test_invalid_baseline_state_reaches_existing_engine_failure_handler(monkeypatch):
    from limen import heartbeat, heartbeat_state

    def invalid(_path):
        raise heartbeat_state.HeartbeatContractError("heartbeat state is unreadable")

    called = []
    monkeypatch.setattr(heartbeat_state, "_read_state", invalid)
    monkeypatch.setattr(heartbeat, "heartbeat_once", lambda *a, **kw: called.append(True) or {"status": "failed"})
    assert entrypoint._scheduled_heartbeat() == 1
    assert called == [True]


def test_whole_tick_deadline_unwinds_owned_child_before_failure_receipt(tmp_path):
    pid_file = tmp_path / "child.pid"
    script = """
import json, subprocess, sys, time
from pathlib import Path
from limen import entrypoint, heartbeat, heartbeat_state, bounded_subprocess
real = subprocess.Popen
def capture(*args, **kwargs):
    child = real(*args, **kwargs)
    Path(sys.argv[1]).write_text(str(child.pid))
    return child
bounded_subprocess.subprocess.Popen = capture
heartbeat_state._read_state = lambda _path: {'consecutive_system_failures': 2}
def work(root, **kwargs):
    return bounded_subprocess.run_bounded_subprocess([sys.executable, '-c', 'import time; time.sleep(30)'],
        cwd=root, timeout_seconds=30, stdout_ceiling=1024, stderr_ceiling=1024)
heartbeat.heartbeat_once = work
def record(root, state_root, duration, previous):
    assert previous == 2 and duration >= 350
    return {'status': 'failed', 'probe': None}
heartbeat_state.record_tick_timeout = record
raise SystemExit(entrypoint._scheduled_heartbeat(wall_seconds=0.6))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(pid_file)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "cli/src"), "LIMEN_HEARTBEAT_STATE_ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1, result.stderr
    assert "heartbeat: failed" in result.stdout
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_file.read_text()), 0)


def test_whole_tick_deadline_includes_blocked_output(tmp_path):
    script = """
import builtins, time
from limen import entrypoint, heartbeat, heartbeat_state
heartbeat_state._read_state = lambda _path: {'consecutive_system_failures': 0}
heartbeat.heartbeat_once = lambda *args, **kwargs: {'status': 'passed'}
heartbeat_state.record_tick_timeout = lambda *args: {'status': 'failed'}
builtins.print = lambda *args, **kwargs: time.sleep(30)
raise SystemExit(entrypoint._scheduled_heartbeat(wall_seconds=0.6))
"""
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "cli/src"), "LIMEN_HEARTBEAT_STATE_ROOT": str(tmp_path)},
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 78
    assert time.monotonic() - started < 5


def test_engine_import_timeout_records_failure_and_enacts_kill_switch(tmp_path):
    script = """
import builtins, json, sys, time
from pathlib import Path
from limen import entrypoint, heartbeat_state
state_root = Path(sys.argv[1])
heartbeat_state._atomic_json(state_root / 'state.json', {
    'schema': heartbeat_state.STATE_SCHEMA, 'consecutive_system_failures': 2,
    'disabled': False, 'probes': {}, 'notification_conditions': {}})
heartbeat_state._disable_launch_agent = lambda: (state_root / 'disabled.marker').write_text('owned label disabled')
original_import = builtins.__import__
def stalled_import(name, *args, **kwargs):
    if name == 'limen.host_admission':
        time.sleep(30)
    return original_import(name, *args, **kwargs)
builtins.__import__ = stalled_import
raise SystemExit(entrypoint._scheduled_heartbeat(wall_seconds=2))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "cli/src"), "LIMEN_HEARTBEAT_STATE_ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1, result.stderr
    import json

    state = json.loads((tmp_path / "state.json").read_text())
    assert state["consecutive_system_failures"] == 3 and state["disabled"]
    assert (tmp_path / "disabled.marker").is_file()
    receipts = list((tmp_path / "receipts").glob("*.json"))
    assert len(receipts) == 1
    assert json.loads(receipts[0].read_text())["reason"] == "tick_wall_timeout"
