"""Tests for scripts/overnight-watch.py.

The monitor is deliberately one-shot by default: launchd can run it cheaply
without keeping an interactive agent conversation open for hours.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "overnight-watch.py"


class _CP:
    def __init__(self, args, rc=0, stdout="", stderr=""):
        self.args = args
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def _fresh_module(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    (tmp_path / "logs" / "async-runs").mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("overnight_watch_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _launchd_output(*, state="active", async_env="1", lanes="auto"):
    return f"""
state = {state}
pid = 4242
last exit code = (never exited)
environment = {{
    LIMEN_DISPATCH_ASYNC => {async_env}
    LIMEN_DISPATCH_LANES => {lanes}
}}
"""


def _mock_launchd(module, monkeypatch, stdout=None, rc=0):
    def fake_run(args, timeout=10):
        if args[:2] == ["launchctl", "print"]:
            return _CP(args, rc=rc, stdout=stdout if stdout is not None else _launchd_output())
        return _CP(args, rc=1, stderr="unexpected command")

    monkeypatch.setattr(module, "run", fake_run)


def _write_heartbeat(module, tick="2026-07-01T09:53:57+00:00", open_count=63):
    module.HEARTBEAT_LOG.write_text(
        "\n".join(
            [
                "heartbeat-loop start",
                "──── beat 62 2026-07-01 05:50:29 ────",
                "  dispatch lanes: codex,claude,opencode,agy,gemini,github_actions from selector [auto]",
                "── async: reaped 0 dead · harvested 3 · 1 still running · launched 2 (cap 3) → ['A', 'B']",
                f"tick emitted: {tick} total=1555 open={open_count} spent=152/600",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_healthy_one_shot_writes_receipts(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)

    assert module.run_once(dry_run=False, json_output=False) == 0
    state = json.loads(module.STATE_PATH.read_text())
    assert state["status"] == "ok"
    assert module.RECEIPT_JSONL.exists()
    assert module.RECEIPT_MD.exists()
    assert not module.ALERT_PATH.exists()


def test_repeated_tick_alerts_when_no_workers(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch, LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS=2)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)
    module.STATE_PATH.write_text(
        json.dumps({"latest_tick": "2026-07-01T09:53:57+00:00", "stale_tick_count": 1}),
        encoding="utf-8",
    )

    snapshot = module.build_snapshot()
    assert snapshot["status"] == "alert"
    assert {alert["id"] for alert in snapshot["alerts"]} == {"heartbeat-progress-stale"}


def test_active_worker_suppresses_repeated_tick_alert(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch, LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS=2)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)
    module.STATE_PATH.write_text(
        json.dumps({"latest_tick": "2026-07-01T09:53:57+00:00", "stale_tick_count": 1}),
        encoding="utf-8",
    )
    (module.ASYNC_RUNS / "GEN-example__codex.running").write_text("{}", encoding="utf-8")

    snapshot = module.build_snapshot()
    assert snapshot["status"] == "ok"
    assert snapshot["worker_count"] == 1


def test_heartbeat_child_suppresses_repeated_tick_alert(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch, LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS=2)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)
    module.STATE_PATH.write_text(
        json.dumps({"latest_tick": "2026-07-01T09:53:57+00:00", "stale_tick_count": 1}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        module,
        "heartbeat_child_processes",
        lambda pid: [{"pid": "99", "command": "scripts/clone-maintenance.sh"}],
    )

    snapshot = module.build_snapshot()
    assert snapshot["status"] == "ok"
    assert snapshot["heartbeat_child_count"] == 1


def test_expected_env_mismatch_alerts(tmp_path, monkeypatch):
    module = _fresh_module(
        tmp_path,
        monkeypatch,
        LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_ASYNC=1,
        LIMEN_OVERNIGHT_WATCH_EXPECT_DISPATCH_LANES="auto",
    )
    _mock_launchd(module, monkeypatch, stdout=_launchd_output(async_env="0", lanes="codex"))
    _write_heartbeat(module)

    snapshot = module.build_snapshot()
    ids = {alert["id"] for alert in snapshot["alerts"]}
    assert "heartbeat-async-env-mismatch" in ids
    assert "heartbeat-lanes-env-mismatch" in ids


def test_alert_state_resolves(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch, LIMEN_OVERNIGHT_WATCH_MAX_STALE_TICKS=1)
    _mock_launchd(module, monkeypatch)
    _write_heartbeat(module)
    module.STATE_PATH.write_text(
        json.dumps({"latest_tick": "2026-07-01T09:53:57+00:00", "stale_tick_count": 0}),
        encoding="utf-8",
    )

    assert module.run_once(dry_run=False, json_output=False) == 1
    assert json.loads(module.ALERT_PATH.read_text())["active"] is True

    _write_heartbeat(module, tick="2026-07-01T10:02:43+00:00", open_count=65)
    assert module.run_once(dry_run=False, json_output=False) == 0
    assert json.loads(module.ALERT_PATH.read_text())["active"] is False
