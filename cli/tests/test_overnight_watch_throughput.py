"""Tests for the overnight monitor's throughput-collapse predicate + effector.

2026-07-08 incident: the fleet idled a full night at ~5% of baseline while every liveness
alert stayed green. These tests pin the movement-vs-progress fix: a derived throughput floor
that fires only on genuine silent stall (open work, no sanctioned suppression), and an effector
that remediates rather than parking the alert on the operator.
"""

from __future__ import annotations

import datetime as dt
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
    # Fast, deterministic windows: 1-minute buckets so a handful of ticks spans enough windows.
    monkeypatch.setenv("LIMEN_THROUGHPUT_WINDOW_MIN", "1")
    for key, value in env.items():
        monkeypatch.setenv(key, str(value))
    (tmp_path / "logs" / "async-runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "heartbeat.out.log").write_text("", encoding="utf-8")
    spec = importlib.util.spec_from_file_location("overnight_watch_throughput_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _seed_ticks(module, completed_series, *, open_count, spent=10, cap=600):
    """Write one tick per distinct 1-minute bucket; completed = done + archived."""
    window_sec = 60
    now_bucket = int(dt.datetime.now(dt.timezone.utc).timestamp() // window_sec)
    base = now_bucket - len(completed_series)
    lines = []
    for i, completed in enumerate(completed_series):
        ts = dt.datetime.fromtimestamp((base + i) * window_sec + 1, dt.timezone.utc)
        lines.append(
            json.dumps(
                {
                    "ts": ts.isoformat(timespec="seconds"),
                    "done": completed,
                    "archived": 0,
                    "open": open_count,
                    "daily_spent": spent,
                    "daily_cap": cap,
                }
            )
        )
    module.TICKS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# completed climbs by 20/window then goes flat for the last 3 → collapse candidate.
_COLLAPSE = [0, 20, 40, 60, 80, 80, 80, 80]
# steady 20/window throughout → healthy.
_HEALTHY = [0, 20, 40, 60, 80, 100, 120, 140]


def test_collapse_fires_on_silent_stall(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    _seed_ticks(module, _COLLAPSE, open_count=50)
    snap = {"dispatch_control": {"allow_dispatch": True}}
    result = module.throughput_snapshot(snap)
    assert result["evaluable"] is True
    assert result["below_floor"] is True
    assert result["suppressed"] is None


def test_healthy_velocity_does_not_fire(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    _seed_ticks(module, _HEALTHY, open_count=50)
    result = module.throughput_snapshot({"dispatch_control": {"allow_dispatch": True}})
    assert result["evaluable"] is True
    assert result["below_floor"] is False


def test_no_open_work_is_suppressed_not_alerted(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    _seed_ticks(module, _COLLAPSE, open_count=0)
    result = module.throughput_snapshot({"dispatch_control": {"allow_dispatch": True}})
    assert result["below_floor"] is False
    assert result["suppressed"] == "no-open-work"


def test_governor_pause_is_suppressed(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "paused")
    _seed_ticks(module, _COLLAPSE, open_count=50)
    result = module.throughput_snapshot({"dispatch_control": {"allow_dispatch": True}})
    assert result["below_floor"] is False
    assert result["suppressed"] == "governor-paused"


def test_vitals_shed_does_not_hide_remote_throughput_collapse(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    module.HEARTBEAT_LOG.write_text(
        "── vitals-pressure: dispatch skipped; merge/heal/status organs already ran ──\n",
        encoding="utf-8",
    )
    _seed_ticks(module, _COLLAPSE, open_count=50)
    result = module.throughput_snapshot({"dispatch_control": {"allow_dispatch": True}})
    assert result["below_floor"] is True
    assert result["suppressed"] is None


def test_budget_exhausted_is_suppressed(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    _seed_ticks(module, _COLLAPSE, open_count=50, spent=600, cap=600)
    result = module.throughput_snapshot({"dispatch_control": {"allow_dispatch": True}})
    assert result["below_floor"] is False
    assert result["suppressed"] == "daily-budget-exhausted"


def test_dispatch_gated_is_suppressed(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    _seed_ticks(module, _COLLAPSE, open_count=50)
    result = module.throughput_snapshot({"dispatch_control": {"allow_dispatch": False}})
    assert result["below_floor"] is False
    assert result["suppressed"] == "dispatch-gated"


def test_insufficient_windows_not_evaluable(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    _seed_ticks(module, [0, 20, 40], open_count=50)
    result = module.throughput_snapshot({"dispatch_control": {"allow_dispatch": True}})
    assert result["evaluable"] is False


def test_collapse_becomes_an_alert(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    _seed_ticks(module, _COLLAPSE, open_count=50)
    snap = {
        "launchd": {"ok": True, "state": "active", "env": {}},
        "log_age_sec": 10,
        "heartbeat": {"latest_tick": {"timestamp": "t"}},
        "worker_count": 0,
        "heartbeat_child_count": 0,
        "dispatch_control": {"allow_dispatch": True},
        "plist_drift": [],
        "throughput": module.throughput_snapshot({"dispatch_control": {"allow_dispatch": True}}),
    }
    status, alerts = module.evaluate(snap)
    assert status == "alert"
    assert "throughput-collapse" in {a["id"] for a in alerts}


# ---------------------------------------------------------------- plist drift
def test_plist_drift_detected_and_reinstalled(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    live = agents / "com.limen.heartbeat.plist"
    live.write_text("<key>LIMEN_ASYNC_MAX</key><string>1</string>", encoding="utf-8")
    committed = tmp_path / "container" / "launchd" / "com.limen.heartbeat.plist"
    committed.parent.mkdir(parents=True)
    committed.write_text("<key>LIMEN_ASYNC_MAX</key><string>10</string>", encoding="utf-8")
    monkeypatch.setattr(module, "LAUNCH_AGENTS", agents)
    monkeypatch.setattr(module, "COMMITTED_PLIST", committed)

    drift = module.plist_drift()
    assert drift == [{"key": "LIMEN_ASYNC_MAX", "live": "1", "committed": "10"}]

    calls = []
    monkeypatch.setattr(module, "run", lambda args, timeout=10: calls.append(args) or _CP(args, rc=0))
    monkeypatch.setattr(module.time, "sleep", lambda *_: None)
    action = module.reinstall_plist()
    assert action["ok"] is True
    assert live.read_text() == committed.read_text()  # committed copied over the drifted live one
    assert any(a[:2] == ["launchctl", "bootout"] for a in calls)
    assert any(a[:2] == ["launchctl", "bootstrap"] for a in calls)


# ---------------------------------------------------------------- effector
def _heal_snapshot(alert_id):
    return {
        "timestamp": "2026-07-09T12:00:00+00:00",
        "alerts": [{"id": alert_id, "evidence": "x"}],
        "launchd": {"ok": True},
    }


def test_collapse_heal_kickstarts_then_escalates_on_recurrence(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    calls = []

    def fake_run(args, timeout=10):
        calls.append(args)
        if args[:3] == ["gh", "issue", "list"]:
            return _CP(args, rc=0, stdout="[]")
        return _CP(args, rc=0, stdout="https://github.com/organvm/limen/issues/999")

    monkeypatch.setattr(module, "run", fake_run)

    # First occurrence: kickstart, no escalation yet.
    snap1 = _heal_snapshot("throughput-collapse")
    actions1 = module.heal(snap1)
    assert any(a.get("action") == "kickstart" for a in actions1)
    assert not any(a.get("action") == "escalate-issue" for a in actions1)
    module.update_state(snap1)  # persists collapse_heal_attempts=1

    # Second occurrence past cooldown: kickstart AND escalate to the issues mirror.
    monkeypatch.setattr(module, "HEAL_COOLDOWN_SEC", 0)
    snap2 = _heal_snapshot("throughput-collapse")
    actions2 = module.heal(snap2)
    assert any(a.get("action") == "kickstart" for a in actions2)
    esc = [a for a in actions2 if a.get("action") == "escalate-issue"]
    assert esc and esc[0]["ok"] is True
    assert any(a[:3] == ["gh", "issue", "create"] for a in calls)


def test_escalation_dedupes_on_existing_issue(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "governor_mode", lambda: "dispatch")
    monkeypatch.setattr(module, "HEAL_COOLDOWN_SEC", 0)
    created = []

    def fake_run(args, timeout=10):
        if args[:3] == ["gh", "issue", "list"]:
            return _CP(args, rc=0, stdout='[{"number": 42}]')
        if args[:3] == ["gh", "issue", "create"]:
            created.append(args)
        return _CP(args, rc=0)

    monkeypatch.setattr(module, "run", fake_run)
    module.STATE_PATH.write_text(json.dumps({"collapse_heal_attempts": 1}), encoding="utf-8")
    actions = module.heal(_heal_snapshot("throughput-collapse"))
    esc = [a for a in actions if a.get("action") == "escalate-issue"]
    assert esc and esc[0].get("deduped") is True
    assert not created  # an open issue already exists — never open a duplicate
