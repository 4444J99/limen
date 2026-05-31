from limen.models import LimenFile


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

    task_types = limen.portal.budget.per_agent

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
