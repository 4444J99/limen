#!/usr/bin/env python3
"""Render quarantined copies of generated public positioning surfaces.

This is a staging-only effector: it never writes the source tree, deploys, or publishes.
The generator integration seam is a manifest plus bounded claim markers:
``<!-- positioning-claim: <id>:start -->`` / ``:end``.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


MANIFEST_SCHEMA = "limen.positioning.public-surface-manifest.v1"
REPORT_SCHEMA = "limen.positioning.claim-policy-report.v1"
class QuarantineError(ValueError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QuarantineError(f"cannot read JSON input: {exc}") from exc
    if not isinstance(document, dict):
        raise QuarantineError("JSON input must be an object")
    return document


def _relative_path(value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise QuarantineError(f"{label} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise QuarantineError(f"{label} must stay beneath the declared source root")
    return path


def _rejected_ids(report: dict[str, Any]) -> set[str]:
    if report.get("schema_version") != REPORT_SCHEMA:
        raise QuarantineError(f"policy report must use {REPORT_SCHEMA}")
    rejected = report.get("rejected_claims")
    if not isinstance(rejected, list) or not rejected:
        raise QuarantineError("policy report must contain at least one rejected claim")
    ids: set[str] = set()
    for row in rejected:
        if not isinstance(row, dict) or not isinstance(row.get("claim_id"), str):
            raise QuarantineError("policy report rejected_claims must expose public-safe ids")
        ids.add(row["claim_id"])
    return ids


def quarantine(source_root: Path, output_root: Path, manifest: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise QuarantineError(f"surface manifest must use {MANIFEST_SCHEMA}")
    surfaces = manifest.get("surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        raise QuarantineError("surface manifest must declare at least one public surface")
    rejected_ids = _rejected_ids(report)
    if output_root.exists():
        raise QuarantineError("output root already exists; quarantine requires a fresh staging directory")

    affected = 0
    copied = 0
    for index, surface in enumerate(surfaces):
        if not isinstance(surface, dict):
            raise QuarantineError(f"surfaces[{index}] must be an object")
        path = _relative_path(surface.get("path"), f"surfaces[{index}].path")
        claim_ids = surface.get("claim_ids")
        if not isinstance(claim_ids, list) or not all(isinstance(item, str) for item in claim_ids):
            raise QuarantineError(f"surfaces[{index}].claim_ids must be a list of identifiers")
        source = source_root / path
        if not source.is_file():
            raise QuarantineError(f"declared public surface is missing: {path}")
        rendered = source.read_text(encoding="utf-8")
        linked = rejected_ids.intersection(claim_ids)
        for claim_id in sorted(linked):
            pattern = re.compile(
                rf"<!-- positioning-claim: {re.escape(claim_id)}:start -->(.*?)<!-- positioning-claim: {re.escape(claim_id)}:end -->",
                re.DOTALL,
            )
            rendered, substitutions = pattern.subn(
                f"<!-- positioning-claim: {claim_id}:quarantined -->", rendered
            )
            if substitutions != 1:
                raise QuarantineError(f"surface {path} must carry exactly one bounded marker for {claim_id}")
            affected += 1
        destination = output_root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        copied += 1
    return {
        "schema_version": "limen.positioning.claim-quarantine-report.v1",
        "input_surface_count": copied,
        "affected_surface_count": affected,
        "quarantined_claim_ids": sorted(rejected_ids),
        "publication_effect": "none",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--policy-report", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = quarantine(args.source_root, args.output_root, _read_json(args.manifest), _read_json(args.policy_report))
    except QuarantineError as exc:
        print(f"claim-surface-quarantine: FAIL: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    print(f"claim-surface-quarantine: PASS ({result['affected_surface_count']} affected surface(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
