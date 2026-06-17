#!/usr/bin/env python3
"""Pull completed Jules session results into the local harvest store.

Fills the gap left by the broken soak-test harvester (LIMEN-077): `limen harvest`
only closes a task when a result file already exists locally, but fresh Jules
completions live remotely until pulled. This walks the current Jules sessions,
and for every task that is still `dispatched`/`in_progress` whose *latest* session
is Completed, pulls its diff into `harvest/<TASK_ID>/result.txt` (and
`harvest/<session_id>.diff`) so `limen harvest` can close it.

Idempotent and read-mostly: it only adds result files for completed sessions and
never mutates repos (no `--apply`) or re-dispatches. Safe to run on a timer.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", LIMEN_ROOT / "tasks.yaml"))
HARVEST = Path.home() / "Workspace" / "session-meta" / "scheduler" / "jules" / "harvest"

_STATUS_KW = ["completed", "failed", "planning", "awaiting", "paused",
              "in progress", "running", "queued"]


def dispatched_tasks() -> set[str]:
    data = yaml.safe_load(TASKS.read_text()) or {}
    return {
        t["id"]
        for t in data.get("tasks", [])
        if t.get("target_agent") == "jules" and t.get("status") in ("dispatched", "in_progress")
    }


def jules_sessions() -> list[tuple[str, str, str]]:
    """Return (session_id, limen_id, status), newest first."""
    r = subprocess.run(
        ["jules", "remote", "list", "--session"],
        capture_output=True, text=True, timeout=90,
    )
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        sid = parts[0]
        m = re.search(r"(LIMEN-\d+)", line)
        if not m:
            continue
        low = line.lower()
        status = next((kw for kw in _STATUS_KW if kw in low), "?")
        rows.append((sid, m.group(1), status))
    return rows


def main() -> int:
    HARVEST.mkdir(parents=True, exist_ok=True)
    dispatched = dispatched_tasks()
    pulled, already, failed = [], [], []
    seen: set[str] = set()
    for sid, lid, status in jules_sessions():
        if lid in seen:
            continue
        seen.add(lid)  # newest session per task only
        if lid not in dispatched or status != "completed":
            continue
        result = HARVEST / lid / "result.txt"
        if result.exists():
            already.append(lid)
            continue
        pr = subprocess.run(
            ["jules", "remote", "pull", "--session", sid],
            capture_output=True, text=True, timeout=120,
        )
        if pr.returncode != 0 or not pr.stdout.strip():
            failed.append(f"{lid}({sid}): {pr.stderr.strip()[:100]}")
            continue
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(pr.stdout)
        (HARVEST / f"{sid}.diff").write_text(pr.stdout)
        pulled.append(lid)
        print(f"  pulled {lid} <- {sid} ({len(pr.stdout)} bytes)")
    print(f"pulled {len(pulled)}: {pulled}")
    if already:
        print(f"already harvested: {already}")
    if failed:
        print(f"pull failures: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
