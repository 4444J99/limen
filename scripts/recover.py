#!/usr/bin/env python3
"""recover.py — the HEAL function (funnel-middle recovery).

Two failure modes leak capacity:
  1. status==failed tasks just sit there. Re-open them at the TOP of the lane cascade
     (codex) so the dispatcher's per-task failover gives them a fresh run across lanes.
  2. status==dispatched jules tasks whose recorded session is no longer in `jules
     remote list` (aged out / lost) are orphaned — re-open so they re-dispatch fresh.

Reversible (only flips status→open + target_agent + logs a heal entry); never deletes,
never dispatches. Bounded by --limit. Run by the daemon's heal voice AND by supervision.
"""
import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import DispatchLogEntry  # noqa: E402

CASCADE_TOP = "codex"


def live_jules_sessions() -> set[str]:
    try:
        r = subprocess.run(["jules", "remote", "list", "--session"],
                           capture_output=True, text=True, timeout=90)
        return {p[0] for ln in r.stdout.splitlines()
                if (p := ln.split()) and p[0].isdigit()}
    except Exception:
        return set()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS"))
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    path = Path(args.tasks)
    lf = load_limen_file(path)
    now = datetime.datetime.now(datetime.timezone.utc)

    live = None  # lazily fetched only if we have orphan candidates
    reopened_failed, reopened_orphan = [], []

    for t in lf.tasks:
        if len(reopened_failed) + len(reopened_orphan) >= args.limit:
            break
        if t.status == "failed":
            t.status = "open"
            t.target_agent = CASCADE_TOP
            t.labels = [x for x in t.labels if not x.startswith("tried:")]
            t.updated = now
            t.dispatch_log.append(DispatchLogEntry(
                timestamp=now, agent="limen", session_id="heal",
                status="open", output="recover: reopened failed → fresh cascade"))
            reopened_failed.append(t.id)
        elif t.status == "dispatched" and t.target_agent == "jules":
            sid = ""
            for e in reversed(t.dispatch_log or []):
                if str(e.session_id or "").isdigit() and len(str(e.session_id)) >= 12:
                    sid = str(e.session_id); break
            if not sid:
                continue
            if live is None:
                live = live_jules_sessions()
            if live and sid not in live:  # session aged out / lost → orphaned
                t.status = "open"
                t.updated = now
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal",
                    status="open", output=f"recover: orphaned (session {sid} gone) → reopened"))
                reopened_orphan.append(t.id)

    print(f"recover: {len(reopened_failed)} failed reopened, {len(reopened_orphan)} orphaned reopened")
    if args.apply:
        save_limen_file(path, lf)
        print("  APPLIED -> tasks.yaml")
    else:
        print("  dry-run (pass --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
