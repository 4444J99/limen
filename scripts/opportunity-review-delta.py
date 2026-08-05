#!/usr/bin/env python3
"""opportunity-review-delta — the inbound-opportunity review-due detector (limen-side of the lane).

THE PROBLEM IT CLOSES: the mail beat now classifies first-touch recruiter/client leads into the
`inbound-lead-hire` / `inbound-lead-deploy` / `inbound-linkedin` protocol classes (UMA
feat/inbound-lead-protocols) and drafts a SAFE first-touch ack. But a LEAD is not a one-shot reply —
it is a pipeline: it moves through interview/offer states, it can stall with the ball in our court,
and a LinkedIn row may have no reply path at all until contact discovery runs. Nothing keeps that
cross-state cadence; it fires only when the operator remembers to look. This is the beat sensor that
replaces that memory: each cadence it reads the obligations ledger, filters the inbound-lead classes,
and surfaces a PII-CLEAN "review-due" delta — counts and org/door only, NEVER a counterparty name or
email — so the handful that actually needs a human move surfaces without a manual sweep.

It is the sibling of relationship-review-delta.py (the Maddie/relationship cadence) one domain over:
same fail-open, read-only, PII-clean, count-only contract; same --json / --notify shape.

DESIGN (bounded, read-only, fail-open, PII-clean):
  - Reads obligations-ledger.json (gitignored; built keylessly by UMA's obligations_build.py). It may
    predate the inbound-lead classes entirely — every field access is guarded; absent ⇒ empty state.
  - Filters obligations to cls ∈ {inbound-lead-hire, inbound-lead-deploy, inbound-linkedin}.
  - If ~/Workspace/application-pipeline exists, shells to its opportunity_sync.py (located at runtime
    under tools/ or scripts/) with --ledger, to fold pipeline-state truth in. Absent / erroring ⇒ a
    PII-clean note and the ledger-only view; never a crash.
  - Computes needs_human deltas: entries in interview/offer states with no fresh next-action; any lead
    where the ball is on us (pending_on == "us") for > 24h (RED); inbound-linkedin rows with no reply
    path (flag "needs contact discovery / Chrome pass"); any counterparty demanding a portal/ATS form.
  - Effector (--notify): appends COUNT-ONLY events to the sealed private log
    ~/Workspace/_people-private/opportunities/review-due.jsonl (dir created 0700) AND pushes a
    count-only line through the existing notify cascade (notify-events._emit → macOS + ntfy).
  - Always writes a PII-clean logs/opportunity-status.json for the faces (counts by class/tier,
    red_count, linkedin_no_path, generated_at) plus a mirror-silence note when zero inbound-linkedin
    rows have EVER been seen (the LinkedIn→Gmail mirror is likely off).
  - FAIL-OPEN: any error prints a PII-clean note and exits 0. It runs on the live beat; it must never
    red the beat and never leak a name.

Usage:
  python3 scripts/opportunity-review-delta.py            # dry: compute + print the count summary only
  python3 scripts/opportunity-review-delta.py --notify   # + append the sealed log + push count-only
  python3 scripts/opportunity-review-delta.py --json      # machine-readable summary (counts only)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
# The ledger the mail organ regenerates every sweep (gitignored). Overridable for tests / alt hosts.
LEDGER = Path(os.environ.get("LIMEN_OBLIGATIONS_LEDGER", ROOT / "obligations-ledger.json"))
STATUS_JSON = LOGS / "opportunity-status.json"
# The application-pipeline checkout supplies pipeline-state truth (interview/offer, pending_on). Host fact.
APPLICATION_PIPELINE = HOME / "Workspace" / "application-pipeline"
# The sealed private opportunities log — sits with the _people-private estate (ARCA-sealed, never public).
OPP_PRIVATE = HOME / "Workspace" / "_people-private" / "opportunities"
REVIEW_LOG = OPP_PRIVATE / "review-due.jsonl"
# A first-seen marker: once ANY inbound-linkedin row is observed, the mirror is proven on. Its absence
# after the sensor has run at least once ⇒ the LinkedIn→Gmail mirror is likely still off.
LINKEDIN_SEEN_MARKER = OPP_PRIVATE / ".linkedin-seen"

# The three inbound-lead protocol classes this lane owns. Single source of truth (the class-parity
# predicate scripts/check-opportunity-lane.sh reads this literal). Kept in exact lockstep with the
# UMA feat/inbound-lead-protocols classes.
INBOUND_CLASSES = ("inbound-lead-hire", "inbound-lead-deploy", "inbound-linkedin")
LINKEDIN_CLASS = "inbound-linkedin"
STALE_ON_US_HOURS = 24  # ball on us longer than this ⇒ RED
PIPELINE_STATES = ("interview", "offer")  # states that owe a fresh next-action


def _log_clean(msg: str) -> None:
    """PII-clean note to STDERR (still captured by the beat log). Never contains a name, email, or
    handle. Stderr so it never pollutes the machine-readable --json summary on stdout."""
    print(f"opportunity-review-delta: {msg}", file=sys.stderr)


def _load_ledger() -> dict:
    """The obligations ledger, or an empty dict. May lack the inbound-lead classes entirely (older build)."""
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _inbound_obligations(ledger: dict) -> list[dict]:
    """Every ledger obligation whose class is one of the inbound-lead classes. Guarded throughout."""
    obligations = ledger.get("obligations")
    if not isinstance(obligations, list):
        return []
    out: list[dict] = []
    for o in obligations:
        if isinstance(o, dict) and o.get("cls") in INBOUND_CLASSES:
            out.append(o)
    return out


def _sync_opportunity_pipeline() -> str | None:
    """If application-pipeline is present, run its opportunity_sync.py (--ledger) to fold pipeline
    truth into the ledger before we read it. Fail-open: absent / erroring ⇒ a PII-clean note, no crash.
    Returns a short PII-clean status note (or None if the pipeline is simply absent)."""
    if not APPLICATION_PIPELINE.exists():
        return None
    sync = None
    for sub in ("tools", "scripts"):
        candidate = APPLICATION_PIPELINE / sub / "opportunity_sync.py"
        if candidate.exists():
            sync = candidate
            break
    if sync is None:
        return "application-pipeline present but opportunity_sync.py not found (tools/ or scripts/) — ledger-only view"
    try:
        proc = subprocess.run(
            [sys.executable, str(sync), "--ledger", str(LEDGER)],
            capture_output=True, timeout=120, cwd=str(APPLICATION_PIPELINE),
        )
        if proc.returncode != 0:
            return f"opportunity_sync.py exited {proc.returncode} — ledger-only view (fail-open)"
        return "opportunity_sync.py ok — pipeline state folded in"
    except (OSError, subprocess.SubprocessError):
        return "opportunity_sync.py could not run — ledger-only view (fail-open)"


def _hours_since(iso: str | None) -> float | None:
    """Hours since an ISO-8601 timestamp, or None if it is absent / unparseable. Fail-open."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None


