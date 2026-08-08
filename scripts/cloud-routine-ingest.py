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


def load_receipts(paths: list[Path]) -> list[CloudRoutineReceiptV1]:
    """Validate every input before any task ticket can be emitted."""
    receipts: list[CloudRoutineReceiptV1] = []
    for path in paths:
        receipts.extend(
            CloudRoutineReceiptV1.model_validate(item)
            for item in _objects_from_path(path)
        )
    return receipts


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

    board = load_limen_file(ROOT / "tasks.yaml")
    plan = plan_task_upserts(
        receipts,
        existing_ids=(task.id for task in board.tasks),
        pending_ids=pending_task_ids(ROOT / "tasks.yaml"),
    )

    submitted: list[str] = []
    if args.apply:
        for task in plan.tasks:
            submit_task_upsert(
                ROOT / "tasks.yaml",
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
