#!/usr/bin/env python3
"""Hermetic default-branch refusal for the lifecycle PR publisher."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts" / "worktree-pr-receipts.py"
SPEC = importlib.util.spec_from_file_location("worktree_pr_receipts", SOURCE)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)

    def fake_git(cwd: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        del cwd, timeout
        if args == ("rev-parse", "--is-inside-work-tree"):
            return subprocess.CompletedProcess(args, 0, "true\n", "")
        if args == ("status", "--porcelain"):
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:3] == ("fetch", "--prune", "origin"):
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(f"unexpected git call after default-branch detection: {args!r}")

    module.git = fake_git
    module.origin_repo = lambda cwd: "organvm/limen"
    module.current_branch = lambda cwd: "main"
    module.default_branch = lambda cwd, repo: "main"
    module.patch_equivalent_or_merged = lambda cwd, base: (_ for _ in ()).throw(
        AssertionError("default branch reached preservation analysis")
    )
    module.remote_head_exists = lambda cwd, branch: (_ for _ in ()).throw(
        AssertionError("default branch reached remote publication")
    )

    result = module.process_item(
        {
            "name": "default-checkout",
            "path": str(root),
            "reason": "unpushed-commits",
        },
        apply=True,
    )

assert result["action"] == "refused_default_branch", result
assert result["branch"] == result["base"] == "main", result
print("PASS: lifecycle receipt publisher refuses the repository default branch before any push")


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    receipt_path = root / "worktree-preservation-receipts.json"
    receipt_path.write_text('{"receipts": []}\n', encoding="utf-8")
    module.PRESERVATION_RECEIPTS = receipt_path
    module.pr_view = lambda cwd, repo, number_or_url: {
        "number": 42,
        "state": "OPEN",
        "isDraft": True,
        "headRefName": "work/idempotent-receipt",
        "headRefOid": "a" * 40,
        "url": "https://github.com/organvm/limen/pull/42",
    }

    rows = [
        {
            "action": "pr_exists",
            "branch": "work/idempotent-receipt",
            "name": "idempotent-receipt",
            "path": str(root),
            "pr": {
                "state": "OPEN",
                "url": "https://github.com/organvm/limen/pull/42",
            },
            "repo": "organvm/limen",
            "url": "https://github.com/organvm/limen/pull/42",
        }
    ]

    first = module.update_preservation_receipts(rows, apply=True)
    first_bytes = receipt_path.read_bytes()
    first_data = json.loads(first_bytes)
    first_timestamp = first_data["receipts"][0]["evidence_updated_utc"]
    second = module.update_preservation_receipts(rows, apply=True)
    second_bytes = receipt_path.read_bytes()
    second_data = json.loads(second_bytes)

assert first == {"updated": 1, "dry_run": False}, first
assert second == {"updated": 0, "dry_run": False}, second
assert second_bytes == first_bytes
assert second_data["receipts"][0]["evidence_updated_utc"] == first_timestamp
print("PASS: unchanged preservation evidence is an idempotent apply fixed point")
