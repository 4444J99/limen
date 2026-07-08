#!/usr/bin/env python3
"""recover.py — the HEAL function (funnel-middle recovery).

Two failure modes leak capacity:
  1. status==failed tasks just sit there. Re-open them at the TOP of the lane cascade
     (codex) so the dispatcher's per-task failover gives them a fresh run across lanes.
  2. status==dispatched jules tasks whose recorded session failed, stalled for
     user feedback / plan approval, or is no longer in `jules remote list` (aged out / lost) are
     orphaned — re-open so they re-dispatch fresh.

Reversible (only flips status→open + target_agent + logs a heal entry); never deletes,
never dispatches. Bounded by --limit. Run by the daemon's heal voice AND by supervision.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import DispatchLogEntry  # noqa: E402
from limen.dispatch import _has_done_transition, _restore_done_status  # noqa: E402

CASCADE_TOP = "codex"
NOOP_RECOVERY_ESCALATION_THRESHOLD = 2
NOOP_FAILURE_RE = re.compile(
    r"\b(?:no[- ]?op|noop|made no changes|no changes|no pr opened|clean-noop)\b",
    re.IGNORECASE,
)


def _noop_failure_count(task) -> int:
    return sum(
        1
        for entry in task.dispatch_log or []
        if str(entry.status or "") == "failed"
        and NOOP_FAILURE_RE.search(str(entry.output or ""))
    )


def _repeated_noop_failure_count(task) -> int:
    count = _noop_failure_count(task)
    if count >= NOOP_RECOVERY_ESCALATION_THRESHOLD:
        return count
    return 0


def live_jules_sessions() -> dict[str, str]:
    try:
        r = subprocess.run(["jules", "remote", "list", "--session"],
                           capture_output=True, text=True, timeout=90)
        sessions = {}
        for line in r.stdout.splitlines():
            parts = line.split()
            if not parts or not parts[0].isdigit():
                continue
            low = line.lower()
            if "failed" in low:
                status = "failed"
            elif "awaiting plan" in low:
                status = "awaiting_plan_approval"
            elif "awaiting user" in low or "awaiting feedback" in low:
                status = "awaiting_user_feedback"
            elif "completed" in low:
                status = "completed"
            elif "planning" in low:
                status = "planning"
            elif "in progress" in low or "running" in low:
                status = "in_progress"
            else:
                status = "unknown"
            sessions[parts[0]] = status
        return sessions
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--task-id", action="append", dest="task_ids", help="Limit recovery to a specific task id")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    path = Path(args.tasks)
    lf = load_limen_file(path)
    now = datetime.datetime.now(datetime.timezone.utc)
    selected_ids = set(args.task_ids or [])

    live = None  # lazily fetched only if we have orphan candidates
    reopened_failed, reopened_orphan, reopened_remote_failed, escalated_noop = [], [], [], []

    for t in lf.tasks:
        if selected_ids and t.id not in selected_ids:
            continue
        if (
            len(reopened_failed)
            + len(reopened_orphan)
            + len(reopened_remote_failed)
            + len(escalated_noop)
            >= args.limit
        ):
            break
        if _has_done_transition(t):
            _restore_done_status(
                t,
                now,
                session_id="heal",
                output="recover: prior done transition wins; restored terminal status",
            )
            continue
        if t.status == "failed":
            repeated_noop_count = _repeated_noop_failure_count(t)
            if repeated_noop_count:
                t.status = "needs_human"
                t.updated = now
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal",
                    status="needs_human",
                    output=(
                        f"recover: repeated no-op failures ({repeated_noop_count}) "
                        "-> needs_human; stop fresh cascade"
                    )))
                escalated_noop.append(t.id)
                continue
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
            if live and live.get(sid) in {"failed", "awaiting_user_feedback", "awaiting_plan_approval"}:
                remote_status = live.get(sid)
                t.status = "open"
                t.target_agent = CASCADE_TOP
                t.updated = now
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal",
                    status="open", output=f"recover: jules session {sid} is {remote_status} → reopened"))
                reopened_remote_failed.append(t.id)
            elif live and sid not in live:  # session aged out / lost → orphaned
                t.status = "open"
                t.updated = now
                t.dispatch_log.append(DispatchLogEntry(
                    timestamp=now, agent="limen", session_id="heal",
                    status="open", output=f"recover: orphaned (session {sid} gone) → reopened"))
                reopened_orphan.append(t.id)

    print(
        f"recover: {len(reopened_failed)} failed reopened, "
        f"{len(reopened_orphan)} orphaned reopened, "
        f"{len(reopened_remote_failed)} remote-failed reopened, "
        f"{len(escalated_noop)} repeated-noop escalated"
    )
    if args.apply:
        save_limen_file(path, lf)
        print("  APPLIED -> tasks.yaml")
    else:
        print("  dry-run (pass --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
