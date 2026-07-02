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
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "usage-telemetry.py"


def _run(tmp_path, heartbeat_lines, opencode_clock=None):
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
    if opencode_clock is not None:
        clock_path = home / ".local" / "share" / "opencode" / "clock.json"
        clock_path.parent.mkdir(parents=True)
        clock_path.write_text(json.dumps(opencode_clock))
    env = dict(os.environ, LIMEN_ROOT=str(root), HOME=str(home))
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
