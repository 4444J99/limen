#!/usr/bin/env python3
"""Hermetic test for the Copilot adapter in insight-cross-vendor-ingest.

Builds a synthetic ~/.copilot/session-store.db (sessions/turns/
assistant_usage_events), points the vendor registry at it, and asserts the
adapter derives the right window-bounded, PII-safe friction signals:

  - out-of-window sessions are excluded
  - single-turn (<=1 turn) sessions are counted as abandons
  - non-normal finish_reason rows are counted as abnormal finishes
  - content_filter_triggered rows are counted
  - token/model/latency patterns are surfaced

Deterministic: a fixed window_start is passed to the adapter, so no reliance on
the real clock or the real Copilot store.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "insight-cross-vendor-ingest.py"
SPEC = importlib.util.spec_from_file_location("insight_cross_vendor_ingest", SOURCE)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def _build_store(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY, cwd TEXT, repository TEXT, host_type TEXT,
            branch TEXT, summary TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL, user_message TEXT, assistant_response TEXT,
            timestamp TEXT
        );
        CREATE TABLE assistant_usage_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            turn_index INTEGER, model TEXT NOT NULL, input_tokens INTEGER,
            output_tokens INTEGER, total_nano_aiu INTEGER, duration_ms INTEGER,
            time_to_first_token_ms INTEGER, finish_reason TEXT,
            content_filter_triggered INTEGER, created_at TEXT
        );
        """
    )
    # s1: in-window, 3 turns, one abnormal finish (length) + one content-filter hit
    # s2: in-window, single turn (abandon)
    # s3: OUT of window (old created_at) — must be excluded entirely
    cur.executemany(
        "INSERT INTO sessions (id, created_at, updated_at) VALUES (?, ?, ?)",
        [
            ("s1", "2026-07-20 10:00:00", "2026-07-20 10:05:00"),
            ("s2", "2026-07-21 09:00:00", "2026-07-21 09:00:30"),
            ("s3", "2020-01-01 00:00:00", "2020-01-01 00:01:00"),
        ],
    )
    cur.executemany(
        "INSERT INTO turns (session_id, turn_index) VALUES (?, ?)",
        [("s1", 0), ("s1", 1), ("s1", 2), ("s2", 0), ("s3", 0), ("s3", 1)],
    )
    cur.executemany(
        """INSERT INTO assistant_usage_events
           (session_id, model, input_tokens, output_tokens, total_nano_aiu,
            duration_ms, time_to_first_token_ms, finish_reason,
            content_filter_triggered, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            ("s1", "gpt-5.5", 1000, 200, 500, 8000, 4000, "stop", 0, "2026-07-20 10:00:10"),
            ("s1", "gpt-5.5", 1500, 50, 700, 9000, 5000, "length", 0, "2026-07-20 10:01:10"),
            ("s1", "gpt-5.5", 800, 10, 300, 7000, 3500, "content_filter", 1, "2026-07-20 10:02:10"),
            ("s2", "gpt-5.5", 500, 100, 200, 6000, 3000, "stop", 0, "2026-07-21 09:00:10"),
            # out-of-window event (belongs to s3) — excluded because s3 is out of window
            ("s3", "gpt-4", 999, 999, 999, 999, 999, "length", 1, "2020-01-01 00:00:10"),
        ],
    )
    con.commit()
    con.close()


with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "session-store.db"
    _build_store(db)

    # Redirect the vendor registry at the synthetic store
    module.VENDOR_REGISTRY["copilot"]["path"] = db

    window_start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    packet = module._ingest_copilot(window_start)

    # Only s1 + s2 are in window; s3 is excluded
    assert packet["sessions_seen"] == 2, packet["sessions_seen"]

    signals = {s["signal"]: s for s in packet["friction_signals"]}

    # s2 is the sole single-turn session
    assert "single_turn_sessions" in signals, signals
    assert signals["single_turn_sessions"]["count"] == 1, signals["single_turn_sessions"]

    # one 'length' + one 'content_filter' = 2 abnormal finishes (s3's excluded)
    assert "abnormal_finish_reasons" in signals, signals
    assert signals["abnormal_finish_reasons"]["count"] == 2, signals["abnormal_finish_reasons"]
    # classification carries the enum distribution
    assert signals["abnormal_finish_reasons"]["classification"].get("length") == 1

    # one content-filter hit in window (s3's is excluded)
    assert "content_filter_triggered" in signals, signals
    assert signals["content_filter_triggered"]["count"] == 1, signals["content_filter_triggered"]

    # patterns surface tokens + top model
    patterns = " ".join(packet["notable_patterns"])
    assert "gpt-5.5" in patterns, patterns

    # PII firewall: the DATA payload (signals + patterns) must carry no message
    # text — only counts/enums/model-ids. (data_quality_notes deliberately names
    # the skipped columns to affirm they're not read, so it's excluded here.)
    payload = repr(packet["friction_signals"]) + " " + patterns
    for forbidden in ("user_message", "assistant_response"):
        assert forbidden not in payload, f"PII column leaked into payload: {forbidden}"

    # out-of-window token counts (999s) must not appear anywhere
    assert "999" not in patterns, patterns

print("PASS: insight-cross-vendor-copilot.test.py")
