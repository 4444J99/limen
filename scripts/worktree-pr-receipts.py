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
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))
PRESERVATION_RECEIPTS = ROOT / "docs" / "worktree-preservation-receipts.json"

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


def pr_number_from_url(url: str) -> int | None:
    match = re.search(r"/pull/(\d+)(?:\D*)$", url or "")
    return int(match.group(1)) if match else None


def pr_view(cwd: Path, repo: str, number_or_url: int | str) -> dict[str, Any]:
    proc = gh(
        cwd,
        "pr",
        "view",
        str(number_or_url),
        "--repo",
        repo,
        "--json",
        "number,state,isDraft,headRefName,headRefOid,url",
        timeout=120,
    )
    if proc.returncode != 0:
        return {}
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


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


def update_preservation_receipts(rows: list[dict[str, Any]], apply: bool) -> dict[str, Any]:
    eligible = [
        row
        for row in rows
        if row.get("action") in {"pr_created", "pr_exists"} and row.get("repo") and row.get("branch")
    ]
    if not eligible:
        return {"updated": 0}
    try:
        data = json.loads(PRESERVATION_RECEIPTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"could not load preservation receipts: {exc}"}
    receipts = data.setdefault("receipts", [])
    by_root = {str(row.get("root")): row for row in receipts if isinstance(row, dict)}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated = 0
    for row in eligible:
        path = Path(str(row.get("path") or ""))
        root = str(row.get("name") or path.name)
        repo = str(row.get("repo"))
        branch = str(row.get("branch"))
        url = str(row.get("url") or (row.get("pr") or {}).get("url") or "")
        number = pr_number_from_url(url)
        view = pr_view(path if path.is_dir() else ROOT, repo, number or url) if (number or url) else {}
        head = str(view.get("headRefOid") or (git(path, "rev-parse", "HEAD").stdout.strip() if path.is_dir() else ""))
        if not url:
            url = str(view.get("url") or "")
        receipt = by_root.get(root)
        if receipt is None:
            receipt = {"root": root}
            receipts.append(receipt)
            by_root[root] = receipt
        pr_number = int(view.get("number") or number or 0)
        new_values = {
            "branch": str(view.get("headRefName") or branch),
            "classification": "open draft PR preserves local worktree head",
            "head": head,
            "lane": "remote-pr-open",
            "next_action": (
                f"Review draft PR #{pr_number}, then merge, supersede, or archive this lane. "
                "Local checkout is no longer the only review surface."
            ),
            "pr_draft": bool(view.get("isDraft", row.get("action") == "pr_created")),
            "pr_number": pr_number,
            "pr_state": str(view.get("state") or (row.get("pr") or {}).get("state") or "OPEN"),
            "pr_url": url,
            "repo": repo,
            "score_discount": 35,
            "status": "open_pr_preserved",
            "worktree": str(path) if path else "",
        }
        evidence_changed = any(receipt.get(key) != value for key, value in new_values.items())
        if evidence_changed or not receipt.get("evidence_updated_utc"):
            receipt.update(new_values)
            receipt["evidence_updated_utc"] = now
            updated += 1
    if updated and apply:
        PRESERVATION_RECEIPTS.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"updated": updated, "dry_run": bool(updated and not apply)}


def process_item(item: dict[str, Any], apply: bool) -> dict[str, Any]:
    path = Path(item["path"])
    reason = str(item.get("reason") or "")
    out: dict[str, Any] = {
        "name": item.get("name"),
        "path": str(path),
        "reason": reason,
        "action": "skip",
    }
    if reason not in {"not-merged-to-default", "unpushed-commits"}:
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

    if branch == base:
        out["action"] = "refused_default_branch"
        out["detail"] = (
            f"refusing lifecycle publication from the default branch {base}; create an isolated topic branch first"
        )
        return out

    if patch_equivalent_or_merged(path, base):
        out["action"] = "already_preserved"
        out["detail"] = f"HEAD is merged or patch-equivalent to origin/{base}"
        return out

    needs_push = reason == "unpushed-commits" or not remote_head_exists(path, branch)
    if needs_push:
        if not apply:
            out["action"] = "would_push"
            out["detail"] = "local HEAD is not preserved on a remote branch"
            return out
        push = git(path, "push", "-u", "origin", branch, timeout=120)
        if push.returncode != 0:
            out["action"] = "error"
            out["detail"] = f"push failed: {(push.stderr or push.stdout).strip()}"
            return out
        out["pushed"] = True

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
    receipt_update = update_preservation_receipts(results, apply=args.apply)
    payload = {
        "apply": bool(args.apply),
        "summary": dict(sorted(summary.items())),
        "receipt_update": receipt_update,
        "results": results,
    }
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
