#!/usr/bin/env python3
"""Bounded JSON CLI for machine-wide Limen host admission."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.host_admission import (  # noqa: E402
    DENIED_EXIT,
    USAGE_EXIT,
    AdmissionController,
    AdmissionStateError,
    host_admission_capabilities,
)
from limen.host_admission_capabilities import host_admission_capabilities  # noqa: E402


def _controller(args: argparse.Namespace) -> AdmissionController:
    root = Path(args.state_root).expanduser() if args.state_root else None
    return AdmissionController(root)


def _emit(payload: dict[str, object], *, report_only: bool = False) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if report_only or payload.get("allowed") else DENIED_EXIT


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", help="test/operator override for the per-user machine store")
    sub = parser.add_subparsers(dest="operation", required=True)

    acquire = sub.add_parser("acquire")
    acquire.add_argument("--kind", required=True, help="execution, heavy, or execution:<sha256>")
    acquire.add_argument("--owner", required=True)
    acquire.add_argument("--surface", required=True)
    acquire.add_argument("--pid", type=int, default=os.getppid())
    acquire.add_argument("--ttl-seconds", type=int)

    for operation in ("refresh", "release"):
        command = sub.add_parser(operation)
        command.add_argument("--lease-id", required=True)
        command.add_argument("--owner", required=True)
        command.add_argument("--pid", type=int, default=os.getppid())
        if operation == "refresh":
            command.add_argument("--ttl-seconds", type=int)
            command.add_argument("--watch", action="store_true")
            command.add_argument("--interval-seconds", type=int, default=60)

    status = sub.add_parser("status")
    status.add_argument("--no-probe", action="store_true")
    sub.add_parser("diagnose")
    sub.add_parser("capabilities")

    args = parser.parse_args()
    controller = _controller(args)
    try:
        if args.operation == "acquire":
            return _emit(
                controller.acquire(
                    args.kind,
                    owner=args.owner,
                    surface=args.surface,
                    pid=args.pid,
                    ttl_seconds=args.ttl_seconds,
                )
            )
        if args.operation == "refresh":
            if args.watch:
                if not 10 <= args.interval_seconds <= 300:
                    raise ValueError("interval-seconds must be between 10 and 300")
                while True:
                    time.sleep(args.interval_seconds)
                    decision = controller.refresh(
                        lease_id=args.lease_id,
                        owner=args.owner,
                        pid=args.pid,
                        ttl_seconds=args.ttl_seconds,
                    )
                    if not decision["allowed"]:
                        return _emit(decision)
            return _emit(
                controller.refresh(
                    lease_id=args.lease_id,
                    owner=args.owner,
                    pid=args.pid,
                    ttl_seconds=args.ttl_seconds,
                )
            )
        if args.operation == "release":
            return _emit(
                controller.release(
                    lease_id=args.lease_id,
                    owner=args.owner,
                    pid=args.pid,
                )
            )
        if args.operation == "diagnose":
            print(json.dumps(controller.diagnose(), indent=2, sort_keys=True))
            return 0
        if args.operation == "capabilities":
            print(json.dumps(host_admission_capabilities(), indent=2, sort_keys=True))
            return 0
        return _emit(controller.status(probe=not args.no_probe), report_only=True)
    except (AdmissionStateError, ValueError) as exc:
        diagnostic = exc.diagnostic() if isinstance(exc, AdmissionStateError) else {"error": str(exc)}
        print(
            json.dumps(
                {
                    "schema": "limen.host_admission_decision.v1",
                    "operation": args.operation,
                    "allowed": False,
                    "reasons": ["state-or-input-invalid"],
                    **diagnostic,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return DENIED_EXIT if isinstance(exc, AdmissionStateError) else USAGE_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
