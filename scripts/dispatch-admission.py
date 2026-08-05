#!/usr/bin/env python3
"""Check the shared dispatch admission gate without launching workers."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.dispatch import dispatch_admission_check  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS"), help="tasks.yaml path")
    parser.add_argument("--task-id", help="explicit human-selected task id, if any")
    parser.add_argument("--check", action="store_true", help="return non-zero when admission blocks")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--no-refresh-handoff",
        action="store_true",
        help="inspect the current handoff without running handoff-relay.py first",
    )
    args = parser.parse_args()

    root = Path(os.environ.get("LIMEN_ROOT", Path.cwd()))
    tasks = Path(args.tasks).expanduser() if args.tasks else root / "tasks.yaml"
    receipt = dispatch_admission_check(
        tasks,
        task_id=args.task_id,
        refresh_handoff=not args.no_refresh_handoff,
    )
    if args.json or args.check:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        state = "allowed" if receipt.get("allow") else "blocked"
        print(f"dispatch-admission: {state} ({receipt.get('status')})")
        if receipt.get("reason"):
            print(f"reason: {receipt['reason']}")
        if receipt.get("next_command"):
            print(f"next: {receipt['next_command']}")
    if args.check and not receipt.get("allow", False):
        return int(receipt.get("exit_code") or 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
