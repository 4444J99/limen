from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import TypedDict


DEBT_REASONS = {
    "dirty",
    "not-a-git-dir",
    "not-merged-to-default",
    "unpushed-commits",
    "unresolved",
}


class WorktreeDebtItem(TypedDict):
    name: str
    path: str
    reason: str
    debt: bool


class WorktreeDebtReport(TypedDict):
    total: int
    debt: int
    by_reason: dict[str, int]
    items: list[WorktreeDebtItem]


def _git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def _remote_default_ref(cwd: Path) -> str | None:
    ref = _git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd)
    if ref.returncode == 0 and ref.stdout.strip():
        return ref.stdout.strip()
    for candidate in ("origin/main", "origin/master"):
        if _git(["show-ref", "--verify", "--quiet", f"refs/remotes/{candidate}"], cwd).returncode == 0:
            return candidate
    return None


def _reachable_from_remote(cwd: Path, head: str) -> bool:
    refs = _git(["for-each-ref", "--format=%(refname)", "refs/remotes"], cwd)
    if refs.returncode != 0:
        return False
    return any(_git(["merge-base", "--is-ancestor", head, ref], cwd).returncode == 0 for ref in refs.stdout.split())


def _merged_into_default(cwd: Path, head: str) -> bool:
    ref = _remote_default_ref(cwd)
    return bool(ref and _git(["merge-base", "--is-ancestor", head, ref], cwd).returncode == 0)


def _patch_equivalent_to_default(cwd: Path) -> bool:
    ref = _remote_default_ref(cwd)
    if not ref:
        return False
    cherry = _git(["cherry", ref, "HEAD"], cwd)
    if cherry.returncode != 0:
        return False
    lines = [line.strip() for line in cherry.stdout.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("-") for line in lines)


def _classify(path: Path, now: float, min_age_h: float, self_guard: set[Path]) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        return "unresolved"
    if resolved in self_guard:
        return "self/live-checkout"
    if _git(["rev-parse", "--is-inside-work-tree"], path).returncode != 0:
        return "not-a-git-dir"
    age_h = (now - path.stat().st_mtime) / 3600.0
    if age_h < min_age_h:
        return f"active(<{min_age_h:g}h)"
    if _git(["status", "--porcelain"], path).stdout.strip():
        return "dirty"
    head = _git(["rev-parse", "HEAD"], path).stdout.strip()
    patch_equivalent = _patch_equivalent_to_default(path)
    if not head or (not _reachable_from_remote(path, head) and not patch_equivalent):
        return "unpushed-commits"
    if not (_merged_into_default(path, head) or patch_equivalent):
        return "not-merged-to-default"
    return "clean+merged+idle"


def _scan_roots(limen_root: Path) -> list[tuple[Path, float]]:
    home = os.environ.get("HOME", "/Users/4jp")
    root = Path(os.environ.get("LIMEN_WORKTREE_ROOT", f"{home}/Workspace/.limen-worktrees"))
    roots = [(root, float(os.environ.get("LIMEN_RECLAIM_MIN_AGE_H", "6")))]
    if os.environ.get("LIMEN_RECLAIM_CLAUDE_WT", "1") == "1":
        roots.append(
            (
                limen_root / ".claude" / "worktrees",
                float(os.environ.get("LIMEN_RECLAIM_CLAUDE_AGE_H", "24")),
            )
        )
    return [(path, age) for path, age in roots if path.is_dir()]


def worktree_debt_report(limen_root: Path | None = None) -> WorktreeDebtReport:
    root = limen_root or Path(os.environ.get("LIMEN_ROOT", f"{os.environ.get('HOME', '/Users/4jp')}/Workspace/limen"))
    self_guard: set[Path] = set()
    for candidate in (root, Path.cwd()):
        try:
            self_guard.add(candidate.resolve())
        except OSError:
            pass

    now = time.time()
    items: list[WorktreeDebtItem] = []
    by_reason: dict[str, int] = {}
    for scan_root, min_age_h in _scan_roots(root):
        for path in sorted(p for p in scan_root.iterdir() if p.is_dir()):
            reason = _classify(path, now, min_age_h, self_guard)
            debt = reason in DEBT_REASONS
            by_reason[reason] = by_reason.get(reason, 0) + 1
            items.append({"name": path.name, "path": str(path), "reason": reason, "debt": debt})

    debt_count = sum(1 for item in items if item["debt"])
    return {"total": len(items), "debt": debt_count, "by_reason": by_reason, "items": items}


def worktree_debt_exceeded(limit: int | None = None) -> tuple[bool, WorktreeDebtReport, int]:
    effective_limit = limit
    if effective_limit is None:
        effective_limit = int(os.environ.get("LIMEN_WORKTREE_DEBT_MAX", "12"))
    report = worktree_debt_report()
    return report["debt"] > effective_limit, report, effective_limit
