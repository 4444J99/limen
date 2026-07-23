from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TypedDict, cast

from limen.capacity import agent_status
from limen.models import LimenFile, Task
from limen.runtime_config import runtime_api_url


class Check(TypedDict):
    id: str
    status: str
    detail: str


class Counts(TypedDict):
    total: int
    open: int
    active: int
    stale: int


class BudgetInfo(TypedDict):
    daily: int
    agent_limit: int
    agent_spent: int
    remaining: int


class ReadinessReport(TypedDict):
    status: str
    agent: str
    generated_at: str
    tasks_path: str
    counts: Counts
    budget: BudgetInfo
    checks: list[Check]
    next_actions: list[str]


class TaskLifecycle(TypedDict):
    id: str
    title: str
    repo: str
    status: str
    priority: str
    assignee: str
    phase: str
    next_gate: str
    stale: bool
    has_issue: bool
    has_pr: bool
    latest_event_at: str | None


class Steering(TypedDict):
    principle: str
    next_batch: list[TaskLifecycle]
    qa_queue: list[TaskLifecycle]
    recovery_queue: list[TaskLifecycle]
    assignment_queue: list[TaskLifecycle]
    archive_queue: list[TaskLifecycle]


class LifecycleCounts(TypedDict):
    total: int
    assign: int
    verify: int
    recover: int
    archive_ready: int
    archived: int


class Mechanism(TypedDict):
    id: str
    label: str
    agent: str
    command: str
    mode: str
    count: int


class QaReport(TypedDict):
    status: str
    surface: str
    agent: str
    generated_at: str
    tasks_path: str
    lifecycle: LifecycleCounts
    steering: Steering
    mechanisms: list[Mechanism]


def _runtime_api_url() -> str:
    """Backward-compatible wrapper around the shared runtime configuration resolver."""
    root = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[3])
    return runtime_api_url(root)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def stale_tasks(
    limen: LimenFile,
    hours: int = 24,
    agent: str | None = None,
    now: datetime | None = None,
) -> list[Task]:
    reference = _ensure_aware(now) if now else datetime.now(UTC)
    cutoff = reference - timedelta(hours=hours)
    candidates: list[Task] = []
    for task in limen.tasks:
        if task.status not in ("dispatched", "in_progress"):
            continue
        if agent and task.target_agent != agent:
            continue
        events = [_ensure_aware(entry.timestamp) for entry in task.dispatch_log if entry.timestamp]
        latest = max(events) if events else None
        if latest is None or latest < cutoff:
            candidates.append(task)
    return candidates


def readiness_report(limen: LimenFile, tasks_path: Path, agent: str = "jules") -> ReadinessReport:
    stale = stale_tasks(limen, agent=agent)
    open_tasks = [task for task in limen.tasks if task.status == "open" and task.target_agent in (agent, "any")]
    active_tasks = [task for task in limen.tasks if task.status in ("dispatched", "in_progress")]
    budget = limen.portal.budget
    spent = budget.track.per_agent.get(agent, 0)
    limit = budget.per_agent.get(agent, budget.daily)
    remaining = max(0, min(budget.daily - budget.track.spent, limit - spent))
    status_row = agent_status(agent)
    agent_reachable = bool(status_row["reachable"])
    checks: list[Check] = cast(
        list[Check],
        [
            {
                "id": "tasks_file",
                "status": "pass" if tasks_path.exists() else "fail",
                "detail": str(tasks_path),
            },
            {
                "id": "task_count",
                "status": "pass" if limen.tasks else "warn",
                "detail": f"{len(limen.tasks)} tasks",
            },
            {
                "id": "stale_claims",
                "status": "warn" if stale else "pass",
                "detail": f"{len(stale)} stale {agent} active tasks",
            },
            {
                "id": "open_queue",
                "status": "pass" if open_tasks else "warn",
                "detail": f"{len(open_tasks)} open {agent} tasks",
            },
            {
                "id": "budget",
                "status": "pass" if remaining > 0 else "fail",
                "detail": f"{remaining}/{limit} {agent} runs remaining",
            },
            {
                "id": "agent_cli",
                "status": "pass" if agent_reachable else "fail",
                "detail": status_row["detail"],
            },
            {
                "id": "api_runtime",
                "status": "pass" if _runtime_api_url() else "warn",
                "detail": _runtime_api_url() or "backend runtime not attached to Firebase static hosting",
            },
        ],
    )
    if any(check["status"] == "fail" for check in checks):
        status = "blocked"
    elif any(check["status"] == "warn" for check in checks):
        status = "degraded"
    else:
        status = "ready"
    return {
        "status": status,
        "agent": agent,
        "generated_at": datetime.now(UTC).isoformat(),
        "tasks_path": str(tasks_path),
        "counts": {
            "total": len(limen.tasks),
            "open": len(open_tasks),
            "active": len(active_tasks),
            "stale": len(stale),
        },
        "budget": {
            "daily": budget.daily,
            "agent_limit": limit,
            "agent_spent": spent,
            "remaining": remaining,
        },
        "checks": checks,
        "next_actions": next_actions(stale, open_tasks, remaining, agent_reachable, agent),
    }


