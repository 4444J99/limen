import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path

from limen.io import save_limen_file
from limen.models import LimenFile, DispatchLogEntry


def _get_jules_sessions() -> dict[str, str]:
    mapping = {}
    try:
        result = subprocess.run(["jules", "remote", "list", "--session"], capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if not parts:
                    continue
                session_id = parts[0]
                if not session_id.isdigit():
                    continue
                match = re.search(r'(LIMEN-\d+)', line)
                if match:
                    mapping[match.group(1)] = session_id
    except Exception:
        pass
    return mapping


def check_jules_harvest(limen: LimenFile, harvest_dir: Path) -> list[str]:
    updated = []
    if not harvest_dir.exists():
        return updated
        
    session_mapping = _get_jules_sessions()
    
    for task in limen.tasks:
        if (
            task.status not in ("dispatched", "in_progress")
            or task.target_agent != "jules"
        ):
            continue
            
        session_id = session_mapping.get(task.id)
        if not session_id and task.dispatch_log:
            session_id = task.dispatch_log[-1].session_id
            
        if session_id:
            diff_file = harvest_dir / f"{session_id}.diff"
            if diff_file.exists():
                now = datetime.now(timezone.utc)
                result = diff_file.read_text().strip()
                task.status = "done"
                task.updated = now
                task.dispatch_log.append(
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id=session_id,
                        status="done",
                        output=result[:500],
                    )
                )
                updated.append(task.id)
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
