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

Usage: dispatch-async.py --lanes auto --per-lane 8 --max 12 [--dry-run]
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.capacity import select_lanes  # noqa: E402
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.models import DispatchLogEntry  # noqa: E402
from limen.dispatch import (  # noqa: E402
    _ASYNC_LANES,
    _PRIORITY_ORDER,
    _apply_result,
    _deps_met,
    _dispatchable,
    _down_lanes,
    _has_done_transition,
    _queue_lock,
    _restore_done_status,
    _routine_generated_buildout_allowed,
)

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
RUNS = ROOT / "logs" / "async-runs"
WORKER = ROOT / "scripts" / "async-run-one.py"


def _int_or_default(raw: object, default: int) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    return _int_or_default(os.environ.get(name), default)


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
    with _queue_lock(TASKS) as got:
        if not got:
            # Lock timed out — skip this pass (honor the contract). The .result.json files are only
            # unlinked INSIDE the lock below, so returning here preserves them for the next beat.
            return applied
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


def inspect_harvest() -> int:
    """Count result files without applying or deleting them."""
    RUNS.mkdir(parents=True, exist_ok=True)
    return len(list(RUNS.glob("*.result.json")))


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
            tid, agent = m.name[: -len(".running")].rsplit("__", 1)
            # if the worker DID finish (result file present), let harvest handle it; don't reap
            if not (RUNS / f"{tid}.result.json").exists():
                # Defer the marker unlink until the reopen is committed under the lock (below), so a
                # lock timeout can't leave the slot leaked (marker gone, task still 'dispatched').
                reaped.append((tid, agent, m))
    if reaped:
        with _queue_lock(TASKS) as got:
            if not got:
                # Lock busy — keep the markers (not yet unlinked) so a later beat retries the reap;
                # unlinking without reopening would leak the concurrency slot forever.
                return []
            lf = load_limen_file(TASKS)
            byid = {t.id: t for t in lf.tasks}
            for tid, agent, _m in reaped:
                t = byid.get(tid)
                if t is not None and t.status == "dispatched":
                    if _has_done_transition(t):
                        _restore_done_status(
                            t,
                            now,
                            agent=agent,
                            session_id="async-reap-stale",
                            output=(
                                "dispatch-async: stale worker marker reaped after prior done; restored terminal status"
                            ),
                        )
                    else:
                        t.status = "open"  # dead worker left no result → retry on a later beat
                        t.updated = now
                        t.dispatch_log.append(
                            DispatchLogEntry(
                                timestamp=now,
                                agent=agent,
                                session_id="async-reap-stale",
                                status="open",
                                output=f"dispatch-async: stale worker marker older than {max_age_s}s reaped; task reopened",
                            )
                        )
            save_limen_file(TASKS, lf)
        # reopen is committed → now safe to remove the markers that freed these slots
        for _tid, _agent, m in reaped:
            m.unlink(missing_ok=True)
    return [tid for tid, _agent, _m in reaped]


def inspect_stale(max_age_s: int) -> list[str]:
    """Return stale marker task ids without deleting markers or reopening tasks."""
    RUNS.mkdir(parents=True, exist_ok=True)
    now = _now()
    stale = []
    for m in RUNS.glob("*__*.running"):
        try:
            age = (now - datetime.datetime.fromisoformat(m.read_text().strip())).total_seconds()
        except Exception:
            age = max_age_s + 1
        if age > max_age_s:
            tid, _agent = m.name[: -len(".running")].rsplit("__", 1)
            if not (RUNS / f"{tid}.result.json").exists():
                stale.append(tid)
    return stale


def default_max_age_s() -> int:
    """Keep stale reaping above the local lane timeout so live bounded workers are not reopened."""
    env = os.environ.get("LIMEN_ASYNC_MAX_AGE")
    if env is not None:
        return max(1, _int_or_default(env, 2100))
    lane_timeout = max(1, _env_int("LIMEN_LANE_TIMEOUT", 1800))
    return max(1200, lane_timeout + 300)


def _running_total() -> int:
    return len(list(RUNS.glob("*.running")))


def _running_local() -> int:
    """In-flight LOCAL-lane runs only. The concurrency cap bounds LOCAL host pressure (each local run
    holds a worktree + a ThreadPoolExecutor slot). An async/remote run (jules, github_actions, ...)
    executes OFF-BOX — a `jules remote new` session runs on Google's VM — so it must NOT consume a
    local slot, or a backlog of local work starves the remote lanes out of the cap entirely (the root
    cause of 'zero jules remote sessions launched'). Remote lanes stay bounded by their per-agent
    budget, not this local cap."""
    total = 0
    for m in RUNS.glob("*__*.running"):
        agent = m.name[: -len(".running")].rsplit("__", 1)[1]
        if agent not in _ASYNC_LANES:
            total += 1
    return total