def _door(o: dict) -> str:
    """The PUBLIC-SAFE routing tag for a lead — its door (hire/deploy/linkedin) and, if present, the
    repo/org slug that drew it. Deliberately org/door only — never a person, email, or handle."""
    cls = o.get("cls", "")
    door = {"inbound-lead-hire": "hire", "inbound-lead-deploy": "deploy",
            LINKEDIN_CLASS: "linkedin"}.get(cls, cls)
    org = o.get("org") or o.get("repo") or o.get("source_repo") or ""
    return f"{door}:{org}" if org else door


def _needs_human(obligations: list[dict]) -> dict:
    """Compute the count-only needs_human deltas. Returns a PII-clean dict of counts + org/door lists.

    Never returns a counterparty name/email — only the derived door tag (_door) and integer counts.
    """
    red_doors: list[str] = []          # ball on us > 24h
    stale_state_doors: list[str] = []  # interview/offer with no fresh next-action
    linkedin_no_path: list[str] = []   # inbound-linkedin with no reply path (needs contact discovery)
    portal_form_doors: list[str] = []  # counterparty demands a portal/ATS form
    for o in obligations:
        cls = o.get("cls", "")
        # RED: the ball is on us and it has been on us too long.
        if str(o.get("pending_on") or "").lower() == "us":
            hrs = _hours_since(o.get("pending_since") or o.get("last_activity"))
            if hrs is None or hrs > STALE_ON_US_HOURS:
                red_doors.append(_door(o))
        # interview/offer state without a fresh next action.
        state = str(o.get("state") or o.get("stage") or "").lower()
        if state in PIPELINE_STATES and not (o.get("next_action") or o.get("next_step")):
            stale_state_doors.append(_door(o))
        # inbound-linkedin with no reply path ⇒ needs contact discovery / Chrome pass.
        if cls == LINKEDIN_CLASS:
            has_path = bool(o.get("reply_to") or o.get("email") or o.get("contact") or o.get("reply_path"))
            if not has_path:
                linkedin_no_path.append(_door(o))
        # a counterparty demanding an external portal/ATS form (we never complete those).
        if o.get("requires_portal_form") or o.get("ats_form") or "portal" in str(o.get("blocker") or "").lower():
            portal_form_doors.append(_door(o))
    return {
        "red_doors": sorted(set(red_doors)),
        "stale_state_doors": sorted(set(stale_state_doors)),
        "linkedin_no_path_doors": sorted(set(linkedin_no_path)),
        "portal_form_doors": sorted(set(portal_form_doors)),
    }


def _counts(obligations: list[dict]) -> dict:
    """PII-clean counts by class and by tier. Only class ids (internal, not PII) and integer counts."""
    by_class: dict[str, int] = {c: 0 for c in INBOUND_CLASSES}
    by_tier: dict[str, int] = {}
    for o in obligations:
        cls = o.get("cls", "")
        if cls in by_class:
            by_class[cls] += 1
        tier = str(o.get("tier") or o.get("rung") or "unknown")
        by_tier[tier] = by_tier.get(tier, 0) + 1
    return {"by_class": by_class, "by_tier": by_tier}


