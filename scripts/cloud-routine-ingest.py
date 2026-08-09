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
        objects = [
            json.loads(line)
            for line in raw.splitlines()
            if line.strip()
        ]
    else:
        objects = payload if isinstance(payload, list) else [payload]
    if not objects:
        raise ValueError(f"{path}: receipt delivery is empty")
    return objects


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
        if previous is None:
            latest[lineage_id] = receipt
            continue
        if receipt.observed_at == previous.observed_at:
            if receipt != previous:
                raise ValueError(
                    "conflicting cloud-routine observations share the same "
                    f"timestamp for {lineage_id}"
                )
            continue
        if receipt.observed_at > previous.observed_at:
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


def validate_lever_owners(
    receipts: list[CloudRoutineReceiptV1],
    *,
    lever_path: Path,
) -> None:
    """Reject any material receipt that names a missing or terminal lever."""
    lever_receipts = [
        receipt
        for receipt in receipts
        if (receipt.owner_ref or "").startswith("lever:")
    ]
    if not lever_receipts:
        return
    states = _lever_states(lever_path)
    owner_ids = {
        (receipt.owner_ref or "").removeprefix("lever:")
        for receipt in lever_receipts
    }
    missing = sorted(owner_ids - states.keys())
    if missing:
        raise ValueError(
            "lever owner_ref does not resolve in his-hand-levers.json: "
            + ", ".join(missing)
        )
    terminal = sorted(
        lever_id
        for lever_id in owner_ids
        if states[lever_id] in TERMINAL_LEVER_STATUSES
    )
    if terminal:
        raise ValueError(
            "lever owner_ref resolves only to a terminal/inactive lever: "
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
    latest = latest_receipts_by_lineage(receipts)
    validate_human_gate_owners(
        latest,
        lever_path=lever_path,
    )
    validate_lever_owners(latest, lever_path=lever_path)
    return receipts


def _merge_historical_observation(
    historical_ids: set[str],
    observed_at: dict[str, datetime],
    task_id: str,
    stamp: datetime | None,
) -> None:
    historical_ids.add(task_id)
    if stamp is None:
        return
    previous = observed_at.get(task_id)
    if previous is None or stamp > previous:
        observed_at[task_id] = stamp


def _tracked_cloud_lineage_path() -> Path:
    return ROOT / "docs" / "receipts" / "cloud-routine-lineage.json"


def _tracked_cloud_task_state() -> tuple[set[str], dict[str, datetime]]:
    """Read append-only cloud lineage from a tracked receipt envelope."""
    source = _tracked_cloud_lineage_path()
    historical_ids: set[str] = set()
    observed_at: dict[str, datetime] = {}
    if not source.is_file():
        return historical_ids, observed_at
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"tracked cloud lineage is unreadable: {source}") from exc
    entries = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"tracked cloud lineage entries must be a list: {source}")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"tracked cloud lineage entry[{index}] is not an object")
        try:
            receipt = CloudRoutineReceiptV1.model_validate(entry)
        except ValidationError as exc:
            raise ValueError(f"tracked cloud lineage entry[{index}] is invalid: {exc}") from exc
        _merge_historical_observation(
            historical_ids,
            observed_at,
            task_id_for(receipt),
            receipt.observed_at,
        )
    return historical_ids, observed_at


def _append_cloud_lineage_receipt(receipt: CloudRoutineReceiptV1) -> None:
    """Append one accepted receipt to the tracked duplicate boundary idempotently."""
    source = _tracked_cloud_lineage_path()
    payload: dict[str, object] = {
        "schema_version": "limen.cloud_routine_lineage.v1",
        "description": "Tracked append-only cloud receipt lineage; consumers may use this as the durable duplicate boundary.",
        "entries": [],
    }
    if source.is_file():
        try:
            loaded = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"tracked cloud lineage is unreadable: {source}") from exc
        if not isinstance(loaded, dict) or not isinstance(loaded.get("entries"), list):
            raise ValueError(f"tracked cloud lineage entries must be a list: {source}")
        payload = loaded
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"tracked cloud lineage entries must be a list: {source}")
    existing: list[CloudRoutineReceiptV1] = []
    for index, entry in enumerate(entries):
        try:
            existing.append(CloudRoutineReceiptV1.model_validate(entry))
        except ValidationError as exc:
            raise ValueError(f"tracked cloud lineage entry[{index}] is invalid: {exc}") from exc
    if any(previous == receipt for previous in existing):
        return
    entries.append(receipt.model_dump(mode="json"))
    source.parent.mkdir(parents=True, exist_ok=True)
    temporary = source.with_suffix(source.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(source)


def _receipt_for_task(task_id: str, receipts: list[CloudRoutineReceiptV1]) -> CloudRoutineReceiptV1:
    matches = [
        receipt
        for receipt in latest_receipts_by_lineage(receipts)
        if task_id == task_id_for(receipt) or task_id.startswith(task_id_for(receipt) + "-")
    ]
    if len(matches) != 1:
        raise ValueError(f"cannot map submitted cloud task to one receipt: {task_id}")
    return matches[0]


def _historical_cloud_task_state(tasks_path: Path) -> tuple[set[str], dict[str, datetime]]:
    """Combine tracked lineage with legacy keeper tickets after board pruning."""
    historical_ids, observed_at = _tracked_cloud_task_state()
    archive = tasks_path.parent / "logs" / "tickets" / "archive"
    observed_pattern = re.compile(r"observed_at=([^;]+)")
    if not archive.is_dir():
        return historical_ids, observed_at
    for path in sorted(archive.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else {}
        candidates = {
            value
            for value in (payload.get("task_id"), patch.get("id"))
            if isinstance(value, str) and value.startswith("CLOUD-")
        }
        if not candidates:
            continue
        context = str(patch.get("context") or "")
        match = observed_pattern.search(context)
        stamp = None
        if match:
            try:
                stamp = datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
            except ValueError:
                stamp = None
        for task_id in candidates:
            _merge_historical_observation(
                historical_ids,
                observed_at,
                task_id,
                stamp,
            )
    return historical_ids, observed_at


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
    historical_ids = {task.id for task in board.tasks}
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
    try:
        archived_ids, archived_observed_at = _historical_cloud_task_state(tasks_path)
    except (OSError, ValueError) as exc:
        print(f"cloud-routine-ingest: invalid tracked lineage: {exc}", file=sys.stderr)
        return 2
    historical_ids.update(archived_ids)
    historical_observed_at.update(archived_observed_at)
    plan = plan_task_upserts(
        receipts,
        existing_ids=(
            task.id for task in board.tasks if str(task.status) in active_statuses
        ),
        pending_ids=pending_task_ids(tasks_path),
        historical_ids=historical_ids,
        historical_observed_at=historical_observed_at,
    )

    submitted: list[str] = []
    submit_error: str | None = None
    if args.apply:
        for task in plan.tasks:
            try:
                receipt = _receipt_for_task(task.id, receipts)
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
                _append_cloud_lineage_receipt(receipt)
            except Exception as exc:
                submit_error = f"{task.id}: {exc}"
                break

    payload = {
        "schema_version": "limen.cloud_routine_ingest_result.v1",
        "mode": "apply" if args.apply else "dry-run",
        "receipts": len(receipts),
        "classified": plan.classified,
        "duplicates": plan.duplicates,
        "new_work": [task.id for task in plan.tasks],
        "submitted": submitted,
        "submit_error": submit_error,
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
        if submit_error:
            print(f"  submit_error: {submit_error}", file=sys.stderr)
    return 1 if submit_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
