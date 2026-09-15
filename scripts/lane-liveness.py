#!/usr/bin/env python3
"""Derive lane liveness from the canonical vendor catalog and task evidence.

This is deliberately observational.  It never dispatches, cancels, or repairs a lane.
An idle lane is healthy; a lane with assigned work but no recent lifecycle evidence is
stalled; an unreadable task projection is unmeasured.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _board_custody import board_path  # noqa: E402

try:
    from limen.census import VENDORS, canonical
except Exception:  # pragma: no cover - a missing catalog is itself unmeasured
    VENDORS = ()

    def canonical(value: str | None) -> str:
        return (value or "").strip()


def parse_time(value: object) -> datetime | None:
    if not value:
        return None
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def task_events(task: dict) -> list[datetime]:
    events: list[datetime] = []
    for entry in task.get("dispatch_log") or []:
        value = parse_time(entry.get("timestamp") or entry.get("at") or entry.get("created_at"))
        if value:
            events.append(value)
    for key in ("updated", "updated_at", "created", "created_at"):
        value = parse_time(task.get(key))
        if value:
            events.append(value)
    return events


def load_tasks(path: Path) -> tuple[list[dict], str | None]:
    if not path.exists():
        return [], f"tasks projection missing: {path}"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [], f"tasks projection unreadable: {exc}"
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        return [], "tasks projection has no list at 'tasks'"
    return [task for task in tasks if isinstance(task, dict)], None


def lane_names(tasks: list[dict], requested: str | None) -> list[str]:
    catalog = [vendor.name for vendor in VENDORS]
    discovered = [
        canonical(str(task.get("target_agent"))) for task in tasks if task.get("target_agent") not in (None, "", "any")
    ]
    names = list(dict.fromkeys(catalog + discovered))
    if requested:
        return [canonical(requested)]
    return names


def evaluate(
    root: Path, requested: str | None, now: datetime, max_age_hours: float, tasks_path: Path | None = None
) -> dict:
    try:
        tasks_source = board_path(tasks_path or (root / "tasks.yaml"))
    except Exception as exc:
        tasks_source = None
        error = f"task custody unavailable: {exc}"
    else:
        tasks, error = load_tasks(tasks_source)
    if tasks_source is None:
        tasks = []
    cutoff = now - timedelta(hours=max_age_hours)
    rows: list[dict] = []
    for lane in lane_names(tasks, requested):
        assigned = [
            task
            for task in tasks
            if canonical(str(task.get("target_agent") or "")) == lane
            and task.get("status") in {"dispatched", "in_progress"}
        ]
        events = [event for task in assigned for event in task_events(task)]
        latest = max(events) if events else None
        if error:
            state = "unmeasured"
            detail = error
        elif not assigned:
            state = "idle"
            detail = "no dispatched or in_progress tasks"
        elif latest is None:
            state = "stalled"
            detail = f"{len(assigned)} active task(s) have no lifecycle timestamp"
        elif latest < cutoff:
            state = "stalled"
            detail = f"latest lifecycle event is {latest.isoformat()}"
        else:
            state = "active"
            detail = f"{len(assigned)} active task(s); latest event {latest.isoformat()}"
        rows.append(
            {
                "lane": lane,
                "state": state,
                "detail": detail,
                "active_tasks": len(assigned),
                "latest_event_at": latest.isoformat() if latest else None,
            }
        )
    bad = [row for row in rows if row["state"] in {"stalled", "unmeasured"}]
    return {
        "schema_version": "limen.lane_liveness.v1",
        "generated_at": now.isoformat(),
        "max_age_hours": max_age_hours,
        "requested_lane": canonical(requested) if requested else None,
        "status": "fail" if bad else "pass",
        "lanes": rows,
        "unmeasured": bool(error),
    }


def write_receipt(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", help="inspect one canonical lane or alias")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--check", action="store_true", help="exit 1 for stalled or unmeasured lanes")
    parser.add_argument("--receipt", type=Path, help="atomically write a runtime receipt")
    parser.add_argument("--tasks", type=Path, help="task projection or private canonical board to inspect")
    parser.add_argument("--now", help="UTC reference time for deterministic tests")
    parser.add_argument(
        "--max-age-hours", type=float, default=float(os.environ.get("LIMEN_LANE_LIVENESS_MAX_AGE_HOURS", "24"))
    )
    args = parser.parse_args()
    now = parse_time(args.now) if args.now else datetime.now(timezone.utc)
    if now is None:
        parser.error("--now must be an ISO-8601 timestamp")
    report = evaluate(ROOT, args.lane, now, args.max_age_hours, args.tasks)
    if args.receipt:
        write_receipt(args.receipt, report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for row in report["lanes"]:
            print(f"lane={row['lane']} state={row['state']} detail={row['detail']}")
        print(f"lane-liveness: {report['status']}")
    return 1 if args.check and report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
