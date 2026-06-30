#!/usr/bin/env python3
"""Create durable PR receipts for clean worktree debt without blocking the loop.

This is intentionally conservative:

- default is dry-run;
- only clean Git worktrees are eligible;
- only `not-merged-to-default` debt roots are considered;
- `--apply` may push a missing remote head and open a draft PR;
- one GitHub or auth failure is recorded per root and never stops the rest.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.worktree_debt import worktree_debt_report  # noqa: E402


def run(args: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def git(cwd: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd, timeout=timeout)


def gh(cwd: Path, *args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return run(["gh", *args], cwd, timeout=timeout)


def origin_repo(cwd: Path) -> str | None:
    remote = git(cwd, "remote", "get-url", "origin").stdout.strip()
    if not remote:
        return None
    match = re.match(r"https://github\.com/([^/]+/[^/.]+)(?:\.git)?$", remote)
    if match:
        return match.group(1)
    match = re.match(r"git@github\.com:([^/]+/[^/.]+)(?:\.git)?$", remote)
    if match:
        return match.group(1)
    return None


def current_branch(cwd: Path) -> str | None:
    value = git(cwd, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    return value if value and value != "HEAD" else None


def default_branch(cwd: Path, repo: str) -> str | None:
    proc = gh(cwd, "repo", "view", repo, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name")
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    proc = git(cwd, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if proc.returncode == 0 and proc.stdout.strip().startswith("origin/"):
        return proc.stdout.strip().split("/", 1)[1]
    for candidate in ("main", "master"):
        if git(cwd, "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{candidate}").returncode == 0:
            return candidate
    return None


def remote_head_exists(cwd: Path, branch: str) -> bool:
    proc = git(cwd, "ls-remote", "--heads", "origin", branch, timeout=120)
    return proc.returncode == 0 and bool(proc.stdout.strip())


def existing_pr(cwd: Path, repo: str, branch: str) -> dict[str, Any] | None:
    proc = gh(
        cwd,
        "pr",
        "list",
        "--repo",
        repo,
        "--head",
        branch,
        "--json",
        "number,state,title,url,baseRefName,headRefName",
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid gh pr list JSON: {exc}") from exc
    return rows[0] if rows else None


def patch_equivalent_or_merged(cwd: Path, base: str) -> bool:
    base_ref = f"origin/{base}"
    if git(cwd, "merge-base", "--is-ancestor", "HEAD", base_ref).returncode == 0:
        return True
    proc = git(cwd, "cherry", base_ref, "HEAD")
    if proc.returncode != 0:
        return False
    rows = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return bool(rows) and all(row.startswith("-") for row in rows)


def create_pr(cwd: Path, repo: str, base: str, branch: str, title: str) -> str:
    body = (
        "Lifecycle preservation PR opened by `scripts/worktree-pr-receipts.py`.\n\n"
        "Purpose:\n"
        "- Move a clean pushed worktree branch out of local-only debt.\n"
        "- Provide an owner review surface without merging or deleting anything.\n\n"
        "Verification performed by the helper:\n"
        "- clean `git status --porcelain`\n"
        "- remote/default branch fetched\n"
        "- missing remote head pushed when needed\n\n"
        "Opened as draft because lifecycle reduction is not merge authorization."
    )
    proc = gh(
        cwd,
        "pr",
        "create",
        "--repo",
        repo,
        "--base",
        base,
        "--head",
        branch,
        "--draft",
        "--title",
        title,
        "--body",
        body,
        timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip())
    return proc.stdout.strip()


def process_item(item: dict[str, Any], apply: bool) -> dict[str, Any]:
    path = Path(item["path"])
    out: dict[str, Any] = {
        "name": item.get("name"),
        "path": str(path),
        "reason": item.get("reason"),
        "action": "skip",
    }
    if item.get("reason") != "not-merged-to-default":
        out["detail"] = "not a PR-receipt candidate"
        return out
    if not path.is_dir():
        out["detail"] = "missing path"
        return out
    if git(path, "rev-parse", "--is-inside-work-tree").returncode != 0:
        out["detail"] = "not a git worktree"
        return out
    status = git(path, "status", "--porcelain").stdout.strip()
    if status:
        out["detail"] = "dirty worktree"
        return out
    repo = origin_repo(path)
    branch = current_branch(path)
    if not repo or not branch:
        out["detail"] = "missing repo or branch"
        return out
    out.update({"repo": repo, "branch": branch})

    fetch = git(path, "fetch", "--prune", "origin", timeout=120)
    if fetch.returncode != 0:
        out["action"] = "error"
        out["detail"] = f"fetch failed: {(fetch.stderr or fetch.stdout).strip()}"
        return out
    base = default_branch(path, repo)
    if not base:
        out["action"] = "error"
        out["detail"] = "could not resolve default branch"
        return out
    out["base"] = base

    if patch_equivalent_or_merged(path, base):
        out["action"] = "already_preserved"
        out["detail"] = f"HEAD is merged or patch-equivalent to origin/{base}"
        return out

    try:
        pr = existing_pr(path, repo, branch)
    except RuntimeError as exc:
        out["action"] = "error"
        out["detail"] = f"gh pr list failed: {exc}"
        return out
    if pr:
        out["action"] = "pr_exists"
        out["pr"] = pr
        return out

    if not remote_head_exists(path, branch):
        if not apply:
            out["action"] = "would_push_and_open_pr"
            out["detail"] = "remote head missing"
            return out
        push = git(path, "push", "-u", "origin", branch, timeout=120)
        if push.returncode != 0:
            out["action"] = "error"
            out["detail"] = f"push failed: {(push.stderr or push.stdout).strip()}"
            return out
        out["pushed"] = True

    if not apply:
        out["action"] = "would_open_pr"
        return out
    try:
        title = f"{path.name} lifecycle checkpoint"
        out["url"] = create_pr(path, repo, base, branch, title)
        out["action"] = "pr_created"
    except RuntimeError as exc:
        out["action"] = "error"
        out["detail"] = f"gh pr create failed: {exc}"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Open draft PR receipts for clean worktree debt.")
    parser.add_argument("--apply", action="store_true", help="push missing heads and create draft PRs")
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    args = parser.parse_args()

    report = worktree_debt_report()
    results = [process_item(item, args.apply) for item in report.get("items", []) if item.get("debt")]
    summary: dict[str, int] = {}
    for row in results:
        action = str(row.get("action") or "unknown")
        summary[action] = summary.get(action, 0) + 1
    payload = {"apply": bool(args.apply), "summary": dict(sorted(summary.items())), "results": results}
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "APPLY" if args.apply else "dry-run"
        print(f"worktree PR receipts [{mode}]: {payload['summary']}")
        for row in results:
            bits = [str(row.get("action")), str(row.get("name"))]
            if row.get("repo"):
                bits.append(str(row["repo"]))
            if row.get("url"):
                bits.append(str(row["url"]))
            elif row.get("pr", {}).get("url"):
                bits.append(str(row["pr"]["url"]))
            elif row.get("detail"):
                bits.append(str(row["detail"]))
            print("  " + " | ".join(bits))
    return 1 if any(row.get("action") == "error" for row in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
