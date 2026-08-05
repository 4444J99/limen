#!/usr/bin/env python3
"""Plan or apply one sanctioned, recoverable worktree-abandonment action."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.worktree_abandonment import (  # noqa: E402
    LockIdentity,
    WorktreeAbandonmentError,
    capture_lock_identity,
    detach_registered_worktree,
    quarantine_path,
    remove_stable_zero_byte_lock,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform the validated action")
    parser.add_argument(
        "--receipt-root",
        type=Path,
        default=Path(
            os.environ.get(
                "LIMEN_WORKTREE_ABANDONMENT_RECEIPTS",
                str(ROOT / "logs" / "worktree-abandonment"),
            )
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    detach = subparsers.add_parser("detach")
    detach.add_argument("--superproject", type=Path, required=True)
    detach.add_argument("--target", type=Path, required=True)
    detach.add_argument("--reason", required=True)

    quarantine = subparsers.add_parser("quarantine")
    quarantine.add_argument("--source", type=Path, required=True)
    quarantine.add_argument("--quarantine-root", type=Path, required=True)
    quarantine.add_argument("--destination-name")
    quarantine.add_argument("--reason", required=True)

    lock = subparsers.add_parser("stable-lock")
    lock.add_argument("--path", type=Path, required=True)
    lock.add_argument("--reason", required=True)
    lock.add_argument("--expected-device", type=int)
    lock.add_argument("--expected-inode", type=int)
    lock.add_argument("--expected-size", type=int)
    lock.add_argument("--expected-mtime-ns", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.apply:
        payload: dict[str, object] = {
            "mode": "plan",
            "command": args.command,
            "apply": False,
        }
        if args.command == "stable-lock":
            payload["identity"] = asdict(capture_lock_identity(args.path))
        else:
            payload["target"] = str(args.target if args.command == "detach" else args.source)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    try:
        if args.command == "detach":
            result = detach_registered_worktree(
                args.superproject,
                args.target,
                reason=args.reason,
                receipt_root=args.receipt_root,
            )
        elif args.command == "quarantine":
            result = quarantine_path(
                args.source,
                args.quarantine_root,
                reason=args.reason,
                receipt_root=args.receipt_root,
                destination_name=args.destination_name,
            )
        else:
            required = (
                args.expected_device,
                args.expected_inode,
                args.expected_size,
                args.expected_mtime_ns,
            )
            if any(value is None for value in required):
                _parser().error("stable-lock --apply requires every --expected-* identity field")
            expected = LockIdentity(
                path=str(args.path.parent.resolve(strict=True) / args.path.name),
                device=args.expected_device,
                inode=args.expected_inode,
                size=args.expected_size,
                mtime_ns=args.expected_mtime_ns,
            )
            result = remove_stable_zero_byte_lock(
                args.path,
                expected,
                reason=args.reason,
                receipt_root=args.receipt_root,
            )
    except (OSError, ValueError, WorktreeAbandonmentError) as exc:
        print(json.dumps({"mode": "apply", "ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({"mode": "apply", "ok": True, "receipt": result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
