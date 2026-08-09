#!/usr/bin/env python3
"""Verify the CloudRoutineReceiptV1 contract and current owned denominator."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.cloud_routine import CloudRoutineReceiptV1  # noqa: E402


def _load_ingest_module():
    path = ROOT / "scripts" / "cloud-routine-ingest.py"
    spec = importlib.util.spec_from_file_location("cloud_routine_ingest_check", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_irf_receipt(
    irf: object,
    *,
    active_levers: set[str],
) -> list[str]:
    """Derive the complete 41-row ownership partition from row-level evidence."""
    failures: list[str] = []
    if not isinstance(irf, dict):
        return ["IRF receipt must be an object"]
    rows = irf.get("rows")
    if not isinstance(rows, list):
        return ["IRF rows must be a list"]
    valid_rows = [row for row in rows if isinstance(row, dict)]
    if len(valid_rows) != len(rows):
        failures.append("IRF rows contain a non-object entry")
    by_id = {
        str(row.get("irf_id")): row
        for row in valid_rows
        if isinstance(row.get("irf_id"), str) and row.get("irf_id")
    }
    if not (
        irf.get("denominator")
        == irf.get("classified")
        == len(rows)
        == len(by_id)
        == 41
    ):
        failures.append("IRF denominator/classification is not exactly 41 unique rows")
    if irf.get("unowned") != []:
        failures.append(f"IRF receipt has unowned rows: {irf.get('unowned')}")

    declared_human = irf.get("human_gate_irf_ids")
    human_ids = (
        {str(irf_id) for irf_id in declared_human}
        if isinstance(declared_human, list)
        else set()
    )
    human_owner = irf.get("human_gate_owner")
    derived_human: set[str] = set()
    for irf_id, row in by_id.items():
        owner_kind = row.get("owner_kind")
        owner_ref = row.get("owner_ref")
        disposition = row.get("disposition")
        if irf_id in human_ids:
            derived_human.add(irf_id)
            if (
                owner_kind != "lever"
                or owner_ref != human_owner
                or disposition != "human_gate"
            ):
                failures.append(f"IRF human-gate ownership drift: {irf_id}")
        elif (
            owner_kind != "irf"
            or owner_ref != f"irf:{irf_id}"
            or disposition != "owned"
        ):
            failures.append(f"IRF owned-row ownership drift: {irf_id}")
    if derived_human != human_ids:
        failures.append("IRF human-gate ID set does not match the row partition")

    # A non-empty human partition must remain attached to a live lever. Once every
    # human action is discharged and rows are reclassified as ordinary owned work,
    # the empty partition is the terminal green state rather than a false failure.
    if human_ids:
        owner_id = str(human_owner or "").removeprefix("lever:")
        if owner_id not in active_levers:
            failures.append(f"IRF human-gate lever is not active: {owner_id or '<missing>'}")
    return failures


def main() -> int:
    failures: list[str] = []
    schema_path = ROOT / "spec" / "contracts" / "cloud-routine-receipt-v1.schema.json"
    receipt_path = ROOT / "docs" / "receipts" / "cloud-routine-findings-20260808.json"
    irf_path = ROOT / "docs" / "receipts" / "irf-p0-owner-classification-20260808.json"
    lever_path = ROOT / "his-hand-levers.json"

    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        raw_receipts = json.loads(receipt_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        if not isinstance(raw_receipts, list) or len(raw_receipts) != 11:
            failures.append("current cloud-routine denominator is not exactly 11 receipts")
            raw_receipts = raw_receipts if isinstance(raw_receipts, list) else []
        receipts: list[CloudRoutineReceiptV1] = []
        for index, raw in enumerate(raw_receipts):
            schema_errors = sorted(
                validator.iter_errors(raw),
                key=lambda error: list(error.absolute_path),
            )
            failures.extend(
                f"receipt[{index}] schema: {error.message}" for error in schema_errors
            )
            try:
                receipts.append(CloudRoutineReceiptV1.model_validate(raw))
            except Exception as exc:
                failures.append(f"receipt[{index}] model: {exc}")
        if len(receipts) == len(raw_receipts):
            ingest = _load_ingest_module()
            ingest.validate_routine_ids(
                receipts,
                manifest_path=ROOT / "cloud-routines.json",
            )
            ingest.validate_human_gate_owners(
                receipts,
                lever_path=lever_path,
            )
            if any(receipt.disposition == "new_work" for receipt in receipts):
                failures.append(
                    "current cloud-routine denominator contains novel new_work; "
                    "the broker task upsert is not yet durably classified"
                )
    except Exception as exc:
        failures.append(f"receipt contract: {exc}")

    try:
        irf = json.loads(irf_path.read_text(encoding="utf-8"))
        active_levers = _load_ingest_module().active_lever_ids(lever_path)
        failures.extend(
            validate_irf_receipt(
                irf,
                active_levers=active_levers,
            )
        )
    except Exception as exc:
        failures.append(f"IRF denominator: {exc}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "OK: CloudRoutineReceiptV1 schema/model/owner parity; "
        "11 current receipts and 41 IRF P0 rows are durably classified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
