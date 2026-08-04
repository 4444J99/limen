#!/usr/bin/env python3
"""Capture and optionally retire mutable agent state after dual restoration."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from limen.agent_state.custody import run_custody_verification_campaign
from limen.agent_state.pipeline import RETIREMENT_AUTHORIZATION_REQUIRED, run_opencode_campaign
from limen.agent_state.tree import plan_cloud_materializations, plan_exact_retention, plan_retention
from limen.agent_state.tree_pipeline import (
    run_cloudkit_materialization_campaign,
    run_cold_tree_campaign,
    run_restore_cloudkit_item_campaign,
    run_resume_cloudkit_materialization_campaign,
    run_resume_cold_tree_campaign,
)

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
        help="reserved for a separately authorized canonical-custody retirement workflow",
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
    tree.add_argument("--hot-days", type=int)
    tree.add_argument("--maximum-hot-gib", type=float)
    tree.add_argument(
        "--capture-all",
        action="store_true",
        help="capture every regular file without an age or size retention heuristic",
    )
    tree.add_argument(
        "--retain-relative",
        action="append",
        default=[],
        help=(
            "retain this exact regular file and capture every other file; repeat as needed; "
            "cannot be combined with age or size retention"
        ),
    )
    tree.add_argument("--run-id")
    tree.add_argument("--resume", action="store_true")
    tree.add_argument(
        "--retire",
        action="store_true",
        help="reserved for a separately authorized canonical-custody retirement workflow",
    )
    cloudkit = subcommands.add_parser(
        "cloudkit-materialized",
        help="capture only materialized iCloud files and optionally evict them through File Provider",
    )
    cloudkit.add_argument("name")
    cloudkit.add_argument("--root", type=Path, required=True)
    cloudkit.add_argument(
        "--vault-root",
        type=Path,
        default=Path("/Volumes/Archive4T/limen-private/arca-vault"),
    )
    cloudkit.add_argument(
        "--external-root",
        type=Path,
        default=Path("/Volumes/Archive4T/limen-private/agent-state-exact"),
    )
    cloudkit.add_argument("--private-receipt", type=Path, required=True)
    cloudkit.add_argument("--run-id")
    cloudkit.add_argument("--resume", action="store_true")
    cloudkit.add_argument("--evict", action="store_true")
    cloudkit.add_argument("--eviction-progress", type=Path)
    cloudkit.add_argument(
        "--prepare-eviction-authorization",
        type=Path,
        help="write one path-free Domus authorization request for the next batch",
    )
    cloudkit.add_argument(
        "--prepare-eviction-campaign-authorization",
        type=Path,
        help="write one path-free Domus authorization request for the immutable corpus",
    )
    cloudkit.add_argument("--eviction-authorizer")
    cloudkit.add_argument("--eviction-authorization", type=Path)
    cloudkit.add_argument("--eviction-signature", type=Path)
    cloudkit.add_argument(
        "--restore-item-hash",
        help="restore exactly one missing captured item by its path-free File Provider hash",
    )
    cloudkit.add_argument(
        "--restore-captured-path-hash",
        help="restore exactly one missing item by its domain-separated captured-path hash",
    )
    cloudkit.add_argument(
        "--restore-captured-name-hash",
        help="restore one uniquely named captured item by its domain-separated basename hash",
    )
    cloudkit.add_argument("--restore-receipt", type=Path)
    cloudkit.add_argument(
        "--apply",
        action="store_true",
        help="explicitly apply the requested one-item restoration after all custody gates pass",
    )
    custody = subcommands.add_parser(
        "custody-receipt",
        help="independently restore both copies and emit the path-free custody contract",
    )
    custody.add_argument("name")
    custody.add_argument("--metabolism-receipt", type=Path, required=True)
    custody.add_argument("--vault-root", type=Path, required=True)
    custody.add_argument("--external-root", type=Path, required=True)
    custody.add_argument("--repository", default="organvm/arca")
    custody.add_argument("--key-service", default="limen-arca-vault")
    custody.add_argument("--output", type=Path, required=True)
    return command


def main(argv: list[str] | None = None) -> int:
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    if getattr(args, "resume", False) and not args.run_id:
        argument_parser.error("--resume requires --run-id")
    if args.command in {"opencode", "cold-tree"} and args.retire:
        argument_parser.error(RETIREMENT_AUTHORIZATION_REQUIRED)
    if (
        args.command == "cold-tree"
        and args.retain_relative
        and (args.hot_days is not None or args.maximum_hot_gib is not None)
    ):
        argument_parser.error("--retain-relative cannot be combined with --hot-days or --maximum-hot-gib")
    if (
        args.command == "cold-tree"
        and args.capture_all
        and (args.retain_relative or args.hot_days is not None or args.maximum_hot_gib is not None)
    ):
        argument_parser.error(
            "--capture-all cannot be combined with --retain-relative, --hot-days, or --maximum-hot-gib"
        )
    if args.command == "cloudkit-materialized":
        restore_selectors = sum(
            bool(value)
            for value in (
                args.restore_item_hash,
                args.restore_captured_path_hash,
                args.restore_captured_name_hash,
            )
        )
        if restore_selectors > 1:
            argument_parser.error("choose exactly one item restoration selector")
        if bool(restore_selectors) != bool(args.restore_receipt):
            argument_parser.error("one item restoration selector and --restore-receipt are required together")
        if restore_selectors and not args.resume:
            argument_parser.error("item restoration requires --resume")
        if restore_selectors and not args.apply:
            argument_parser.error("item restoration requires explicit --apply")
        if args.apply and not restore_selectors:
            argument_parser.error("--apply is only valid with one item restoration selector")
        if restore_selectors and (
            args.evict
            or args.prepare_eviction_authorization
            or args.prepare_eviction_campaign_authorization
            or args.eviction_authorization
            or args.eviction_signature
            or args.eviction_progress
        ):
            argument_parser.error("item restoration cannot be combined with eviction operations")
        if args.prepare_eviction_authorization and args.prepare_eviction_campaign_authorization:
            argument_parser.error("choose one eviction authorization planning mode")
        if (args.prepare_eviction_authorization or args.prepare_eviction_campaign_authorization) and args.evict:
            argument_parser.error("authorization planning and --evict are separate operations")
        if (
            args.prepare_eviction_authorization or args.prepare_eviction_campaign_authorization
        ) and not args.eviction_authorizer:
            argument_parser.error("eviction authorization planning requires --eviction-authorizer")
        if args.evict and (not args.eviction_authorization or not args.eviction_signature):
            argument_parser.error("--evict requires --eviction-authorization and --eviction-signature")
        if not args.evict and (args.eviction_authorization or args.eviction_signature):
            argument_parser.error("signed eviction inputs require --evict")
    if args.command == "custody-receipt":
        metabolism, projected, metabolism_changed, custody_changed = run_custody_verification_campaign(
            args.name,
            args.metabolism_receipt,
            args.vault_root,
            args.external_root,
            args.output,
            repository=args.repository,
            key_service=args.key_service,
        )
        print(
            json.dumps(
                {
                    "schema": projected.schema_version,
                    "custody_id": projected.custody_id,
                    "restoration_count": len(projected.restoration_proofs),
                    "source_retired": metabolism.source_retired,
                    "metabolism_changed": metabolism_changed,
                    "changed": custody_changed,
                },
                sort_keys=True,
            )
        )
        return 0
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
        if args.capture_all:
            plan = plan_exact_retention(args.root, retain_paths=())
        elif args.retain_relative:
            plan = plan_exact_retention(args.root, retain_paths=tuple(args.retain_relative))
        else:
            plan = plan_retention(
                args.root,
                hot_days=args.hot_days if args.hot_days is not None else 7,
                maximum_hot_bytes=int(
                    (args.maximum_hot_gib if args.maximum_hot_gib is not None else 2.0) * 1024 * 1024 * 1024
                ),
            )
        if args.resume:
            receipt = run_resume_cold_tree_campaign(
                args.name,
                plan,
                args.vault_root,
                args.external_root,
                args.private_receipt,
                retire=args.retire,
                run_id=args.run_id,
            )
        else:
            receipt = run_cold_tree_campaign(
                args.name,
                plan,
                args.vault_root,
                args.external_root,
                args.private_receipt,
                retire=args.retire,
                run_id=args.run_id,
            )
    elif args.command == "cloudkit-materialized":
        if args.restore_item_hash or args.restore_captured_path_hash or args.restore_captured_name_hash:
            restore = run_restore_cloudkit_item_campaign(
                args.name,
                args.root,
                args.vault_root,
                args.external_root,
                args.private_receipt,
                args.restore_receipt,
                run_id=args.run_id,
                item_hash=args.restore_item_hash,
                captured_path_hash=args.restore_captured_path_hash,
                captured_name_hash=args.restore_captured_name_hash,
            )
            print(json.dumps(restore, sort_keys=True))
            return 0
        if args.resume:
            receipt = run_resume_cloudkit_materialization_campaign(
                args.name,
                args.root,
                args.vault_root,
                args.external_root,
                args.private_receipt,
                evict=args.evict,
                run_id=args.run_id,
                progress_path=args.eviction_progress,
                prepare_authorization=args.prepare_eviction_authorization,
                prepare_campaign_authorization=args.prepare_eviction_campaign_authorization,
                authorization_principal=args.eviction_authorizer,
                authorization_receipt=args.eviction_authorization,
                authorization_signature=args.eviction_signature,
            )
        else:
            plan = plan_cloud_materializations(args.root)
            receipt = run_cloudkit_materialization_campaign(
                args.name,
                plan,
                args.vault_root,
                args.external_root,
                args.private_receipt,
                evict=args.evict,
                run_id=args.run_id,
                progress_path=args.eviction_progress,
                prepare_authorization=args.prepare_eviction_authorization,
                prepare_campaign_authorization=args.prepare_eviction_campaign_authorization,
                authorization_principal=args.eviction_authorizer,
                authorization_receipt=args.eviction_authorization,
                authorization_signature=args.eviction_signature,
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
