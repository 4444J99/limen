#!/usr/bin/env python3
"""Digest-gated lifecycle typing across the complete GitHub PR estate."""

from __future__ import annotations

import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BASE_SCRIPT = ROOT / "scripts" / "pr-lifecycle-manifest.py"
SCHEMA = "limen.pr_lifecycle_estate_manifest.v1"
PUBLIC_RECEIPT_SCHEMA = "limen.pr_lifecycle_estate_receipt.v1"
DISPOSITION = "lifecycle:blocked"


def _load_base():
    loader = importlib.machinery.SourceFileLoader("pr_lifecycle_manifest_base", str(BASE_SCRIPT))
    spec = importlib.util.spec_from_loader("pr_lifecycle_manifest_base", loader)
    if spec is None:
        raise RuntimeError("cannot load PR lifecycle manifest base")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


BASE = _load_base()
ManifestError = BASE.ManifestError


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _core(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "scope": "complete-github-estate",
        "effect": f"add-label:{DISPOSITION}",
        "disposition": DISPOSITION,
        "items": items,
    }


def build_plan(ledger: dict[str, Any], *, review_basis: str) -> dict[str, Any]:
    reconciliation = ledger.get("cursor_reconciliation") or {}
    failure_count = reconciliation.get("failure_count")
    if failure_count is None:
        failure_count = len(reconciliation.get("failures") or [])
    if not ledger.get("exhaustive") or int(failure_count):
        raise ManifestError("PR-debt ledger is not exhaustive")
    items = [
        {
            "repository": str(row["repository"]),
            "number": int(row["number"]),
            "head_oid": str(row["head_oid"]),
            "private": bool(row.get("private")),
            "pr_key": str(
                row.get("pr_key") or hashlib.sha256(f"{row['repository']}#{int(row['number'])}".encode()).hexdigest()
            ),
            "title": str(row["title"]),
            "draft": bool(row["draft"]),
            "url": str(row["url"]),
        }
        for row in ledger.get("pull_requests") or []
        if not row.get("lifecycle_disposition") and row.get("repository") and row.get("number") and row.get("head_oid")
    ]
    items.sort(key=lambda item: (item["repository"], int(item["number"])))
    core = _core(items)
    return {
        **core,
        "generated_at": _now(),
        "review_basis": review_basis,
        "source_ledger_content_sha256": ledger.get("content_sha256"),
        "source_open_pr_count": int(ledger.get("open_pr_count") or 0),
        "source_lifecycle_untyped_count": int(ledger.get("lifecycle_untyped_count") or 0),
        "repository_count": len({item["repository"] for item in items}),
        "plan_sha256": _hash(core),
        "status": "planned",
    }


def validate(plan: dict[str, Any], expected_sha: str) -> None:
    if plan.get("schema") != SCHEMA or plan.get("disposition") != DISPOSITION:
        raise ManifestError("unsupported estate manifest")
    items = plan.get("items")
    if not isinstance(items, list):
        raise ManifestError("estate manifest items are invalid")
    digest = _hash(_core(items))
    if digest != plan.get("plan_sha256") or digest != expected_sha:
        raise ManifestError("estate manifest digest does not match --expected-plan-sha")