def _running_for(agent: str) -> int:
    return len(list(RUNS.glob(f"*__{agent}.running")))


def reserve_and_launch(agents, per_agent, cap, dry):
    """Reserve open tasks (under lock) up to the concurrency cap + per-agent budget, then spawn
    detached workers. Returns the list of (agent, task_id) launched/would-launch."""
    now = _now()
    picked = []
    picked_ids = set()
    with _queue_lock(TASKS) as got:
        if not got:
            # Lock busy — reserve nothing this round. Returning BEFORE `picked` is used to spawn
            # detached workers (below) prevents launching workers for tasks never persisted as
            # 'dispatched', which would double-dispatch. Self-corrects next beat.
            return []
        lf = load_limen_file(TASKS)
        track = lf.portal.budget.track
        daily = lf.portal.budget.daily
        # The cap counts only LOCAL in-flight runs; remote/async lanes run off-box and are budgeted
        # separately below (see _running_local).
        slots = max(0, cap - _running_local())
        spent = track.spent
        id2 = {t.id: t for t in lf.tasks}  # for dependency resolution
        for agent in agents:
            is_async = agent in _ASYNC_LANES  # remote lane (jules, ...) — off-box, not gated by the local cap
            if not is_async and slots <= 0:
                continue  # local slot budget spent — but a later async lane may still launch off-box
            capa = lf.portal.budget.per_agent.get(agent)
            aspent = track.per_agent.get(agent, 0) + _running_for(agent)  # count in-flight vs budget
            rem = daily - spent if capa is None else max(0, min(daily - spent, capa - aspent))
            if rem <= 0:
                continue
            cands = [
                t
                for t in lf.tasks
                if _dispatchable(t)
                and (t.target_agent == agent or t.target_agent == "any")
                and t.budget_cost <= rem
                and _deps_met(t, id2)
                and _routine_generated_buildout_allowed(t)
            ]
            cands.sort(key=lambda t: _PRIORITY_ORDER.get(t.priority, 99))
            taken = 0
            for t in cands:
                if taken >= per_agent:
                    break
                if not is_async and slots <= 0:
                    break  # local slot budget spent for this beat (async lanes are not slot-bound)
                if t.id in picked_ids:
                    continue
                if t.budget_cost > rem:
                    continue
                picked.append((agent, t.id))
                picked_ids.add(t.id)
                rem -= t.budget_cost
                spent += t.budget_cost
                if not dry:
                    t.status = "dispatched"
                    t.updated = now
                    t.dispatch_log.append(
                        DispatchLogEntry(
                            timestamp=now,
                            agent=agent,
                            session_id="async-reserve",
                            status="dispatched",
                            output="dispatch-async: reserved before detached worker launch",
                        )
                    )
                if not is_async:
                    slots -= 1  # only local runs consume a local concurrency slot
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
            stdout=logf,
            stderr=logf,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ, "PYTHONPATH": str(ROOT / "cli" / "src")},
        )
    return picked


def resolve_lanes(selector: str, down: set[str]) -> list[str]:
    try:
        board = load_limen_file(TASKS)
    except Exception:
        board = None
    lanes = select_lanes(selector, board, down_lanes=down)
    return lanes or [agent for agent in ("codex",) if agent not in down]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lanes", default="auto")
    ap.add_argument("--per-lane", type=int, default=max(1, _env_int("LIMEN_LOCAL_LIMIT", 8)))
    ap.add_argument("--max", type=int, default=max(1, _env_int("LIMEN_ASYNC_MAX", 12)))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    down = _down_lanes()
    lanes = resolve_lanes(a.lanes, down)
    if down:
        print(f"── skipping down lanes: {sorted(down)}")
    max_age = default_max_age_s()
    if a.dry_run:
        reaped = inspect_stale(max_age)
        applied = inspect_harvest()
    else:
        reaped = reap_stale(max_age)
        applied = harvest()
    running = _running_total()
    launched = reserve_and_launch(lanes, a.per_lane, a.max, a.dry_run)
    verb = "would launch" if a.dry_run else "launched"
    print(
        f"── async: reaped {len(reaped)} dead · harvested {applied} · {running} still running · "
        f"{verb} {len(launched)} (cap {a.max}) → {[t for _, t in launched]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
