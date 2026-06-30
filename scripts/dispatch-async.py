#!/usr/bin/env python3
"""dispatch-async.py — ASYNC dispatch: decouple the beat from agent runtime (the real throughput fix
for "the slowest of N agents gates the whole beat / 900s gates every beat").

Each beat this does TWO fast, non-blocking things:
  (1) HARVEST — apply any finished background runs (logs/async-runs/*.result.json) to tasks.yaml
      under the queue-lock (reload-fresh + _apply_result, same as the sync commit).
  (2) RESERVE + LAUNCH — pick open tasks per lane within budget + a GLOBAL CONCURRENCY CAP, mark
      them dispatched, then SPAWN detached async-run-one workers and RETURN IMMEDIATELY.

Agents run in the background; their results land on a later beat. Beats stay fast regardless of how
slow any single agent is. Opt-in: the heartbeat calls this instead of dispatch-parallel.py when
LIMEN_DISPATCH_ASYNC=1. The synchronous dispatch-parallel.py is left completely unchanged.

Concurrency: at most LIMEN_ASYNC_MAX (default 12) background runs at once; per-agent in-flight count
is tracked via <task-id>__<agent>.running markers so budgets aren't blown between reserve & harvest.

Usage: dispatch-async.py --lanes codex,claude,opencode,jules --per-lane 8 --max 12 [--dry-run]
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.capacity import PAID_AGENT_ORDER, canonical_agent, capacity_census  # noqa: E402
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import DispatchLogEntry  # noqa: E402
from limen.dispatch import _queue_lock, _apply_result, _down_lanes, _PRIORITY_ORDER, _deps_met  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
RUNS = ROOT / "logs" / "async-runs"
WORKER = ROOT / "scripts" / "async-run-one.py"


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _clear_running_markers(task_id: str) -> None:
    prefix = f"{task_id}__"
    for marker in RUNS.glob("*.running"):
        if marker.name.startswith(prefix):
            marker.unlink(missing_ok=True)


def harvest() -> int:
    """Apply finished background runs to tasks.yaml under the lock. Returns count applied."""
    RUNS.mkdir(parents=True, exist_ok=True)
    files = sorted(RUNS.glob("*.result.json"))
    if not files:
        return 0
    now = _now()
    applied = 0
    with _queue_lock(TASKS):
        lf = load_limen_file(TASKS)
        byid = {t.id: t for t in lf.tasks}
        track = lf.portal.budget.track
        for rf in files:
            try:
                data = json.loads(rf.read_text())
            except Exception:
                rf.unlink(missing_ok=True)
                continue
            t = byid.get(data.get("task_id"))
            if t is not None and data.get("result") != "__notask__":
                _apply_result(t, data.get("agent"), data.get("result"), now, track)
                applied += 1
            if data.get("task_id"):
                _clear_running_markers(str(data.get("task_id")))
            rf.unlink(missing_ok=True)
        if applied:
            save_limen_file(TASKS, lf)
    return applied


def reap_stale(max_age_s: int):
    """Free slots from DEAD workers. A .running marker older than max_age with no result file means
    the detached worker crashed/was-killed before finishing (OOM, host sleep, SIGKILL). Remove the
    marker and reopen the task so it's retried — otherwise it would leak a concurrency slot forever.
    A live slow worker is younger than max_age (call_agent_dispatch caps the agent at its timeout)."""
    RUNS.mkdir(parents=True, exist_ok=True)
    now = _now()
    reaped = []
    for m in RUNS.glob("*__*.running"):
        try:
            age = (now - datetime.datetime.fromisoformat(m.read_text().strip())).total_seconds()
        except Exception:
            age = max_age_s + 1  # unreadable/empty marker → treat as stale
        if age > max_age_s:
            tid, agent = m.name[:-len(".running")].rsplit("__", 1)
            # if the worker DID finish (result file present), let harvest handle it; don't reap
            if not (RUNS / f"{tid}.result.json").exists():
                reaped.append((tid, agent))
                m.unlink(missing_ok=True)
    if reaped:
        with _queue_lock(TASKS):
            lf = load_limen_file(TASKS)
            byid = {t.id: t for t in lf.tasks}
            for tid, agent in reaped:
                t = byid.get(tid)
                if t is not None and t.status == "dispatched":
                    t.status = "open"  # dead worker left no result → retry on a later beat
                    t.updated = now
                    t.dispatch_log.append(DispatchLogEntry(
                        timestamp=now,
                        agent=agent,
                        session_id="async-reap-stale",
                        status="open",
                        output=f"dispatch-async: stale worker marker older than {max_age_s}s reaped; task reopened",
                    ))
            save_limen_file(TASKS, lf)
    return [tid for tid, _agent in reaped]


def _running_total() -> int:
    return len(list(RUNS.glob("*.running")))


def _running_for(agent: str) -> int:
    return len(list(RUNS.glob(f"*__{agent}.running")))


def reserve_and_launch(agents, per_agent, cap, dry):
    """Reserve open tasks (under lock) up to the concurrency cap + per-agent budget, then spawn
    detached workers. Returns the list of (agent, task_id) launched/would-launch."""
    now = _now()
    picked = []
    with _queue_lock(TASKS):
        lf = load_limen_file(TASKS)
        track = lf.portal.budget.track
        daily = lf.portal.budget.daily
        slots = max(0, cap - _running_total())
        spent = track.spent
        id2 = {t.id: t for t in lf.tasks}  # for dependency resolution
        for agent in agents:
            if slots <= 0:
                break
            capa = lf.portal.budget.per_agent.get(agent)
            aspent = track.per_agent.get(agent, 0) + _running_for(agent)  # count in-flight vs budget
            rem = daily - spent if capa is None else max(0, min(daily - spent, capa - aspent))
            if rem <= 0:
                continue
            cands = [t for t in lf.tasks
                     if t.status == "open" and (t.target_agent == agent or t.target_agent == "any")
                     and t.budget_cost <= rem and _deps_met(t, id2)]
            cands.sort(key=lambda t: _PRIORITY_ORDER.get(t.priority, 99))
            taken = 0
            for t in cands:
                if slots <= 0 or taken >= per_agent:
                    break
                picked.append((agent, t.id))
                if not dry:
                    t.status = "dispatched"
                    t.updated = now
                    t.dispatch_log.append(DispatchLogEntry(
                        timestamp=now,
                        agent=agent,
                        session_id="async-reserve",
                        status="dispatched",
                        output="dispatch-async: reserved before detached worker launch",
                    ))
                slots -= 1
                taken += 1
        if not dry and picked:
            save_limen_file(TASKS, lf)
    if dry:
        return picked
    # outside the lock: write markers + spawn detached workers (fast; we never wait on them)
    for agent, tid in picked:
        (RUNS / f"{tid}__{agent}.running").write_text(now.isoformat())
        logf = open(RUNS / f"{tid}.log", "a")
        subprocess.Popen(
            [sys.executable, str(WORKER), "--agent", agent, "--task-id", tid],
            stdout=logf, stderr=logf, stdin=subprocess.DEVNULL, start_new_session=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "cli" / "src")},
        )
    return picked


def resolve_lanes(selector: str, down: set[str]) -> list[str]:
    raw = (selector or "auto").strip()
    if raw == "all":
        return [agent for agent in PAID_AGENT_ORDER if agent not in down]
    if raw == "auto":
        try:
            board = load_limen_file(TASKS)
            rows = capacity_census(board)
        except Exception:
            rows = []
        lanes = [
            str(row.get("agent"))
            for row in rows
            if row.get("reachable") and str(row.get("agent")) not in down
        ]
        return lanes or [agent for agent in ("codex",) if agent not in down]
    lanes: list[str] = []
    for item in raw.split(","):
        agent = canonical_agent(item.strip())
        if agent and agent in PAID_AGENT_ORDER and agent not in down and agent not in lanes:
            lanes.append(agent)
    return lanes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lanes", default="auto")
    ap.add_argument("--per-lane", type=int, default=int(os.environ.get("LIMEN_LOCAL_LIMIT", "8")))
    ap.add_argument("--max", type=int, default=int(os.environ.get("LIMEN_ASYNC_MAX", "12")))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    down = _down_lanes()
    lanes = resolve_lanes(a.lanes, down)
    if down:
        print(f"── skipping down lanes: {sorted(down)}")
    reaped = reap_stale(int(os.environ.get("LIMEN_ASYNC_MAX_AGE", "1200")))
    applied = harvest()
    running = _running_total()
    launched = reserve_and_launch(lanes, a.per_lane, a.max, a.dry_run)
    verb = "would launch" if a.dry_run else "launched"
    print(f"── async: reaped {len(reaped)} dead · harvested {applied} · {running} still running · "
          f"{verb} {len(launched)} (cap {a.max}) → {[t for _, t in launched]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
