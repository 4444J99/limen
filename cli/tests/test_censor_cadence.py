"""Tests for the Censor's cadence gating — mirrors scripts/test_censor.py.

These cover the due_tiers wall-clock-elapsed logic including the MONTHLY tier
that was added to complete the cadence engine. All existing tiers remain unchanged.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location("censor", Path(__file__).resolve().parents[2] / "scripts" / "censor.py")
censor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(censor)


def _ts(dt):
    return dt.isoformat(timespec="seconds")


def test_due_tiers_monthly_after_30d():
    now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    state = {
        "last_run": {
            "hourly": _ts(now - timedelta(hours=1)),
            "daily": _ts(now - timedelta(hours=25)),
            "weekly": _ts(now - timedelta(days=8)),
            "monthly": _ts(now - timedelta(days=31)),
        }
    }
    due = censor.due_tiers(state, now)
    assert "monthly" in due


def test_due_tiers_monthly_not_before_30d():
    now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    state = {
        "last_run": {
            "hourly": _ts(now - timedelta(minutes=30)),
            "daily": _ts(now - timedelta(hours=25)),
            "weekly": _ts(now - timedelta(days=8)),
            "monthly": _ts(now - timedelta(days=29)),
        }
    }
    due = censor.due_tiers(state, now)
    assert "monthly" not in due


def test_due_tiers_first_run_includes_monthly():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    assert set(censor.due_tiers({"last_run": {}}, now)) == {"hourly", "daily", "weekly", "monthly"}


def test_due_tiers_existing_tiers_unchanged():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    state = {
        "last_run": {
            "hourly": _ts(now - timedelta(minutes=30)),
            "daily": _ts(now - timedelta(hours=25)),
            "weekly": _ts(now - timedelta(days=2)),
            "monthly": _ts(now - timedelta(days=29)),
        }
    }
    due = censor.due_tiers(state, now)
    assert "hourly" not in due
    assert "daily" in due
    assert "weekly" not in due
    assert "monthly" not in due


def test_force_monthly_via_override():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    fresh = {"last_run": {"monthly": _ts(now)}}
    assert censor.due_tiers(fresh, now, force="monthly") == ["monthly"]


def test_state_persistence_round_trip(tmp_path):
    state_path = tmp_path / "censor-state.json"
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    state = {
        "last_run": {
            "monthly": _ts(now - timedelta(days=31)),
        }
    }
    Path(state_path).write_text(censor.json.dumps(state))
    loaded = censor._load_json(str(state_path), {"last_run": {}})
    due = censor.due_tiers(loaded, now)
    assert "monthly" in due
    state["last_run"]["monthly"] = _ts(now)
    Path(state_path).write_text(censor.json.dumps(state))
    loaded = censor._load_json(str(state_path), {"last_run": {}})
    due = censor.due_tiers(loaded, now)
    assert "monthly" not in due
