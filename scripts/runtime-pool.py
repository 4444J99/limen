#!/usr/bin/env python3
"""Bounded adapter for Domus and native managed-growth operations."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli/src"))
from limen.host_admission import AdmissionStateError
from limen.resource_envelope import ResourceGraphError, ResourceTelemetryUnavailable
from limen.runtime_pool import PoolUnavailable, RuntimePool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("observe", "reserve", "release"))
    parser.add_argument("--root", type=Path, default=Path.home())
    parser.add_argument("--owner")
    parser.add_argument("--pid", type=int, default=os.getppid())
    parser.add_argument("--bytes", type=int)
    parser.add_argument("--claim-id")
    parser.add_argument("--reservation-id")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    controller = RuntimePool()
    try:
        if args.operation == "observe":
            result = controller.observe(args.root)
        elif args.operation == "reserve":
            result = controller.reserve(
                args.root, owner=args.owner, pid=args.pid, growth_bytes=args.bytes, claim_id=args.claim_id
            )
        else:
            result = controller.release_growth(args.reservation_id, owner=args.owner, pid=args.pid)
    except (
        PoolUnavailable,
        ResourceGraphError,
        ResourceTelemetryUnavailable,
        AdmissionStateError,
        OSError,
        ValueError,
        TypeError,
    ) as exc:
        result = {
            "allowed": False,
            "denial_reasons": [str(exc) if isinstance(exc, PoolUnavailable) else type(exc).__name__],
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("allowed", result.get("released", False)) else 75


if __name__ == "__main__":
    raise SystemExit(main())
