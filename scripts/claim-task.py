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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli" / "src"))
from limen.intake import IntakeContractError, normalize_selected_legacy_task  # noqa: E402
from limen import runtime_requirements  # noqa: E402

VALID_CLAIM_AGENTS = {
    "agy",
    "claude",
    "codex",
    "copilot",
    "gemini",
    "github_actions",
    "jules",
    "opencode",
    "oz",
    "warp",
}


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


def parse_nonnegative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        raise SystemExit(f"{field_name} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise SystemExit(f"{field_name} must be a non-negative integer") from None
    if parsed < 0:
        raise SystemExit(f"{field_name} must be a non-negative integer")
    return parsed


def optional_nonnegative_int(mapping: dict[str, Any], key: str, field_name: str) -> int:
    if key not in mapping:
        return 0
    return parse_nonnegative_int(mapping[key], field_name)


def claim_task(data: dict[str, Any], task_id: str, agent: str, session_id: str) -> dict[str, Any]:
    if agent not in VALID_CLAIM_AGENTS:
        allowed = ", ".join(sorted(VALID_CLAIM_AGENTS))
        raise SystemExit(f"agent must be one of: {allowed}")

    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        raise SystemExit("tasks file has no tasks list")

    for task in tasks:
        if task.get("id") != task_id:
            continue
        status = task.get("status")
        if status != "open":
            raise SystemExit(f"task {task_id} is not open; current status is {status!r}")

        readiness = runtime_requirements.evaluate_execution_requirements(task)
        if not readiness.ready:
            reason = "; ".join(readiness.blockers)
            raise SystemExit(f"runtime requirements blocked {task_id}: {reason}")

        budget_cost = optional_nonnegative_int(task, "budget_cost", "budget_cost")
        portal = data.setdefault("portal", {})
        if not isinstance(portal, dict):
            raise SystemExit("portal must be a mapping")
        budget = portal.setdefault("budget", {})
        if not isinstance(budget, dict):
            raise SystemExit("portal.budget must be a mapping")
        track = budget.setdefault("track", {})
        if not isinstance(track, dict):
            raise SystemExit("portal.budget.track must be a mapping")
        spent = optional_nonnegative_int(track, "spent", "portal.budget.track.spent")
        per_agent = track.setdefault("per_agent", {})
        if not isinstance(per_agent, dict):
            raise SystemExit("portal.budget.track.per_agent must be a mapping")
        agent_spent = parse_nonnegative_int(
            per_agent[agent] if agent in per_agent else 0,
            f"portal.budget.track.per_agent.{agent}",
        )

        try:
            normalize_selected_legacy_task(task)
        except IntakeContractError as exc:
            raise SystemExit(f"typed intake blocked {task_id}: {exc}") from None

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

        track["spent"] = spent + budget_cost
        per_agent[agent] = agent_spent + budget_cost
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
            f"DRY-RUN claim: {task['id']} -> {task['target_agent']} status={task['status']} session={args.session_id}"
        )
        return 0

    with args.tasks.open("w") as stream:
        yaml.safe_dump(data, stream, default_flow_style=False, sort_keys=False)
    print(f"claimed {task['id']} for {task['target_agent']} in {args.tasks}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
