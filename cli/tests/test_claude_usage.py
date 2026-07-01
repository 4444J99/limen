from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "claude-usage.py"


def _run(root: Path, env_extra: dict | None = None) -> dict:
    import os

    env = {**os.environ, "LIMEN_ROOT": str(root), **(env_extra or {})}
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", "--no-write"],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )
    return json.loads(out.stdout)


def _write_usage(root: Path, claude_entry: dict) -> None:
    (root / "logs").mkdir(parents=True, exist_ok=True)
    (root / "logs" / "usage.json").write_text(json.dumps({"generated": "x", "vendors": {"claude": claude_entry}}))


def test_all_avenues_dark_returns_unknown(tmp_path: Path) -> None:
    """No signals anywhere → gauge is UNKNOWN, forcing a conservative (shed-early) read —
    never a silent 'all clear'."""
    report = _run(tmp_path)
    assert report["resolved"] is None
    assert report["trust"] == "unknown"
    assert report["used_percent"] is None
    # the full trail is still present — a dark avenue is VISIBLE, not a forgettable hole
    assert {a["avenue"] for a in report["avenues"]} == {"proxy", "ondisk", "poll", "counts", "reactive"}


def test_counts_avenue_uses_fleet_cap_not_a_fabricated_one(tmp_path: Path) -> None:
    _write_usage(
        tmp_path,
        {
            "consumed": 25_000_000,
            "possible": 100_000_000,
            "limit_source": "ESTIMATE — tune to plan",
            "window": "5h rolling",
            "health": "ok",
        },
    )
    report = _run(tmp_path)
    assert report["avenue"] == "counts"
    assert report["used_percent"] == 25.0  # 25M / 100M — the fleet's OWN cap
    assert report["trust"] == "estimate"  # cap is an estimate → stays untrusted


def test_explicit_cap_raises_trust_to_proxy(tmp_path: Path) -> None:
    _write_usage(tmp_path, {"consumed": 25_000_000, "possible": 100_000_000, "health": "ok"})
    report = _run(tmp_path, {"LIMEN_CLAUDE_WEEKLY_TOKENS": "50000000"})
    assert report["avenue"] == "counts"
    assert report["used_percent"] == 50.0  # 25M / 50M human cap
    assert report["trust"] == "proxy"  # real numerator + human-set cap


def test_reactive_429_is_last_resort_hard_stop(tmp_path: Path) -> None:
    """No token count to divide (no cap) but a real 429 → reactive avenue reports exhausted."""
    _write_usage(tmp_path, {"health": "rate-limited"})
    report = _run(tmp_path)
    assert report["avenue"] == "reactive"
    assert report["used_percent"] == 100.0
    assert report["trust"] == "measured"


def test_counts_precedes_reactive_when_both_available(tmp_path: Path) -> None:
    """Cascade order: a usable counts reading wins over the reactive fallback."""
    _write_usage(tmp_path, {"consumed": 10_000_000, "possible": 100_000_000, "health": "rate-limited"})
    report = _run(tmp_path)
    assert report["avenue"] == "counts"
