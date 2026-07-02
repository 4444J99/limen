#!/usr/bin/env python3
"""Claim one open Limen task without bypassing board accounting."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def default_tasks_path() -> Path:
    if tasks_env := os.environ.get("LIMEN_TASKS"):
        return Path(tasks_env)
    if root_env := os.environ.get("LIMEN_ROOT"):
        return Path(root_env) / "tasks.yaml"
    return Path(__file__).resolve().parents[1] / "tasks.yaml"


def load_board(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"tasks file not found: {path}")
    with path.open() as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise SystemExit(f"tasks file did not parse as a mapping: {path}")
    return data


def claim_task(data: dict[str, Any], task_id: str, agent: str, session_id: str) -> dict[str, Any]:
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise SystemExit("tasks file has no tasks list")

    for task in tasks:
        if task.get("id") != task_id:
            continue
        status = task.get("status")
        if status != "open":
            raise SystemExit(f"task {task_id} is not open; current status is {status!r}")

        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        task["target_agent"] = agent
        task["status"] = "dispatched"
        task["updated"] = now
        task.setdefault("dispatch_log", []).append(
            {
                "timestamp": now,
                "agent": agent,
                "session_id": session_id,
                "status": "dispatched",
                "output": f"claim-task: reserved {task_id} for {agent}",
            }
        )

        budget_cost = int(task.get("budget_cost") or 0)
        track = data.setdefault("portal", {}).setdefault("budget", {}).setdefault("track", {})
        track["spent"] = int(track.get("spent") or 0) + budget_cost
        per_agent = track.setdefault("per_agent", {})
        per_agent[agent] = int(per_agent.get(agent) or 0) + budget_cost
        return task

    raise SystemExit(f"task {task_id} not found")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id", help="open task id to claim")
    parser.add_argument("agent", help="agent name to reserve the task for")
    parser.add_argument("--tasks", type=Path, default=default_tasks_path(), help="path to tasks.yaml")
    parser.add_argument(
        "--session-id",
        default=os.environ.get("LIMEN_SESSION_ID", "manual-claim"),
        help="session id to record in dispatch_log",
    )
    parser.add_argument("--live", action="store_true", help="write the claim; otherwise only preview")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = load_board(args.tasks)
    task = claim_task(data, args.task_id, args.agent, args.session_id)

    if not args.live:
        print(
            "DRY-RUN claim: "
            f"{task['id']} -> {task['target_agent']} "
            f"status={task['status']} session={args.session_id}"
        )
        return 0

    with args.tasks.open("w") as stream:
        yaml.safe_dump(data, stream, default_flow_style=False, sort_keys=False)
    print(f"claimed {task['id']} for {task['target_agent']} in {args.tasks}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
