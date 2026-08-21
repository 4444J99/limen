"""Tests for the overnight monitor's throughput-collapse diagnostic.

2026-07-08 incident: the fleet idled a full night at ~5% of baseline while every liveness
alert stayed green. These tests pin the movement-vs-progress fix: a derived throughput floor
that fires only on genuine silent stall (open work, no sanctioned suppression). The diagnostic
is read-only and leaves remediation to an explicit operator command.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "overnight-watch.py"


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


def test_load_ticks_streams_file_instead_of_reading_whole_ledger(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)
    _seed_ticks(module, _HEALTHY, open_count=50)
    original_read_text = Path.read_text

    def guarded_read_text(path_obj, *args, **kwargs):
        if path_obj == module.TICKS_PATH:
            raise AssertionError("load_ticks should stream lines, not Path.read_text().splitlines()")
        return original_read_text(path_obj, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    ticks = module.load_ticks()
    assert len(ticks) == len(_HEALTHY)


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


def test_throughput_alert_exposes_no_automatic_host_or_issue_effector(tmp_path, monkeypatch):
    module = _fresh_module(tmp_path, monkeypatch)

    for name in (
        "bootstrap_service",
        "reinstall_plist",
        "kickstart_service",
        "escalate_issue",
        "heal",
    ):
        assert not hasattr(module, name)
