#!/usr/bin/env python3
"""check-mail-answered.py — the executable predicate for "email is getting answered".

The C_MAIL organ's failure mode (2026-06→07) was silent: the beat's draft *effector* was
stripped out and the whole heartbeat later froze, so the obligations ledger stopped being
rebuilt and no reply-owed mail got drafted — while every read-only status probe still looked
"green". This predicate is the sensor that would have gone red the moment that happened.

Exit 0  ⟺  the mail effector is alive:
  1. the ledger exists and is FRESH (rebuilt within LIMEN_MAIL_LEDGER_MAX_AGE_HOURS), and
  2. every reply-owed obligation has been ENRICHED with draft_text (the draft effector ran).

Exit 1 otherwise (missing / stale ledger, or reply-owed mail with no composed draft).

PII-safe by construction: prints COUNTS only, never senders/subjects/bodies — it is meant to
be safe to surface on the beat log and public-ish faces. Sensor-without-effector is a defect
([[sensor-without-effector-defect]]); here the effector is the beat's draft step and this is
its paired sensor.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
LEDGER = Path(os.environ.get("LIMEN_OBLIGATIONS_LEDGER", ROOT / "obligations-ledger.json"))
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


def main() -> int:
    if not LEDGER.exists():
        print(f"mail-answered: FAIL — no obligations ledger at {LEDGER} (the beat never built it)")
        return 1
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — any parse failure is a red predicate
        print(f"mail-answered: FAIL — ledger unreadable: {exc}")
        return 1

    obligations = data.get("obligations") or []
    reply_owed = [o for o in obligations if isinstance(o, dict) and o.get("requires_reply")]
    drafted = [o for o in reply_owed if str(o.get("draft_text") or "").strip()]
    saved = [o for o in reply_owed if o.get("draft_saved")]
    undrafted = len(reply_owed) - len(drafted)

    generated = _parse_ts(str(data.get("generated_at") or ""))
    if generated is None:
        print("mail-answered: FAIL — ledger has no parseable generated_at (freshness unknown)")
        return 1
    age_hours = (datetime.now(timezone.utc) - generated).total_seconds() / 3600.0

    stale = age_hours > MAX_AGE_HOURS
    unenriched = undrafted > 0

    status = "OK" if not (stale or unenriched) else "FAIL"
    print(
        f"mail-answered: {status} — ledger age {age_hours:.1f}h/{MAX_AGE_HOURS:.0f}h, "
        f"reply_owed={len(reply_owed)} drafted={len(drafted)} saved={len(saved)} "
        f"undrafted={undrafted}"
    )
    if stale:
        print(f"  · STALE: ledger not rebuilt in {age_hours:.1f}h — the beat/effector is not running")
    if unenriched:
        print(f"  · UNENRICHED: {undrafted} reply-owed obligation(s) have no composed draft")
    return 0 if status == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
