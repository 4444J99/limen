import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from limen.io import save_limen_file
from limen.models import DispatchLogEntry, LimenFile, Task


def resolve_agent() -> str:
    return os.environ.get("LIMEN_AGENT", "claude")


def session_id() -> str:
    return os.environ.get(
        "CLAUDE_SESSION_ID", os.environ.get("GEMINI_SESSION_ID", "cli")
    )


def call_agent_dispatch(agent: str, task: Task, dry_run: bool) -> bool:
    dispatch_cmd = os.environ.get("LIMEN_DISPATCH_CMD", "agent-dispatch")
    prompt = f"Complete task {task.id}: {task.title}"
    if task.repo:
        prompt += f" in repository {task.repo}"
    if task.context:
        prompt += f"\nContext: {task.context}"
    if task.urls:
        prompt += f"\nReferences: {', '.join(task.urls)}"

    cmd = [dispatch_cmd, agent, prompt]
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
        print(f"  dispatch command not found: {dispatch_cmd}")
        return False
    except subprocess.TimeoutExpired:
        print(f"  timed out: {task.id}")
        return False


def dispatch_tasks(
    limen: LimenFile,
    tasks_path: Path,
    agent: str | None = None,
    budget: int | None = None,
    dry_run: bool = True,
    task_id: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    budget = budget or limen.portal.budget.daily

    track = limen.portal.budget.track
    if track.date != today:
        track.date = today
        track.spent = 0
        track.per_agent = {}

    remaining = budget - track.spent
    if remaining <= 0:
        print(f"Daily budget exhausted ({track.spent}/{budget} spent)")
        return

    agent_filter = agent or resolve_agent()
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
