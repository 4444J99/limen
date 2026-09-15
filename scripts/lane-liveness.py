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
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from _board_custody import PrivateCustodyUnavailable, board_path
except ImportError:

    class PrivateCustodyUnavailable(Exception):
        pass

    def board_path(path):
        raise PrivateCustodyUnavailable("custody dependency unavailable")


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
    if yaml is None:
        return [], "YAML dependency unavailable"
    try:
        from limen.models import VALID_STATUSES
    except ImportError:
        return [], "task schema dependency unavailable"
    if not path.exists():
        return [], f"tasks projection missing: {path}"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return [], f"tasks projection unreadable: {exc}"
    tasks = payload.get("tasks") if isinstance(payload, dict) else None
    if not isinstance(tasks, list):
        return [], "tasks projection has no list at 'tasks'"
    if any(not isinstance(task, dict) for task in tasks):
        return [], "tasks projection contains malformed entries"
    if any(
        not isinstance(task.get("id"), str)
        or not task["id"]
        or not isinstance(task.get("status"), str)
        or task.get("status") not in VALID_STATUSES
        or not isinstance(task.get("target_agent"), str)
        for task in tasks
    ):
        return [], "tasks projection has malformed task identities"
    if len({task["id"] for task in tasks}) != len(tasks):
        return [], "tasks projection contains duplicate task identities"
    return tasks, None


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
    except (PrivateCustodyUnavailable, Exception) as exc:
        tasks_source = None
        error = f"task custody unavailable: {exc}"
    else:
        tasks, error = load_tasks(tasks_source)
    if tasks_source is None:
        tasks = []
    cutoff = now - timedelta(hours=max_age_hours)
    catalog = {vendor.name for vendor in VENDORS}
    if not catalog:
        error = error or "vendor catalog unavailable"
    observations = []
    client = None
    broker_error = None
    try:
        from limen.conduct.client import client_from_env

        client = client_from_env()
        client.timeout = 3
        client.capabilities()
    except Exception:
        broker_error = "conduct broker unavailable"
    deadline = time.monotonic() + 20
    graphs = {}
    for task in tasks:
        if task.get("status") not in ("dispatched", "in_progress"):
            continue
        lane = canonical(str(task.get("target_agent") or "unknown"))
        state, detail, stamp = "unmeasured", broker_error, None
        try:
            if client is None or time.monotonic() >= deadline:
                raise ValueError("broker unavailable or observation deadline exhausted")
            current = client.task_run(str(task["id"]))
            if not current.get("found"):
                raise ValueError("active projection task has no broker run")
            root_id = current["root_run_id"]
            if root_id not in graphs:
                graphs[root_id] = client.graph(root_id)
            node = next(n for n in graphs[root_id]["nodes"] if n["run_id"] == current["run_id"])
            lease = node["lease"]
            lane = canonical(lease["executor"]["agent"])
            stamp = parse_time(lease.get("heartbeat_at"))
            hard_deadline = parse_time(lease.get("hard_deadline"))
            if lane not in catalog or stamp is None or stamp > now or hard_deadline is None:
                raise ValueError("unknown executor or invalid heartbeat")
            state = (
                "active"
                if stamp >= cutoff and hard_deadline > now and lease.get("state") in ("reserved", "active")
                else "stalled"
            )
            detail = "broker lease heartbeat evaluated"
        except Exception:
            detail = "broker lease evidence unavailable or malformed"
        observations.append({"lane": lane, "state": state, "latest": stamp, "detail": detail})
    rows = []
    names = lane_names(tasks, requested)
    if not requested:
        names = list(dict.fromkeys(names + [o["lane"] for o in observations]))
    for lane in names:
        assigned = [o for o in observations if o["lane"] == lane]
        unresolved = any(o["lane"] in ("any", "unknown") for o in observations)
        if error or broker_error or lane not in catalog or unresolved:
            state, detail = "unmeasured", error or broker_error or "unknown executor lane"
        elif any(o["state"] == "unmeasured" for o in assigned):
            state, detail = "unmeasured", "one or more tasks lack broker evidence"
        elif any(o["state"] == "stalled" for o in assigned):
            state, detail = "stalled", "one or more task leases are stale"
        else:
            state, detail = ("active", "all task leases fresh") if assigned else ("idle", "no active tasks")
        latest = max((o["latest"] for o in assigned if o["latest"]), default=None)
        rows.append(
            {
                "lane": lane,
                "state": state,
                "detail": detail,
                "active_tasks": len(assigned),
                "latest_event_at": latest.isoformat() if latest else None,
            }
        )
    unmeasured = bool(error or broker_error or not rows or any(r["state"] == "unmeasured" for r in rows))
    return {
        "schema_version": "limen.lane_liveness.v1",
        "generated_at": now.isoformat(),
        "max_age_hours": max_age_hours,
        "requested_lane": canonical(requested) if requested else None,
        "status": "fail" if unmeasured or any(r["state"] == "stalled" for r in rows) else "pass",
        "lanes": rows,
        "unmeasured": unmeasured,
    }


def write_receipt(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
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
