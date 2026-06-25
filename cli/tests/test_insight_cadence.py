"""Tests for the insight-cadence organ — due_tiers gating + signal aggregation.

These cover the PURE logic: cadence gating, insight production in each tier,
owner derivation, and the health stamp. No actuators, no real signal files.
"""

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "insight_cadence",
    Path(__file__).resolve().parents[2] / "scripts" / "insight-cadence.py",
)
ic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ic)


def _ts(dt):
    return dt.isoformat(timespec="seconds")


# ─── due_tiers ─────────────────────────────────────────────────────────


def test_due_tiers_first_run_all_due():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    assert set(ic.due_tiers({"last_run": {}}, now)) == {"hourly", "daily", "weekly", "monthly"}


def test_due_tiers_respects_elapsed():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    state = {
        "last_run": {
            "hourly": _ts(now - timedelta(minutes=30)),
            "daily": _ts(now - timedelta(hours=25)),
            "weekly": _ts(now - timedelta(days=2)),
        }
    }
    due = ic.due_tiers(state, now)
    assert "hourly" not in due
    assert "daily" in due
    assert "weekly" not in due


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
    due = ic.due_tiers(state, now)
    assert "monthly" in due


def test_due_tiers_monthly_not_yet():
    now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    state = {
        "last_run": {
            "monthly": _ts(now - timedelta(days=29)),
        }
    }
    due = ic.due_tiers(state, now)
    assert "monthly" not in due


def test_due_tiers_none_due():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    state = {
        "last_run": {
            "hourly": _ts(now - timedelta(minutes=30)),
            "daily": _ts(now - timedelta(hours=23)),
            "weekly": _ts(now - timedelta(days=6)),
            "monthly": _ts(now - timedelta(days=29)),
        }
    }
    assert ic.due_tiers(state, now) == []


def test_force_tier_overrides():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    fresh = {"last_run": {"hourly": _ts(now)}}
    assert ic.due_tiers(fresh, now, force="hourly") == ["hourly"]
    assert ic.due_tiers(fresh, now, force="monthly") == ["monthly"]


def test_force_invalid_tier():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    assert ic.due_tiers({}, now, force="nonexistent") == []


# ─── owner derivation ──────────────────────────────────────────────────


def test_owner_from_organ_health():
    assert ic._owner_from_source("organ-health", "sustain") == "scripts/sustain"


def test_owner_from_organ_health_with_slash():
    assert ic._owner_from_source("organ-health", "organvm/limen") == "organvm/limen"


def test_owner_from_usage():
    assert ic._owner_from_source("usage", "codex") == "organvm/codex"


def test_owner_from_ledger():
    assert ic._owner_from_source("ledger", "organvm/limen") == "organvm/limen"


def test_owner_from_ledger_fallback():
    assert ic._owner_from_source("ledger", "") == "organvm/limen"


def test_owner_from_self_improve():
    assert ic._owner_from_source("self-improve", "codex") == "scripts/codex"


def test_owner_from_censor_decisions():
    assert ic._owner_from_source("censor-decisions", "") == "scripts/censor.py"


# ─── severity derivation ────────────────────────────────────────────────


def test_severity_critical():
    assert ic._severity_from_age(50, 10) == "critical"


def test_severity_high():
    assert ic._severity_from_age(30, 10) == "high"


def test_severity_medium():
    assert ic._severity_from_age(15, 10) == "medium"


def test_severity_low():
    assert ic._severity_from_age(5, 10) == "low"


def test_severity_none():
    assert ic._severity_from_age(None, 10) == "medium"
    assert ic._severity_from_age(5, None) == "medium"
    assert ic._severity_from_age(None, None) == "medium"


# ─── window_start_for ──────────────────────────────────────────────────


def test_window_start_aligns_to_tier_period():
    now = datetime(2026, 6, 24, 12, 30, 45, tzinfo=timezone.utc)
    ws = ic.window_start_for("hourly", now)
    assert "T12:00:00" in ws  # floored to the hour


def test_window_start_daily():
    now = datetime(2026, 6, 24, 12, 30, 45, tzinfo=timezone.utc)
    ws = ic.window_start_for("daily", now)
    assert "T00:00:00" in ws  # floored to the day


