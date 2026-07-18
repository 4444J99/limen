#!/usr/bin/env python3
"""check-correspondence-drain-trend.py — prove the correspondence ledger is CONVERGING, or say where it isn't.

The gap this closes: check-correspondence-terminal.py proves the walk reached a fixed point THIS beat
(every reply-owed row disposed), but logs/correspondence-dispositions.json is a memoryless snapshot —
nothing trends `reply_owed`/`needs_human` across beats, so "is the organ actually DRAINING, or stalled
at a high plateau?" needs a human eye. correspondence-walk.py::_append_trend now appends one counts-only
point per ledger rebuild to logs/correspondence-drain-trend.jsonl; this sensor reads the tail of that
series and judges the SLOPE.

Convergence is a DIRECTION, never an absolute floor: `reply_owed` never reaches zero (the legal/
precedent `held` rows are an irreducible floor), so flat-at-floor is CONVERGED (exit 0), not a stall.
Over a window spanning ≥ --stale-hours the organ is NON-CONVERGENT (exit 1 with --check) iff any of:
  • reply_owed is RISING (last > first) — inflow outrunning drain, the ledger is growing; or
  • needs_human is RISING (last > first) — human-blocked backlog accumulating; or
  • draft_missing > 0 at EVERY point in the window — a HOLD row stuck without its composed draft.
A series too short (< --min-points) or too fresh (span < --stale-hours) is "not yet chronic" ⇒ exit 0.

Exit codes: 0 = draining / converged / not-yet-judgeable; 1 = sustained non-convergence (with --check).
Stamps logs/correspondence-drain-trend-status.json (counts only — this face publishes). Fixture-testable:
--trend-file bypasses the live series. Sibling of check-correspondence-terminal.py and heal-convergence.py.

Usage:
  python3 scripts/check-correspondence-drain-trend.py            # report + stamp
  python3 scripts/check-correspondence-drain-trend.py --check    # gate mode
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))
TREND_JSONL = Path(os.environ.get("LIMEN_CORRESPONDENCE_TREND_FILE", ROOT / "logs" / "correspondence-drain-trend.jsonl"))

WINDOW = int(os.environ.get("LIMEN_CORRESPONDENCE_TREND_WINDOW", "8"))
MIN_POINTS = int(os.environ.get("LIMEN_CORRESPONDENCE_TREND_MIN_POINTS", "3"))
STALE_HOURS = float(os.environ.get("LIMEN_CORRESPONDENCE_TREND_STALE_HOURS", "24"))


def _parse_ts(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _load_points(path: Path) -> list[dict]:
    """The append-only trend series, oldest→newest. Fail-open: absent/torn ⇒ []; a torn line is skipped."""
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def assess(points: list[dict], window: int, min_points: int, stale_hours: float) -> dict:
    """Pure verdict over the trend series — fixture-testable, no I/O."""
    win = points[-window:] if window > 0 else list(points)
    n = len(win)
    if n < min_points:
        return {
            "points_total": len(points), "window_points": n, "verdict": "insufficient-history",
            "converging": True, "span_hours": None,
            "reply_owed_delta": None, "needs_human_delta": None, "draft_missing_persistent": False,
            "signals": [],
        }

    first, last = win[0], win[-1]
    t0, t1 = _parse_ts(first.get("timestamp")), _parse_ts(last.get("timestamp"))
    span_hours = (t1 - t0).total_seconds() / 3600.0 if (t0 and t1) else None

    reply_delta = _int(last.get("reply_owed")) - _int(first.get("reply_owed"))
    human_delta = _int(last.get("needs_human")) - _int(first.get("needs_human"))
    draft_persistent = all(_int(p.get("draft_missing")) > 0 for p in win)

    span_ok = span_hours is not None and span_hours >= stale_hours
    signals = []
    if span_ok:
        if reply_delta > 0:
            signals.append("reply_owed-rising")
        if human_delta > 0:
            signals.append("needs_human-rising")
        if draft_persistent:
            signals.append("draft-missing-persistent")

    if not span_ok:
        verdict = "too-fresh"
    elif signals:
        verdict = "stalled"
    elif reply_delta < 0:
        verdict = "draining"
    else:
        verdict = "converged"   # flat over a full window at/above the irreducible floor

    return {
        "points_total": len(points), "window_points": n,
        "span_hours": round(span_hours, 2) if span_hours is not None else None,
        "reply_owed_first": _int(first.get("reply_owed")), "reply_owed_last": _int(last.get("reply_owed")),
        "reply_owed_delta": reply_delta,
        "needs_human_first": _int(first.get("needs_human")), "needs_human_last": _int(last.get("needs_human")),
        "needs_human_delta": human_delta,
        "draft_missing_persistent": draft_persistent,
        "signals": signals, "verdict": verdict, "converging": not signals,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Correspondence drain-trend convergence report / gate.")
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 on sustained non-convergence")
    ap.add_argument("--window", type=int, default=WINDOW, help="most-recent points to assess")
    ap.add_argument("--min-points", type=int, default=MIN_POINTS, help="min points before a trend is judgeable")
    ap.add_argument("--stale-hours", type=float, default=STALE_HOURS, help="window must span this long to call a stall")
    ap.add_argument("--trend-file", default=str(TREND_JSONL), help="fixture JSONL — bypasses the live series")
    ap.add_argument("--stamp", default=str(ROOT / "logs" / "correspondence-drain-trend-status.json"))
    args = ap.parse_args(argv)

    points = _load_points(Path(args.trend_file))
    a = assess(points, args.window, args.min_points, args.stale_hours)

    payload = {
        "schema": "limen.correspondence.drain-trend.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trend_file": str(args.trend_file),
        **a,
    }
    try:
        p = Path(args.stamp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"  (stamp skipped: {exc})", file=sys.stderr)

    span = f"{a['span_hours']}h" if a.get("span_hours") is not None else "—"
    rd, hd = a.get("reply_owed_delta"), a.get("needs_human_delta")
    print(
        f"correspondence-drain-trend: {a['verdict'].upper()} — {a['points_total']} points "
        f"({a['window_points']} in window, span {span}), "
        f"Δreply_owed={rd if rd is not None else '—'} Δneeds_human={hd if hd is not None else '—'}"
        + (f" · signals: {', '.join(a['signals'])}" if a.get("signals") else "")
    )

    if args.check and a["signals"]:
        print("correspondence-drain-trend: RED — the ledger is not draining "
              f"({', '.join(a['signals'])}); the organ is re-owing faster than it clears", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
