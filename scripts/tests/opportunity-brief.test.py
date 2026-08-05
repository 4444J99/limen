#!/usr/bin/env python3
"""Hermetic regression for opportunity-brief.py's STALE WARM LEADS surfacing.

Pure, no mail, no live state: point LIMEN_ROOT at a temp dir holding a crafted
logs/correspondence-dispositions.json, load compose(), and assert:

  1. stale_awaiting > 0 renders the "STALE WARM LEADS ... — follow up or drop" cue,
     the count is folded into the subject's `owed` total, and NO per-lead PII
     (recipient / subject) leaks into the emailed body (the counts-only invariant).
  2. stale_awaiting == 0 renders no stale cue (today's baseline — no false nag).
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
_PII_RECIPIENT = "sekrit.recruiter@example.com"
_PII_SUBJECT = "Re: your Staff Engineer application at AcmeCorp"


def _compose_with(disp: dict):
    """Load opportunity-brief.py against a temp LIMEN_ROOT carrying `disp`, return (subject, body)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "logs").mkdir()
        (root / "logs" / "correspondence-dispositions.json").write_text(json.dumps(disp))
        os.environ["LIMEN_ROOT"] = str(root)
        # ROOT is a module-level constant read at import — load fresh under the temp root.
        spec = importlib.util.spec_from_file_location("opportunity_brief", SCRIPTS / "opportunity-brief.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.compose()


def main() -> int:
    fails: list[str] = []

    # 1. stale_awaiting=2 → cue renders, owed reflects +2, no PII leak.
    disp_stale = {
        "reply_owed": 0,
        "stale_awaiting": 2,
        "needs_human": 2,
        "by_disposition": {"awaiting-them": 0, "held": 0, "needs-human": 2},
        # PII lives only in rows[]/sidecar; the brief must never echo it into the body.
        "rows": [{"recipient": _PII_RECIPIENT, "subject": _PII_SUBJECT, "disposition": "needs-human"}],
    }
    subject, body = _compose_with(disp_stale)
    if "STALE WARM LEADS" not in body:
        fails.append("stale_awaiting=2: expected 'STALE WARM LEADS' cue in body")
    if "follow up or drop" not in body:
        fails.append("stale_awaiting=2: expected 'follow up or drop' action cue")
    if "2" not in body.split("STALE WARM LEADS", 1)[-1][:40]:
        fails.append("stale_awaiting=2: expected the count '2' on the cue line")
    # owed subtotal drives the subject; 2 stale + 0 else ⇒ '2 owed'.
    if "2 owed" not in subject:
        fails.append(f"stale_awaiting=2: expected '2 owed' in subject, got: {subject!r}")
    if _PII_RECIPIENT in body or _PII_SUBJECT in body:
        fails.append("PII LEAK: recipient/subject from rows[] appeared in the emailed body")

    # 2. stale_awaiting=0 → no cue, no false nag (today's live baseline).
    _s0, body0 = _compose_with({"reply_owed": 0, "stale_awaiting": 0, "by_disposition": {}})
    if "STALE WARM LEADS" in body0:
        fails.append("stale_awaiting=0: cue rendered when it must be silent")

    if fails:
        print("FAIL opportunity-brief.test.py")
        for f in fails:
            print("  -", f)
        return 1
    print("PASS opportunity-brief.test.py — stale-warm-lead cue renders, counted, PII-clean; silent at 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
