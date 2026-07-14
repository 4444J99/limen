#!/usr/bin/env python3
"""heal-dispatch.py — close the loop verify-dispatch.py opened. NO SILENT FAILURES.

recover.py heals failed + orphaned-jules. It does NOT know about the silent-failure
classes verify-dispatch.py surfaces, so those tasks sit stuck in 'dispatched' forever:
  - PR_MERGED        : PR merged but task still 'dispatched'  → status=done (work landed)
  - PR_CLOSED        : PR closed unmerged                     → status=open (re-dispatch)
  - DISPATCHED_NO_PR : local lane 'dispatched' but no PR URL  → status=open (re-dispatch)

Safe by the same rules as recover.py: only flips status (+ a heal log entry), never
deletes, never pushes/merges/dispatches. Reversible. Acquires the shared queue-lock so it
never races the daemon's tasks.yaml writes; RELOADS fresh under the lock and RE-CHECKS each
task's current state before changing it (so it can't clobber progress the daemon made
between the verify pass and now). Dry-run by default; --apply to write.

Usage:  python3 scripts/heal-dispatch.py [--apply]
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.chronic import CHRONIC_FLEET_DEBT_LABEL, chronic_escalated_to_needs_human  # noqa: E402
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import DispatchLogEntry  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
LOCKD = ROOT / "logs" / ".queue.lock.d"
PR_RE = re.compile(r"github\.com/[^/]+/[^/]+/pull/\d+")
CASCADE_TOP = "codex"


def acquire_lock(timeout=15):
    for _ in range(timeout):
        try:
            LOCKD.mkdir()
            return True
        except FileExistsError:
            time.sleep(1)
    return False


def last_session(t):
    log = t.dispatch_log or []
    return str(log[-1].session_id) if log else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    vf = ROOT / "logs" / "dispatch-verify.json"
    if not vf.exists():
        print("no logs/dispatch-verify.json — run verify-dispatch.py first")
        return 1
    verify = json.loads(vf.read_text())
    det = verify.get("detail", {})
    merged_ids = {x["id"] for x in det.get("PR_MERGED", [])}
    closed_ids = {x["id"] for x in det.get("PR_CLOSED", [])}
    nopr_ids = {x["id"] for x in det.get("DISPATCHED_NO_PR", [])}
    open_pr_ids = {x["id"] for x in det.get("PR_OPEN", [])}
    # CHRONIC: reopened >=3x, never produced a PR (verify-dispatch surfaces these). Re-looping them
    # just burns capacity with zero output — but chronic churn is the FLEET's inability, not a human
    # atom, so it parks in failed_blocked (which nothing recycles), NOT needs_human (the human
    # surface). The exact `needs-human` label is the his-hand opt-out, mirroring heal-board's
    # label-wins rule. Reversible status flip. ([[no-never-happens-again]])
    chronic_ids = {x["id"] for x in verify.get("chronic", [])}

    if not acquire_lock():
        print("queue lock held by daemon — skipping this pass (will retry next tick)")
        return 0
    try:
        path = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
        lf = load_limen_file(path)
        now = datetime.datetime.now(datetime.timezone.utc)
        merged_done, open_pr_done, reopened, parked, rehomed = [], [], [], [], []

        def park_chronic(t, why: str):
            """Park chronic fleet-debt in failed_blocked; a `needs-human`-labeled task stays on
            the human surface (his-hand opt-out). The opt-out write says "kept", never "escalat…",
            so chronic_escalated_to_needs_human() can never re-home it later."""
            if "needs-human" in (t.labels or []):
                t.status = "needs_human"
                out = f"heal-dispatch: {why} → needs_human (kept: needs-human label)"
            else:
                t.status = "failed_blocked"
                if CHRONIC_FLEET_DEBT_LABEL not in (t.labels or []):
                    t.labels = list(t.labels or []) + [CHRONIC_FLEET_DEBT_LABEL]
                out = f"heal-dispatch: {why} → failed_blocked (fleet-debt, off the human surface)"
            t.updated = now
            t.dispatch_log.append(DispatchLogEntry(
                timestamp=now, agent="limen", session_id="heal", status=t.status, output=out))
            parked.append(f"{t.id} → {t.status}")

        for t in lf.tasks:
            # CHRONIC parking runs on the churning (open/failed) chronic tasks, NOT the dispatched
            # ones the loop below handles — stop them re-looping without polluting the human
            # surface. Idempotent (a parked task is neither open/failed nor chronic-listed again).
            if t.id in chronic_ids and t.status in ("open", "failed"):
                park_chronic(t, "chronic (reopened ≥3×, never a PR)")
                continue
            # SELF-MIGRATION: a task the machine previously escalated to needs_human for chronic
            # churn is fleet-debt mis-homed on the human surface — re-home it to failed_blocked.
            # Log-evidence predicate, not the verify chronic list (chronic_tasks() never scans
            # needs_human). Structurally idempotent: once moved, no branch matches it again.
            if (t.status == "needs_human" and "needs-human" not in (t.labels or [])
                    and chronic_escalated_to_needs_human(t)):
                t.status = "failed_blocked"
                t.updated = now
                if CHRONIC_FLEET_DEBT_LABEL not in (t.labels or []):
                    t.labels = list(t.labels or []) + [CHRONIC_FLEET_DEBT_LABEL]
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal", status="failed_blocked",
                    output="heal-dispatch: chronic escalation re-homed needs_human → failed_blocked "
                           "(fleet-debt, not a human atom)"))
                rehomed.append(t.id)
                continue
            if t.status != "dispatched":   # re-check fresh state under lock
                continue
            if t.id in merged_ids:
                t.status = "done"
                t.updated = now
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal",
                    status="done", output="heal-dispatch: PR merged → done"))
                merged_done.append(t.id)
            elif t.id in open_pr_ids:
                # work produced an OPEN PR (awaiting merge) — mark done at the dispatch level
                # so it leaves the loop and is NOT recycled into a DUPLICATE PR. The merge
                # itself is tracked separately (PR-close backlog), gated on CI/billing.
                t.status = "done"
                t.updated = now
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal",
                    status="done", output="heal-dispatch: PR open (awaiting merge) → done"))
                open_pr_done.append(t.id)
            elif t.id in closed_ids or t.id in nopr_ids:
                # NO_PR: only reopen if STILL no PR url (daemon may have re-dispatched)
                if t.id in nopr_ids and PR_RE.search(last_session(t)):
                    continue
                if t.id in chronic_ids:
                    park_chronic(t, "dispatched with no PR and chronic (reopened ≥3×)")
                    continue
                t.status = "open"
                t.target_agent = t.target_agent or CASCADE_TOP
                t.labels = [x for x in t.labels if not x.startswith("tried:")]
                t.updated = now
                why = "PR closed unmerged" if t.id in closed_ids else "dispatched but no PR (silent no-op)"
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal",
                    status="open", output=f"heal-dispatch: {why} → reopened"))
                reopened.append(t.id)

        print(f"heal-dispatch: {len(merged_done)} merged→done, "
              f"{len(open_pr_done)} open-pr→done, {len(reopened)} stuck→open, "
              f"{len(parked)} chronic→parked, {len(rehomed)} needs_human→failed_blocked re-homed")
        for i in merged_done:
            print(f"    merged: {i}")
        for i in open_pr_done:
            print(f"    open:   {i}")
        for i in reopened:
            print(f"    reopen: {i}")
        for i in parked:
            print(f"    park:   {i}")
        for i in rehomed:
            print(f"    rehome: {i}")
        if args.apply:
            save_limen_file(path, lf)
            print("  APPLIED -> tasks.yaml")
        else:
            print("  dry-run (pass --apply)")
    finally:
        try:
            LOCKD.rmdir()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
