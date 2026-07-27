#!/usr/bin/env python3
"""Run one registry-owned core Omega predicate and emit its typed owner receipt."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)).resolve()
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.omega_owner_receipt import (
    OmegaOwnerReceiptError,
    run_owner_predicate,
)

CORE_REGISTRY = ROOT / "institutio" / "governance" / "omega-core-rungs.json"


def _safe_path(relative: str) -> Path:
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts:
        raise OmegaOwnerReceiptError("core owner receipt path is unsafe")
    resolved = (ROOT / path).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise OmegaOwnerReceiptError("core owner receipt escapes the repository") from exc
    return resolved


def _core_rung(rung_id: str) -> tuple[str, Path, int]:
    try:
        payload = json.loads(CORE_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OmegaOwnerReceiptError(f"core rung registry is unreadable: {exc}") from exc
    rows = payload.get("rungs") if isinstance(payload, dict) else None
    if payload.get("schema") != "limen.omega_rung_registry.v1" or not isinstance(rows, list):
        raise OmegaOwnerReceiptError("core rung registry schema is unsupported")
    matches = [row for row in rows if isinstance(row, dict) and row.get("id") == rung_id]
    if len(matches) != 1:
        raise OmegaOwnerReceiptError(f"{rung_id}: core rung is missing or duplicated")
    rung = matches[0]
    if rung.get("tier") != "live":
        raise OmegaOwnerReceiptError(f"{rung_id}: only live core rungs emit owner receipts")
    predicate = str(rung.get("predicate") or "").strip()
    receipts = [
        descriptor
        for descriptor in (rung.get("semantic_inputs") or [])
        if isinstance(descriptor, dict) and descriptor.get("role") == "owner_receipt"
    ]
    if len(receipts) != 1:
        raise OmegaOwnerReceiptError(f"{rung_id}: live core rung must declare exactly one owner receipt")
    descriptor = receipts[0]
    if (
        descriptor.get("normalization") != "json"
        or descriptor.get("volatile_fields") != ["observed_at"]
        or not isinstance(descriptor.get("max_age_seconds"), int)
    ):
        raise OmegaOwnerReceiptError(f"{rung_id}: core owner receipt descriptor is invalid")
    timeout = rung.get("timeout")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 7200:
        raise OmegaOwnerReceiptError(f"{rung_id}: core predicate timeout is invalid")
    return predicate, _safe_path(str(descriptor.get("path") or "")), timeout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rung-id", required=True)
    args = parser.parse_args(argv)
    try:
        predicate, receipt_path, timeout = _core_rung(args.rung_id)
        exit_code, stdout, stderr, _receipt = run_owner_predicate(
            root=ROOT,
            rung_id=args.rung_id,
            predicate=predicate,
            receipt_path=receipt_path,
            timeout_seconds=timeout,
        )
    except OmegaOwnerReceiptError as exc:
        print(f"omega-owner-receipt: {exc}", file=sys.stderr)
        return 1
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
