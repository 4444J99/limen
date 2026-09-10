#!/usr/bin/env python3
"""Validate branch-family ownership and generated branch documentation."""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio/governance/branch-families.yaml"
DOCUMENT = ROOT / "BRANCHES.md"
DERIVER = ROOT / "scripts/derive-branches.py"


def branches(remote: bool) -> list[str]:
    prefix = "refs/remotes/origin" if remote else "refs/heads"
    result = subprocess.run(
        ["git", "-C", str(ROOT), "for-each-ref", "--format=%(refname:strip=3)", prefix],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line and line != "HEAD"]


def pull_request_branches(repository: str) -> set[str]:
    result = subprocess.run(
        ["gh", "pr", "list", "--repo", repository, "--state", "all", "--limit", "1000", "--json", "headRefName"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = yaml.safe_load(result.stdout)
    if not isinstance(payload, list):
        raise ValueError("GitHub pull-request branch response is not a list")
    return {
        row["headRefName"]
        for row in payload
        if isinstance(row, dict) and isinstance(row.get("headRefName"), str) and row["headRefName"]
    }


def expected_document(registry: dict) -> str:
    spec = importlib.util.spec_from_file_location("derive_branches", DERIVER)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load branch-document deriver")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.render(registry)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote", action="store_true", help="check locally known origin branches")
    parser.add_argument("--branch", action="append", default=[], help="check an explicit branch name")
    args = parser.parse_args()
    try:
        registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
        if registry.get("schema_version") != 1 or registry.get("repository") != "4444J99/limen":
            raise ValueError("invalid branch-family registry header")
        families = registry.get("families")
        if not isinstance(families, list) or not families:
            raise ValueError("families must be a non-empty list")
        patterns = []
        names = set()
        for row in families:
            if not isinstance(row, dict) or set(row) != {"name", "match", "owner", "intent", "receipt"}:
                raise ValueError("every family must declare name, match, owner, intent, and receipt")
            if not all(isinstance(row[key], str) and row[key] for key in row):
                raise ValueError(f"invalid family row: {row!r}")
            if row["name"] in names:
                raise ValueError(f"duplicate family name: {row['name']}")
            names.add(row["name"])
            patterns.append((row["name"], re.compile(row["match"])))
        receipts = registry.get("unintegrated_branch_receipts")
        if not isinstance(receipts, list):
            raise ValueError("unintegrated_branch_receipts must be a list")
        receipt_branches = set()
        for receipt in receipts:
            if not isinstance(receipt, dict) or set(receipt) != {"branch", "family", "owner_issue"}:
                raise ValueError("every unintegrated branch receipt must declare branch, family, and owner_issue")
            branch = receipt["branch"]
            family = receipt["family"]
            owner_issue = receipt["owner_issue"]
            if not isinstance(branch, str) or not isinstance(family, str) or not isinstance(owner_issue, int) or owner_issue < 1:
                raise ValueError(f"invalid unintegrated branch receipt: {receipt!r}")
            if branch in receipt_branches:
                raise ValueError(f"duplicate unintegrated branch receipt: {branch}")
            receipt_branches.add(branch)
            expected = [name for name, pattern in patterns if pattern.fullmatch(branch)]
            if expected != [family]:
                raise ValueError(f"{branch}: receipt family {family!r} does not match its owning family {expected}")
        if DOCUMENT.read_text(encoding="utf-8") != expected_document(registry):
            raise ValueError("BRANCHES.md drifted; run python3 scripts/derive-branches.py")
        candidates = args.branch or branches(args.remote)
        for branch in candidates:
            matches = [name for name, pattern in patterns if pattern.fullmatch(branch)]
            if len(matches) != 1:
                raise ValueError(f"{branch}: expected exactly one owning family, found {matches}")
        if args.remote:
            # A non-trunk branch not represented by a pull request is still work:
            # this receipt list binds each known unintegrated branch to an issue.
            unintegrated = set(candidates) - {"main"} - pull_request_branches(str(registry["repository"]))
            missing = unintegrated - receipt_branches
            stale = receipt_branches - set(candidates)
            if missing:
                raise ValueError(f"unintegrated branches lack owner receipts: {sorted(missing)}")
            if stale:
                raise ValueError(f"unintegrated branch receipts no longer name remote branches: {sorted(stale)}")
        print(f"branch-family governance passed: {len(candidates)} branch(es), {len(families)} family row(s)")
        return 0
    except (OSError, ValueError, yaml.YAMLError, subprocess.CalledProcessError, re.error) as exc:
        print(f"check-branch-families: FAIL — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
