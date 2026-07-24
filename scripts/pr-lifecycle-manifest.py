#!/usr/bin/env python3
"""Plan and apply exact-head PR lifecycle labels through a reviewed manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LIFECYCLE_LABELS = frozenset(
    {
        "lifecycle:delivery",
        "lifecycle:preservation",
        "lifecycle:active-human",
        "lifecycle:blocked",
        "lifecycle:superseded",
    }
)
SCHEMA = "limen.pr_lifecycle_manifest.v2"


class ManifestError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _run_gh(args: list[str]) -> str:
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        raise ManifestError(result.stderr.strip() or "gh command failed")
    return result.stdout


def fetch_open_prs(repository: str) -> list[dict[str, Any]]:
    output = _run_gh(
        [
            "pr",
            "list",
            "--repo",
            repository,
            "--state",
            "open",
            "--limit",
            "1000",
            "--json",
            "number,headRefOid,title,isDraft,labels,url",
        ]
    )
    decoded = json.loads(output)
    if not isinstance(decoded, list):
        raise ManifestError("GitHub PR response is not a list")
    return decoded


def lifecycle_labels(row: dict[str, Any]) -> set[str]:
    labels = row.get("labels") or []
    return {
        str(item.get("name") or "")
        for item in labels
        if isinstance(item, dict) and str(item.get("name") or "") in LIFECYCLE_LABELS
    }


def _plan_core(repository: str, disposition: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "repository": repository,
        "effect": f"add-label:{disposition}",
        "disposition": disposition,
        "items": items,
    }


def build_plan(
    repository: str,
    disposition: str,
    rows: list[dict[str, Any]],
    *,
    review_basis: str,
) -> dict[str, Any]:
    if disposition not in LIFECYCLE_LABELS:
        raise ManifestError(f"unsupported lifecycle disposition: {disposition}")
    items = [
        {
            "number": int(row["number"]),
            "head_oid": str(row["headRefOid"]),
            "title": str(row["title"]),
            "draft": bool(row["isDraft"]),
            "url": str(row["url"]),
        }
        for row in rows
        if not lifecycle_labels(row)
    ]
    items.sort(key=lambda item: int(item["number"]))
    core = _plan_core(repository, disposition, items)
    return {
        **core,
        "generated_at": _now(),
        "review_basis": review_basis,
        "plan_sha256": _canonical_hash(core),
        "status": "planned",
    }


def validate_manifest(manifest: dict[str, Any], expected_sha: str) -> None:
    if manifest.get("schema") != SCHEMA:
        raise ManifestError("unsupported manifest schema")
    disposition = str(manifest.get("disposition") or "")
    items = manifest.get("items")
    if disposition not in LIFECYCLE_LABELS or not isinstance(items, list):
        raise ManifestError("invalid manifest disposition or items")
    core = _plan_core(str(manifest.get("repository") or ""), disposition, items)
    actual = _canonical_hash(core)
    if actual != manifest.get("plan_sha256") or actual != expected_sha:
        raise ManifestError("manifest digest does not match --expected-plan-sha")


def _preflight(manifest: dict[str, Any], rows: list[dict[str, Any]]) -> list[int]:
    by_number = {int(row["number"]): row for row in rows}
    disposition = str(manifest["disposition"])
    pending: list[int] = []
    for item in manifest["items"]:
        number = int(item["number"])
        current = by_number.get(number)
        if current is None:
            raise ManifestError(f"PR #{number} is no longer open")
        if str(current.get("headRefOid") or "") != item["head_oid"]:
            raise ManifestError(f"PR #{number} exact head drifted")
        labels = lifecycle_labels(current)
        if labels == {disposition}:
            continue
        if labels:
            raise ManifestError(f"PR #{number} lifecycle label drifted: {sorted(labels)}")
        pending.append(number)
    return pending


def apply_manifest(manifest: dict[str, Any], expected_sha: str) -> dict[str, Any]:
    validate_manifest(manifest, expected_sha)
    repository = str(manifest["repository"])
    disposition = str(manifest["disposition"])
    pending = _preflight(manifest, fetch_open_prs(repository))
    for number in pending:
        _run_gh(
            [
                "pr",
                "edit",
                str(number),
                "--repo",
                repository,
                "--add-label",
                disposition,
            ]
        )
    residual = _preflight(manifest, fetch_open_prs(repository))
    if residual:
        raise ManifestError(f"post-apply verification missing labels: {residual}")
    return {
        **manifest,
        "status": "applied_verified",
        "apply_receipt": {
            "applied_at": _now(),
            "effect_count": len(pending),
            "verified_count": len(manifest["items"]),
            "merge_effects": 0,
            "close_effects": 0,
            "postcondition": "Every manifest PR remains open at its exact planned head with exactly the reviewed lifecycle label.",
        },
    }


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--repo")
    parser.add_argument("--disposition", choices=sorted(LIFECYCLE_LABELS))
    parser.add_argument("--review-basis")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-plan-sha")
    args = parser.parse_args(argv)
    try:
        if args.plan:
            if not args.repo or not args.disposition or not args.review_basis:
                raise ManifestError("--plan requires --repo, --disposition, and --review-basis")
            payload = build_plan(
                args.repo,
                args.disposition,
                fetch_open_prs(args.repo),
                review_basis=args.review_basis,
            )
        else:
            if not args.expected_plan_sha:
                raise ManifestError("--apply requires --expected-plan-sha")
            payload = json.loads(args.manifest.read_text())
            payload = apply_manifest(payload, args.expected_plan_sha)
        _write(args.manifest, payload)
        print(
            json.dumps(
                {"status": payload["status"], "plan_sha256": payload["plan_sha256"], "items": len(payload["items"])}
            )
        )
        return 0
    except (OSError, ValueError, json.JSONDecodeError, ManifestError) as exc:
        print(f"pr-lifecycle-manifest: BLOCKED — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
