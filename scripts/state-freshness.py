#!/usr/bin/env python3
"""state-freshness — a generic "did this state file stop refreshing?" guard.

A monitor that silently stops writing is worse than no monitor: everything downstream
keeps reading the last-good file and reports all-clear while the world moves on. That is
exactly the 2026-07-21 failure that blinded the opportunity engine for ~18h — the beat
ticked, but ``logs/opportunity-status.json`` had not been rewritten, and nothing noticed.

``scripts/host-pressure-stale.py`` already guards the VITALS gauge that way, but bespoke.
This is the same idea factored into ONE parameterized rung so the next state file that can
freeze (opportunity-status now; more later) is a one-line registry entry, not a new script.
The alarm is the *staleness*, not the contents — the effector for the contents is whatever
organ writes the file.

Contract (matches host-pressure-stale + the sensor registry):
  * READ-ONLY. The only side effect is one onset-deduped macOS notification via _notify.
  * Fails TOWARD stale: an absent file, an unparseable/absent timestamp field, or a
    timestamp older than --max-age-seconds all exit 1 (advisory in the registry) — because
    a frozen writer is precisely how the file goes missing or quits advancing.
  * Exit 0 = fresh (writer alive); exit 1 = stale (surface it). Never raises past main().

Usage:
  state-freshness.py --file logs/opportunity-status.json --field generated_at \
      --max-age-seconds 46800 --key opportunity-status-stale --label "opportunity engine"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _notify  # noqa: E402


def _root() -> Path:
    env = os.environ.get("LIMEN_ROOT")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[1]


def _get_field(obj: dict, dotted: str):
    """Read a top-level or dotted-path field; None if any segment is missing."""
    cur = obj
    for seg in dotted.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return None
        cur = cur[seg]
    return cur


def _parse_ts(raw: str) -> datetime:
    """Parse ISO8601 (Z or naive-UTC) into an aware UTC datetime."""
    ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Flag a state file that has stopped refreshing.")
    ap.add_argument("--file", required=True, help="state file, relative to LIMEN_ROOT or absolute")
    ap.add_argument("--field", default="generated_at", help="timestamp field (dotted path ok)")
    ap.add_argument("--max-age-seconds", type=float, required=True, help="stale if older than this")
    ap.add_argument("--key", default=None, help="notify dedup key (default: <stem>-stale)")
    ap.add_argument("--label", default=None, help="human label (default: file stem)")
    args = ap.parse_args(argv)

    root = _root()
    path = Path(args.file)
    if not path.is_absolute():
        path = root / path
    label = args.label or path.stem
    key = args.key or f"{path.stem}-stale"

    def stale(msg: str) -> int:
        line = f"state-freshness: STALE — {label}: {msg}"
        print(line)
        _notify.notify_once(root, key, line, title="LIMEN state-freshness")
        return 1

    if not path.exists():
        return stale(f"{path} absent — the writer may have stopped")

    try:
        raw = _get_field(json.loads(path.read_text()), args.field)
    except Exception as exc:
        return stale(f"unreadable ({exc})")
    if raw is None:
        return stale(f"no '{args.field}' field in {path.name}")

    try:
        ts = _parse_ts(raw)
    except Exception as exc:
        return stale(f"unparseable '{args.field}'={raw!r} ({exc})")

    age_s = (datetime.now(timezone.utc) - ts).total_seconds()
    if age_s > args.max_age_seconds:
        return stale(
            f"{path.name} '{args.field}' is {age_s / 3600:.1f}h old "
            f"(budget {args.max_age_seconds / 3600:.1f}h) — the writer has stopped refreshing it"
        )

    _notify.clear_condition(root, key)
    print(
        f"state-freshness: ok — {label}: {path.name} {age_s / 3600:.1f}h old (budget {args.max_age_seconds / 3600:.1f}h)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
