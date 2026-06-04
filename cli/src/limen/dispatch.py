import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from limen.io import save_limen_file
from limen.models import DispatchLogEntry, LimenFile, Task
from limen.doctor import stale_tasks


def resolve_agent() -> str:
    return os.environ.get("LIMEN_AGENT", "claude")


def session_id() -> str:
    return os.environ.get(
        "CLAUDE_SESSION_ID", os.environ.get("GEMINI_SESSION_ID", "cli")
    )


def call_agent_dispatch(agent: str, task: Task, dry_run: bool) -> bool:
    if agent == "jules":
        return _call_jules(task, dry_run)
    dispatch_cmd = os.environ.get("LIMEN_DISPATCH_CMD", "agent-dispatch")
    prompt = _build_prompt(task)
    cmd = [dispatch_cmd, agent, prompt]
    return _run_cmd(cmd, task, dry_run)


def _build_prompt(task: Task) -> str:
    parts = [f"Complete task {task.id}: {task.title}"]
    if task.repo:
        parts.append(f" in repository {task.repo}")
    if task.context:
        parts.append(f"\nContext: {task.context}")
    if task.urls:
        parts.append(f"\nReferences: {', '.join(task.urls)}")
    return "".join(parts)


def _run_cmd(cmd: list[str], task: Task, dry_run: bool) -> bool:
    if dry_run:
        print(f"  would: {' '.join(cmd)}")
        return True
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            print(f"  dispatched: {task.id}")
            return True
        print(f"  FAILED ({result.returncode}): {task.id}")
        if result.stderr:
            print(f"    stderr: {result.stderr[:500]}")
        return False
    except FileNotFoundError:
        print(f"  dispatch command not found: {cmd[0]}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  timed out: {task.id}")
        return False


def _call_jules(task: Task, dry_run: bool) -> bool:
    repo = task.repo or os.environ.get("LIMEN_ROOT", ".")
    prompt = _build_prompt(task)
    cmd = [os.environ.get("LIMEN_JULES_BIN", "jules"), "new", "--repo", repo, prompt]
    return _run_cmd(cmd, task, dry_run)


def _reset_budget_if_needed(limen: LimenFile, now: datetime) -> None:
    today = now.strftime("%Y-%m-%d")
    track = limen.portal.budget.track
    if track.date != today:
        track.date = today
        track.spent = 0
        track.per_agent = {agent: 0 for agent in limen.portal.budget.per_agent}


def _remaining_budget(limen: LimenFile, agent: str, budget: int) -> int:
    track = limen.portal.budget.track
    daily_remaining = budget - track.spent
    agent_limit = limen.portal.budget.per_agent.get(agent)
    if agent_limit is None:
        return max(0, daily_remaining)
    agent_spent = track.per_agent.get(agent, 0)
    return max(0, min(daily_remaining, agent_limit - agent_spent))


def dispatch_tasks(
    limen: LimenFile,
    tasks_path: Path,
    agent: str | None = None,
    budget: int | None = None,
    dry_run: bool = True,
    task_id: str | None = None,
    limit: int | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    budget = budget or limen.portal.budget.daily

    _reset_budget_if_needed(limen, now)
    track = limen.portal.budget.track

    agent_filter = agent or resolve_agent()
    remaining = _remaining_budget(limen, agent_filter, budget)
    if remaining <= 0:
        print(f"Budget exhausted for {agent_filter} ({track.spent}/{budget} total spent)")
        return

    tasks = limen.tasks

    if task_id:
        tasks = [t for t in tasks if t.id == task_id]
        if not tasks:
            print(f"Task {task_id} not found")
            return

    candidates = [
        t
        for t in tasks
        if t.status == "open"
        and (t.target_agent == agent_filter or t.target_agent == "any")
        and t.budget_cost <= remaining
    ]
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}
    candidates.sort(key=lambda t: priority_order.get(t.priority, 99))

    if limit is not None:
        candidates = candidates[: max(0, limit)]

    if not candidates:
        print(
            f"No open tasks for agent '{agent_filter}' within remaining budget ({remaining})"
        )
        return

    mode = "DRY-RUN" if dry_run else "LIVE"
    print(
        f"── limen dispatch ({mode}) — agent={agent_filter} budget_remaining={remaining}"
    )

    dispatched = 0
    for task in candidates:
        if remaining < task.budget_cost:
            break

        entry = DispatchLogEntry(
            timestamp=now,
            agent=agent_filter,
            session_id=session_id(),
            status="dispatched",
        )

        success = call_agent_dispatch(agent_filter, task, dry_run)
        if not success and not dry_run:
            entry.status = "failed"
            task.status = "failed"
            task.updated = now
            task.dispatch_log.append(entry)
        elif not dry_run:
            task.status = "dispatched"
            task.updated = now
            task.dispatch_log.append(entry)
            track.spent += task.budget_cost
            track.per_agent[agent_filter] = (
                track.per_agent.get(agent_filter, 0) + task.budget_cost
            )
            remaining -= task.budget_cost

        dispatched += 1

    if not dry_run:
        save_limen_file(tasks_path, limen)

    print(f"── {mode}: {dispatched} task(s)")


def release_stale_tasks(
    limen: LimenFile,
    tasks_path: Path,
    hours: int = 24,
    dry_run: bool = True,
    agent: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    candidates = stale_tasks(limen, hours=hours, agent=agent)

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"── limen release-stale ({mode}) — hours={hours} candidates={len(candidates)}")
    for task in candidates:
        print(f"  {task.id} {task.status} {task.target_agent} — {task.title}")
        if not dry_run:
            task.status = "open"
            task.updated = now
            task.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=now,
                    agent="limen",
                    session_id=session_id(),
                    status="open",
                    output=f"Released stale claim after {hours}h",
                )
            )

    if not dry_run:
        save_limen_file(tasks_path, limen)
    return {
        "status": "dry_run" if dry_run else "applied",
        "agent": agent,
        "hours": hours,
        "tasks_path": str(tasks_path),
        "count": len(candidates),
        "released": [task.id for task in candidates],
        "candidates": [
            {
                "id": task.id,
                "title": task.title,
                "repo": task.repo,
                "target_agent": task.target_agent,
                "status": task.status if dry_run else "open",
            }
            for task in candidates
        ],
    }
