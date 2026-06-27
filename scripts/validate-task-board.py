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
    for task in data.get("tasks") or []:
        status = str(task.get("status", ""))
        if status not in valid:
            invalid.append((str(task.get("id", "<missing-id>")), status))

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

    print(f"Task board statuses valid ({len(data.get('tasks') or [])} tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