def _iso(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _task_lifecycle(task: Task, stale_ids: set[str]) -> TaskLifecycle:
    events = sorted(
        [_ensure_aware(entry.timestamp) for entry in task.dispatch_log if entry.timestamp],
        reverse=True,
    )
    stale = task.id in stale_ids
    has_pr = any("/pull/" in url for url in task.urls)
    has_issue = any("/issues/" in url for url in task.urls)
    if task.status == "archived":
        phase = "archived"
    elif task.status == "done":
        phase = "archive"
    elif stale or task.status in ("failed", "failed_blocked", "needs_human"):
        phase = "recover"
    elif has_pr or task.status in ("dispatched", "in_progress"):
        phase = "verify"
    else:
        phase = "assign"
    if phase == "archived":
        next_gate = "suppressed from active steering"
    elif phase == "archive":
        next_gate = "archive evidence and suppress from active steering"
    elif phase == "recover":
        next_gate = "release stale claim or reassign with failure note"
    elif phase == "verify":
        next_gate = "verify PR/runtime evidence, then close or return"
    else:
        next_gate = "assign to agent with budget and acceptance gate"
    return {
        "id": task.id,
        "title": task.title,
        "repo": task.repo or "",
        "status": task.status,
        "priority": task.priority,
        "assignee": task.target_agent or "unassigned",
        "phase": phase,
        "next_gate": next_gate,
        "stale": stale,
        "has_issue": has_issue,
        "has_pr": has_pr,
        "latest_event_at": _iso(events[0] if events else task.updated or task.created),
    }


def qa_report(
    limen: LimenFile,
    tasks_path: Path,
    agent: str = "jules",
    now: datetime | None = None,
) -> QaReport:
    reference = _ensure_aware(now) if now else datetime.now(UTC)
    stale_ids = {task.id for task in stale_tasks(limen, now=reference)}
    items = [_task_lifecycle(task, stale_ids) for task in limen.tasks]
    phase_order = {"recover": 0, "verify": 1, "assign": 2, "archive": 3, "archived": 4}
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "backlog": 4}
    steering = sorted(
        [item for item in items if item["phase"] not in ("archive", "archived")],
        key=lambda item: (
            phase_order.get(item["phase"], 99),
            priority_order.get(item["priority"], 99),
            str(item["id"]),
        ),
    )
    qa_items = [item for item in items if item["phase"] == "verify"]
    recover_items = [item for item in items if item["phase"] == "recover"]
    assign_items = [item for item in items if item["phase"] == "assign"]
    archive_ready = [item for item in items if item["phase"] == "archive"]
    archived_items = [item for item in items if item["phase"] == "archived"]
    return {
        "status": "degraded" if recover_items else "ok",
        "surface": "qa",
        "agent": agent,
        "generated_at": reference.isoformat(),
        "tasks_path": str(tasks_path),
        "lifecycle": {
            "total": len(items),
            "assign": len(assign_items),
            "verify": len(qa_items),
            "recover": len(recover_items),
            "archive_ready": len(archive_ready),
            "archived": len(archived_items),
        },
        "steering": {
            "principle": "Every visible item is a portal into one task lifecycle; closed work is archived out of active steering.",
            "next_batch": steering[:24],
            "qa_queue": qa_items[:24],
            "recovery_queue": recover_items[:24],
            "assignment_queue": assign_items[:24],
            "archive_queue": archive_ready[:24],
        },
        "mechanisms": [
            {
                "id": "release-stale",
                "label": "Release stale claims",
                "agent": agent,
                "command": "POST /api/release-stale?hours=24&dry_run=false",
                "mode": "human-approved apply",
                "count": len(recover_items),
            },
            {
                "id": "qa-verify",
                "label": "Verify PR and runtime evidence",
                "agent": "qa",
                "command": "POST /api/tasks/{task_id}/verify",
                "mode": "human-approved evidence gate",
                "count": len(qa_items),
            },
            {
                "id": "assign-next",
                "label": "Assign or reassign next task",
                "agent": "steering",
                "command": "POST /api/tasks/{task_id}/assign",
                "mode": "human-approved assignment",
                "count": len(assign_items),
            },
            {
                "id": "archive-done",
                "label": "Archive closed evidence",
                "agent": "system",
                "command": "POST /api/tasks/{task_id}/archive",
                "mode": "human-approved archive",
                "count": len(archive_ready),
            },
        ],
    }


def next_actions(
    stale: list[Task],
    open_tasks: list[Task],
    remaining: int,
    has_agent_cli: bool,
    agent: str,
) -> list[str]:
    actions: list[str] = []
    if stale:
        actions.append(f"limen release-stale --agent {agent} --hours 24 --apply")
    if open_tasks and remaining > 0 and has_agent_cli:
        actions.append(f"limen dispatch --agent {agent} --limit {min(remaining, len(open_tasks))} --live")
    if not has_agent_cli:
        actions.append(f"Install or configure {agent} dispatch CLI")
    if remaining <= 0:
        actions.append(f"Wait for {agent} budget reset or lower dispatch volume")
    if not actions:
        actions.append("No immediate action required")
    return actions


def print_readiness(report: ReadinessReport) -> None:
    print(f"── limen doctor — status={report['status']} agent={report['agent']}")
    for check in report["checks"]:
        print(f"  {check['status'].upper():5} {check['id']}: {check['detail']}")
    print("── next actions")
    for action in report["next_actions"]:
        print(f"  {action}")


def print_qa_report(report: QaReport) -> None:
    lifecycle = report["lifecycle"]
    print(
        "── limen qa"
        f" — status={report['status']}"
        f" recover={lifecycle['recover']}"
        f" verify={lifecycle['verify']}"
        f" assign={lifecycle['assign']}"
        f" archive={lifecycle['archive_ready']}"
    )
    print("── next steering batch")
    for item in report["steering"]["next_batch"]:
        print(f"  {item['phase'].upper():7} {item['id']} {item['assignee']} — {item['title']}")
    print("── mechanisms")
    for mechanism in report["mechanisms"]:
        print(f"  {mechanism['count']:3} {mechanism['id']}: {mechanism['command']}")


def write_report(report: ReadinessReport | QaReport, path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
