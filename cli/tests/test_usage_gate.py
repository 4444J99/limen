"""Honest-work gate: dispatch/route must skip lanes the LIVE usage meter says are dead.

Regression guard for the 2026-06-19 bug where codex burned its 5h token budget (usage.json
health="exhausted") yet the dispatcher kept assigning to it because _down_lanes() only read a
static hand-maintained file. The fix derives the down-set from logs/usage.json (self-healing)."""

import json

import pytest
from limen.dispatch import _down_lanes, _usage_dead_lanes


@pytest.fixture(autouse=True)
def disable_oauth_preflight(monkeypatch):
    monkeypatch.setenv("LIMEN_OAUTH_PREFLIGHT", "0")


def _write_usage(root, vendors):
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "usage.json").write_text(json.dumps({"generated": "t", "vendors": vendors}))


def test_usage_dead_lanes_flags_exhausted_ratelimited_and_reserve(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(
        tmp_path,
        {
            "codex": {"health": "exhausted"},
            "gemini": {"health": "rate-limited"},
            "jules": {"health": "low"},  # at/below reserve -> STOP before 0 (paced-out)
            "opencode": {"health": "throttle"},  # still has runway -> stays UP (steer signal only)
            "claude": {"health": "ok"},
        },
    )
    assert _usage_dead_lanes() == {"codex", "gemini", "jules"}


def test_agy_dispatch_count_proxy_exhaustion_stays_up(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(
        tmp_path,
        {
            "agy": {
                "health": "exhausted",
                "signal": "dispatch-count",
                "limit_source": "operator board cap until live vendor meter",
                "remaining": 0,
                "headroom_pct": 0,
            },
            "gemini": {
                "health": "exhausted",
                "signal": "dispatch-count",
                "limit_source": "operator board cap until live vendor meter",
                "remaining": 0,
                "headroom_pct": 0,
            },
            "jules": {
                "health": "exhausted",
                "signal": "dispatch-count",
                "limit_source": "known hard cap",
                "remaining": 0,
                "headroom_pct": 0,
            },
        },
    )
    assert _usage_dead_lanes() == {"gemini", "jules"}
    assert _down_lanes() == {"gemini", "jules"}


def test_agy_recent_rate_limit_still_down(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(
        tmp_path,
        {
            "agy": {
                "health": "rate-limited",
                "signal": "dispatch-count",
                "limit_source": "operator board cap until live vendor meter",
                "recent_rate_limit": True,
            },
        },
    )
    assert _usage_dead_lanes() == {"agy"}


def test_throttle_lane_stays_up(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(tmp_path, {"codex": {"health": "throttle", "remaining": 10}, "claude": {"health": "ok"}})
    assert _usage_dead_lanes() == set()
    assert _down_lanes() == set()


def test_zero_headroom_throttle_lane_is_down(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(
        tmp_path,
        {
            "codex": {"health": "throttle", "remaining": "0", "headroom_pct": "0"},
            "claude": {"health": "throttle", "remaining": 10, "headroom_pct": 10},
        },
    )
    assert _usage_dead_lanes() == {"codex"}
    assert _down_lanes() == {"codex"}


def test_down_lanes_unions_manual_file_and_live_meter(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(tmp_path, {"codex": {"health": "exhausted"}})
    (tmp_path / "logs" / "lanes-down.txt").write_text("agy  # bin missing\n# a comment line\n\n")
    assert _down_lanes() == {"codex", "agy"}


def test_reserve_low_lane_is_down_ok_stays_up(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    _write_usage(tmp_path, {"codex": {"health": "ok"}, "claude": {"health": "low"}})
    assert _down_lanes() == {"claude"}


def test_missing_usage_json_is_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    assert _usage_dead_lanes() == set()
    assert _down_lanes() == set()
