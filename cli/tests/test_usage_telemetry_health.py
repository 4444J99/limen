"""Regression guard for the vendor-health meter — the 'utilize all lanes forever' invariant.

The meter once falsely benched claude (a transcript that merely MENTIONED 'rate limit' tripped a
text regex) and gemini (a one-time 'RATE-LIMIT gemini' marker in the heartbeat log stuck forever).
These tests pin the fix: a lane is gated ONLY by a real, RECENT rate-limit — a lane with full
headroom and no fresh signal is never benched.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "usage-telemetry.py"


def _run(tmp_path, heartbeat_lines, opencode_clock=None, extra_env=None, provider_outcomes=None):
    """Run usage-telemetry.py against an isolated root + empty HOME (so claude/codex read 0 tokens)."""
    root = tmp_path / "root"
    home = tmp_path / "home"
    (root / "logs").mkdir(parents=True)
    (home / ".claude" / "projects").mkdir(parents=True)
    (home / ".codex" / "sessions").mkdir(parents=True)
    (root / "logs" / "usage-limits.json").write_text(
        json.dumps(
            {
                "gemini": {"limit": 200, "unit": "runs", "window": "24h"},
            }
        )
    )
    (root / "logs" / "heartbeat.out.log").write_text("\n".join(heartbeat_lines))
    (root / "tasks.yaml").write_text("tasks: []\nportal: {}\n")
    if provider_outcomes is not None:
        (root / "logs" / "provider-outcomes.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in provider_outcomes)
        )
    if opencode_clock is not None:
        clock_path = home / ".local" / "share" / "opencode" / "clock.json"
        clock_path.parent.mkdir(parents=True)
        clock_path.write_text(json.dumps(opencode_clock))
    env = dict(os.environ, LIMEN_ROOT=str(root), HOME=str(home))
    if extra_env:
        env.update(extra_env)
    subprocess.run([sys.executable, str(SCRIPT)], env=env, check=True, capture_output=True)
    return json.loads((root / "logs" / "usage.json").read_text())["vendors"]


def test_stale_ratelimit_marker_does_not_bench_a_headroom_lane(tmp_path):
    # an OLD 'RATE-LIMIT gemini' marker buried far above the tail window must NOT gate gemini —
    # gemini has 0/200 consumed (100% headroom), so it must come back 'ok'.
    lines = ["RATE-LIMIT gemini"] + [f"beat {i} ok" for i in range(600)]
    vendors = _run(tmp_path, lines)
    assert vendors["gemini"]["health"] == "ok", vendors["gemini"]
    assert vendors["gemini"]["headroom_pct"] == 100


def test_recent_ratelimit_marker_does_gate(tmp_path):
    # a FRESH marker inside the tail window is a real signal → gemini is rate-limited (time-boxed).
    lines = [f"beat {i} ok" for i in range(50)] + ["RATE-LIMIT gemini"]
    vendors = _run(tmp_path, lines)
    assert vendors["gemini"]["health"] == "rate-limited", vendors["gemini"]


def test_headroom_lane_with_no_signal_is_ok(tmp_path):
    # no markers at all → every healthy-headroom lane is 'ok', never benched.
    vendors = _run(tmp_path, [f"beat {i} ok" for i in range(20)])
    for name in ("gemini",):
        assert vendors[name]["health"] == "ok", (name, vendors[name])


def test_opencode_prefers_internal_clock_when_present(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        {
            "heavy_used": 120,
            "cache_read_used": 30,
            "cap_tokens": 1000,
            "used_pct": 15,
            "health": "ok",
        },
    )

    assert vendors["opencode"]["signal"] == "db-meter"
    assert vendors["opencode"]["consumed"] == 150
    assert vendors["opencode"]["possible"] == 1000
    assert vendors["opencode"]["clock_used_pct"] == 15


def test_opencode_clock_accepts_string_numerics(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        {
            "heavy_used": "120",
            "cache_read_used": "30",
            "cap_tokens": "1000",
            "used_pct": "15",
            "health": "ok",
        },
    )

    assert vendors["opencode"]["signal"] == "db-meter"
    assert vendors["opencode"]["consumed"] == 150
    assert vendors["opencode"]["possible"] == 1000
    assert vendors["opencode"]["clock_used_pct"] == 15


def test_opencode_clock_malformed_numerics_do_not_crash(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        {
            "heavy_used": "bad",
            "cache_read_used": 30,
            "cap_tokens": "nan",
            "used_pct": False,
            "health": "ok",
        },
    )

    assert vendors["opencode"]["signal"] == "db-meter"
    assert vendors["opencode"]["consumed"] == 30
    assert vendors["opencode"]["possible"] == 0
    assert vendors["opencode"]["clock_used_pct"] == 0


def test_opencode_usage_includes_provider_outcome_health(tmp_path):
    now = datetime.now(timezone.utc)
    rows = []
    for index, terminal in enumerate(("stream_failure", "timeout")):
        finished = now - timedelta(seconds=5 - index)
        rows.append(
            {
                "schema": "limen.provider_outcome.v1",
                "provider": "provider-z",
                "runtime_model": "provider-z/arbitrary-runtime",
                "catalog_hash": "a" * 64,
                "execution_profile_hash": "b" * 64,
                "terminal_class": terminal,
                "started_at": (finished - timedelta(seconds=1)).isoformat(),
                "finished_at": finished.isoformat(),
                "retry_count": index,
                "receipt_reference": "task:fixture",
            }
        )

    vendors = _run(tmp_path, ["beat ok"], provider_outcomes=rows)

    assert vendors["opencode"]["provider_outcome_health"] == "degraded"
    assert vendors["opencode"]["provider_cooldown_count"] >= 1
    assert vendors["opencode"]["provider_last_terminal_failure"]
    assert len(vendors["opencode"]["provider_health_snapshot_hash"]) == 64


def test_malformed_cooldown_env_does_not_crash(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        extra_env={"LIMEN_RL_COOLDOWN_MIN": "not-a-number"},
    )

    assert vendors["gemini"]["health"] == "ok"


def test_malformed_reserve_env_does_not_poison_pacing(tmp_path):
    vendors = _run(
        tmp_path,
        ["beat ok"],
        extra_env={"LIMEN_RESERVE_PCT": "nan", "LIMEN_RESERVE_FLOOR_PCT": "200"},
    )

    assert vendors["gemini"]["reserve_pct"] == 15.0
    assert vendors["gemini"]["effective_reserve_pct"] == 15.0
    assert vendors["gemini"]["health"] == "ok"
