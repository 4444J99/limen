#!/usr/bin/env python3
"""opportunity-brief — the engine's DAILY VOICE to the operator (SPEAK rung).

The monitoring apparatus (mail sweep → obligations ledger → opportunity-review-delta →
correspondence-walk) surfaces everything to logs/*.json + a sealed private digest the
operator never opens. A continuous engine that is invisible *feels* like no engine at all.

This closes that gap: once per day it composes a plain-text brief from the already-computed
state files and EMAILS it to the operator's own inbox (padavano.anthony@gmail.com) — the one
surface he already reads. No new app, no phone subscribe, no lever. Reuses the headless
`scripts/mail-send` lane (UMA mail_send.py; creds hydrated by the credential organ).

Contract (matches the sibling sensors — opportunity-review-delta, correspondence-walk):
  * READ-ONLY over state; the only side effect is one email to SELF + a once/day stamp file.
  * Fail-OPEN: any error → log one line, exit 0. Never crash the beat.
  * Idempotent: at most one brief per calendar day (stamp in logs/opportunity-brief-state.json);
    --force overrides, --dry-run prints the body and sends nothing.
  * Recipient is HARDCODED to the operator's own address — never a third party, so no send gate
    beyond the human-invocation-is-authorization contract mail-send already enforces.

Usage:
  python3 scripts/opportunity-brief.py            # send today's brief if not already sent
  python3 scripts/opportunity-brief.py --dry-run  # print the brief, send nothing
  python3 scripts/opportunity-brief.py --force     # send even if one already went out today
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
OPERATOR_EMAIL = os.environ.get("LIMEN_OPERATOR_EMAIL", "padavano.anthony@gmail.com")
STATE_PATH = ROOT / "logs" / "opportunity-brief-state.json"


def _load(rel: str, default):
    """Load a JSON state file relative to ROOT; fail-open to `default`."""
    try:
        return json.loads((ROOT / rel).read_text())
    except Exception:
        return default


def _age_hours(iso: str | None) -> float | None:
    """Hours since an ISO8601 timestamp (Z or naive-UTC), or None if unparseable."""
    if not iso:
        return None
    try:
        s = iso.replace("Z", "+00:00")
        ts = _dt.datetime.fromisoformat(s)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=_dt.timezone.utc)
        now = _dt.datetime.now(_dt.timezone.utc)
        return round((now - ts).total_seconds() / 3600.0, 1)
    except Exception:
        return None


def _door_titles(doors: list, limit: int = 6) -> list[str]:
    """Pull human-readable one-liners from a doors[] list, defensively."""
    out = []
    for d in (doors or [])[:limit]:
        if isinstance(d, dict):
            label = d.get("title") or d.get("org") or d.get("who") or d.get("id") or "(unnamed)"
            extra = d.get("why") or d.get("next_step") or d.get("state") or ""
            out.append(f"    • {label}" + (f" — {extra}" if extra else ""))
        else:
            out.append(f"    • {d}")
    return out


def compose() -> tuple[str, str]:
    """Build (subject, body) from the live state files. Pure — no I/O side effects."""
    opp = _load("logs/opportunity-status.json", {})
    disp = _load("logs/correspondence-dispositions.json", {})
    ledger = _load("obligations-ledger.json", {})
    funnel = _load("logs/profile-conversion-funnel-latest.json", {})

    total_inbound = int(opp.get("total_inbound", 0) or 0)
    red_count = int(opp.get("red_count", 0) or 0)
    stale_count = int(opp.get("stale_state_count", 0) or 0)
    linkedin_no_path = int(opp.get("linkedin_no_path", 0) or 0)
    portal_forms = int(opp.get("portal_form_count", 0) or 0)
    mirror_silence = bool(opp.get("mirror_silence", False))
    by_class = (opp.get("counts", {}) or {}).get("by_class", {}) or {}
    doors = opp.get("doors", {}) or {}

    reply_owed = int(disp.get("reply_owed", 0) or 0)
    awaiting_them = int((disp.get("by_disposition", {}) or {}).get("awaiting-them", 0) or 0)
    held = int((disp.get("by_disposition", {}) or {}).get("held", 0) or 0)
    # Warm leads we replied to that went cold past the 14d stale flip (correspondence-walk.py) —
    # the "follow up or drop" decisions the operator owes. Count only; identity stays in the
    # sealed 0700 sidecar, never the emailed body.
    stale_awaiting = int(disp.get("stale_awaiting", 0) or 0)

    opp_age = _age_hours(opp.get("generated_at"))
    ledger_age = _age_hours(ledger.get("generated_at"))

    bottleneck = funnel.get("bottleneck", {}) or {}
    bstage = bottleneck.get("stage")
    bwhy = bottleneck.get("why") or ""
    broute = bottleneck.get("route") or ""
    funnel_age = _age_hours(funnel.get("generated"))

    today = _dt.datetime.now(_dt.timezone.utc).strftime("%a %b %-d")
    owed = red_count + stale_count + linkedin_no_path + portal_forms + reply_owed + stale_awaiting

    subject = (
        f"Opportunity brief — {owed} owed, {total_inbound} inbound, "
        f"LinkedIn {'OFF' if mirror_silence else 'on'}"
        f"{f' · bottleneck: {bstage}' if bstage else ''} · {today}"
    )

    L: list[str] = []
    L.append(f"OPPORTUNITY BRIEF — {today}")
    L.append("=" * 52)
    L.append("")
    if owed == 0 and total_inbound == 0:
        L.append("All quiet — nothing owed on your side. The engine is watching.")
    else:
        L.append(f"You owe a move on {owed} item(s). Details below.")
    L.append("")

    # The single bottleneck routes Aug-1 effort: don't build past the constraint. Named by
    # scripts/conversion-funnel.py (seen -> inbound -> revenue), refreshed on the beat (O2).
    if bstage:
        L.append(f"🎯 BOTTLENECK: {bstage} — the one constraint to push on.")
        if bwhy:
            L.append(f"    {bwhy}")
        if broute:
            L.append(f"    → {broute}")
        L.append("")

    L.append(f"INBOUND LEADS (in-flight): {total_inbound}")
    for cls, n in by_class.items():
        if n:
            L.append(f"    {cls}: {n}")
    L.append("")

    if red_count:
        L.append(f"⏰ BALL ON YOU >24h (RED): {red_count}")
        L.extend(_door_titles(doors.get("red_doors")))
        L.append("")
    if stale_count:
        L.append(f"🕓 STALE (awaiting them, going cold): {stale_count}")
        L.extend(_door_titles(doors.get("stale_state_doors")))
        L.append("")
    if portal_forms:
        L.append(f"📝 PORTAL/ATS FORM demanded: {portal_forms}")
        L.extend(_door_titles(doors.get("portal_form_doors")))
        L.append("")

    L.append("LINKEDIN:")
    if mirror_silence:
        L.append("    ⚠ Mirror is OFF — LinkedIn messages/InMails are NOT reaching the engine.")
        L.append("      One-time fix: LinkedIn → Settings → Communications → turn ON email")
        L.append("      notifications for messages & InMail. Then every LinkedIn touch flows in.")
    else:
        L.append("    Mirror on — LinkedIn touches flow into the pipeline.")
    if linkedin_no_path:
        L.append(f"    {linkedin_no_path} LinkedIn lead(s) with no reply path (contact-discovery queued).")
    L.append("")

    L.append("CORRESPONDENCE:")
    L.append(f"    reply-owed: {reply_owed}   awaiting-them: {awaiting_them}   held (your sig): {held}")
    if stale_awaiting:
        L.append(f"    🕰 STALE WARM LEADS (we replied, went cold >14d): {stale_awaiting} — follow up or drop")
        L.append("       who/thread in your sealed sidecar: _people-private/correspondence/dispositions-detail.jsonl")
    L.append("")

    # Engine-health footer — freshness proves the beat is actually alive (catches the
    # 2026-07-21 "22h blind" class of failure at a glance, from the operator's own inbox).
    L.append("-" * 52)
    fresh = []
    if opp_age is not None:
        flag = " ⚠ STALE" if opp_age > 6 else ""
        fresh.append(f"opportunity scan {opp_age}h ago{flag}")
    if ledger_age is not None:
        flag = " ⚠ STALE" if ledger_age > 6 else ""
        fresh.append(f"mail ledger {ledger_age}h ago{flag}")
    if funnel_age is not None:
        flag = " ⚠ STALE" if funnel_age > 30 else ""
        fresh.append(f"funnel {funnel_age}h ago{flag}")
    L.append("engine: " + ("; ".join(fresh) if fresh else "state files missing ⚠"))
    L.append("")
    L.append("(auto-sent daily by scripts/opportunity-brief.py — the engine's voice)")

    return subject, "\n".join(L)


def _already_sent_today() -> bool:
    st = _load("logs/opportunity-brief-state.json", {})
    return st.get("last_sent_date") == _dt.date.today().isoformat()


def _stamp_sent(subject: str) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(
                {
                    "last_sent_date": _dt.date.today().isoformat(),
                    "last_sent_at": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                    "subject": subject,
                },
                indent=2,
            )
        )
    except Exception:
        pass


def _send(subject: str, body: str) -> int:
    """Send via the headless mail-send lane. Returns the subprocess exit code."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(body)
        body_path = f.name
    try:
        proc = subprocess.run(
            [
                str(ROOT / "scripts" / "mail-send"),
                "--to",
                OPERATOR_EMAIL,
                "--subject",
                subject,
                "--body-file",
                body_path,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            sys.stderr.write(f"opportunity-brief: send failed rc={proc.returncode}: {proc.stderr.strip()[:200]}\n")
        return proc.returncode
    finally:
        try:
            os.unlink(body_path)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compose + email the daily opportunity brief to the operator.")
    ap.add_argument("--dry-run", action="store_true", help="print the brief; send nothing")
    ap.add_argument("--force", action="store_true", help="send even if one already went out today")
    args = ap.parse_args(argv)

    if os.environ.get("LIMEN_OPPORTUNITY_BRIEF", "1") != "1" and not args.dry_run and not args.force:
        print("opportunity-brief: gated off (LIMEN_OPPORTUNITY_BRIEF!=1)")
        return 0

    try:
        subject, body = compose()
    except Exception as e:  # fail-open — never crash the beat
        sys.stderr.write(f"opportunity-brief: compose failed, skipping ({e})\n")
        return 0

    if args.dry_run:
        print(f"Subject: {subject}\n\n{body}")
        return 0

    if _already_sent_today() and not args.force:
        print(f"opportunity-brief: already sent today — skip (subject would be: {subject})")
        return 0

    rc = _send(subject, body)
    if rc == 0:
        _stamp_sent(subject)
        print(f"opportunity-brief: sent to {OPERATOR_EMAIL} — {subject}")
    # fail-open even on send failure — a bad send must not crash the beat
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