def _emit_notify(title: str, msg: str) -> None:
    """Push a count-only line through the EXISTING notify cascade (notify-events._emit → macOS + ntfy).
    Fail-open: if notify-events is unimportable or the cascade errors, skip silently — never crash."""
    try:
        spec = importlib.util.spec_from_file_location(
            "_notify_events_probe", ROOT / "scripts" / "notify-events.py")
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        emit = getattr(module, "_emit", None)
        if callable(emit):
            emit(title, msg)
    except Exception:  # noqa: BLE001 — the cascade is best-effort; never red the beat
        pass


def _write_effector(events: list[dict]) -> None:
    """Append COUNT-ONLY records to the sealed private review-due log (0700 dir). No names, ever."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OPP_PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with REVIEW_LOG.open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps({**ev, "detected_at": stamp}) + "\n")


def _mark_linkedin_seen() -> None:
    try:
        OPP_PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        LINKEDIN_SEEN_MARKER.touch()
    except OSError:
        pass


def _mirror_silence(linkedin_count: int) -> bool:
    """True ⇒ emit the mirror-silence note: no inbound-linkedin row has EVER been seen (mirror likely
    off). Once one is seen we drop a durable marker so the note stops firing on a genuinely-empty week."""
    if linkedin_count > 0:
        _mark_linkedin_seen()
        return False
    return not LINKEDIN_SEEN_MARKER.exists()


def _write_status(status: dict) -> None:
    """Write the PII-clean face JSON. Fail-open — a write error is noted, never fatal."""
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        STATUS_JSON.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        _log_clean("could not write logs/opportunity-status.json (fail-open)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Inbound-opportunity review-due detector (count-only, PII-clean).")
    ap.add_argument("--notify", action="store_true", help="append the sealed count-only log + push via the notify cascade")
    ap.add_argument("--json", action="store_true", help="print a machine-readable (count-only) summary")
    args = ap.parse_args(argv)

    # FAIL-OPEN wrapper: nothing below may red the beat or leak.
    try:
        sync_note = _sync_opportunity_pipeline()
        if sync_note:
            _log_clean(sync_note)

        ledger = _load_ledger()
        obligations = _inbound_obligations(ledger)
        counts = _counts(obligations)
        needs = _needs_human(obligations)
        linkedin_count = counts["by_class"].get(LINKEDIN_CLASS, 0)
        mirror_off = _mirror_silence(linkedin_count)

        red_count = len(needs["red_doors"])
        linkedin_no_path = len(needs["linkedin_no_path_doors"])

        status = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "counts": counts,
            "red_count": red_count,
            "linkedin_no_path": linkedin_no_path,
            "stale_state_count": len(needs["stale_state_doors"]),
            "portal_form_count": len(needs["portal_form_doors"]),
            "total_inbound": len(obligations),
            "doors": needs,  # org/door tags only — PII-clean by construction (_door)
            "mirror_silence": mirror_off,
        }
        _write_status(status)

        if mirror_off:
            _log_clean("mirror-silence: zero inbound-linkedin rows ever seen — the LinkedIn→Gmail mirror is likely OFF")

        # The --notify effector: only fire when there is something a human owes (RED, stale-state,
        # no-path, or a portal-form demand). A quiet week writes nothing and pushes nothing.
        events: list[dict] = []
        if red_count:
            events.append({"kind": "red_ball_on_us", "count": red_count, "doors": needs["red_doors"]})
        if needs["stale_state_doors"]:
            events.append({"kind": "stale_pipeline_state", "count": len(needs["stale_state_doors"]),
                           "doors": needs["stale_state_doors"]})
        if linkedin_no_path:
            events.append({"kind": "linkedin_no_reply_path", "count": linkedin_no_path,
                           "doors": needs["linkedin_no_path_doors"]})
        if needs["portal_form_doors"]:
            events.append({"kind": "portal_form_demanded", "count": len(needs["portal_form_doors"]),
                           "doors": needs["portal_form_doors"]})

        if args.notify and events:
            _write_effector(events)
            _emit_notify(
                "LIMEN opportunity review-due",
                f"{red_count} RED (ball on us >24h), {linkedin_no_path} LinkedIn no-path, "
                f"{len(needs['stale_state_doors'])} stale interview/offer across {len(obligations)} inbound leads",
            )

        if args.json:
            print(json.dumps({
                "total_inbound": len(obligations),
                "by_class": counts["by_class"],
                "red_count": red_count,
                "linkedin_no_path": linkedin_no_path,
                "stale_state_count": len(needs["stale_state_doors"]),
                "portal_form_count": len(needs["portal_form_doors"]),
                "mirror_silence": mirror_off,
            }))
        else:
            # The primary beat-log summary line goes to stdout (the count face of the run).
            print(
                f"opportunity-review-delta: {len(obligations)} inbound leads — {red_count} RED (ball on us >24h), "
                f"{linkedin_no_path} LinkedIn no-path, {len(needs['stale_state_doors'])} stale interview/offer"
            )
        return 0
    except Exception as exc:  # noqa: BLE001 — beat safety: never propagate, never leak the message verbatim
        _log_clean(f"skipped on error ({type(exc).__name__})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
