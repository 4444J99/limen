#!/usr/bin/env python3
"""Summarize local/remote lifecycle pressure for session hooks.

This is deliberately small and PII-free. It gives hooks a way to keep local disk
pressure and remote preservation pressure visible without touching tracked files.

Outputs:
* stdout: one compact Markdown line for SessionStart orientation.
* --write: ignored JSON/Markdown snapshots under logs/.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
WORKTREE_ROOT = ROOT.parent / ".limen-worktrees"
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PROMPT_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
CORPUS_INVENTORY = PRIVATE_ROOT / "inventory" / "session-corpus-ledger.json"
OUT_JSON = ROOT / "logs" / "session-lifecycle-pressure.json"
OUT_MD = ROOT / "logs" / "session-lifecycle-pressure.md"
REMOTE_MISSING_CLOSED_REASONS = {
    "clean+merged+idle",
    "documented-residue",
    "owner-blocker",
    "remote-merged",
    "remote-pr-open",
    "remote-superseded",
}


def fmt_bytes(n: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"


def load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        try:
            total += child.stat().st_size
        except OSError:
            continue
    return total


def count_dirs(path: Path) -> int:
    if not path.is_dir():
        return 0
    try:
        return sum(1 for child in path.iterdir() if child.is_dir())
    except OSError:
        return 0


def count_files(path: Path) -> int:
    if not path.is_dir():
        return 0
    try:
        return sum(1 for child in path.rglob("*") if child.is_file())
    except OSError:
        return 0


def run_worktree_debt() -> dict[str, Any]:
    proc = subprocess.run(
        ["python3", str(ROOT / "scripts" / "worktree-debt.py"), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return {"total": 0, "debt": 0, "limit": 0, "by_reason": {}, "error": proc.stderr.strip()}
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {"total": 0, "debt": 0, "limit": 0, "by_reason": {}, "error": "invalid worktree-debt JSON"}


def remote_missing_counts(worktree_remote: dict[str, Any], wt_report: dict[str, Any]) -> dict[str, Any]:
    raw_missing = int(worktree_remote.get("remote_branches_missing") or 0)
    missing_roots = [
        str(receipt.get("name"))
        for receipt in worktree_remote.get("receipts") or []
        if isinstance(receipt, dict) and receipt.get("remote_branch") == "missing" and receipt.get("name")
    ]
    by_name = {
        str(item.get("name")): item
        for item in wt_report.get("items") or []
        if isinstance(item, dict) and item.get("name")
    }
    if not missing_roots or not by_name:
        return {
            "raw": raw_missing,
            "unresolved": raw_missing,
            "closed": 0,
            "closed_roots": [],
            "unresolved_roots": missing_roots,
        }

    closed_roots: list[str] = []
    unresolved_roots: list[str] = []
    for root in missing_roots:
        item = by_name.get(root)
        reason = str((item or {}).get("reason") or "")
        if item and not item.get("debt") and reason in REMOTE_MISSING_CLOSED_REASONS:
            closed_roots.append(root)
        else:
            unresolved_roots.append(root)
    return {
        "raw": raw_missing,
        "unresolved": len(unresolved_roots),
        "closed": len(closed_roots),
        "closed_roots": closed_roots,
        "unresolved_roots": unresolved_roots,
    }


def build_snapshot() -> dict[str, Any]:
    prompt = load_json(PROMPT_INDEX)
    corpus = load_json(CORPUS_INVENTORY)
    remote = prompt.get("remote") or {}
    worktree_remote = remote.get("worktrees") or {}
    task_prs = remote.get("task_prs") or {}
    task_pr_counts = task_prs.get("counts") or {}
    cloud = prompt.get("cloud") or {}
    object_store = corpus.get("object_store") or {}
    if not object_store:
        object_store = {
            "object_count": count_files(PRIVATE_ROOT / "objects"),
            "object_bytes": dir_size(PRIVATE_ROOT / "objects"),
        }

    wt_report = run_worktree_debt()
    worktree_bytes = dir_size(WORKTREE_ROOT)
    private_bytes = dir_size(PRIVATE_ROOT)
    total_local_bytes = worktree_bytes + private_bytes
    debt = int(wt_report.get("debt") or 0)
    limit = int(wt_report.get("limit") or 0)
    over_cap = limit > 0 and debt > limit
    missing_remote = remote_missing_counts(worktree_remote, wt_report)
    pr_errors = int(task_pr_counts.get("ERROR") or 0)

    pressure: list[str] = []
    if over_cap:
        pressure.append("worktree debt above cap")
    elif debt:
        pressure.append("worktree debt open")
    if int(missing_remote["unresolved"]):
        pressure.append("remote branch gaps")
    if pr_errors:
        pressure.append("PR receipt errors")
    if not cloud.get("runtime_url_configured"):
        pressure.append("runtime unconfigured")

    return {
        "worktrees": {
            "root": str(WORKTREE_ROOT),
            "roots": count_dirs(WORKTREE_ROOT),
            "bytes": worktree_bytes,
            "debt": debt,
            "limit": limit,
            "over_cap": over_cap,
            "by_reason": wt_report.get("by_reason") or {},
        },
        "private_corpus": {
            "root": str(PRIVATE_ROOT),
            "bytes": private_bytes,
            "object_count": int(object_store.get("object_count") or 0),
            "object_bytes": int(object_store.get("object_bytes") or 0),
        },
        "remote": {
            "enabled": bool(remote.get("enabled")),
            "remote_branches_present": int(worktree_remote.get("remote_branches_present") or 0),
            "remote_branches_missing": int(missing_remote["raw"]),
            "remote_branches_unresolved_missing": int(missing_remote["unresolved"]),
            "remote_branches_closed_by_live_scanner": int(missing_remote["closed"]),
            "remote_branches_closed_roots": missing_remote["closed_roots"],
            "remote_branches_unresolved_roots": missing_remote["unresolved_roots"],
            "open_prs": int(worktree_remote.get("open_prs") or 0),
            "merged_prs": int(worktree_remote.get("merged_prs") or 0),
            "task_pr_errors": pr_errors,
        },
        "cloud": {
            "enabled": bool(cloud.get("enabled")),
            "runtime_url_configured": bool(cloud.get("runtime_url_configured")),
            "cloudflare_deploy_auth_present": bool(cloud.get("cloudflare_deploy_auth_present")),
        },
        "local_total_bytes": total_local_bytes,
        "pressure": pressure,
    }


def render(snapshot: dict[str, Any]) -> str:
    wt = snapshot["worktrees"]
    corpus = snapshot["private_corpus"]
    remote = snapshot["remote"]
    pressure = ", ".join(snapshot["pressure"]) if snapshot["pressure"] else "within guardrails"
    remote_missing = f"{remote['remote_branches_present']}/{remote['remote_branches_missing']}"
    if remote["remote_branches_unresolved_missing"] != remote["remote_branches_missing"]:
        remote_missing += f" (unresolved {remote['remote_branches_unresolved_missing']})"
    return (
        "**Lifecycle pressure** — "
        f"worktrees {wt['roots']} roots / {fmt_bytes(wt['bytes'])} / debt {wt['debt']}/{wt['limit']} · "
        f"private corpus {fmt_bytes(corpus['bytes'])} ({corpus['object_count']} objects) · "
        f"remote branches present/missing {remote_missing} · "
        f"state: {pressure}"
    )


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    OUT_MD.write_text(markdown + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize local/remote lifecycle pressure.")
    parser.add_argument("--write", action="store_true", help="write ignored logs snapshots")
    args = parser.parse_args()

    snapshot = build_snapshot()
    markdown = render(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
    print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
