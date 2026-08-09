#!/usr/bin/env python3
"""Validate CloudRoutineReceiptV1 deliveries and submit novel work via TABVLARIVS."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.cloud_routine import (
    CloudRoutineReceiptV1,
    plan_task_upserts,
    task_id_for,
)  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.tabularius import pending_task_ids, submit_task_upsert  # noqa: E402


TERMINAL_LEVER_STATUSES = frozenset({"discharged", "retired", "done", "closed"})


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


def _lever_states(path: Path) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    levers = payload.get("levers") if isinstance(payload, dict) else None
    if not isinstance(levers, list):
        raise ValueError("human-lever registry must contain a levers list")
    states: dict[str, str] = {}
    for lever in levers:
        if not isinstance(lever, dict) or not isinstance(lever.get("id"), str):
            continue
        status = str(lever.get("status") or "").strip().lower()
        # Legacy active levers often omit status; only an explicit discharge closes one.
        if lever.get("discharged"):
            status = "discharged"
        states[str(lever["id"])] = status
    return states


def active_lever_ids(path: Path) -> set[str]:
    """Return registered levers that still represent live human ownership."""
    return {
        lever_id
        for lever_id, status in _lever_states(path).items()
        if status not in TERMINAL_LEVER_STATUSES
    }



def latest_receipts_by_lineage(
    receipts: list[CloudRoutineReceiptV1],
) -> list[CloudRoutineReceiptV1]:
    """Keep only the newest observation for live owner resolution."""
    latest: dict[str, CloudRoutineReceiptV1] = {}
    for receipt in receipts:
        lineage_id = task_id_for(receipt)
        previous = latest.get(lineage_id)
        if previous is None or receipt.observed_at >= previous.observed_at:
            latest[lineage_id] = receipt
    return list(latest.values())

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
    states = _lever_states(lever_path)
    owner_ids = {
        (receipt.owner_ref or "").removeprefix("lever:")
        for receipt in human_gate_receipts
    }
    missing = sorted(owner_ids - states.keys())
    if missing:
        raise ValueError(
            "human_gate owner_ref does not resolve in his-hand-levers.json: "
            + ", ".join(missing)
        )
    terminal = sorted(
        lever_id
        for lever_id in owner_ids
        if states[lever_id] in TERMINAL_LEVER_STATUSES
    )
    if terminal:
        raise ValueError(
            "human_gate owner_ref resolves only to a terminal/inactive lever: "
            + ", ".join(terminal)
        )


def registered_routine_ids(path: Path = ROOT / "cloud-routines.json") -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    routines = payload.get("routines") if isinstance(payload, dict) else None
    if not isinstance(routines, list):
        raise ValueError("cloud-routines.json must contain a routines list")
    routine_ids = {
        str(routine.get("name"))
        for routine in routines
        if isinstance(routine, dict) and isinstance(routine.get("name"), str)
    }
    if not routine_ids:
        raise ValueError("cloud-routines.json contains no routine names")
    return routine_ids


def validate_routine_ids(
    receipts: list[CloudRoutineReceiptV1],
    *,
    manifest_path: Path = ROOT / "cloud-routines.json",
) -> None:
    registered = registered_routine_ids(manifest_path)
    unknown = sorted({receipt.routine_id for receipt in receipts} - registered)
    if unknown:
        raise ValueError("routine_id is absent from cloud-routines.json: " + ", ".join(unknown))


def load_receipts(
    paths: list[Path],
    *,
    lever_path: Path = ROOT / "his-hand-levers.json",
    manifest_path: Path = ROOT / "cloud-routines.json",
) -> list[CloudRoutineReceiptV1]:
    """Validate every input and resolve every human owner before task emission."""
    receipts: list[CloudRoutineReceiptV1] = []
    for path in paths:
        receipts.extend(
            CloudRoutineReceiptV1.model_validate(item)
            for item in _objects_from_path(path)
        )
    validate_routine_ids(receipts, manifest_path=manifest_path)
    validate_human_gate_owners(
        latest_receipts_by_lineage(receipts),
        lever_path=lever_path,
    )
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
    historical_observed_at: dict[str, datetime] = {}
    for task in board.tasks:
        context = str(task.context or "")
        match = re.search(r"observed_at=([^;]+)", context)
        if match:
            try:
                historical_observed_at[task.id] = datetime.fromisoformat(
                    match.group(1).replace("Z", "+00:00")
                )
            except ValueError:
                pass
    plan = plan_task_upserts(
        receipts,
        existing_ids=(
            task.id for task in board.tasks if str(task.status) in active_statuses
        ),
        pending_ids=pending_task_ids(tasks_path),
        historical_ids=(task.id for task in board.tasks),
        historical_observed_at=historical_observed_at,
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
