#!/usr/bin/env python3
"""Prove generated estate-audit custody on two registered physical devices."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

DEFAULT_REGISTRY = ROOT / "institutio" / "governance" / "estate-audit-custody-targets.json"
SINGLE_RAIL_SCRIPT = ROOT / "scripts" / "estate-audit-custody.py"


def parse_args(*, max_roots: int, max_seconds: int) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.add_argument("--limen-root", type=Path, default=ROOT)
    parser.add_argument("--max-roots", type=int, default=max_roots)
    parser.add_argument("--max-seconds", type=int, default=max_seconds)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _emit(payload: dict[str, object], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return
    fields = [
        f"status={payload.get('status', 'unknown')}",
        f"roots={payload.get('root_count', 0)}",
        f"plan_sha256={payload.get('plan_sha256', '')}",
        f"changed={str(payload.get('changed', False)).lower()}",
    ]
    if "error" in payload:
        fields.append(f"error={payload['error']}")
    print("estate-audit-paired-custody: " + " ".join(fields))


def _blocked(error: str) -> dict[str, object]:
    return {
        "schema": "limen.estate_audit_paired_custody_projection.v1",
        "status": "blocked",
        "error": error,
    }


def main() -> int:
    try:
        from limen.estate_audit_custody import MAX_ROOTS, MAX_SECONDS
        from limen.estate_audit_paired_custody import (
            PairedCustodyError,
            blocked_projection,
            run_paired_custody,
        )
    except (ModuleNotFoundError, ImportError):
        _emit(_blocked("dependency-unavailable"), as_json="--json" in sys.argv[1:])
        return 4

    args = parse_args(max_roots=MAX_ROOTS, max_seconds=MAX_SECONDS)
    try:
        result = run_paired_custody(
            repository_root=ROOT,
            limen_root=args.limen_root,
            registry_path=DEFAULT_REGISTRY,
            single_rail_script=SINGLE_RAIL_SCRIPT,
            max_roots=args.max_roots,
            max_seconds=args.max_seconds,
        )
        _emit(result, as_json=args.json)
        return 0
    except PairedCustodyError as exc:
        _emit(blocked_projection(exc), as_json=args.json)
        return 3
    # This executable is a redaction boundary: no private mount or checkout
    # detail from an unexpected local fault reaches unattended logs.
    except Exception:  # noqa: BLE001
        _emit(_blocked("unexpected-error"), as_json=args.json)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
