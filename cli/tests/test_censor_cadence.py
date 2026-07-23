"""Tests for the Censor's cadence gating — mirrors scripts/test_censor.py.

These cover the due_tiers wall-clock-elapsed logic including the MONTHLY tier
that was added to complete the cadence engine. All existing tiers remain unchanged.
"""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "censor.py"


def _load_censor(module_name="censor"):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


censor = _load_censor()


def _ts(dt):
    return dt.isoformat(timespec="seconds")


def test_due_tiers_monthly_after_30d():
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
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
    now = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)
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
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    assert set(censor.due_tiers({"last_run": {}}, now)) == {"hourly", "daily", "weekly", "monthly"}


def test_due_tiers_existing_tiers_unchanged():
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
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
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
    fresh = {"last_run": {"monthly": _ts(now)}}
    assert censor.due_tiers(fresh, now, force="monthly") == ["monthly"]


def test_state_persistence_round_trip(tmp_path):
    state_path = tmp_path / "censor-state.json"
    now = datetime(2026, 6, 24, 12, 0, tzinfo=UTC)
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


def test_malformed_timeout_env_falls_back(monkeypatch):
    monkeypatch.setenv("LIMEN_CENSOR_TIMEOUT", "not-an-int")
    assert _load_censor("censor_bad_timeout").ACTUATOR_TIMEOUT == 300

    monkeypatch.setenv("LIMEN_CENSOR_TIMEOUT", "0")
    assert _load_censor("censor_zero_timeout").ACTUATOR_TIMEOUT == 300

    monkeypatch.setenv("LIMEN_CENSOR_TIMEOUT", "12")
    assert _load_censor("censor_custom_timeout").ACTUATOR_TIMEOUT == 12


def test_census_is_counts_only(tmp_path, monkeypatch):
    module = _load_censor("censor_census")
    logs = tmp_path / "logs"
    censor_dir = tmp_path / "censor"
    logs.mkdir()
    censor_dir.mkdir()
    protocols = censor_dir / "protocols.yaml"
    precedents = censor_dir / "precedents.jsonl"
    state = logs / "censor-state.json"
    last = logs / "censor-last.json"
    residuals = logs / "censor-residual.json"
    protocols.write_text(
        """
protocols:
  - id: PRIVATE-PROTOCOL
    when:
      signal: private
""",
        encoding="utf-8",
    )
    precedents.write_text(json.dumps({"subject": "private precedent"}) + "\n", encoding="utf-8")
    state.write_text(json.dumps({"last_run": {"hourly": "2026-07-06T00:00:00+00:00"}}), encoding="utf-8")
    last.write_text(json.dumps({"decisions": [{"signal": {"subject": "private signal"}}]}), encoding="utf-8")
    residuals.write_text(json.dumps([{"title": "private residual"}]), encoding="utf-8")
    monkeypatch.setattr(module, "PROTOCOLS", protocols)
    monkeypatch.setattr(module, "PRECEDENTS_PATH", precedents)
    monkeypatch.setattr(module, "STATE_PATH", state)
    monkeypatch.setattr(module, "LAST_PATH", last)
    monkeypatch.setattr(module, "RESIDUAL_PATH", residuals)

    census = module.census()
    encoded = json.dumps(census, sort_keys=True)

    assert census == {
        "tiers": 4,
        "protocols": 1,
        "precedents": 1,
        "state_tiers": 1,
        "last_decisions": 1,
        "residuals": 1,
        "actuator_timeout_s": module.ACTUATOR_TIMEOUT,
    }
    assert "PRIVATE-PROTOCOL" not in encoded
    assert "private precedent" not in encoded
    assert "private signal" not in encoded
    assert "private residual" not in encoded
