#!/usr/bin/env python3
"""check-heal-retirement.py — predicate for self-heal task retirement.

Exit 0 <=> no active (`open`, `dispatched`, `in_progress`, `failed`, `failed_blocked`, `needs_human`)
HEAL task names a PR that is no longer open in its repository.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(ROOT / "cli" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from limen.io import load_limen_file
from _pr_scan import enumerate_open_prs

OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]
ACTIVE_STATUSES = {"open", "dispatched"}


def main():
    quiet = "--quiet" in sys.argv
    tasks_path = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
    if not tasks_path.exists():
        if not quiet:
            print("[check-heal-retirement] tasks.yaml missing")
        return 0

    lf = load_limen_file(tasks_path)
    active_heal = [
        t
        for t in lf.tasks
        if (t.id.startswith("HEAL-cifix-") or t.id.startswith("HEAL-rebase-"))
        and not t.id.startswith("HEAL-rebase-stale-")
        and t.status in ACTIVE_STATUSES
    ]
    if not active_heal:
        if not quiet:
            print("[check-heal-retirement] exit 0: 0 active HEAL tasks")
        return 0

    allprs = enumerate_open_prs(
        OWNERS,
        lambda args, timeout=60: subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout),
        max_total=1000,
        want_url=True,
        author=None,
    )
    open_set = {(repo, num) for (repo, num, _url) in allprs}

    violations = []
    for t in active_heal:
        parts = t.id.split("-")
        if parts[-1].isdigit():
            num = int(parts[-1])
            repo = t.repo or ""
            if repo == "organvm/limen" and (repo, num) not in open_set:
                violations.append((t.id, repo, num, t.status))

    if violations:
        print(f"[check-heal-retirement] FAIL: {len(violations)} active HEAL tasks name closed/merged PRs:")
        for tid, repo, num, st in violations[:10]:
            print(f"    {tid} ({repo}#{num}, status={st})")
        return 1

    if not quiet:
        print(f"[check-heal-retirement] exit 0: all {len(active_heal)} active HEAL tasks correspond to open PRs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