# ─── aggregation shapes (dry-run, no signal files) ─────────────────────


def test_aggregate_hourly_returns_list():
    insights = ic.aggregate_hourly()
    assert isinstance(insights, list)


def test_aggregate_daily_returns_list():
    insights = ic.aggregate_daily()
    assert isinstance(insights, list)


def test_aggregate_weekly_returns_list():
    insights = ic.aggregate_weekly()
    assert isinstance(insights, list)


def test_aggregate_monthly_returns_list():
    insights = ic.aggregate_monthly()
    assert isinstance(insights, list)


# ─── produce shape ──────────────────────────────────────────────────────


def test_produce_hourly_shape():
    report = ic.produce("hourly", {}, dry_run=True)
    assert report["tier"] == "hourly"
    assert "generated_at" in report
    assert "window_start" in report
    assert isinstance(report["insights"], list)
    if report["insights"]:
        ins = report["insights"][0]
        assert "id" in ins
        assert "severity" in ins
        assert "title" in ins
        assert "owner" in ins
        assert ins["owner"]  # non-empty
        assert "source" in ins
        assert "suggested_action" in ins
        assert isinstance(ins["healable"], bool)


def test_produce_daily_shape():
    report = ic.produce("daily", {}, dry_run=True)
    assert report["tier"] == "daily"
    assert isinstance(report["insights"], list)


def test_produce_weekly_shape():
    report = ic.produce("weekly", {}, dry_run=True)
    assert report["tier"] == "weekly"
    assert isinstance(report["insights"], list)


def test_produce_monthly_shape():
    report = ic.produce("monthly", {}, dry_run=True)
    assert report["tier"] == "monthly"
    assert isinstance(report["insights"], list)


# ─── markdown rendering ──────────────────────────────────────────────────


def test_render_markdown_contains_tier():
    report = {"tier": "hourly", "generated_at": "2026-06-24T12:00:00",
              "window_start": "2026-06-24T12:00:00", "insights": []}
    md = ic._render_markdown(report)
    assert "hourly" in md
    assert "0 insights" in md


def test_render_markdown_with_insight():
    report = {
        "tier": "hourly",
        "generated_at": "2026-06-24T12:00:00",
        "window_start": "2026-06-24T12:00:00",
        "insights": [{
            "id": "test-1", "severity": "high", "title": "test insight",
            "detail": "test detail", "owner": "scripts/test",
            "source": "/tmp/test.json", "suggested_action": "fix it",
            "healable": True,
        }],
    }
    md = ic._render_markdown(report)
    assert "test insight" in md
    assert "HIGH" in md
    assert "fix it" in md


# ─── health stamp ────────────────────────────────────────────────────────


def test_stamp_health_writes(tmp_path):
    orig_root = ic.ROOT
    orig_logs = ic.LOGS
    orig_health = ic.HEALTH_PATH
    try:
        ic.LOGS = tmp_path
        ic.HEALTH_PATH = tmp_path / "insight-cadence-health.json"
        ic._stamp_health()
        assert ic.HEALTH_PATH.exists()
        data = json.loads(ic.HEALTH_PATH.read_text())
        assert data["organ"] == "insight-cadence"
        assert "timestamp" in data
    finally:
        ic.ROOT = orig_root
        ic.LOGS = orig_logs
        ic.HEALTH_PATH = orig_health


# ─── state persistence ──────────────────────────────────────────────────


def test_state_persistence_round_trip(tmp_path):
    state_path = tmp_path / "insight-cadence-state.json"
    now = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)
    state = {"last_run": {"monthly": _ts(now - timedelta(days=31))}}
    Path(state_path).write_text(json.dumps(state))
    loaded = ic._load_json(str(state_path), {})
    due = ic.due_tiers(loaded, now)
    assert "monthly" in due
    state["last_run"]["monthly"] = _ts(now)
    Path(state_path).write_text(json.dumps(state))
    loaded = ic._load_json(str(state_path), {})
    due = ic.due_tiers(loaded, now)
    assert "monthly" not in due
