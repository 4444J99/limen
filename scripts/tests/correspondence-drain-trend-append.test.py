#!/usr/bin/env python3
"""Hermetic regression for correspondence-walk.py::_append_trend — the drain-trend producer.

Locks the "one point per beat, not per invocation" contract: the writer appends one counts-only
point per NEW ledger snapshot (deduped by ledger_generated_at), soft-caps the series, and fails
open on a torn tail. No beat, no Gmail, no network — the function is exercised against a temp LOGS.
"""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]


def _load_walk():
    spec = importlib.util.spec_from_file_location("correspondence_walk", SCRIPTS / "correspondence-walk.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _status(ledger_ts: str, reply_owed: int, needs_human: int = 2, draft_missing: int = 0) -> dict:
    return {
        "generated_at": "2026-07-18T00:00:00Z",
        "ledger_generated_at": ledger_ts,
        "reply_owed": reply_owed,
        "terminal": reply_owed - draft_missing,
        "needs_human": needs_human,
        "non_terminal": draft_missing,
        "fixed_point": draft_missing == 0,
    }


def _lines(path: Path) -> list[dict]:
    out: list[dict] = []
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue  # tolerate a torn line, exactly as the production reader does
    return out


def main() -> int:
    mod = _load_walk()
    with tempfile.TemporaryDirectory() as td:
        logs = Path(td) / "logs"
        trend = logs / "correspondence-drain-trend.jsonl"
        mod.LOGS = logs
        mod.TREND_JSONL = trend
        mod.TREND_MAX_ROWS = 5

        # 1. First append writes exactly one point.
        mod._append_trend(_status("2026-07-15T00:00:00Z", 20))
        assert len(_lines(trend)) == 1, "first append should write one point"

        # 2. Re-walking the SAME ledger snapshot adds nothing (one point per beat, not per invocation).
        mod._append_trend(_status("2026-07-15T00:00:00Z", 20))
        mod._append_trend(_status("2026-07-15T00:00:00Z", 20))
        assert len(_lines(trend)) == 1, "same ledger snapshot must not append a second point"

        # 3. A NEW ledger snapshot appends a fresh point.
        mod._append_trend(_status("2026-07-16T00:00:00Z", 17))
        rows = _lines(trend)
        assert len(rows) == 2, "new ledger snapshot should append"
        assert rows[-1]["reply_owed"] == 17 and rows[-1]["draft_missing"] == 0, rows[-1]

        # 4. The counts-only point carries no PII keys (this face publishes).
        assert set(rows[-1]) == {
            "timestamp", "ledger_generated_at", "reply_owed", "terminal", "needs_human",
            "draft_missing", "fixed_point",
        }, rows[-1]

        # 5. Soft cap: appending past TREND_MAX_ROWS keeps only the last N points.
        for i in range(10):
            mod._append_trend(_status(f"2026-08-{i + 1:02d}T00:00:00Z", 15 - i))
        rows = _lines(trend)
        assert len(rows) == mod.TREND_MAX_ROWS, f"series should cap at {mod.TREND_MAX_ROWS}, got {len(rows)}"
        assert rows[-1]["reply_owed"] == 6, rows[-1]  # 15 - 9 (last of the loop)

        # 6. Fail-open on a torn tail: a garbage last line must not raise; a fresh point still lands.
        with trend.open("a", encoding="utf-8") as fh:
            fh.write("{ not json\n")
        mod._append_trend(_status("2026-09-01T00:00:00Z", 3))
        rows = _lines(trend)
        assert rows and rows[-1]["reply_owed"] == 3, "torn tail must fail open and still append the fresh point"

    print("correspondence-drain-trend-append.test: all cases pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
