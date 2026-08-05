#!/usr/bin/env python3
"""lane-fitness — per-(task_class, agent) conversion rate ledger.

Reads tasks.yaml dispatch_log, computes per-(agent, task_class) conversion rates,
writes logs/lane-fitness.json. Dispatch consults this at pick time (fail-open) to
deprioritize (agent, class) pairs with demonstrated poor fit.

Named params (env-overridable, declared in institutio/governance/parameters.yaml):
  LIMEN_FITNESS_MIN_N       (default 5)    min attempts before a pair is judged fit/unfit
  LIMEN_FITNESS_UNFIT_RATE  (default 0.25) conversion rate below which a pair is "unfit"
  LIMEN_FITNESS_WINDOW_DAYS (default 30)   rolling window in days for dispatch_log entries

READ-ONLY on tasks.yaml. PII-clean: only task types/labels, no titles/ids/content.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
TASKS = Path(os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
FITNESS_JSON = ROOT / "logs" / "lane-fitness.json"

# Statuses that count as "attempted" (a real dispatch effort was made)
_ATTEMPTED_STATUSES: frozenset[str] = frozenset(
    {
        "done",
        "failed",
        "noop",
        "archived",
        "failed_blocked",
        "timeout->jules",
        "failed->opencode",
        "failed->gemini",
        "failed->codex",
        "failed->claude",
        "failed->agy",
        "failed->jules",
        "failed->github_actions",
        "failed->ollama",
        "ratelimited->opencode",
        "ratelimited->jules",
    }
)
_DONE_STATUSES: frozenset[str] = frozenset({"done"})


def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.environ.get(name, default))
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        v = float(os.environ.get(name, default))
        return v if 0.0 <= v <= 1.0 else default
    except (TypeError, ValueError):
        return default


def _load_tasks() -> list[dict]:
    try:
        with open(TASKS) as f:
            data = yaml.safe_load(f)
        return data.get("tasks", []) if isinstance(data, dict) else []
    except Exception:
        return []


def compute(
    *,
    min_attempts: int,
    unfit_rate: float,
    window_days: int,
) -> dict:
    """Compute per-(agent, task_class) tallies from tasks.yaml dispatch_log."""
    tasks = _load_tasks()
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    # tallies[agent][task_class] = [done, attempted]
    tallies: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    for t in tasks:
        task_type = t.get("type")
        task_labels = list(t.get("labels") or [])
        classes = [c for c in ([task_type] + task_labels) if c]
        if not classes:
            continue
        for e in t.get("dispatch_log") or []:
            agent = e.get("agent")
            status = str(e.get("status") or "")
            if not agent or status not in _ATTEMPTED_STATUSES:
                continue
            ts_raw = e.get("timestamp")
            if ts_raw:
                try:
                    ts = datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                    if ts < cutoff:
                        continue
                except Exception:
                    pass
            for c in classes:
                tallies[agent][c][1] += 1
                if status in _DONE_STATUSES:
                    tallies[agent][c][0] += 1

    pairs: dict[str, dict[str, dict]] = {}
    unfit_pairs: list[dict] = []

    for agent, classes in sorted(tallies.items()):
        pairs[agent] = {}
        for cls, (done, attempted) in sorted(classes.items(), key=lambda x: -x[1][1]):
            rate = round(done / attempted, 4) if attempted else 0.0
            if attempted < min_attempts:
                fit: bool | None = None
            elif rate < unfit_rate:
                fit = False
            else:
                fit = True
            pairs[agent][cls] = {"done": done, "attempted": attempted, "rate": rate, "fit": fit}
            if fit is False:
                unfit_pairs.append(
                    {
                        "agent": agent,
                        "task_class": cls,
                        "done": done,
                        "attempted": attempted,
                        "rate": rate,
                    }
                )

    unfit_pairs.sort(key=lambda x: -x["attempted"])
    lane_count = len([a for a in pairs if any(v["fit"] is False for v in pairs[a].values())])
    summary = f"{len(unfit_pairs)} unfit pairs across {lane_count} lanes"

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "params": {
            "min_attempts": min_attempts,
            "unfit_rate": unfit_rate,
            "window_days": window_days,
        },
        "pairs": pairs,
        "unfit_pairs": unfit_pairs,
        "summary": summary,
    }


def _print_table(data: dict) -> None:
    params = data.get("params", {})
    print(f"=== LANE FITNESS ({data.get('summary', '?')}) ===")
    print(
        f"params: min_attempts={params.get('min_attempts')} "
        f"unfit_rate={params.get('unfit_rate')} "
        f"window_days={params.get('window_days')}"
    )
    print()
    unfit = data.get("unfit_pairs", [])
    print(
        f"TOP UNFIT PAIRS (>={params.get('min_attempts')} attempts, "
        f"<{int((params.get('unfit_rate') or 0) * 100)}% done rate):"
    )
    for u in unfit[:30]:
        print(f"  {u['agent']:12} {u['task_class']:36} {u['done']}/{u['attempted']} = {u['rate']:.1%}")
    if len(unfit) > 30:
        print(f"  ... and {len(unfit) - 30} more")
    print()
    print(f"generated: {data.get('generated')}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute per-(agent, task_class) lane fitness")
    ap.add_argument("--check", action="store_true", help="Print table only, no write")
    ap.add_argument("--write", action="store_true", help="Write logs/lane-fitness.json (default)")
    args = ap.parse_args()

    min_attempts = _env_int("LIMEN_FITNESS_MIN_N", 5)
    unfit_rate = _env_float("LIMEN_FITNESS_UNFIT_RATE", 0.25)
    window_days = _env_int("LIMEN_FITNESS_WINDOW_DAYS", 30)

    data = compute(min_attempts=min_attempts, unfit_rate=unfit_rate, window_days=window_days)
    _print_table(data)

    if not args.check:
        FITNESS_JSON.parent.mkdir(exist_ok=True)
        try:
            FITNESS_JSON.write_text(json.dumps(data, indent=2))
            print(f"wrote {FITNESS_JSON}")
        except OSError as e:
            print(f"lane-fitness: could not write {FITNESS_JSON} ({e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
