#!/usr/bin/env python3
"""Preserve daemon-owned live state without stranding local commits.

The heartbeat owns a few tracked live-state surfaces (`tasks.yaml` and selected generated office
dashboards). This script publishes only those paths to `origin/main`. It creates the commit with a
temporary index and pushes the commit object directly; the local branch advances only after the push
succeeds, so a network/rebase failure never leaves the live root locally ahead.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
DEFAULT_BRANCH = os.environ.get("LIMEN_RELEASE_BRANCH", "main")
DEFAULT_PATHS = (
    "tasks.yaml",
    "organs/financial/STATUS.md",
    "organs/financial/cashflow.md",
)


def git(args: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def short_output(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:220]


def resolve_paths(raw_paths: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_paths:
        path = raw.strip().strip("/")
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def changed_allowed_paths(paths: list[str]) -> list[str]:
    proc = git(["status", "--porcelain", "--", *paths])
    if proc.returncode != 0:
        return []
    changed: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        if path in paths and path not in changed:
            changed.append(path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Commit and push daemon-owned live-state paths.")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    configured = os.environ.get("LIMEN_PRESERVE_LIVE_STATE_PATHS")
    raw_paths = args.path or (configured.split(os.pathsep) if configured else list(DEFAULT_PATHS))
    paths = resolve_paths(raw_paths)
    if not paths:
        print("preserve-live-state: no paths configured")
        return 0

    inside = git(["rev-parse", "--is-inside-work-tree"])
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        print("preserve-live-state: not a git repo")
        return 0

    branch = git(["symbolic-ref", "--quiet", "--short", "HEAD"])
    if branch.returncode != 0 or branch.stdout.strip() != args.branch:
        print(f"preserve-live-state: on {branch.stdout.strip() or 'detached'}, not {args.branch}; skip")
        return 0

    fetch = git(["fetch", "--quiet", "origin", args.branch])
    if fetch.returncode != 0:
        print(f"preserve-live-state: fetch failed ({short_output(fetch)}); skip")
        return 0

    head = git(["rev-parse", "HEAD"]).stdout.strip()
    remote = git(["rev-parse", f"origin/{args.branch}"]).stdout.strip()
    if not head or head != remote:
        print(f"preserve-live-state: live root not at origin/{args.branch}; skip")
        return 0

    changed = changed_allowed_paths(paths)
    if not changed:
        print("preserve-live-state: no daemon-owned changes")
        return 0
    if args.dry_run:
        print(f"preserve-live-state: would preserve {', '.join(changed)}")
        return 0

    with tempfile.NamedTemporaryFile(prefix="limen-live-state-index-") as tmp:
        env = {"GIT_INDEX_FILE": tmp.name}
        read_tree = git(["read-tree", "HEAD"], env=env)
        if read_tree.returncode != 0:
            print(f"preserve-live-state: read-tree failed ({short_output(read_tree)})")
            return 0
        add = git(["add", "-A", "--", *changed], env=env)
        if add.returncode != 0:
            print(f"preserve-live-state: add failed ({short_output(add)})")
            return 0
        diff = git(["diff", "--cached", "--quiet", "--", *changed], env=env)
        if diff.returncode == 0:
            print("preserve-live-state: allowed changes resolved to no diff")
            return 0
        tree = git(["write-tree"], env=env)
        if tree.returncode != 0 or not tree.stdout.strip():
            print(f"preserve-live-state: write-tree failed ({short_output(tree)})")
            return 0
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        commit = git(["commit-tree", tree.stdout.strip(), "-p", head, "-m", f"limen: preserve live daemon state {stamp}"], env=env)
        if commit.returncode != 0 or not commit.stdout.strip():
            print(f"preserve-live-state: commit-tree failed ({short_output(commit)})")
            return 0
        commit_sha = commit.stdout.strip()

    push = git(["push", "origin", f"{commit_sha}:refs/heads/{args.branch}"])
    if push.returncode != 0:
        print(f"preserve-live-state: push failed ({short_output(push)}); local branch unchanged")
        return 0

    update_local = git(["update-ref", f"refs/heads/{args.branch}", commit_sha, head])
    update_remote = git(["update-ref", f"refs/remotes/origin/{args.branch}", commit_sha, remote])
    reset_index = git(["reset", "-q", "--", *changed])
    final_head = git(["rev-parse", "HEAD"]).stdout.strip()
    final_remote = git(["rev-parse", f"origin/{args.branch}"]).stdout.strip()
    final_dirty = changed_allowed_paths(changed)
    if (
        (update_local.returncode != 0 or update_remote.returncode != 0 or reset_index.returncode != 0)
        and (final_head != commit_sha or final_remote != commit_sha or final_dirty)
    ):
        print("preserve-live-state: pushed but local ref/index refresh needs next sync-release")
        return 0

    print(f"preserve-live-state: pushed {commit_sha[:8]} ({', '.join(changed)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
