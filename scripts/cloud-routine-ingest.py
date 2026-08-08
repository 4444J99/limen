#!/usr/bin/env python3
"""Validate CloudRoutineReceiptV1 deliveries and submit novel work via TABVLARIVS."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.cloud_routine import CloudRoutineReceiptV1, plan_task_upserts  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.tabularius import pending_task_ids, submit_task_upsert  # noqa: E402


def _objects_from_path(path: Path) -> list[object]:
    raw = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return [
            json.loads(line)
            for line in raw.splitlines()
            if line.strip()
        ]
    return payload if isinstance(payload, list) else [payload]


def _lever_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    levers = payload.get("levers") if isinstance(payload, dict) else None
    if not isinstance(levers, list):
        raise ValueError("human-lever registry must contain a levers list")
    return {
        str(lever["id"])
        for lever in levers
        if isinstance(lever, dict) and isinstance(lever.get("id"), str)
    }


def validate_human_gate_owners(
    receipts: list[CloudRoutineReceiptV1],
    *,
    lever_path: Path,
) -> None:
    """Reject human gates whose named durable lever does not exist."""
    human_gate_receipts = [
        receipt for receipt in receipts if receipt.disposition == "human_gate"
    ]
    if not human_gate_receipts:
        return
    known = _lever_ids(lever_path)
    missing = sorted(
        {
            (receipt.owner_ref or "").removeprefix("lever:")
            for receipt in human_gate_receipts
            if (receipt.owner_ref or "").removeprefix("lever:") not in known
        }
    )
    if missing:
        raise ValueError(
            "human_gate owner_ref does not resolve in his-hand-levers.json: "
            + ", ".join(missing)
        )


def load_receipts(
    paths: list[Path],
    *,
    lever_path: Path = ROOT / "his-hand-levers.json",
) -> list[CloudRoutineReceiptV1]:
    """Validate every input and resolve every human owner before task emission."""
    receipts: list[CloudRoutineReceiptV1] = []
    for path in paths:
        receipts.extend(
            CloudRoutineReceiptV1.model_validate(item)
            for item in _objects_from_path(path)
        )
    validate_human_gate_owners(receipts, lever_path=lever_path)
    return receipts


def _tasks_path() -> Path:
    """Resolve the read-only board projection independently of this script checkout."""
    explicit = os.environ.get("LIMEN_TASKS")
    if explicit:
        return Path(explicit).expanduser()
    limen_root = os.environ.get("LIMEN_ROOT")
    if limen_root:
        return Path(limen_root).expanduser() / "tasks.yaml"
    return ROOT / "tasks.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest typed cloud-routine outcomes through TABVLARIVS."
    )
    parser.add_argument("receipts", nargs="+", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.apply and os.environ.get("LIMEN_CLOUD_ROUTINE_INGEST_APPLY", "0") != "1":
        parser.error("--apply requires LIMEN_CLOUD_ROUTINE_INGEST_APPLY=1")

    try:
        receipts = load_receipts(args.receipts)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"cloud-routine-ingest: invalid receipt: {exc}", file=sys.stderr)
        return 2

    tasks_path = _tasks_path()
    board = load_limen_file(tasks_path)
    active_statuses = {
        "open",
        "dispatched",
        "in_progress",
        "failed",
        "failed_blocked",
        "needs_human",
    }
    plan = plan_task_upserts(
        receipts,
        existing_ids=(
            task.id for task in board.tasks if str(task.status) in active_statuses
        ),
        pending_ids=pending_task_ids(tasks_path),
        historical_ids=(task.id for task in board.tasks),
    )

    submitted: list[str] = []
    if args.apply:
        for task in plan.tasks:
            submit_task_upsert(
                tasks_path,
                task,
                agent="cloud-routine-ingest",
                session_id=os.environ.get(
                    "LIMEN_SESSION_ID",
                    "cloud-routine-ingest",
                ),
            )
            submitted.append(task.id)

    payload = {
        "schema_version": "limen.cloud_routine_ingest_result.v1",
        "mode": "apply" if args.apply else "dry-run",
        "receipts": len(receipts),
        "classified": plan.classified,
        "duplicates": plan.duplicates,
        "new_work": [task.id for task in plan.tasks],
        "submitted": submitted,
    }
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            "cloud-routine-ingest: "
            f"{len(receipts)} receipt(s), "
            f"{plan.classified} classified without new work, "
            f"{plan.duplicates} duplicate(s), "
            f"{len(plan.tasks)} novel task(s) "
            f"[{payload['mode']}]"
        )
        for task in plan.tasks:
            verb = "submitted" if args.apply else "would submit"
            print(f"  {verb} {task.id} -> {task.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
