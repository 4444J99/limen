#!/usr/bin/env python3
"""Sole exact-tip CAS effector and crash reconciler for remote branch deletion."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.remote_reap import (  # noqa: E402
    apply_capability,
    atomic_json,
    keeper_redemption_path,
    load_model,
    reconcile_effect,
)
from limen.universe_recovery import ReapCapabilityV1, ReapJournalV1, ReapPlanV1  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply or reconcile one remote-ref reap capability")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--reconcile", action="store_true")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--capability", type=Path)
    args = parser.parse_args()
    redemption_path = keeper_redemption_path()
    try:
        current = load_model(args.journal, ReapJournalV1)
        if args.reconcile:
            if args.capability is None:
                parser.error("--reconcile requires --capability")
            reconciled = reconcile_effect(
                repository_root=args.repository_root,
                current=current,
                capability=load_model(args.capability, ReapCapabilityV1),
                redemption_path=redemption_path,
            )
            atomic_json(args.journal, reconciled.model_dump(mode="json"))
            print(f"remote-reap-effect: reconciled state={reconciled.state}")
            return 0 if reconciled.state == "completed" else 1
        if args.plan is None or args.capability is None:
            parser.error("--apply requires --plan and --capability")
        signing_material = os.environ.get(
            "LIMEN_REMOTE_REAP_CAPABILITY_KEY", ""
        )  # allow-secret: runtime env reference only
        if not signing_material:
            raise ValueError("keeper capability key is unavailable")
        result = apply_capability(
            repository_root=args.repository_root,
            plan=load_model(args.plan, ReapPlanV1),
            capability=load_model(args.capability, ReapCapabilityV1),
            journal_path=args.journal,
            redemption_path=redemption_path,
            signing_material=signing_material.encode(),
        )
    except Exception as exc:
        print(f"remote-reap-effect: denied: {exc}", file=sys.stderr)
        return 1
    print(f"remote-reap-effect: completed {result.repository} {result.ref}@{result.expected_tip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
