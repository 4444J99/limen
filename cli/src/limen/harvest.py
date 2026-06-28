import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path

from limen.io import save_limen_file
from limen.models import LimenFile, DispatchLogEntry


def _get_jules_sessions(harvest_dir: Path) -> dict[str, str]:
    mapping = {}
    if harvest_dir.exists():
        for list_file in harvest_dir.glob(".list-*.txt"):
            try:
                for line in list_file.read_text().splitlines():
                    parts = line.split()
                    if not parts:
                        continue
                    session_id = parts[0]
                    if not session_id.isdigit():
                        continue
                    match = re.search(r"((?:LIMEN-\d+)|(?:GH-[A-Za-z0-9._-]+))", line)
                    if match:
                        mapping[match.group(1)] = session_id
            except Exception:
                pass
    try:
        result = subprocess.run(
            ["jules", "remote", "list", "--session"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if not parts:
                    continue
                session_id = parts[0]
                if not session_id.isdigit():
                    continue
                match = re.search(r"((?:LIMEN-\d+)|(?:GH-[A-Za-z0-9._-]+))", line)
                if match:
                    mapping[match.group(1)] = session_id
    except Exception:
        pass
    return mapping


def _diff_is_real(diff_text: str) -> bool:
    """True only if a harvested diff represents actual work.

    A jules result counts as 'done' only when a hand actually moved: a non-empty
    unified diff with real content changes. Rejects the empty placeholder (e.g. a
    ``patch.diff`` of ``index 0000000..e69de29`` with no hunks) and whitespace-only
    output. Exposed by the 2026-06-25 VIGILIA dispatch, where harvest marked tasks
    'done' the instant a ``.diff`` file existed — 'done' must mean done.
    """
    text = (diff_text or "").strip()
    if not text:
        return False
    if "diff --git" not in text and not text.lstrip().startswith("--- "):
        return False
    for line in text.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line[:1] in ("+", "-") and line[1:].strip():
            return True
        if line.startswith("Binary files") and line.rstrip().endswith("differ"):
            return True
    return False


def check_jules_harvest(limen: LimenFile, harvest_dir: Path) -> list[str]:
    updated: list[str] = []
    if not harvest_dir.exists():
        return updated

    session_mapping = _get_jules_sessions(harvest_dir)

    for task in limen.tasks:
        if task.status not in ("dispatched", "in_progress") or task.target_agent != "jules":
            continue

        session_id = session_mapping.get(task.id)
        if not session_id and task.dispatch_log:
            session_id = task.dispatch_log[-1].session_id

        if session_id:
            diff_file = harvest_dir / f"{session_id}.diff"
            if diff_file.exists():
                now = datetime.now(timezone.utc)
                result = diff_file.read_text().strip()
                if not _diff_is_real(result):
                    # jules finished but produced nothing usable (empty/garbage
                    # diff). Do NOT mark done, and do NOT archive/cancel it:
                    # preserve the prompt-started work in the recovery lifecycle.
                    task.status = "failed"
                    if "noop" not in task.labels:
                        task.labels.append("noop")
                    task.updated = now
                    task.dispatch_log.append(
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id=session_id,
                            status="failed",
                            output=result[:500],
                        )
                    )
                    print(f"  rejected {task.id}: jules diff empty/garbage — not 'done'")
                    continue
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
            if not result:
                # empty result file is not completion — don't false-done it.
                continue
            task.status = "done"
            task.updated = now
            task.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=now,
                    agent="jules",
                    session_id=task.dispatch_log[-1].session_id if task.dispatch_log else "harvest",
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
