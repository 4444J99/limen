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
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.dispatch import _resolve_repo_dir, _down_lanes  # noqa: E402

LOCAL = set(LOCAL_CHECKOUT_AGENTS)


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

    cands = [
        t for t in lf.tasks
        if t.status == "open" and canonical_agent(t.target_agent) in LOCAL and _resolve_repo_dir(t) is not None
    ]
    counts = {x: 0 for x in lanes}
    for i, t in enumerate(cands):
        lane = lanes[i % len(lanes)]
        t.target_agent = lane
        counts[lane] += 1

    print(f"rebalanced {len(cands)} dispatchable local tasks across {lanes}: {counts}")
    if args.apply:
        save_limen_file(path, lf)
        print("APPLIED -> tasks.yaml")
    else:
        print("dry-run (pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
