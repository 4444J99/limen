from __future__ import annotations

import os
import json
import subprocess
import time
from pathlib import Path
from typing import Any, TypedDict

from limen.worktree_roots import iter_worktree_targets


DEBT_REASONS = {
    "dirty",
    "not-a-git-dir",
    "not-merged-to-default",
    "unpushed-commits",
    "unresolved",
}
REAPABLE_REASONS = {
    "clean+merged+idle",
}

DOCUMENTED_RESIDUE_LANES = {"documented-residue"}
DOCUMENTED_RESIDUE_STATUSES = {
    "cache_only_residue",
    "documented_non_source_residue",
    "empty_generated_residue",
}
REMOTE_SUPERSEDED_LANES = {"remote-superseded"}
REMOTE_SUPERSEDED_STATUSES = {"superseded_on_origin_main"}
REMOTE_MERGED_LANES = {"remote-merged"}
REMOTE_MERGED_STATUSES = {"merged_pr_preserved"}
REMOTE_PR_OPEN_LANES = {"remote-pr-open"}
REMOTE_PR_OPEN_STATUSES = {"open_pr_preserved"}
OWNER_BLOCKER_LANES = {"owner-blocker"}
OWNER_BLOCKER_STATUSES = {"history_mismatch_patch_preserved", "private_patch_preserved"}
GENERATED_LOG_SHELL_FILES = {
    "logs/session-lifecycle-pressure.md",
    "logs/session-lifecycle-pressure.json",
}


class WorktreeDebtItem(TypedDict):
    name: str
    path: str
    reason: str
    debt: bool
    reapable: bool


class WorktreeDebtReport(TypedDict):
    total: int
    debt: int
    reapable: int
    by_reason: dict[str, int]
    by_reapable_reason: dict[str, int]
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
    refs = _git(["for-each-ref", f"--contains={head}", "--format=%(refname)", "refs/remotes"], cwd)
    if refs.returncode != 0:
        return False
    return bool(refs.stdout.strip())


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


def _git_toplevel(cwd: Path) -> Path | None:
    top = _git(["rev-parse", "--show-toplevel"], cwd)
    if top.returncode != 0 or not top.stdout.strip():
        return None
    try:
        return Path(top.stdout.strip()).resolve()
    except OSError:
        return Path(top.stdout.strip())


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _load_preservation_receipts(limen_root: Path) -> dict[str, dict[str, Any]]:
    path = limen_root / "docs" / "worktree-preservation-receipts.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    receipts: dict[str, dict[str, object]] = {}
    items = data.get("receipts")
    if isinstance(items, list):
        for receipt in items:
            if not isinstance(receipt, dict):
                continue
            root = receipt.get("root")
            if isinstance(root, str) and root:
                receipts[root] = receipt
    return receipts


