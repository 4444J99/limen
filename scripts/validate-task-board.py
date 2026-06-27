#!/usr/bin/env python3
"""Validate live task-board lifecycle states against the canonical MCP vocabulary."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TASKS = ROOT / "tasks.yaml"
MCP_SERVER = ROOT / "mcp" / "src" / "limen_mcp" / "server.py"


def load_valid_statuses() -> set[str]:
    module = ast.parse(MCP_SERVER.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "VALID_STATUSES":
                    value = ast.literal_eval(node.value)
                    return {str(item) for item in value}
    raise RuntimeError(f"VALID_STATUSES not found in {MCP_SERVER}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    args = parser.parse_args()

    valid = load_valid_statuses()
    data = yaml.safe_load(args.tasks.read_text()) or {}
    invalid: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    log_mismatches: list[tuple[str, str, str]] = []
    reopened_done: list[tuple[str, str]] = []
    dispatchable_human: list[tuple[str, str]] = []
    for task in data.get("tasks") or []:
        task_id = str(task.get("id", "<missing-id>"))
        if task_id in seen_ids:
            duplicate_ids.append(task_id)
        seen_ids.add(task_id)

        status = str(task.get("status", ""))
        if status not in valid:
            invalid.append((task_id, status))
            continue

        log = task.get("dispatch_log") or []
        if log:
            last_status = str((log[-1] or {}).get("status", ""))
            if last_status in valid and last_status != status:
                log_mismatches.append((task_id, status, last_status))
            if any(str((entry or {}).get("status", "")) == "done" for entry in log):
                if status not in {"done", "archived"}:
                    reopened_done.append((task_id, status))

        labels = {str(label) for label in (task.get("labels") or [])}
        if "needs-human" in labels and status in {"open", "dispatched", "in_progress"}:
            dispatchable_human.append((task_id, status))

    if invalid:
        print(
            f"{args.tasks} has {len(invalid)} task(s) with non-canonical status "
            f"(valid: {', '.join(sorted(valid))})",
            file=sys.stderr,
        )
        for task_id, status in invalid[:50]:
            print(f"  {task_id}: {status}", file=sys.stderr)
        if len(invalid) > 50:
            print(f"  ... {len(invalid) - 50} more", file=sys.stderr)
        return 1

    if duplicate_ids:
        print(
            f"{args.tasks} has {len(duplicate_ids)} duplicate task id(s)",
            file=sys.stderr,
        )
        for task_id in duplicate_ids[:50]:
            print(f"  {task_id}", file=sys.stderr)
        if len(duplicate_ids) > 50:
            print(f"  ... {len(duplicate_ids) - 50} more", file=sys.stderr)
        return 1

    if log_mismatches:
        print(
            f"{args.tasks} has {len(log_mismatches)} task(s) whose latest canonical "
            "dispatch_log status disagrees with task.status",
            file=sys.stderr,
        )
        for task_id, status, last_status in log_mismatches[:50]:
            print(f"  {task_id}: task.status={status}, latest_log.status={last_status}", file=sys.stderr)
        if len(log_mismatches) > 50:
            print(f"  ... {len(log_mismatches) - 50} more", file=sys.stderr)
        return 1

    if reopened_done:
        print(
            f"{args.tasks} has {len(reopened_done)} task(s) reopened after a done transition",
            file=sys.stderr,
        )
        for task_id, status in reopened_done[:50]:
            print(f"  {task_id}: {status}", file=sys.stderr)
        if len(reopened_done) > 50:
            print(f"  ... {len(reopened_done) - 50} more", file=sys.stderr)
        return 1

    if dispatchable_human:
        print(
            f"{args.tasks} has {len(dispatchable_human)} needs-human task(s) still "
            "available to dispatch",
            file=sys.stderr,
        )
        for task_id, status in dispatchable_human[:50]:
            print(f"  {task_id}: {status}", file=sys.stderr)
        if len(dispatchable_human) > 50:
            print(f"  ... {len(dispatchable_human) - 50} more", file=sys.stderr)
        return 1

    print(f"Task board statuses valid ({len(data.get('tasks') or [])} tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
