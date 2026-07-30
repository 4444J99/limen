#!/usr/bin/env python3
"""Discover, restore, and verify bounded external custody for estate-audit roots."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.estate_audit_custody import (
    DEFAULT_CUSTODY_ROOT,
    MAX_ROOTS,
    MAX_SECONDS,
    EstateAuditCustodyError,
    apply_plan,
    assert_custody_target_identity,
    discover_plan,
    preflight_plan,
    public_receipt,
    verify_receipt,
)

RESULT_SCHEMA = "limen.estate_audit_custody_result.v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="discover the complete bounded source plan")
    mode.add_argument("--apply", action="store_true", help="hydrate and restore the exact checked plan")
    mode.add_argument(
        "--verify-receipt",
        action="store_true",
        help="re-verify an existing exact-plan receipt through a fresh restore",
    )
    parser.add_argument("--limen-root", type=Path, default=ROOT)
    parser.add_argument("--custody-root", type=Path, default=DEFAULT_CUSTODY_ROOT)
    parser.add_argument("--expected-plan-sha")
    parser.add_argument("--expected-volume-uuid")
    parser.add_argument("--expected-physical-identity")
    parser.add_argument("--max-roots", type=int, default=MAX_ROOTS)
    parser.add_argument("--max-seconds", type=int, default=MAX_SECONDS)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _emit(payload: dict[str, Any], *, as_json: bool) -> None:
    output = {"result_schema": RESULT_SCHEMA, **payload}
    if as_json:
        print(json.dumps(output, separators=(",", ":"), sort_keys=True))
        return
    fields = [
        f"status={output.get('status', 'unknown')}",
        f"roots={output.get('root_count', 0)}",
        f"repositories={output.get('repository_count', 0)}",
        f"heads={output.get('head_count', 0)}",
        f"plan_sha256={output.get('plan_sha256', '')}",
    ]
    if "changed" in output:
        fields.append(f"changed={str(output['changed']).lower()}")
    print("estate-audit-custody: " + " ".join(fields))


def _require_expected(args: argparse.Namespace) -> str:
    value = str(args.expected_plan_sha or "")
    if not value:
        raise EstateAuditCustodyError("expected-plan-sha-required")
    return value


def _identity_guard(args: argparse.Namespace):
    expected_uuid = str(args.expected_volume_uuid or "")
    expected_physical = str(args.expected_physical_identity or "")
    if bool(expected_uuid) != bool(expected_physical):
        raise EstateAuditCustodyError("expected-custody-identity-incomplete")
    if not expected_uuid:
        return None
    return lambda resolved_root: assert_custody_target_identity(
        resolved_root,
        expected_volume_uuid=expected_uuid,
        expected_physical_identity=expected_physical,
    )


def main() -> int:
    args = parse_args()
    try:
        deadline = time.monotonic() + args.max_seconds
        identity_guard = _identity_guard(args)
        if args.verify_receipt:
            expected = _require_expected(args)
            receipt = verify_receipt(
                args.custody_root,
                expected,
                full_restore=True,
                max_seconds=args.max_seconds,
                identity_guard=identity_guard,
                deadline=deadline,
            )
            _emit(public_receipt(receipt, changed=False), as_json=args.json)
            return 0

        plan = discover_plan(
            args.limen_root,
            max_roots=args.max_roots,
            deadline=deadline,
        )
        if args.expected_plan_sha and args.expected_plan_sha != plan.plan_sha256:
            raise EstateAuditCustodyError("plan-sha-mismatch")
        if args.check:
            _emit(
                {
                    **plan.public_payload(),
                    **preflight_plan(
                        plan,
                        max_seconds=args.max_seconds,
                        deadline=deadline,
                    ),
                },
                as_json=args.json,
            )
            return 0

        expected = _require_expected(args)
        receipt, changed = apply_plan(
            plan,
            args.custody_root,
            expected_plan_sha256=expected,
            revalidate=lambda: discover_plan(
                args.limen_root,
                max_roots=args.max_roots,
                deadline=deadline,
            ),
            max_seconds=args.max_seconds,
            identity_guard=identity_guard,
            deadline=deadline,
        )
        _emit(public_receipt(receipt, changed=changed), as_json=args.json)
        return 0
    except EstateAuditCustodyError as exc:
        _emit({"status": "blocked", "error": exc.code}, as_json=args.json)
        return 3
    # This executable is the public redaction boundary: unexpected local faults must not
    # serialize private checkout or custody paths into unattended logs.
    except Exception:  # noqa: BLE001
        _emit({"status": "blocked", "error": "unexpected-error"}, as_json=args.json)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
