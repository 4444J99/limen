#!/usr/bin/env python3
"""Capture and optionally retire mutable agent state after dual restoration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from limen.agent_state.pipeline import run_opencode_campaign
from limen.agent_state.tree import plan_retention
from limen.agent_state.tree_pipeline import run_cold_tree_campaign

HOME = Path.home()
LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", HOME / "Workspace" / "limen")).expanduser()


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    subcommands = command.add_subparsers(dest="command", required=True)
    opencode = subcommands.add_parser("opencode", help="capture the OpenCode SQLite store")
    opencode.add_argument(
        "--source",
        type=Path,
        default=HOME / ".local" / "share" / "opencode" / "opencode.db",
    )
    opencode.add_argument(
        "--vault-root",
        type=Path,
        default=Path("/Volumes/Archive4T/limen-private/arca-vault"),
    )
    opencode.add_argument(
        "--external-root",
        type=Path,
        default=Path("/Volumes/Archive4T/limen-private/agent-state-exact"),
    )
    opencode.add_argument(
        "--private-receipt",
        type=Path,
        default=LIMEN_ROOT / ".limen-private" / "session-corpus" / "lifecycle" / "agent-state" / "opencode.json",
    )
    opencode.add_argument("--run-id")
    opencode.add_argument(
        "--retire",
        action="store_true",
        help="replace the source only after every custody and restoration gate passes",
    )
    tree = subcommands.add_parser("cold-tree", help="capture a bounded cold file set")
    tree.add_argument("name")
    tree.add_argument("--root", type=Path, required=True)
    tree.add_argument(
        "--vault-root",
        type=Path,
        default=Path("/Volumes/Archive4T/limen-private/arca-vault"),
    )
    tree.add_argument(
        "--external-root",
        type=Path,
        default=Path("/Volumes/Archive4T/limen-private/agent-state-exact"),
    )
    tree.add_argument("--private-receipt", type=Path, required=True)
    tree.add_argument("--hot-days", type=int, default=7)
    tree.add_argument("--maximum-hot-gib", type=float, default=2.0)
    tree.add_argument("--run-id")
    tree.add_argument("--retire", action="store_true")
    return command


def main() -> int:
    args = parser().parse_args()
    if args.command == "opencode":
        receipt = run_opencode_campaign(
            args.source,
            args.vault_root,
            args.external_root,
            args.private_receipt,
            retire=args.retire,
            run_id=args.run_id,
        )
    elif args.command == "cold-tree":
        plan = plan_retention(
            args.root,
            hot_days=args.hot_days,
            maximum_hot_bytes=int(args.maximum_hot_gib * 1024 * 1024 * 1024),
        )
        receipt = run_cold_tree_campaign(
            args.name,
            plan,
            args.vault_root,
            args.external_root,
            args.private_receipt,
            retire=args.retire,
            run_id=args.run_id,
        )
    else:
        raise AssertionError(args.command)
    print(
        json.dumps(
            {
                "schema": receipt.schema,
                "run_id": receipt.run_id,
                "atom_count": receipt.atom_count,
                "duplicate_payloads": receipt.duplicate_payloads,
                "git_commit": receipt.git_commit,
                "git_receipt_commit": receipt.git_receipt_commit,
                "restorations": {proof.scope: proof.passed for proof in receipt.restorations},
                "source_retired": receipt.source_retired,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
