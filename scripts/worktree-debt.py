#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.worktree_debt import worktree_debt_report  # noqa: E402


def int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description="Report preserved worktree lifecycle debt.")
    parser.add_argument("--json", action="store_true", help="emit the raw debt report as JSON")
    parser.add_argument(
        "--fail-over-cap",
        action="store_true",
        help="exit non-zero when debt exceeds LIMEN_WORKTREE_DEBT_MAX",
    )
    parser.add_argument(
        "--fail-reapable-over-cap",
        action="store_true",
        help="exit non-zero when reapable roots exceed LIMEN_WORKTREE_REAPABLE_MAX",
    )
    args = parser.parse_args()

    report = worktree_debt_report()
    limit = int_env("LIMEN_WORKTREE_DEBT_MAX", 12)
    reapable_limit = int_env("LIMEN_WORKTREE_REAPABLE_MAX", 0)
    if args.json:
        print(
            json.dumps(
                {**report, "limit": limit, "reapable_limit": reapable_limit},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"worktree lifecycle debt: {report['debt']} debt roots / {report['total']} scanned (cap {limit})")
        print(f"worktree reapable roots: {report['reapable']} roots (cap {reapable_limit})")
        for reason, count in sorted(report["by_reason"].items()):
            print(f"  {reason}: {count}")
        if report["debt"] > limit:
            print("  gate: routine generated build-out dispatch is suppressed")
        if report["reapable"] > reapable_limit:
            print("  gate: run scripts/reclaim-worktrees.py --apply --force or record a blocker per retained root")
    if args.fail_over_cap and report["debt"] > limit:
        return 1
    if args.fail_reapable_over_cap and report["reapable"] > reapable_limit:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
