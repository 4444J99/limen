#!/usr/bin/env python3
"""async-run-one.py — detached worker for the ASYNC dispatch engine.

Runs ONE task's full isolated dispatch (worktree → agent → commit → push → PR) via the SAME
call_agent_dispatch the sync path uses, then writes the raw result to
logs/async-runs/<task-id>.result.json (atomically) and clears its running-marker. It deliberately
does NOT touch tasks.yaml — the orchestrator (dispatch-async.py) harvests result files under the
queue-lock. This is what decouples agent runtime from the beat: the orchestrator spawns these
detached and returns immediately; a slow/stuck agent can no longer gate the whole beat.

Usage (spawned detached by dispatch-async.py; rarely run by hand):
    async-run-one.py --agent codex --task-id CIFIX-foo
"""
import argparse
import datetime
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file  # noqa: E402
from limen.dispatch import call_agent_dispatch  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
RUNS = ROOT / "logs" / "async-runs"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--task-id", required=True)
    a = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)
    err = None
    try:
        lf = load_limen_file(TASKS)
        task = next((t for t in lf.tasks if t.id == a.task_id), None)
        result = call_agent_dispatch(a.agent, task, dry_run=False) if task is not None else "__notask__"
    except Exception as e:  # never crash without leaving a result the harvester can apply
        result = False
        err = str(e)[:300]
    out = {
        "task_id": a.task_id,
        "agent": a.agent,
        "result": result,  # bool | str (PR url / __noop__ / __ratelimit__ / __timeout__)
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "err": err,
    }
    tmp = RUNS / f"{a.task_id}.result.tmp"
    tmp.write_text(json.dumps(out))
    tmp.replace(RUNS / f"{a.task_id}.result.json")  # atomic publish
    try:
        (RUNS / f"{a.task_id}__{a.agent}.running").unlink()
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
