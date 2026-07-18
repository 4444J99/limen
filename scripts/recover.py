#!/usr/bin/env python3
"""recover.py — the HEAL function (funnel-middle recovery).

Two failure modes leak capacity:
  1. status==failed tasks just sit there. Re-open them at the TOP of the lane cascade
     (codex) so the dispatcher's per-task failover gives them a fresh run across lanes.
  2. status==dispatched jules tasks whose recorded session failed, stalled for
     user feedback / plan approval, or is positively confirmed absent are orphaned — re-open so
     they re-dispatch fresh. A miss in a non-exhaustive remote catalog is held, never reopened.

Reversible (only flips status→open + target_agent + logs a heal entry); never deletes,
never dispatches. Bounded by --limit. Run by the daemon's heal voice AND by supervision.
"""

import argparse
import datetime
import os
import re
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file, queue_lock, save_limen_file  # noqa: E402
from limen.jules_remote import (  # noqa: E402
    JulesRemoteSnapshot,
    classify_jules_claim,
    coerce_jules_snapshot,
    probe_jules_remote_session_absences,
    probe_jules_remote_sessions,
    task_jules_session_id,
)
from limen.models import DispatchLogEntry, has_jules_landing_hold  # noqa: E402
from limen.dispatch import (  # noqa: E402
    WORKSTREAM_SUCCESSOR_REQUIRED_LABEL,
    _has_done_transition,
    _restore_done_status,
)
from limen.chronic import CHRONIC_FLEET_DEBT_LABEL  # noqa: E402

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
        if str(entry.status or "") == "failed" and NOOP_FAILURE_RE.search(str(entry.output or ""))
    )


def _repeated_noop_failure_count(task) -> int:
    count = _noop_failure_count(task)
    if count >= NOOP_RECOVERY_ESCALATION_THRESHOLD:
        return count
    return 0


def live_jules_sessions(session_ids: Iterable[str] = ()) -> JulesRemoteSnapshot:
    snapshot = probe_jules_remote_sessions()
    return probe_jules_remote_session_absences(snapshot, session_ids)


def _recover(args: argparse.Namespace, path: Path) -> int:
    lf = load_limen_file(path)
    now = datetime.datetime.now(datetime.timezone.utc)
    selected_ids = set(args.task_ids or [])
    jules_session_ids = [
        task_jules_session_id(task)
        for task in lf.tasks
        if (not selected_ids or task.id in selected_ids)
        and task.status == "dispatched"
        and task.target_agent == "jules"
        and not has_jules_landing_hold(task)
        and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL not in (task.labels or [])
        and not _has_done_transition(task)
    ]

    live: JulesRemoteSnapshot | None = None  # lazily fetched only if we have orphan candidates
    reopened_failed: list[str] = []
    reopened_orphan: list[str] = []
    reopened_remote_failed: list[str] = []
    escalated_noop: list[str] = []
    held_landing: list[str] = []
    held_successor: list[str] = []
    restored_done: list[str] = []

    for t in lf.tasks:
        if selected_ids and t.id not in selected_ids:
            continue
        if (
            len(reopened_failed) + len(reopened_orphan) + len(reopened_remote_failed) + len(escalated_noop)
            >= args.limit
        ):
            break
        if has_jules_landing_hold(t):
            held_landing.append(t.id)
            continue
        if _has_done_transition(t):
            if _restore_done_status(
                t,
                now,
                session_id="heal",
                output="recover: prior done transition wins; restored terminal status",
            ):
                restored_done.append(t.id)
            continue
        if WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (t.labels or []):
            # A status flip does not revoke the immutable packet boundary. Hold
            # every non-terminal lifecycle state, including stale dispatched
            # rows, without probing or reopening the old provider session.
            held_successor.append(t.id)
            continue
        if t.status == "failed":
            repeated_noop_count = _repeated_noop_failure_count(t)
            if repeated_noop_count:
                # Repeated no-ops are the FLEET's inability (it keeps producing nothing), not a human
                # atom — park in failed_blocked (which nothing recycles: recover reopens `failed`, not
                # `failed_blocked`), NOT needs_human, so the human surface stays truthful. Same
                # fleet-debt class heal-dispatch parks chronic churn in (see limen.chronic); tagged so
                # it reads as debt. Historical needs_human no-op dumps are re-homed by heal-dispatch's
                # self-migration, whose predicate now also matches the "repeated no-op failures" string.
                t.status = "failed_blocked"
                t.updated = now
                if CHRONIC_FLEET_DEBT_LABEL not in (t.labels or []):
                    t.labels = list(t.labels or []) + [CHRONIC_FLEET_DEBT_LABEL]
                t.dispatch_log.append(
                    DispatchLogEntry(
                        timestamp=now,
                        agent="limen",
                        session_id="heal",
                        status="failed_blocked",
                        output=(
                            f"recover: repeated no-op failures ({repeated_noop_count}) "
                            "-> failed_blocked (fleet-debt, off the human surface)"
                        ),
                    )
                )
                escalated_noop.append(t.id)
                continue
            t.status = "open"
            t.target_agent = CASCADE_TOP
            t.labels = [x for x in t.labels if not x.startswith("tried:")]
            t.updated = now
            t.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=now,
                    agent="limen",
                    session_id="heal",
                    status="open",
                    output="recover: reopened failed → fresh cascade",
                )
            )
            reopened_failed.append(t.id)
        elif t.status == "dispatched" and t.target_agent == "jules":
            sid = task_jules_session_id(t)
            if not sid:
                continue
            if live is None:
                live = coerce_jules_snapshot(live_jules_sessions(jules_session_ids))
            action, remote_status = classify_jules_claim(live, sid)
            if action == "recover":
                t.status = "open"
                t.target_agent = CASCADE_TOP
                t.updated = now
                t.dispatch_log.append(
                    DispatchLogEntry(
                        timestamp=now,
                        agent="limen",
                        session_id="heal",
                        status="open",
                        output=f"recover: jules session {sid} is {remote_status} → reopened",
                    )
                )
                reopened_remote_failed.append(t.id)
            elif action == "release":
                t.status = "open"
                t.updated = now
                t.dispatch_log.append(
                    DispatchLogEntry(
                        timestamp=now,
                        agent="limen",
                        session_id="heal",
                        status="open",
                        output=f"recover: orphaned (session {sid} gone) → reopened",
                    )
                )
                reopened_orphan.append(t.id)

    print(
        f"recover: {len(reopened_failed)} failed reopened, "
        f"{len(reopened_orphan)} orphaned reopened, "
        f"{len(reopened_remote_failed)} remote-failed reopened, "
        f"{len(escalated_noop)} repeated-noop escalated, "
        f"{len(held_landing)} jules-landing held, "
        f"{len(held_successor)} successor-required held"
    )
    if args.apply:
        changed = bool(restored_done or reopened_failed or reopened_orphan or reopened_remote_failed or escalated_noop)
        if changed:
            save_limen_file(path, lf)
            print("  APPLIED -> tasks.yaml")
        else:
            print("  UNCHANGED -> tasks.yaml")
    else:
        print("  dry-run (pass --apply)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--task-id", action="append", dest="task_ids", help="Limit recovery to a specific task id")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    path = Path(args.tasks)
    if not args.apply:
        return _recover(args, path)
    with queue_lock(path) as got:
        if not got:
            print("recover: queue lock busy — skipped this pass")
            return 0
        return _recover(args, path)


if __name__ == "__main__":
    raise SystemExit(main())
