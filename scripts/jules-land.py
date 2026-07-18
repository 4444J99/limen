#!/usr/bin/env python3
"""Land completed Jules sessions through bounded custody and board transactions.

Dry-run by default. ``--apply`` performs the external Git/PR work and records
the exact durable outcome. ``--limit`` bounds attempted sessions.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.io import load_limen_file  # noqa: E402
from limen.jules_landing_custody import completed_sessions  # noqa: E402
from limen.jules_landing_transaction import process_session  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument(
        "--recover",
        action="store_true",
        help=(
            "also re-land jules tasks marked done that NEVER got a PR (the "
            "harvest gap: harvest closed them without applying the diff)"
        ),
    )
    args = parser.parse_args()

    board = load_limen_file(TASKS)
    session_to_task: dict[str, str] = {}
    for task in board.tasks:
        for entry in task.dispatch_log or []:
            session_id = str(entry.session_id or "")
            if session_id.isdigit():
                session_to_task[session_id] = task.id

    done = 0
    attempted = 0
    for session_id, task_id in completed_sessions(session_to_task):
        if attempted >= max(0, args.limit):
            break
        if not task_id:
            continue
        attempted += 1
        if process_session(
            TASKS,
            task_id,
            session_id,
            apply=args.apply,
            recover=args.recover,
        ):
            done += 1
    if args.apply and done:
        print(f"  APPLIED -> {done} jules session(s) landed + marked done")
    elif not args.apply:
        print("  dry-run (pass --apply to land for real)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
