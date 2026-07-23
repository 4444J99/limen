#!/usr/bin/env python3
"""Jules daily-quota sensor: used-vs-target, orphaned completions, recovery states.

The vendor grants a daily task quota that expires unused at reset; 2026-01-21 ->
2026-07-23 the lane sat silent with no gauge (183 days, zero landed output). This
sensor is that gauge. It never mutates anything: the EFFECTORS are the existing beat
rungs — drain.sh (jules-land) lands finished sessions, metabolize 4b dispatch fills
the quota.

Exit 0 = healthy. Exit 1 (advisory) when finished work sits unowned (orphans), when
sessions need recovery (failed / awaiting feedback / awaiting plan approval), or when
usage is still under target late in the UTC day (LIMEN_JULES_QUOTA_ALARM_HOUR).
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.capacity import derived_daily_floor  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.jules_landing_custody import completed_sessions, load_orphan_adoptions  # noqa: E402
from limen.jules_remote import JULES_RECOVERY_STATES, probe_jules_remote_sessions  # noqa: E402
from limen.models import dispatch_session_id  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
ADOPTIONS = Path(os.environ.get("LIMEN_JULES_ADOPTIONS", str(ROOT / "docs" / "jules-orphan-adoptions.jsonl")))


def used_today(board: object, today: date) -> int:
    """Count Jules dispatch receipts stamped today (UTC) — the system's own launch count."""
    used = 0
    for task in getattr(board, "tasks", None) or []:
        for entry in task.dispatch_log or []:
            if str(getattr(entry, "agent", "") or "").lower() != "jules":
                continue
            if str(getattr(entry, "status", "") or "").lower() != "dispatched":
                continue
            stamp = getattr(entry, "timestamp", None)
            when = stamp.date() if isinstance(stamp, datetime) else None
            if when == today:
                used += 1
    return used


def main() -> int:
    board = load_limen_file(TASKS)
    now = datetime.now(timezone.utc)
    used = used_today(board, now.date())
    target = derived_daily_floor("jules", board)

    session_to_task: dict[str, str] = {}
    for task in board.tasks:
        for entry in task.dispatch_log or []:
            session_id = dispatch_session_id(entry)
            if session_id.isdigit():
                session_to_task[session_id] = task.id

    snapshot = probe_jules_remote_sessions()
    adopted = load_orphan_adoptions(ADOPTIONS)
    orphans = 0
    recovery = 0
    probe_note = ""
    if snapshot.available:
        orphans = sum(
            1
            for sid, task_id in completed_sessions(session_to_task, snapshot=snapshot)
            if not task_id and sid not in adopted
        )
        recovery = sum(1 for session in snapshot.sessions.values() if session.status in JULES_RECOVERY_STATES)
    else:
        probe_note = f" probe_unavailable({snapshot.error[:60]})"

    try:
        alarm_hour = int(os.environ.get("LIMEN_JULES_QUOTA_ALARM_HOUR", "18") or "18")
    except ValueError:
        alarm_hour = 18
    under_late = used < target and now.hour >= alarm_hour
    print(f"  jules-quota: used={used} target={target} orphans={orphans} recovery={recovery}{probe_note}")
    return 1 if (orphans or recovery or under_late) else 0


if __name__ == "__main__":
    raise SystemExit(main())
