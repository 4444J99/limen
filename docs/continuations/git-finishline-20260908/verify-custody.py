#!/usr/bin/env python3
"""Verify archived objects independently; do not change refs or restore work files."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True, timeout=90
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stash-bundle", type=Path, required=True)
    parser.add_argument("--board-bundle", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    stashes = json.loads((here / "stash-custody.json").read_text())
    branches = json.loads((here / "branch-custody.json").read_text())
    prs = json.loads((here / "pr-custody.json").read_text())
    if len(stashes["stashes"]) != 26 or len(branches["branches"]) != 9 or len(prs["pull_requests"]) != 9:
        raise ValueError("original custody denominator changed")
    bundles = {
        "original": (args.stash_bundle, stashes["bundle_sha256"]),
        "companion": (args.board_bundle, branches["companion_bundle"]["sha256"]),
    }
    restored_stashes = restored_branches = 0
    for name, (bundle, expected_digest) in bundles.items():
        bundle = bundle.expanduser().resolve(strict=True)
        with bundle.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != expected_digest:
            raise ValueError(f"{name} archive checksum mismatch")
        with tempfile.TemporaryDirectory(prefix="limen-custody-check-") as temporary:
            root = Path(temporary)
            git(root, "init", "--bare", "--quiet")
            git(root, "bundle", "verify", str(bundle))
            git(root, "bundle", "unbundle", str(bundle))
            if (root / "objects/info/alternates").exists():
                raise ValueError("restore must not borrow source objects")
            if name == "original":
                for stash in stashes["stashes"]:
                    commit = stash["commit"]
                    git(root, "cat-file", "-e", f"{commit}^{{commit}}")
                    if git(root, "rev-parse", f"{commit}^{{tree}}") != stash["tree"]:
                        raise ValueError("stash worktree tree mismatch")
                    if git(root, "show", "-s", "--format=%P", commit).split() != stash["parents"]:
                        raise ValueError("stash parent/index/untracked lineage mismatch")
                    if stash["untracked_tree"]:
                        git(root, "cat-file", "-e", f"{stash['untracked_tree']}^{{tree}}")
                    restored_stashes += 1
            for branch in branches["branches"]:
                if branch["archive"] == name:
                    git(root, "cat-file", "-e", f"{branch['tip']}^{{commit}}")
                    restored_branches += 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "independently_restored_stashes": restored_stashes,
                "independently_restored_deleted_tips": restored_branches,
                "original_pr_count": len(prs["pull_requests"]),
                "scope": "archive custody; no claim of deployment, merge, or live runtime health",
            }
        )
    )


if __name__ == "__main__":
    main()
