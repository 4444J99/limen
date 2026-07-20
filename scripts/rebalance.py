#!/usr/bin/env python3
"""rebalance.py — spread OPEN, locally-cloned, local-lane tasks round-robin across
the healthy local lanes so no vendor sits idle.

The vendor-tiering router (route.py) prefers codex and only falls back to agy/claude,
which leaves those lanes idle. This deliberately fans the dispatchable local work
across every live lane to use all available capacity.

Safe: only rewrites `target_agent` on tasks that are status==open AND already routed
to a local lane AND whose repo resolves to a local checkout (i.e. already
dispatchable). Uses Limen's own loader/saver so tasks.yaml round-trips identically
to a normal dispatch. Read-only unless --apply.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.capacity import LOCAL_CHECKOUT_AGENTS, canonical_agent  # noqa: E402
from limen.io import load_limen_file, queue_lock  # noqa: E402
from limen.tabularius import apply_limen_file_sync  # noqa: E402
from limen.dispatch import (  # noqa: E402
    _deps_met,
    _dispatchable,
    _down_lanes,
    _resolve_repo_dir,
    _routine_generated_buildout_allowed,
    agent_can_run_task,
)

LOCAL = set(LOCAL_CHECKOUT_AGENTS)


def _timeout_to_jules(task) -> bool:
    labels = set(getattr(task, "labels", None) or [])
    if "slow" not in labels:
        return False
    for entry in reversed(getattr(task, "dispatch_log", None) or []):
        status = str(getattr(entry, "status", "") or "")
        output = str(getattr(entry, "output", "") or "")
        if "timeout->jules" in status or "timeout->jules" in output:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS"))
    ap.add_argument("--lanes", required=True, help="comma-separated healthy local lanes")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    down = _down_lanes()
    lanes = [
        canonical_agent(x.strip())
        for x in args.lanes.split(",")
        if x.strip() and canonical_agent(x.strip()) not in down
    ]
    if not lanes:
        print(f"no productive lanes (given lanes all down: {sorted(down)})")
        return 2
    if down:
        print(f"skipping down lanes: {sorted(down)} — re-routing their tasks to {lanes}")
    path = Path(args.tasks)
    lf = load_limen_file(path)

    id2 = {t.id: t for t in lf.tasks}
    cands = [
        t
        for t in lf.tasks
        if _dispatchable(t)
        and canonical_agent(t.target_agent) in LOCAL
        and _resolve_repo_dir(t) is not None
        and _deps_met(t, id2)
        and _routine_generated_buildout_allowed(t)
        and not _timeout_to_jules(t)
    ]
    counts = {x: 0 for x in lanes}
    assignments = {}
    skipped = 0
    lane_index = 0
    for t in cands:
        assigned = None
        for _ in lanes:
            lane = lanes[lane_index % len(lanes)]
            lane_index += 1
            if agent_can_run_task(lane, t):
                assigned = lane
                break
        if assigned is None:
            skipped += 1
            continue
        assignments[t.id] = assigned
        t.target_agent = assigned
        counts[assigned] += 1

    print(f"rebalanced {sum(counts.values())} dispatchable local tasks across {lanes}: {counts}")
    if skipped:
        print(f"skipped {skipped} task(s) with no safe productive lane")
    if args.apply:
        with queue_lock(path) as got:
            if not got:
                print("queue busy — skipped applying rebalance this pass (self-corrects next beat).")
                return 0
            fresh = load_limen_file(path)
            applied = 0
            for task in fresh.tasks:
                assigned = assignments.get(task.id)
                if not assigned:
                    continue
                if task.status != "open" or canonical_agent(task.target_agent) not in LOCAL:
                    continue
                if _timeout_to_jules(task) or not agent_can_run_task(assigned, task):
                    continue
                task.target_agent = assigned
                applied += 1
            apply_limen_file_sync(path, fresh, agent="rebalance", session_id="apply")
        print(f"APPLIED -> tasks.yaml ({applied} target_agent update(s))")
    else:
        print("dry-run (pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
