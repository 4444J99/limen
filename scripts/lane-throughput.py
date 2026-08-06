#!/usr/bin/env python3
"""Lane throughput governor gauge: per-lane cap/mode/rate vs the daily target.

The governor (capacity.lane_throughput_cap) clamps each lane's dispatch volume to its
LANDED evidence — full target only while landed/dispatched holds the floor rate. This
sensor is the gauge: it prints the live cap table, appends one JSONL history row per
lane per run (logs/lane-throughput.jsonl), and goes advisory-red (exit 1) when a lane
has been clamped below target on two or more distinct days — a sustained clamp means
the LANDING organs (jules-land, owner-route-drain, merge-drain) own the fix, not more
dispatch.

Read-only over the board; never mutates dispatch state.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.capacity import DEFAULT_DAILY_TASK_TARGETS, lane_throughput_cap  # noqa: E402
from limen.io import load_limen_file  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
HISTORY = Path(os.environ.get("LIMEN_LANE_THROUGHPUT_HISTORY", str(ROOT / "logs" / "lane-throughput.jsonl")))


def _prior_clamped_days(history_path: Path, agent: str, today: str) -> set[str]:
    days: set[str] = set()
    try:
        with open(history_path) as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("agent") != agent or row.get("mode") != "throttled":
                    continue
                day = str(row.get("ts", ""))[:10]
                if day and day != today:
                    days.add(day)
    except OSError:
        pass
    return days


def main() -> int:
    board = load_limen_file(TASKS)
    now = datetime.now(timezone.utc)
    today = now.date().isoformat()
    sustained: list[str] = []
    rows = []
    for agent in sorted(DEFAULT_DAILY_TASK_TARGETS):
        cap = lane_throughput_cap(board, agent, now=now)
        rows.append(cap)
        rate = "-" if cap["rate"] is None else f"{cap['rate']:.0%}"
        print(
            f"  lane-throughput: {agent} cap={cap['cap']}/{cap['target']} mode={cap['mode']} "
            f"dispatched={cap['dispatched']} landed={cap['landed']} rate={rate}"
        )
        if cap["mode"] == "throttled" and _prior_clamped_days(HISTORY, agent, today):
            sustained.append(agent)
    try:
        HISTORY.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY, "a") as fh:
            for cap in rows:
                fh.write(json.dumps({"ts": now.isoformat(timespec="seconds"), **cap}) + "\n")
    except OSError:
        pass
    if sustained:
        print(
            "  lane-throughput: SUSTAINED CLAMP "
            + ", ".join(sustained)
            + " — landing owns the fix: drain.sh (jules-land / owner-route-drain / merge-drain)"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
