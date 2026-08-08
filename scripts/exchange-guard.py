#!/usr/bin/env python3
"""exchange-guard — flags money moved inside a call window (organvm/limen#2088).

THE PATTERN IT CLOSES: consequential decisions made on a SYNCHRONOUS channel. On a live call the
pause required to evaluate a request is itself an observable act the other party is present for, so
the ordinary defense ("pause, name the state, ask who benefits") has its first step structurally
removed. That is a property of the medium, not a character flaw — which is why the fix is channel
selection (POTESTAS protocol #2105) and this guard is how you find out whether it held.

WHAT IT IS NOT: a judgement about anyone. It reports that a structurally-recognizable pattern
occurred — a transfer inside a call window — and nothing about intent, and nothing about a person.

CONTRACT (identical to scripts/relationship-review-delta.py, the shipped template for this class):
  - READ-ONLY, immutable sqlite URIs. Never locks the live Messages or CallHistory DBs.
  - COUNT-ONLY stdout. Never a name, handle, or message body. `--detail` adds timestamps and
    amounts for interactive use; the beat never passes it.
  - FAIL-OPEN. Any error (DB absent, Full Disk Access denied, locked, schema drift) prints a
    PII-clean note and exits 0. This runs on the beat; it must never red it and must never leak.

DATA-LAYER NOTES (each cost a session to establish):
  - Payments are `balloon_bundle_id LIKE '%PeerPayment%'` — NOT PassKit. Searching PassKit returns
    nothing and reads as "no money moved."
  - The amount is NOT recoverable by a raw-byte regex over payload_data: the plist stores NSStrings
    as UTF-16, so `$7` is `\\x00$\\x007` on disk and a bytes-level `\\$\\d` finds only the plist's own
    `$3`/`$4` internals. Parse the plist, then read the DECODED strings — where the amount appears
    TWICE, in the ldtext ("Sent $7 with Apple Cash.") and the caption ("$7 Payment").
  - `message.date` is NANOSECONDS since the Apple epoch (2001-01-01, offset 978307200).
  - ZANSWERED is ALWAYS 0 for outgoing calls. Connectedness is `ZDURATION > 0`.

Usage:
  python3 scripts/exchange-guard.py                 # count-only summary
  python3 scripts/exchange-guard.py --detail        # + timestamps and amounts (interactive only)
  python3 scripts/exchange-guard.py --json          # machine-readable counts
  python3 scripts/exchange-guard.py --window 15     # minutes either side of a connected call
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CHAT_DB = HOME / "Library" / "Messages" / "chat.db"
CALL_DB = HOME / "Library" / "Application Support" / "CallHistoryDB" / "CallHistory.storedata"

APPLE_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01
DEFAULT_WINDOW_MIN = int(os.environ.get("LIMEN_EXCHANGE_GUARD_WINDOW_MIN", "15"))

AMOUNT_RE = re.compile(r"\$\s?([0-9][0-9,]*(?:\.[0-9]{1,2})?)")


def _clean(msg: str) -> None:
    """PII-clean line to stdout (captured by the beat log). Never a name or a handle."""
    print(f"exchange-guard: {msg}")


def _ro(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True, timeout=5)


def _apple_ns_to_dt(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / 1_000_000_000 + APPLE_EPOCH_OFFSET, tz=timezone.utc)


def _apple_s_to_dt(s: float) -> datetime:
    return datetime.fromtimestamp(s + APPLE_EPOCH_OFFSET, tz=timezone.utc)


def _amount_from_payload(payload: bytes | None) -> float | None:
    """The amount, read from the DECODED plist strings.

    The value appears twice — once in the ldtext, once in the caption — which is what distinguishes
    it from any incidental number. A bytes-level regex cannot see it (UTF-16), and that failure mode
    is silent: it returns the plist's own `$3`/`$4` internals and looks like a successful parse.
    """
    if not payload:
        return None
    try:
        obj = plistlib.loads(payload)
    except Exception:
        return None

    strings: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            strings.append(node)

    walk(obj)

    counts: dict[str, int] = {}
    for s in strings:
        for raw in AMOUNT_RE.findall(s):
            counts[raw] = counts.get(raw, 0) + 1
    if not counts:
        return None
    # Prefer a value seen in more than one string (ldtext + caption); fall back to the largest.
    repeated = [v for v, c in counts.items() if c >= 2]
    pick = max(repeated or list(counts), key=lambda v: float(v.replace(",", "")))
    try:
        return float(pick.replace(",", ""))
    except ValueError:
        return None


def _payments() -> list[tuple[datetime, float | None, bool]]:
    """(when, amount, is_outgoing) for every Apple Cash balloon. Handles are never read."""
    conn = _ro(CHAT_DB)
    try:
        rows = conn.execute(
            "SELECT date, payload_data, is_from_me FROM message "
            "WHERE balloon_bundle_id LIKE '%PeerPayment%' AND date IS NOT NULL ORDER BY date"
        ).fetchall()
    finally:
        conn.close()
    return [(_apple_ns_to_dt(int(d)), _amount_from_payload(pd), bool(me)) for d, pd, me in rows]


def _connected_calls() -> list[tuple[datetime, float]]:
    """(start, duration_seconds) for CONNECTED calls only.

    ZANSWERED is always 0 for outgoing calls, so answering it as a boolean silently reclassifies
    every outgoing call as missed. Duration is the honest signal.
    """
    conn = _ro(CALL_DB)
    try:
        rows = conn.execute(
            "SELECT ZDATE, ZDURATION FROM ZCALLRECORD WHERE ZDATE IS NOT NULL AND ZDURATION > 0"
        ).fetchall()
    finally:
        conn.close()
    return [(_apple_s_to_dt(float(d)), float(dur)) for d, dur in rows]


def _flag(
    payments: list[tuple[datetime, float | None, bool]],
    calls: list[tuple[datetime, float]],
    window_min: int,
) -> list[tuple[datetime, float | None, bool]]:
    pad = window_min * 60
    spans = [(start.timestamp() - pad, start.timestamp() + dur + pad) for start, dur in calls]
    out = []
    for when, amt, outgoing in payments:
        ts = when.timestamp()
        if any(lo <= ts <= hi for lo, hi in spans):
            out.append((when, amt, outgoing))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Flag transfers decided inside a call window.")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW_MIN, help="minutes either side of a connected call")
    ap.add_argument("--detail", action="store_true", help="print timestamps and amounts (interactive only)")
    ap.add_argument("--json", action="store_true", help="machine-readable counts")
    args = ap.parse_args(argv)

    try:
        for db in (CHAT_DB, CALL_DB):
            if not db.exists():
                _clean("a source database is not present on this host — nothing to check (exit 0)")
                return 0
        payments = _payments()
        calls = _connected_calls()
        flagged = _flag(payments, calls, args.window)
    except Exception as exc:  # fail-open: this runs on the beat
        _clean(f"unavailable ({type(exc).__name__}) — treating as no finding (exit 0)")
        return 0

    sent = [p for p in flagged if p[2]]
    total = sum(a for _, a, out in flagged if out and a is not None)

    if args.json:
        print(
            json.dumps(
                {
                    "payments_total": len(payments),
                    "connected_calls": len(calls),
                    "window_minutes": args.window,
                    "flagged": len(flagged),
                    "flagged_outgoing": len(sent),
                    "flagged_outgoing_amount": round(total, 2),
                }
            )
        )
        return 0

    _clean(
        f"{len(payments)} transfer(s), {len(calls)} connected call(s); "
        f"{len(flagged)} transfer(s) inside a ±{args.window}min call window "
        f"({len(sent)} outgoing, ${total:,.2f})"
    )
    if args.detail:
        for when, amt, outgoing in flagged:
            direction = "sent" if outgoing else "received"
            shown = f"${amt:,.2f}" if amt is not None else "amount unparsed"
            print(f"  {when.strftime('%Y-%m-%d %H:%M:%S')}Z  {direction:8s} {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
