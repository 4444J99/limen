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


def last_tick(path):
    """Return the previous tick record, or None. Bounded tail read — the file grows forever."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 8192))
            lines = [ln for ln in f.read().decode("utf-8", "replace").splitlines() if ln.strip()]
        return json.loads(lines[-1]) if lines else None
    except (OSError, ValueError, IndexError):
        return None


def completed_count(record):
    """done + archived — the monotonic completion counter ('done' alone drops on archival)."""
    if not isinstance(record, dict):
        return None
    try:
        return int(record.get("done", 0)) + int(record.get("archived", 0))
    except (TypeError, ValueError):
        return None


rec = {
    "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "total": len(tasks),
    "open": n("open"),
    "dispatched": n("dispatched"),
    "done": n("done"),
    "failed": n("failed"),
    "archived": n("archived"),
    "daily_spent": track.get("spent", 0),
    "daily_cap": budget.get("daily", 300),
    "per_agent_spent": {a: tp.get(a, 0) for a in caps},
}

logs = root / "logs"
logs.mkdir(exist_ok=True)
ticks_path = logs / "ticks.jsonl"
prev_completed = completed_count(last_tick(ticks_path))
now_completed = completed_count(rec)
rec["done_delta"] = max(0, now_completed - prev_completed) if prev_completed is not None else None

with open(ticks_path, "a") as f:
    f.write(json.dumps(rec) + "\n")
delta = rec["done_delta"] if rec["done_delta"] is not None else "n/a"
print(
    f"tick emitted: {rec['ts']} total={rec['total']} open={rec['open']} "
    f"spent={rec['daily_spent']}/{rec['daily_cap']} done_delta={delta}"
)
