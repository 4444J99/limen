#!/usr/bin/env python3
"""Proof-gated removal of regenerable dependency caches.

Only ignored ``node_modules`` directories inside Git repositories with a
lockfile are eligible. Check/apply use the same canonical manifest digest;
apply re-scans live process CWDs and the filesystem and fails closed on drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

LOCKFILES = ("pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "bun.lockb")
SCHEMA = "limen.generated_cache_reclaim.v1"


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


def active_cwds() -> set[Path]:
    result = run(["lsof", "-a", "-d", "cwd", "-Fn"])
    if result.returncode not in {0, 1}:
        raise RuntimeError("process-cwd-sensor-unavailable")
    return {Path(line[1:]).resolve() for line in result.stdout.splitlines() if line.startswith("n") and len(line) > 1}


def repo_root(path: Path) -> Path | None:
    result = run(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def directory_size(path: Path) -> int:
    result = run(["du", "-sk", str(path)])
    if result.returncode != 0:
        raise RuntimeError(f"size-sensor-unavailable:{path}")
    return int(result.stdout.split(maxsplit=1)[0]) * 1024


def cache_is_ignored(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return run(["git", "check-ignore", "-q", "--", str(relative)], cwd=root).returncode == 0


def scan(workspace: Path, *, minimum_bytes: int = 1024 * 1024) -> list[dict[str, object]]:
    workspace = workspace.resolve()
    cwds = active_cwds()
    roots: dict[Path, bool] = {}
    candidates: list[dict[str, object]] = []

    for current, directories, _files in os.walk(workspace):
        current_path = Path(current)
        if "node_modules" not in directories:
            continue
        cache = (current_path / "node_modules").resolve()
        directories.remove("node_modules")
        if cache.is_symlink() or not cache.is_dir() or not is_within(cache, workspace):
            continue
        root = repo_root(current_path)
        if root is None or not is_within(cache, root):
            continue
        if root not in roots:
            roots[root] = any(cwd == root or is_within(cwd, root) for cwd in cwds)
        if roots[root] or not any((root / name).is_file() for name in LOCKFILES):
            continue
        if not cache_is_ignored(cache, root):
            continue
        size = directory_size(cache)
        if size < minimum_bytes:
            continue
        candidates.append(
            {
                "path": str(cache),
                "repo_root": str(root),
                "size_bytes": size,
                "recovery": "reinstall from repository lockfile",
            }
        )

    return sorted(candidates, key=lambda item: str(item["path"]))


def canonical_manifest(workspace: Path, candidates: list[dict[str, object]]) -> dict[str, object]:
    body = {
        "schema": SCHEMA,
        "workspace_root": str(workspace.resolve()),
        "candidates": candidates,
    }
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return body | {"plan_sha256": hashlib.sha256(encoded).hexdigest()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--workspace-root", type=Path, default=Path.home() / "Workspace")
    parser.add_argument("--minimum-mib", type=int, default=1)
    parser.add_argument("--expected-plan-sha")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.apply and not args.expected_plan_sha:
        print("generated-cache-reclaim: --apply requires --expected-plan-sha", file=sys.stderr)
        return 2
    manifest = canonical_manifest(
        args.workspace_root,
        scan(args.workspace_root, minimum_bytes=max(0, args.minimum_mib) * 1024 * 1024),
    )
    if args.apply and args.expected_plan_sha != manifest["plan_sha256"]:
        print(
            "generated-cache-reclaim: candidate drift "
            f"expected={args.expected_plan_sha} actual={manifest['plan_sha256']}",
            file=sys.stderr,
        )
        return 3

    removed: list[dict[str, object]] = []
    if args.apply:
        for candidate in manifest["candidates"]:
            path = Path(str(candidate["path"]))
            shutil.rmtree(path)
            removed.append(candidate)

    output = manifest | {
        "candidate_count": len(manifest["candidates"]),
        "candidate_bytes": sum(int(item["size_bytes"]) for item in manifest["candidates"]),
        "removed_count": len(removed),
        "removed_bytes": sum(int(item["size_bytes"]) for item in removed),
    }
    if args.json:
        print(json.dumps(output, sort_keys=True))
    else:
        print(
            "generated-cache-reclaim: "
            f"candidates={output['candidate_count']} bytes={output['candidate_bytes']} "
            f"removed={output['removed_count']} plan_sha256={manifest['plan_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
