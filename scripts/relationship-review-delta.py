#!/usr/bin/env python3
"""relationship-review-delta — the review-due detector (the L1 effector for the Maddie/relationship cadence).

THE PROBLEM IT CLOSES: the relationship-pipeline delta review ("review her messages / dice up what needs
tending") keeps NO cross-review state and has NO schedule — it fires only when the operator remembers to ask,
so a wave of new asks can sit unreviewed indefinitely. This is the beat sensor that replaces the operator's
memory: on a weekly cadence it counts, per person, how many NEW inbound messages have arrived since the last
review recorded in that person's durable register, and when the volume crosses a threshold it surfaces a
PII-CLEAN "review due" signal — a count, never a name — so the operator knows to run the (semantic) dice-up.

It does NOT auto-dice: extracting the actual asks is a reasoning pass, not a deterministic one. This detector
only answers "is a review owed, and roughly how big" — the honest deterministic half.

DESIGN (bounded, read-only, fail-open, PII-clean):
  - Reads the slug list from the relationship-pipeline `people.json` and each person's durable register
    `~/Workspace/_people-private/people/<slug>/open-asks.yaml` (the `last_review` cursor).
  - Counts inbound messages since `last_review` from `~/Library/Messages/chat.db` via a READ-ONLY, immutable
    sqlite connection (never locks the live Messages DB). Phone handles are read at runtime and NEVER printed.
  - Effector (`--notify`): appends a per-slug record to the SEALED private log `~/Workspace/_people-private/
    review-due.jsonl` and stamps `review_due` back into the register. The only thing printed to stdout (which
    the beat log captures) is a count-only summary — no person is ever named on a public surface.
  - FAIL-OPEN: any error (chat.db absent / FDA-denied / locked / bad register) prints a PII-clean note and
    exits 0. This runs on the live beat; it must never red the beat and never leak.

Usage:
  python3 scripts/relationship-review-delta.py            # dry: compute + print the count summary only
  python3 scripts/relationship-review-delta.py --notify   # + write the sealed log + register review_due flag
  python3 scripts/relationship-review-delta.py --json      # machine-readable summary (counts only)
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

HOME = Path.home()
# Canonical host paths (facts on this machine, not tunable config — kept out of the parameter panel).
RP_ROOT = HOME / "Workspace" / "4444J99" / "relationship-pipeline"
PEOPLE_PRIVATE = HOME / "Workspace" / "_people-private" / "people"
CHAT_DB = HOME / "Library" / "Messages" / "chat.db"
REVIEW_LOG = PEOPLE_PRIVATE.parent / "review-due.jsonl"  # sealed with the _people-private estate
# New inbound messages since last review at or above this count ⇒ a delta review is worth running.
THRESHOLD = int(os.environ.get("LIMEN_RELATIONSHIP_REVIEW_THRESHOLD", "20"))
APPLE_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01 (Apple Core Data epoch)


def _log_clean(msg: str) -> None:
    """PII-clean line to stdout (captured by the beat log). Never contains a name or a handle."""
    print(f"relationship-review-delta: {msg}")


def _slugs_and_handles() -> list[tuple[str, list[str]]]:
    """(slug, [handles]) from people.json. Handles are PII — returned for querying, never logged."""
    people = json.loads((RP_ROOT / "people.json").read_text(encoding="utf-8")).get("people", [])
    out: list[tuple[str, list[str]]] = []
    for person in people:
        slug = person.get("slug")
        if not slug:
            continue
        handles: list[str] = []
        for h in person.get("handles", []) or []:
            handles.append(h if isinstance(h, str) else (h.get("handle") or h.get("id") or ""))
        out.append((slug, [h for h in handles if h]))
    return out


def _last_review_cursor(slug: str) -> str | None:
    """The `last_review` date from the person's durable register, or None if there is no register yet."""
    reg = PEOPLE_PRIVATE / slug / "open-asks.yaml"
    if not reg.exists():
        return None
    data = yaml.safe_load(reg.read_text(encoding="utf-8")) or {}
    val = data.get("last_review")
    return str(val) if val is not None else None


def _apple_ns_since(date_str: str) -> int:
    """Convert a YYYY-MM-DD (local midnight) cursor to the chat.db nanosecond timestamp threshold."""
    dt = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    return int((dt.timestamp() - APPLE_EPOCH_OFFSET) * 1_000_000_000)


def _count_new_inbound(handles: list[str], since_ns: int) -> int:
    """Read-only COUNT of inbound messages from `handles` after `since_ns`. Immutable ⇒ never locks live DB."""
    uri = f"file:{CHAT_DB}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        placeholders = ",".join("?" for _ in handles)
        sql = (
            f"SELECT COUNT(*) FROM message m JOIN handle h ON m.handle_id = h.ROWID "
            f"WHERE h.id IN ({placeholders}) AND m.is_from_me = 0 AND m.date > ?"
        )
        row = conn.execute(sql, [*handles, since_ns]).fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Relationship review-due detector (deterministic half).")
    ap.add_argument("--notify", action="store_true", help="write the sealed review-due log + register flag")
    ap.add_argument("--json", action="store_true", help="print a machine-readable (count-only) summary")
    args = ap.parse_args(argv)

    # FAIL-OPEN wrapper: nothing below may red the beat or leak.
    try:
        if not CHAT_DB.exists():
            _log_clean("chat.db not present — skipping (nothing to detect)")
            return 0

        results: list[dict] = []
        for slug, handles in _slugs_and_handles():
            cursor = _last_review_cursor(slug)
            if not cursor or not handles:
                continue  # only track people who have a durable register and a handle
            try:
                new_inbound = _count_new_inbound(handles, _apple_ns_since(cursor))
            except sqlite3.OperationalError:
                # Almost always Full Disk Access denied to this interpreter — fail-open, note it once.
                _log_clean("chat.db unreadable (Full Disk Access for the beat interpreter?) — skipping")
                return 0
            results.append({"slug": slug, "last_review": cursor, "new_inbound": new_inbound,
                            "review_due": new_inbound >= THRESHOLD})

        due = [r for r in results if r["review_due"]]
        if args.notify and due:
            _write_effector(due)

        if args.json:
            # Count-only: slugs are internal identifiers, not handles; still, summarize rather than dump.
            print(json.dumps({"checked": len(results), "review_due": len(due), "threshold": THRESHOLD}))
        else:
            _log_clean(f"{len(due)}/{len(results)} people review-due (>= {THRESHOLD} new inbound since last review)")
        return 0
    except Exception as exc:  # noqa: BLE001 — beat safety: never propagate, never leak the message verbatim
        _log_clean(f"skipped on error ({type(exc).__name__})")
        return 0


def _write_effector(due: list[dict]) -> None:
    """Append to the sealed private review-due log (append-only; the commented register is never rewritten).

    The next review reads this log to know a dice-up is owed. We deliberately do NOT edit open-asks.yaml here —
    that file carries extensive human-authored comments a `yaml.safe_dump` round-trip would destroy; its
    review_due state is derived from this log, not stamped back into the YAML.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    REVIEW_LOG.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_LOG.open("a", encoding="utf-8") as fh:
        for r in due:
            fh.write(json.dumps({**r, "detected_at": stamp}) + "\n")


if __name__ == "__main__":
    sys.exit(main())
