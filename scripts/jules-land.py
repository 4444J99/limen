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
from limen.jules_landing_custody import completed_sessions, load_orphan_adoptions  # noqa: E402
from limen.jules_landing_transaction import process_session  # noqa: E402
from limen.models import dispatch_session_id  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
ADOPTIONS = Path(os.environ.get("LIMEN_JULES_ADOPTIONS", str(ROOT / "docs" / "jules-orphan-adoptions.jsonl")))


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
            session_id = dispatch_session_id(entry)
            if session_id.isdigit():
                session_to_task[session_id] = task.id

    adopted = load_orphan_adoptions(ADOPTIONS)
    done = 0
    attempted = 0
    orphans: list[str] = []
    for session_id, task_id in completed_sessions(session_to_task):
        if not task_id:
            # A completed session with no receipt mapping is finished work sitting unowned
            # at the provider — surface it loudly (the 2026-07-23 overnight canaries sat
            # invisible here), unless the adoption ledger records an out-of-band landing.
            if session_id not in adopted:
                orphans.append(session_id)
            continue
        if attempted >= max(0, args.limit):
            break
        attempted += 1
        if process_session(
            TASKS,
            task_id,
            session_id,
            apply=args.apply,
            recover=args.recover,
        ):
            done += 1
    for session_id in orphans:
        print(
            f"  ORPHAN jules session {session_id}: completed with no task mapping — the launch "
            f"bypassed dispatch receipts; land it (jules remote pull --session {session_id} --apply) "
            f"or record the out-of-band landing in {ADOPTIONS.name}"
        )
    if orphans:
        print(f"  {len(orphans)} orphan completed jules session(s): finished work is unowned at the provider")
    if args.apply and done:
        print(f"  APPLIED -> {done} jules session(s) landed + marked done")
    elif not args.apply:
        print("  dry-run (pass --apply to land for real)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
