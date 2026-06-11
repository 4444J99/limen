from datetime import date, datetime
from math import ceil
from typing import Any

from limen.models import LimenFile


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _throughput(limen: LimenFile) -> dict[str, int | str | None]:
    tasks = limen.tasks
    today = date.today()
    created_dates = [created for task in tasks if (created := _as_date(task.created))]
    first_created = min(created_dates) if created_dates else today
    age_days = max(1, (today - first_created).days + 1)
    daily_capacity = int(limen.portal.budget.daily or 0)
    done = len([task for task in tasks if task.status in ("done", "archived")])
    not_done = len(tasks) - done
    event_statuses = [
        entry.status for task in tasks for entry in task.dispatch_log if entry.status
    ]
    recorded_starts = len(
        [status for status in event_statuses if status in ("dispatched", "in_progress")]
    )
    recorded_finishes = len(
        [
            status
            for status in event_statuses
            if status in ("done", "completed", "failed", "failed_blocked")
        ]
    )
    return {
        "first_created": first_created.isoformat(),
        "current_date": today.isoformat(),
        "age_days": age_days,
        "daily_capacity": daily_capacity,
        "expected_capacity_runs": daily_capacity * age_days,
        "task_burndown_target_per_day": ceil(len(tasks) / age_days) if tasks else 0,
        "recorded_events": len(event_statuses),
        "recorded_starts": recorded_starts,
        "recorded_finishes": recorded_finishes,
        "done": done,
        "not_done": not_done,
    }


def print_status(
    limen: LimenFile,
    agent_filter: str | None = None,
    status_filter: str | None = None,
) -> None:
    track = limen.portal.budget.track
    daily = limen.portal.budget.daily
    print(f"Portal: {limen.portal.name}")
    print(f"Budget: {track.spent}/{daily} runs used today")
    if track.per_agent:
        per = ", ".join(f"{k}: {v}" for k, v in track.per_agent.items())
        print(f"  per agent: {per}")
    throughput = _throughput(limen)
    print(
        "Throughput:"
        f" created {throughput['first_created']} -> {throughput['current_date']}"
        f" ({throughput['age_days']} days),"
        f" capacity {throughput['daily_capacity']}/day = {throughput['expected_capacity_runs']} run slots,"
        f" drain target {throughput['task_burndown_target_per_day']} tasks/day"
    )
    print(
        "  recorded:"
        f" {throughput['recorded_events']} log events,"
        f" {throughput['recorded_starts']} starts,"
        f" {throughput['recorded_finishes']} finishes,"
        f" {throughput['done']} done,"
        f" {throughput['not_done']} not done"
    )
    print()

    tasks = limen.tasks
    if agent_filter:
        tasks = [
            t
            for t in tasks
            if t.target_agent == agent_filter or t.target_agent == "any"
        ]
    if status_filter:
        tasks = [t for t in tasks if t.status == status_filter]

    if not tasks:
        print("No tasks match the current filters")
        return


    header = f"{'ID':<12} {'Title':<50} {'Agent':<10} {'Status':<14} {'Priority':<10} {'Budget':<6}"
    sep = "-" * len(header)
    print(header)
    print(sep)

    for t in tasks:
        title = (t.title[:47] + "...") if len(t.title) > 50 else t.title
        print(
            f"{t.id:<12} {title:<50} {t.target_agent:<10} {t.status:<14} {t.priority:<10} {t.budget_cost:<6}"
        )

    counts = {
        s: len([t for t in tasks if t.status == s])
        for s in ("open", "dispatched", "in_progress", "done", "failed")
    }
    active = [f"{k}={v}" for k, v in counts.items() if v > 0]
    print(f"\n{len(tasks)} tasks ({', '.join(active)})")
