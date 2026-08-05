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
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", LIMEN_ROOT / "tasks.yaml"))
HARVEST = Path.home() / "Workspace" / "session-meta" / "scheduler" / "jules" / "harvest"

_STATUS_KW = ["completed", "failed", "planning", "awaiting", "paused", "in progress", "running", "queued"]


def _logical_session(entry: dict) -> str:
    return str(entry.get("logical_session_id") or entry.get("session_id") or "")


def _jules(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    """Run a `jules` command. Fails OPEN (returncode 1), never raises — mirrors gitvs.py:_gh.

    The `jules` CLI is a local-machine tool absent on CI runners (and can vanish on a broken
    install). A missing binary must degrade to a clean skip, not a FileNotFoundError that dumps a
    traceback into the conductor report and masks the report's real signal (see the swallowed
    ``|| { echo … }`` in scripts/conductor-report.sh)."""
    if not shutil.which("jules"):
        return subprocess.CompletedProcess(args, 1, "", "jules not found")
    try:
        return subprocess.run(["jules", *args], capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # fail open — a jules fault must never crash the harvest→close pipeline
        return subprocess.CompletedProcess(args, 1, "", str(e))


def dispatched_by_session() -> dict[str, str]:
    """Map the RECORDED jules session_id -> task_id for every dispatched/in_progress
    jules task. This is the robust key: it bypasses description parsing (which breaks
    on the LIMEN-* vs GH-* id schemes AND on jules-list truncation). Falls back to a
    description-id mapping for any task whose dispatch_log lacks a numeric session."""
    data = yaml.safe_load(TASKS.read_text()) or {}
    by_sid: dict[str, str] = {}
    for t in data.get("tasks", []):
        if t.get("target_agent") != "jules" or t.get("status") not in ("dispatched", "in_progress"):
            continue
        for entry in reversed(t.get("dispatch_log", []) or []):
            sid = _logical_session(entry)
            if sid.isdigit() and len(sid) >= 12:
                by_sid[sid] = t["id"]
                break
    return by_sid


_TASK_ID_RE = re.compile(r"Complete task (\S+?):")


def dispatched_jules_ids() -> set[str]:
    """Every task id currently dispatched/in_progress on the jules lane — the robust
    match target, since the recorded session_id is often 'cli' (jules-new stdout parse
    failed at dispatch). The jules session Description carries 'Complete task <ID>:'."""
    data = yaml.safe_load(TASKS.read_text()) or {}
    return {
        t["id"]
        for t in data.get("tasks", [])
        if t.get("target_agent") == "jules" and t.get("status") in ("dispatched", "in_progress")
    }


def jules_sessions() -> list[tuple[str, str, str]]:
    """Return (session_id, status, task_id), newest first. session_id from the numeric ID
    column (never truncated); task_id parsed from the Description ('Complete task <ID>:'),
    which is the reliable session→task key when the recorded session_id was lost."""
    r = _jules(["remote", "list", "--session"], timeout=90)
    rows = []
    for line in r.stdout.splitlines():  # empty when jules is absent → no rows, clean skip
        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue
        sid = parts[0]
        low = line.lower()
        status = next((kw for kw in _STATUS_KW if kw in low), "?")
        m = _TASK_ID_RE.search(line)
        rows.append((sid, status, m.group(1) if m else ""))
    return rows


def main() -> int:
    HARVEST.mkdir(parents=True, exist_ok=True)
    by_sid = dispatched_by_session()  # numeric session_id -> task (when captured)
    open_jules = dispatched_jules_ids()  # robust target set (by task id in description)
    pulled, already, failed = [], [], []
    for sid, status, desc_tid in jules_sessions():
        # prefer the recorded numeric mapping; fall back to the description task id
        tid = by_sid.get(sid) or (desc_tid if desc_tid in open_jules else None)
        if not tid or status != "completed":
            continue
        result = HARVEST / tid / "result.txt"
        diff = HARVEST / f"{sid}.diff"
        if result.exists() and diff.exists():
            already.append(tid)
            continue
        pr = _jules(["remote", "pull", "--session", sid], timeout=120)
        if pr.returncode != 0 or not pr.stdout.strip():
            failed.append(f"{tid}({sid}): {pr.stderr.strip()[:100]}")
            continue
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text(pr.stdout)
        diff.write_text(pr.stdout)
        pulled.append(tid)
        print(f"  pulled {tid} <- {sid} ({len(pr.stdout)} bytes)")
    print(f"pulled {len(pulled)}: {pulled}")
    if already:
        print(f"already harvested: {already}")
    if failed:
        print(f"pull failures: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
