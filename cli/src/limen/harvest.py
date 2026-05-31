from datetime import datetime, timezone
from pathlib import Path

from limen.io import save_limen_file
from limen.models import LimenFile, DispatchLogEntry


def check_jules_harvest(limen: LimenFile, harvest_dir: Path) -> list[str]:
    updated = []
    if not harvest_dir.exists():
        return updated
    for task in limen.tasks:
        if (
            task.status not in ("dispatched", "in_progress")
            or task.target_agent != "jules"
        ):
            continue
        task_dir = harvest_dir / task.id
        if task_dir.exists() and (task_dir / "result.txt").exists():
            now = datetime.now(timezone.utc)
            result = (task_dir / "result.txt").read_text().strip()
            task.status = "done"
            task.updated = now
            task.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=now,
                    agent="jules",
                    session_id=task.dispatch_log[-1].session_id
                    if task.dispatch_log
                    else "harvest",
                    status="done",
                    output=result[:500],
                )
            )
            updated.append(task.id)
    return updated


def harvest_results(
    limen: LimenFile,
    tasks_path: Path,
    agent: str | None = None,
) -> None:
    scheduler_root = Path.home() / "Workspace" / "session-meta" / "scheduler"
    harvest_dir = scheduler_root / "jules" / "harvest"

    updated = []

    if not agent or agent == "jules":
        updated.extend(check_jules_harvest(limen, harvest_dir))

    if updated:
        save_limen_file(tasks_path, limen)
        print(f"Harvested {len(updated)} task(s): {', '.join(updated)}")
    else:
        print("No completed tasks to harvest")
