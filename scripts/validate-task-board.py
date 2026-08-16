#!/usr/bin/env python3
"""Validate the live task board — whichever of its two legitimate shapes it carries.

The public ``tasks.yaml`` has two lawful shapes, and which one is correct depends on
whether the board partition has cut over:

* **full board** (pre-cutover) — ``version``, a portal budget, and task rows. Validated
  against the canonical MCP status vocabulary plus the schema/budget/required-field
  contract this predicate absorbed from the ``validate`` workflow's inline heredoc.
* **public aggregate** (post-cutover) — ``limen.public_board_projection.v1``: counts
  only, ``tasks: []``. Canonical state lives in the authenticated Durable Object.

Treating the aggregate as a malformed full board is what kept publication PR #2001 red
("Missing version"). But the aggregate must not simply be waved through either: its whole
reason to exist is that partner-lane work attribution never reaches a public surface. So
the aggregate arm asserts the LEAK invariant — zero task rows and no task material
anywhere in the document — which is a strictly stronger check than the full-board arm
could make. A public file that regains task rows fails here, loudly.

    python3 scripts/validate-task-board.py                    # the repo's public board
    python3 scripts/validate-task-board.py --tasks <path>     # any projection
    python3 scripts/validate-task-board.py --require-shape aggregate   # pin the shape
"""

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


PUBLIC_AGGREGATE_SCHEMA = "limen.public_board_projection.v1"

# Fields that only ever belong to a task row. Their presence anywhere in the public
# aggregate means work material crossed the partition — the exact leak the partition
# exists to prevent, and the reason this arm is stricter than the full-board arm.
TASK_MATERIAL_KEYS = frozenset(
    {"id", "title", "repo", "context", "predicate", "receipt_target", "target_agent", "dispatch_log"}
)


def document_is_aggregate(data: dict) -> bool:
    return str(data.get("schema_version") or "") == PUBLIC_AGGREGATE_SCHEMA


def _leaked_task_material(node, path: str = "") -> list[str]:
    """Every location under the aggregate that carries task-row material."""

    findings: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if key in TASK_MATERIAL_KEYS:
                findings.append(here)
            findings.extend(_leaked_task_material(value, here))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            findings.extend(_leaked_task_material(value, f"{path}[{index}]"))
    return findings


def validate_aggregate(path: Path, data: dict) -> int:
    """The public projection is a health surface: counts only, and provably no work material."""

    tasks = data.get("tasks")
    if tasks is None or not isinstance(tasks, list):
        print(f"{path}: public aggregate must carry an explicit empty tasks list", file=sys.stderr)
        return 1
    if tasks:
        print(
            f"{path}: public aggregate carries {len(tasks)} task row(s); canonical task state "
            "belongs to the authenticated keeper, never the public projection",
            file=sys.stderr,
        )
        return 1

    projection = ((data.get("portal") or {}).get("public_projection")) or {}
    missing = [field for field in ("total", "completed", "by_status") if field not in projection]
    if missing:
        print(f"{path}: public aggregate is missing projection field(s): {missing}", file=sys.stderr)
        return 1

    leaks = _leaked_task_material(data)
    if leaks:
        print(
            f"{path}: public aggregate leaks {len(leaks)} task-material field(s) — "
            "partner-lane attribution must never reach a public surface",
            file=sys.stderr,
        )
        for leak in leaks[:50]:
            print(f"  {leak}", file=sys.stderr)
        return 1

    print(
        f"Public board aggregate valid (total={projection.get('total')}, "
        f"completed={projection.get('completed')}, zero task rows, no task material)"
    )
    return 0


def validate_full_board_contract(path: Path, data: dict) -> int:
    """Schema version, budget sanity, and required task fields.

    Absorbed from the `validate` workflow's inline heredoc so the contract lives in the
    named predicate — runnable locally, shape-aware, and one place to change.
    """

    version = data.get("version")
    if not version:
        print(f"{path}: missing version", file=sys.stderr)
        return 1
    print(f"Schema version: {version}")

    budget = ((data.get("portal") or {}).get("budget")) or {}
    daily = budget.get("daily")
    per_agent = budget.get("per_agent") or {}
    if daily is None:
        print(f"{path}: portal.budget.daily is required on a full board", file=sys.stderr)
        return 1
    total = sum(per_agent.values())
    print(f"Daily budget: {daily}, Sum of per-agent: {total}")
    if total > daily * 2:
        print(f"{path}: per-agent sum exceeds 2x daily budget", file=sys.stderr)
        return 1

    required = ("id", "title", "status", "target_agent", "priority")
    tasks = data.get("tasks") or []
    for task in tasks:
        missing = [field for field in required if task.get(field) is None]
        if missing:
            print(f"{path}: task {task.get('id', '<no id>')} missing required fields: {missing}", file=sys.stderr)
            return 1
    print(f"All {len(tasks)} tasks have required fields")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks", type=Path, default=DEFAULT_TASKS)
    parser.add_argument(
        "--require-shape",
        choices=("full", "aggregate"),
        default=None,
        help="fail unless the board carries this shape (default: accept either lawful shape)",
    )
    args = parser.parse_args()

    valid = load_valid_statuses()
    data = yaml.safe_load(args.tasks.read_text()) or {}

    shape = "aggregate" if document_is_aggregate(data) else "full"
    if args.require_shape and args.require_shape != shape:
        print(f"{args.tasks}: expected the {args.require_shape} board shape, found {shape}", file=sys.stderr)
        return 1
    if shape == "aggregate":
        return validate_aggregate(args.tasks, data)

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
            f"{args.tasks} has {len(invalid)} task(s) with non-canonical status (valid: {', '.join(sorted(valid))})",
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
            f"{args.tasks} has {len(dispatchable_human)} needs-human task(s) still available to dispatch",
            file=sys.stderr,
        )
        for task_id, status in dispatchable_human[:50]:
            print(f"  {task_id}: {status}", file=sys.stderr)
        if len(dispatchable_human) > 50:
            print(f"  ... {len(dispatchable_human) - 50} more", file=sys.stderr)
        return 1

    # Status semantics first, schema/budget contract second. The status checks are this
    # predicate's original purpose and its callers pass deliberately minimal fixtures
    # (a two-row board proving a duplicate id, with no version or budget); running the
    # contract first answers every one of those with "missing version" and hides the
    # defect actually under test. Order changes which failure surfaces, never whether
    # the contract is enforced.
    contract = validate_full_board_contract(args.tasks, data)
    if contract != 0:
        return contract

    print(f"Task board statuses valid ({len(data.get('tasks') or [])} tasks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
