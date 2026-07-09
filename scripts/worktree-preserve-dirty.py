#!/usr/bin/env python3
"""Preserve dirty worktree debt as owner-blocker receipts.

This is a custody helper, not a cleanup helper. It captures a private patch and
bounded public metadata for dirty worktrees, then records an owner-blocker receipt
in docs/worktree-preservation-receipts.json. Physical removal still belongs to the
reclaim acceptance surface after a human/owner decision.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.worktree_debt import worktree_debt_report  # noqa: E402

PRESERVATION_RECEIPTS = ROOT / "docs" / "worktree-preservation-receipts.json"
PRIVATE_ROOT = ROOT / ".limen-private" / "session-corpus" / "lifecycle" / "worktree-preserve"
REMOTE_RE = re.compile(r"(?:github\.com[:/])([^/\s]+)/([^/\s]+?)(?:\.git)?$")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_name(value: str) -> str:
    cleaned = SAFE_NAME_RE.sub("-", value.strip()).strip("-._")
    return cleaned[:80] or "worktree"


def run_git(path: Path, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def repo_slug(remote: str) -> str | None:
    match = REMOTE_RE.search(remote.strip())
    return f"{match.group(1)}/{match.group(2)}" if match else None


def git_lines(path: Path, args: list[str], timeout: int = 60) -> list[str]:
    proc = run_git(path, args, timeout=timeout)
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def load_receipts() -> dict[str, Any]:
    try:
        data = json.loads(PRESERVATION_RECEIPTS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"generated_utc": utc_now(), "receipts": []}
    if not isinstance(data, dict):
        return {"generated_utc": utc_now(), "receipts": []}
    data.setdefault("receipts", [])
    return data


def rel_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except (OSError, ValueError):
        return str(path)


def preserve_item(item: dict[str, Any], stamp: str, apply: bool) -> dict[str, Any]:
    path = Path(str(item["path"]))
    root = str(item.get("name") or path.name)
    branch = run_git(path, ["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    head = run_git(path, ["rev-parse", "HEAD"]).stdout.strip()
    remote = run_git(path, ["remote", "get-url", "origin"]).stdout.strip()
    status_branch = run_git(path, ["status", "--short", "--branch"]).stdout
    status_porcelain = run_git(path, ["status", "--porcelain=v1"]).stdout
    dirty_paths = git_lines(path, ["diff", "--name-only", "HEAD"], timeout=120)
    untracked_paths = git_lines(path, ["ls-files", "--others", "--exclude-standard"], timeout=120)
    patch = run_git(path, ["diff", "--binary", "HEAD"], timeout=180).stdout
    private_dir = PRIVATE_ROOT / f"{stamp}-{safe_name(root)}"
    private_patch = private_dir / "dirty.patch"
    private_receipt = private_dir / "receipt.json"
    if apply:
        private_dir.mkdir(parents=True, exist_ok=True)
        (private_dir / "status-branch.txt").write_text(status_branch, encoding="utf-8", errors="replace")
        (private_dir / "status-porcelain.txt").write_text(status_porcelain, encoding="utf-8", errors="replace")
        (private_dir / "dirty-paths.txt").write_text("\n".join(dirty_paths) + "\n", encoding="utf-8")
        (private_dir / "untracked-paths.txt").write_text("\n".join(untracked_paths) + "\n", encoding="utf-8")
        private_patch.write_text(patch, encoding="utf-8", errors="replace")
    patch_sha = file_sha256(private_patch) if apply else sha256_text(patch)
    receipt = {
        "branch": branch,
        "classification": "dirty worktree privately preserved; owner decision required",
        "dirty_patch_bytes": len(patch.encode("utf-8", errors="replace")),
        "dirty_patch_command": "git diff --binary HEAD",
        "dirty_patch_sha256": patch_sha,
        "dirty_paths_count": len(dirty_paths),
        "dirty_paths_sha256": sha256_text("\n".join(sorted(dirty_paths))),
        "dirty_paths_sample": dirty_paths[:25],
        "evidence_updated_utc": utc_now(),
        "head": head,
        "lane": "owner-blocker",
        "next_action": (
            "Do not delete, reclaim, force-push, or auto-port this worktree from lifecycle cleanup. "
            "A private patch/status receipt exists; create a narrow owner packet to review, push, "
            "supersede, or retire this preserved dirty state."
        ),
        "private_patch": rel_to_root(private_patch),
        "private_patch_sha256": patch_sha,
        "private_receipt": rel_to_root(private_receipt),
        "repo": repo_slug(remote) or remote,
        "root": root,
        "status": "private_patch_preserved",
        "untracked_paths_count": len(untracked_paths),
        "untracked_paths_sha256": sha256_text("\n".join(sorted(untracked_paths))),
        "untracked_paths_sample": untracked_paths[:25],
        "worktree": str(path),
        "worktree_status": status_branch.splitlines(),
    }
    if apply:
        private_receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write private receipts and update preservation ledger")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--limit", type=int, default=0, help="maximum dirty roots to preserve; 0 means all")
    args = parser.parse_args()

    report = worktree_debt_report(ROOT)
    dirty = [item for item in report.get("items", []) if item.get("reason") == "dirty" and item.get("debt")]
    if args.limit > 0:
        dirty = dirty[: args.limit]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    receipts = [preserve_item(item, stamp, args.apply) for item in dirty]
    updated = 0
    if args.apply and receipts:
        data = load_receipts()
        receipt_rows = data.setdefault("receipts", [])
        by_root = {str(row.get("root")): row for row in receipt_rows if isinstance(row, dict)}
        for receipt in receipts:
            existing = by_root.get(str(receipt.get("root")))
            if existing is None:
                receipt_rows.append(receipt)
                updated += 1
            elif any(existing.get(key) != value for key, value in receipt.items()):
                existing.update(receipt)
                updated += 1
        data["generated_utc"] = utc_now()
        PRESERVATION_RECEIPTS.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    payload = {
        "apply": bool(args.apply),
        "requested": len(dirty),
        "updated": updated,
        "roots": [receipt.get("root") for receipt in receipts],
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        mode = "APPLY" if args.apply else "dry-run"
        print(f"worktree dirty preserve [{mode}]: {len(dirty)} root(s), updated {updated}")
        for root in payload["roots"][:40]:
            print(f"  {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
