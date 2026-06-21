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
    # just burns capacity with zero output, so ESCALATE to needs_human (surface to the human, the
    # cheapest path) instead of silently recycling. Reversible status flip. ([[no-never-happens-again]])
    chronic_ids = {x["id"] for x in verify.get("chronic", [])}

    if not acquire_lock():
        print("queue lock held by daemon — skipping this pass (will retry next tick)")
        return 0
    try:
        path = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
        lf = load_limen_file(path)
        now = datetime.datetime.now(datetime.timezone.utc)
        done, reopened, escalated = [], [], []

        for t in lf.tasks:
            # CHRONIC escalation runs on the churning (open/failed) chronic tasks, NOT the dispatched
            # ones the loop below handles — stop them re-looping; surface for a human. Idempotent
            # (skips ones already needs_human). Reversible.
            if t.id in chronic_ids and t.status in ("open", "failed"):
                t.status = "needs_human"
                t.updated = now
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal", status="needs_human",
                    output="heal-dispatch: chronic (reopened ≥3×, never a PR) → escalated, stop re-looping"))
                escalated.append(t.id)
                continue
            if t.status != "dispatched":   # re-check fresh state under lock
                continue
            if t.id in merged_ids:
                t.status = "done"
                t.updated = now
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal",
                    status="done", output="heal-dispatch: PR merged → done"))
                done.append(t.id)
            elif t.id in open_pr_ids:
                # work produced an OPEN PR (awaiting merge) — mark done at the dispatch level
                # so it leaves the loop and is NOT recycled into a DUPLICATE PR. The merge
                # itself is tracked separately (PR-close backlog), gated on CI/billing.
                t.status = "done"
                t.updated = now
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal",
                    status="done", output="heal-dispatch: PR open (awaiting merge) → done"))
                done.append(t.id)
            elif t.id in closed_ids or t.id in nopr_ids:
                # NO_PR: only reopen if STILL no PR url (daemon may have re-dispatched)
                if t.id in nopr_ids and PR_RE.search(last_session(t)):
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

        print(f"heal-dispatch: {len(done)} merged→done, {len(reopened)} stuck→open, "
              f"{len(escalated)} chronic→needs_human")
        for i in done:
            print(f"    done:   {i}")
        for i in reopened:
            print(f"    reopen: {i}")
        for i in escalated:
            print(f"    escalate: {i}")
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
