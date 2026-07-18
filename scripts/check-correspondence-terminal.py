#!/usr/bin/env python3
"""check-correspondence-terminal.py — the executable predicate for "correspondence is walked to the end".

The done-predicate twin of correspondence-walk.py (the effector) and a sibling of
check-mail-answered.py one lane over. Where check-mail-answered proves every reply-owed row was
DRAFTED, this proves every reply-owed row reached a TERMINAL DISPOSITION and the walk is at a
fixed point — the machine half of the AUTONOMY_PAUSED release predicate ("every audited row has
a terminal disposition").

Exit 0  ⟺  the correspondence walk is drained:
  1. the obligations ledger exists and is FRESH (rebuilt within LIMEN_MAIL_LEDGER_MAX_AGE_HOURS),
  2. every reply-owed obligation has a disposition row in logs/correspondence-dispositions.json
     (joined by the SAME _ob_key the walk/sender use), and
  3. no row is a HOLD lacking a composed draft (draft_missing == 0), i.e. fixed_point == true.

Exit 1 otherwise (missing/stale ledger, an un-walked reply-owed row, or a draft-missing HOLD row).

PII-safe by construction: prints COUNTS only. Sensor-without-effector is a defect
([[sensor-without-effector-defect]]); the effector here is correspondence-walk.py.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
LEDGER = Path(os.environ.get("LIMEN_OBLIGATIONS_LEDGER", ROOT / "obligations-ledger.json"))
DISPOSITIONS = Path(os.environ.get("LIMEN_CORRESPONDENCE_DISPOSITIONS", ROOT / "logs" / "correspondence-dispositions.json"))
MAX_AGE_HOURS = float(os.environ.get("LIMEN_MAIL_LEDGER_MAX_AGE_HOURS", "12"))


def _parse_ts(raw: str) -> datetime | None:
    if not raw:
        return None
    txt = raw.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(txt)
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def main() -> int:
    ledger = _load(LEDGER)
    if ledger is None:
        print(f"correspondence-terminal: FAIL — no/unreadable obligations ledger at {LEDGER}")
        return 1

    generated = _parse_ts(str(ledger.get("generated_at") or ""))
    if generated is None:
        print("correspondence-terminal: FAIL — ledger has no parseable generated_at (freshness unknown)")
        return 1
    age_hours = (datetime.now(timezone.utc) - generated).total_seconds() / 3600.0
    stale = age_hours > MAX_AGE_HOURS

    disp = _load(DISPOSITIONS)
    if disp is None:
        print(f"correspondence-terminal: FAIL — no dispositions file at {DISPOSITIONS} (the walk never ran)")
        return 1

    obligations = ledger.get("obligations") or []
    reply_owed_keys = set()
    for o in obligations:
        if isinstance(o, dict) and o.get("requires_reply"):
            mids = o.get("message_ids") or []
            tail = mids[0] if mids else (o.get("sample_subjects") or [""])[0][:40]
            reply_owed_keys.add(f"{o.get('cls')}|{o.get('domain')}|{tail}")

    rows = disp.get("rows") or []
    disposed_keys = {r.get("ob_key") for r in rows if isinstance(r, dict)}
    draft_missing = sum(1 for r in rows if isinstance(r, dict) and r.get("draft_missing"))
    needs_human = sum(1 for r in rows if isinstance(r, dict) and r.get("disposition") == "needs-human")

    un_walked = reply_owed_keys - disposed_keys
    fixed_point = bool(disp.get("fixed_point"))

    ok = (not stale) and (not un_walked) and (draft_missing == 0) and fixed_point
    status = "OK" if ok else "FAIL"
    print(
        f"correspondence-terminal: {status} — ledger age {age_hours:.1f}h/{MAX_AGE_HOURS:.0f}h, "
        f"reply_owed={len(reply_owed_keys)} walked={len(reply_owed_keys) - len(un_walked)} "
        f"draft_missing={draft_missing} needs_human={needs_human} fixed_point={fixed_point}"
    )
    if stale:
        print(f"  · STALE: ledger not rebuilt in {age_hours:.1f}h — the beat/effector is not running")
    if un_walked:
        print(f"  · UN-WALKED: {len(un_walked)} reply-owed obligation(s) have no disposition row")
    if draft_missing:
        print(f"  · DRAFT-MISSING: {draft_missing} HOLD row(s) lack a composed draft")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
