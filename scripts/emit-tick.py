#!/usr/bin/env python3
"""emit-tick.py — append one structured heartbeat-tick record to logs/ticks.jsonl so
the autonomic loop becomes chartable in the portal (instead of free-text logs)."""
import datetime
import json
import os
from pathlib import Path

import yaml

root = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
d = yaml.safe_load((root / "tasks.yaml").read_text()) or {}
tasks = d.get("tasks", [])
budget = (d.get("portal") or {}).get("budget") or {}
caps = budget.get("per_agent", {}) or {}
track = budget.get("track", {}) or {}
tp = track.get("per_agent", {}) or {}


def n(status):
    return sum(1 for t in tasks if t.get("status") == status)


rec = {
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "total": len(tasks),
    "open": n("open"),
    "dispatched": n("dispatched"),
    "done": n("done"),
    "failed": n("failed"),
    "cancelled": n("cancelled"),
    "daily_spent": track.get("spent", 0),
    "daily_cap": budget.get("daily", 300),
    "per_agent_spent": {a: tp.get(a, 0) for a in caps},
}

logs = root / "logs"
logs.mkdir(exist_ok=True)
with open(logs / "ticks.jsonl", "a") as f:
    f.write(json.dumps(rec) + "\n")
print(f"tick emitted: {rec['ts']} total={rec['total']} open={rec['open']} spent={rec['daily_spent']}/{rec['daily_cap']}")
