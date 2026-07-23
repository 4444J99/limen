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


def test_malformed_freshness_env_falls_back(tmp_path: Path) -> None:
    report = _run(tmp_path, {"LIMEN_CLAUDE_GAUGE_FRESH_S": "bad"})

    assert report["resolved"] is None
    assert report["trust"] == "unknown"


def test_malformed_proxy_percent_is_visible_dark_avenue(tmp_path: Path) -> None:
    import time

    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "anthropic-ratelimit.json").write_text(
        json.dumps({"captured_at": time.time(), "weekly": {"used_percent": "not-a-number"}})
    )

    report = _run(tmp_path)

    proxy = next(a for a in report["avenues"] if a["avenue"] == "proxy")
    assert proxy["used_percent"] is None
    assert "malformed" in proxy["note"]


def test_malformed_proxy_timestamp_does_not_abort(tmp_path: Path) -> None:
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "anthropic-ratelimit.json").write_text(
        json.dumps({"captured_at": "not-a-time", "weekly": {"used_percent": 12}})
    )

    report = _run(tmp_path)

    assert report["avenue"] == "proxy"
    assert report["used_percent"] == 12.0


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


def test_counts_avenue_tolerates_string_numbers(tmp_path: Path) -> None:
    _write_usage(tmp_path, {"consumed": "25000000", "possible": "50000000", "health": "ok"})

    report = _run(tmp_path, {"LIMEN_CLAUDE_WEEKLY_TOKENS": "bad"})

    assert report["avenue"] == "counts"
    assert report["used_percent"] == 50.0


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


def _synth_transcript(dir_: Path, output_tokens: int) -> None:
    """One recent transcript record carrying a usage block — the on-disk avenue's raw material."""
    import datetime

    dir_.mkdir(parents=True, exist_ok=True)
    now_iso = datetime.datetime.now(datetime.UTC).isoformat()
    rec = {
        "timestamp": now_iso,
        "message": {
            "usage": {
                "input_tokens": 0,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            }
        },
    }
    (dir_ / "s.jsonl").write_text(json.dumps(rec) + "\n")


def _calibrate(root: Path, tdir: Path, session_pct: float, weekly_pct: float) -> None:
    import os

    env = {**os.environ, "LIMEN_ROOT": str(root), "LIMEN_CLAUDE_TRANSCRIPTS_DIR": str(tdir)}
    subprocess.run(
        [sys.executable, str(SCRIPT), "--calibrate", str(session_pct), str(weekly_pct)],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )


def test_ondisk_calibrated_gauge_from_transcripts(tmp_path: Path) -> None:
    """The forever bridge: one /status calibration turns the transcripts the fleet ALREADY writes into
    a live gauge — recomputed each beat, no paste, no auth. cost/pct at calibration = the derived cap."""
    tdir = tmp_path / "transcripts" / "proj"
    _synth_transcript(tdir, output_tokens=1000)  # weighted cost = 5*1000 = 5000
    _calibrate(tmp_path, tdir, 20.0, 5.0)  # anchor: current session cost <-> 20%
    report = _run(tmp_path, {"LIMEN_CLAUDE_TRANSCRIPTS_DIR": str(tdir)})
    assert report["avenue"] == "ondisk"  # calibrated on-disk beats the raw counts estimate
    assert report["trust"] == "calibrated"
    assert report["used_percent"] == 20.0  # numerator unchanged since calibration -> reads 20%


def test_ondisk_dark_without_calibration(tmp_path: Path) -> None:
    """No calibration file -> the on-disk avenue stays dark (never a fabricated cap); cascade falls through."""
    tdir = tmp_path / "transcripts" / "proj"
    _synth_transcript(tdir, output_tokens=1000)
    report = _run(tmp_path, {"LIMEN_CLAUDE_TRANSCRIPTS_DIR": str(tdir)})
    ondisk = next(a for a in report["avenues"] if a["avenue"] == "ondisk")
    assert ondisk["used_percent"] is None
    assert "no calibration" in ondisk["note"]
