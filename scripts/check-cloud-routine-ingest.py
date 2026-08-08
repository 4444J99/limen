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
            _load_ingest_module().validate_human_gate_owners(
                receipts,
                lever_path=lever_path,
            )
    except Exception as exc:
        failures.append(f"receipt contract: {exc}")

    try:
        irf = json.loads(irf_path.read_text(encoding="utf-8"))
        rows = irf["rows"]
        by_id = {row["irf_id"]: row for row in rows}
        human_ids = set(irf["human_gate_irf_ids"])
        if not irf["denominator"] == irf["classified"] == len(rows) == len(by_id) == 41:
            failures.append("IRF denominator/classification is not exactly 41 unique rows")
        if irf["unowned"]:
            failures.append(f"IRF receipt has unowned rows: {irf['unowned']}")
        if not human_ids:
            failures.append("IRF human-gate denominator is empty")
        for irf_id in sorted(human_ids):
            row = by_id.get(irf_id)
            if not row:
                failures.append(f"IRF human-gate row missing: {irf_id}")
                continue
            if (
                row.get("owner_kind") != "lever"
                or row.get("owner_ref") != irf["human_gate_owner"]
                or row.get("disposition") != "human_gate"
            ):
                failures.append(f"IRF human-gate ownership drift: {irf_id}")
        lever_payload = json.loads(lever_path.read_text(encoding="utf-8"))
        lever_ids = {lever["id"] for lever in lever_payload["levers"]}
        owner_id = str(irf["human_gate_owner"]).removeprefix("lever:")
        if owner_id not in lever_ids:
            failures.append(f"IRF human-gate lever is not registered: {owner_id}")
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