def _group(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[str(item["repository"])].append(item)
    return dict(grouped)


def _preflight_repo(repository: str, items: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[int]:
    current = {int(row["number"]): row for row in rows}
    pending = []
    for item in items:
        number = int(item["number"])
        row = current.get(number)
        if row is None:
            raise ManifestError(f"{repository}#{number} is no longer open")
        if str(row.get("headRefOid") or "") != item["head_oid"]:
            raise ManifestError(f"{repository}#{number} exact head drifted")
        labels = BASE.lifecycle_labels(row)
        if labels == {DISPOSITION}:
            continue
        if labels:
            raise ManifestError(f"{repository}#{number} lifecycle label drifted: {sorted(labels)}")
        pending.append(number)
    return pending


def _ensure_label(repository: str) -> None:
    labels = json.loads(BASE._run_gh(["label", "list", "--repo", repository, "--limit", "1000", "--json", "name"]))
    if any(isinstance(row, dict) and row.get("name") == DISPOSITION for row in labels):
        return
    BASE._run_gh(
        [
            "label",
            "create",
            DISPOSITION,
            "--repo",
            repository,
            "--color",
            "d4a72c",
            "--description",
            "Fail-closed pending explicit lifecycle review",
        ]
    )


def _repo_is_archived(repository: str) -> bool:
    payload = json.loads(BASE._run_gh(["repo", "view", repository, "--json", "isArchived"]))
    return bool(payload.get("isArchived"))


def apply_plan(plan: dict[str, Any], expected_sha: str) -> dict[str, Any]:
    validate(plan, expected_sha)
    grouped = _group(plan["items"])
    pending: dict[str, list[int]] = {}
    for repository, items in grouped.items():
        pending[repository] = _preflight_repo(repository, items, BASE.fetch_open_prs(repository))
    archived = {repository for repository in sorted(grouped) if _repo_is_archived(repository)}
    mutable = set(grouped) - archived
    for repository in sorted(mutable):
        _ensure_label(repository)
    effect_count = 0
    for repository in sorted(mutable):
        for number in pending[repository]:
            BASE._run_gh(["pr", "edit", str(number), "--repo", repository, "--add-label", DISPOSITION])
            effect_count += 1
    for repository in sorted(mutable):
        items = grouped[repository]
        residual = _preflight_repo(repository, items, BASE.fetch_open_prs(repository))
        if residual:
            raise ManifestError(f"{repository} post-apply labels missing: {residual}")
    for repository in sorted(archived):
        if not _repo_is_archived(repository):
            raise ManifestError(f"{repository} archived status drifted")
        _preflight_repo(repository, grouped[repository], BASE.fetch_open_prs(repository))
    immutable_item_count = sum(len(grouped[repository]) for repository in archived)
    return {
        **plan,
        "status": ("applied_verified_with_immutable_residual" if archived else "applied_verified"),
        "apply_receipt": {
            "applied_at": _now(),
            "effect_count": effect_count,
            "verified_count": len(plan["items"]) - immutable_item_count,
            "repository_count": len(grouped),
            "immutable_archived_repository_count": len(archived),
            "immutable_archived_item_count": immutable_item_count,
            "immutable_archived_repository_hashes": sorted(
                hashlib.sha256(repository.encode()).hexdigest() for repository in archived
            ),
            "merge_effects": 0,
            "close_effects": 0,
        },
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def public_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    items = payload["items"]
    private_items = [item for item in items if item.get("private")]
    public_items = [item for item in items if not item.get("private")]
    private_repository_hashes = sorted(
        {hashlib.sha256(str(item["repository"]).encode()).hexdigest() for item in private_items}
    )
    return {
        "schema": PUBLIC_RECEIPT_SCHEMA,
        "status": payload["status"],
        "disposition": payload["disposition"],
        "plan_sha256": payload["plan_sha256"],
        "source_ledger_content_sha256": payload.get("source_ledger_content_sha256"),
        "source_open_pr_count": payload.get("source_open_pr_count"),
        "source_lifecycle_untyped_count": payload.get("source_lifecycle_untyped_count"),
        "item_count": len(items),
        "public_item_count": len(public_items),
        "private_item_count": len(private_items),
        "repository_count": payload["repository_count"],
        "private_repository_count": len(private_repository_hashes),
        "private_repository_hashes": private_repository_hashes,
        "private_pr_keys": sorted(item["pr_key"] for item in private_items),
        "effect": payload["effect"],
        "review_basis": payload["review_basis"],
        "apply_receipt": payload.get("apply_receipt"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review-basis")
    parser.add_argument("--expected-plan-sha")
    parser.add_argument("--public-receipt", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.plan:
            if args.ledger is None or not args.review_basis:
                raise ManifestError("--plan requires --ledger and --review-basis")
            payload = build_plan(json.loads(args.ledger.read_text()), review_basis=args.review_basis)
        else:
            if not args.expected_plan_sha:
                raise ManifestError("--apply requires --expected-plan-sha")
            payload = apply_plan(json.loads(args.manifest.read_text()), args.expected_plan_sha)
        _write(args.manifest, payload)
        if args.public_receipt:
            _write(args.public_receipt, public_receipt(payload))
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "plan_sha256": payload["plan_sha256"],
                    "items": len(payload["items"]),
                    "repositories": payload["repository_count"],
                }
            )
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError, ManifestError) as exc:
        print(f"pr-lifecycle-estate-manifest: BLOCKED — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