def _is_documented_residue(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    classification = str(receipt.get("classification") or "")
    return (
        lane in DOCUMENTED_RESIDUE_LANES
        or status in DOCUMENTED_RESIDUE_STATUSES
        or classification == "documented non-source residue"
    )


def _is_remote_superseded(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    return lane in REMOTE_SUPERSEDED_LANES or status in REMOTE_SUPERSEDED_STATUSES


def _is_remote_merged(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    return lane in REMOTE_MERGED_LANES or status in REMOTE_MERGED_STATUSES


def _is_remote_pr_open(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    return lane in REMOTE_PR_OPEN_LANES or status in REMOTE_PR_OPEN_STATUSES


def _is_owner_blocker(path: Path, preservation_receipts: dict[str, dict[str, object]]) -> bool:
    receipt = preservation_receipts.get(path.name)
    if not receipt:
        return False
    lane = str(receipt.get("lane") or "")
    status = str(receipt.get("status") or "")
    has_private_receipt = bool(receipt.get("private_receipt") or receipt.get("private_patch_sha256"))
    return has_private_receipt and (lane in OWNER_BLOCKER_LANES or status in OWNER_BLOCKER_STATUSES)


def is_generated_log_shell(path: Path) -> bool:
    """True for disposable non-git worktree shells containing only pressure receipts."""
    if not path.is_dir():
        return False
    try:
        files = {item.relative_to(path).as_posix() for item in path.rglob("*") if item.is_file()}
    except OSError:
        return False
    return bool(files) and files <= GENERATED_LOG_SHELL_FILES


def _agy_scratch_root() -> Path:
    home = os.environ.get("HOME", "/Users/4jp")
    return Path(os.environ.get("LIMEN_AGY_SCRATCH_ROOT", f"{home}/.gemini/antigravity-cli/scratch")).expanduser()


def _inside_agy_scratch_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(_agy_scratch_root().resolve())
        return True
    except (OSError, ValueError):
        return False


def _classify(
    path: Path,
    now: float,
    min_age_h: float,
    self_guard: set[Path],
    preservation_receipts: dict[str, dict[str, object]],
) -> str:
    try:
        resolved = path.resolve()
    except OSError:
        return "unresolved"
    if resolved in self_guard:
        return "self/live-checkout"
    if _inside_agy_scratch_root(path):
        return "antigravity-scratch-managed"
    if _is_documented_residue(path, preservation_receipts):
        return "documented-residue"
    if _is_remote_superseded(path, preservation_receipts):
        return "remote-superseded"
    if _is_remote_merged(path, preservation_receipts):
        return "remote-merged"
    if _is_remote_pr_open(path, preservation_receipts):
        return "remote-pr-open"
    if _is_owner_blocker(path, preservation_receipts):
        return "owner-blocker"
    top = _git_toplevel(path)
    if top is None:
        if is_generated_log_shell(path):
            return "generated-log-shell"
        return "not-a-git-dir"
    if top != resolved:
        return "self/live-checkout" if top in self_guard else "not-a-git-dir"
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


def worktree_debt_report(limen_root: Path | None = None) -> WorktreeDebtReport:
    root = limen_root or Path(os.environ.get("LIMEN_ROOT", f"{os.environ.get('HOME', '/Users/4jp')}/Workspace/limen"))
    self_guard: set[Path] = set()
    for candidate in (root, Path.cwd()):
        try:
            self_guard.add(candidate.resolve())
        except OSError:
            pass

    now = time.time()
    preservation_receipts = _load_preservation_receipts(root)
    items: list[WorktreeDebtItem] = []
    by_reason: dict[str, int] = {}
    by_reapable_reason: dict[str, int] = {}
    for target in iter_worktree_targets(root):
        path = target.path
        reason = _classify(path, now, target.min_age_h, self_guard, preservation_receipts)
        debt = reason in DEBT_REASONS
        reapable = reason in REAPABLE_REASONS
        by_reason[reason] = by_reason.get(reason, 0) + 1
        if reapable:
            by_reapable_reason[reason] = by_reapable_reason.get(reason, 0) + 1
        items.append({"name": path.name, "path": str(path), "reason": reason, "debt": debt, "reapable": reapable})

    debt_count = sum(1 for item in items if item["debt"])
    reapable_count = sum(1 for item in items if item["reapable"])
    return {
        "total": len(items),
        "debt": debt_count,
        "reapable": reapable_count,
        "by_reason": by_reason,
        "by_reapable_reason": by_reapable_reason,
        "items": items,
    }


def worktree_debt_exceeded(limit: int | None = None) -> tuple[bool, WorktreeDebtReport, int]:
    effective_limit = limit
    if effective_limit is None:
        effective_limit = _int_env("LIMEN_WORKTREE_DEBT_MAX", 12)
    report = worktree_debt_report()
    return report["debt"] > effective_limit, report, effective_limit


def worktree_reapable_exceeded(limit: int | None = None) -> tuple[bool, WorktreeDebtReport, int]:
    effective_limit = limit
    if effective_limit is None:
        effective_limit = _int_env("LIMEN_WORKTREE_REAPABLE_MAX", 0)
    report = worktree_debt_report()
    return report["reapable"] > effective_limit, report, effective_limit
