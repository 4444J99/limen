"""Crash-visible transactional initialization for disposable linked worktrees."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal


WORKTREE_INITIALIZATION_SCHEMA = "limen.worktree_initialization.v1"
InitializationState = Literal["staging", "validated", "moving", "published", "crashed"]
InitializationPhase = Literal["preflight", "add", "validate-staging", "move", "validate-final"]
PhaseHook = Callable[[InitializationPhase, Path], None]


@dataclass(frozen=True)
class WorktreeInitialization:
    final_path: Path
    staging_path: Path
    branch: str
    checkout_ref: str
    expected_head: str
    journal_path: Path
    receipt: dict[str, Any]


class WorktreeInitializationError(RuntimeError):
    """Initialization stopped with a durable typed crash receipt and no cleanup."""

    def __init__(self, message: str, *, journal_path: Path, receipt: dict[str, Any]):
        self.journal_path = journal_path
        self.receipt = receipt
        super().__init__(message)


def _run_git(repo: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(["git", "-C", str(repo), *args], 1, "", str(exc))


def _git_value(repo: Path, *args: str) -> str:
    result = _run_git(repo, *args)
    value = result.stdout.strip()
    if result.returncode != 0 or not value:
        raise RuntimeError((result.stderr or result.stdout or "git-value-unavailable").strip())
    return value


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_text(path: Path, value: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_state(
    journal: Path,
    receipt: dict[str, Any],
    *,
    state: InitializationState,
    phase: InitializationPhase,
    crash_code: str | None = None,
    crash_detail: str | None = None,
) -> dict[str, Any]:
    updated = {
        **receipt,
        "state": state,
        "phase": phase,
        "updated_at": _now(),
        "crash": (
            {"code": crash_code, "detail": crash_detail}
            if crash_code is not None and crash_detail is not None
            else None
        ),
    }
    _atomic_json(journal, updated)
    return updated


def _validate_checkout(path: Path, *, expected_head: str, branch: str) -> dict[str, str]:
    head = _git_value(path, "rev-parse", "HEAD")
    if head != expected_head:
        raise RuntimeError("head-mismatch")
    branch_name = _git_value(path, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch_name != branch:
        raise RuntimeError("branch-mismatch")
    head_tree = _git_value(path, "rev-parse", "HEAD^{tree}")
    index_tree = _git_value(path, "write-tree")
    if index_tree != head_tree:
        raise RuntimeError("index-tree-mismatch")
    cached = _run_git(path, "diff", "--cached", "--quiet", "HEAD", "--")
    if cached.returncode != 0:
        raise RuntimeError("index-differs-from-head")
    working = _run_git(path, "diff", "--quiet", "--")
    if working.returncode != 0:
        raise RuntimeError("worktree-differs-from-index")
    status = _run_git(path, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status.returncode != 0:
        raise RuntimeError("worktree-status-unavailable")
    if status.stdout:
        raise RuntimeError("worktree-has-untracked-paths")
    return {
        "head": head,
        "branch": branch_name,
        "head_tree": head_tree,
        "index_tree": index_tree,
    }


def _common_git_dir(repo: Path) -> Path:
    raw = Path(_git_value(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    return raw.resolve(strict=True)


def _journal_path(common_dir: Path, final_path: Path, branch: str) -> Path:
    key = hashlib.sha256(f"{final_path}\0{branch}".encode()).hexdigest()
    return common_dir / "limen-worktree-initialization" / f"{key}.json"


def initialize_worktree(
    repo: Path,
    final_path: Path,
    *,
    branch: str,
    checkout_ref: str,
    task_id: str,
    phase_hook: PhaseHook | None = None,
) -> WorktreeInitialization:
    """Stage, validate, atomically publish, and revalidate one linked worktree.

    Any failure preserves the staging or published root exactly where it stopped
    and records ``state=crashed``. Recovery belongs to the sanctioned abandonment
    workflow; this initializer never resets, cleans, or recursively deletes.
    """

    repo = repo.resolve(strict=True)
    final_path = final_path.expanduser()
    parent = final_path.parent.resolve(strict=True)
    final_path = parent / final_path.name
    common_dir = _common_git_dir(repo)
    journal = _journal_path(common_dir, final_path, branch)
    staging = parent / f".limen-init-{final_path.name}-{secrets.token_hex(6)}"
    expected_head = ""
    receipt: dict[str, Any] = {
        "schema": WORKTREE_INITIALIZATION_SCHEMA,
        "state": "staging",
        "phase": "preflight",
        "created_at": _now(),
        "updated_at": _now(),
        "task_id": task_id,
        "repository": str(repo),
        "final_path": str(final_path),
        "staging_path": str(staging),
        "branch": branch,
        "checkout_ref": checkout_ref,
        "expected_head": None,
        "same_filesystem": False,
        "staging_validation": None,
        "final_validation": None,
        "crash": None,
    }
    _atomic_json(journal, receipt)
    phase: InitializationPhase = "preflight"
    try:
        if phase_hook:
            phase_hook(phase, staging)
        if final_path.exists() or final_path.is_symlink():
            raise RuntimeError("final-path-already-exists")
        if staging.exists() or staging.is_symlink():
            raise RuntimeError("staging-path-already-exists")
        expected_head = _git_value(repo, "rev-parse", checkout_ref)
        receipt["expected_head"] = expected_head
        phase = "add"
        receipt = _write_state(journal, receipt, state="staging", phase=phase)
        if phase_hook:
            phase_hook(phase, staging)
        added = _run_git(repo, "worktree", "add", "-b", branch, str(staging), checkout_ref)
        if added.returncode != 0:
            raise RuntimeError(f"worktree-add-failed: {(added.stderr or added.stdout).strip()[:300]}")

        phase = "validate-staging"
        if phase_hook:
            phase_hook(phase, staging)
        staging_validation = _validate_checkout(staging, expected_head=expected_head, branch=branch)
        git_dir = Path(_git_value(staging, "rev-parse", "--path-format=absolute", "--git-dir")).resolve(strict=True)
        receipt["staging_validation"] = staging_validation
        receipt["same_filesystem"] = os.stat(staging).st_dev == os.stat(parent).st_dev
        if not receipt["same_filesystem"]:
            raise RuntimeError("staging-path-is-not-on-final-filesystem")
        receipt = _write_state(journal, receipt, state="validated", phase=phase)

        phase = "move"
        receipt = _write_state(journal, receipt, state="moving", phase=phase)
        if final_path.exists() or final_path.is_symlink():
            raise RuntimeError("final-path-appeared-before-move")
        if os.stat(staging).st_dev != os.stat(parent).st_dev:
            raise RuntimeError("staging-path-crossed-filesystem")
        os.rename(staging, final_path)
        if phase_hook:
            phase_hook(phase, final_path)

        backlink = git_dir / "gitdir"
        _atomic_text(backlink, f"{final_path / '.git'}\n")

        phase = "validate-final"
        if phase_hook:
            phase_hook(phase, final_path)
        final_validation = _validate_checkout(final_path, expected_head=expected_head, branch=branch)
        receipt["final_validation"] = final_validation
        receipt = _write_state(journal, receipt, state="published", phase=phase)
        return WorktreeInitialization(
            final_path=final_path,
            staging_path=staging,
            branch=branch,
            checkout_ref=checkout_ref,
            expected_head=expected_head,
            journal_path=journal,
            receipt=receipt,
        )
    except Exception as exc:
        detail = " ".join(str(exc).split())[:500] or exc.__class__.__name__
        code = detail.split(":", 1)[0]
        try:
            receipt = _write_state(
                journal,
                receipt,
                state="crashed",
                phase=phase,
                crash_code=code,
                crash_detail=detail,
            )
        except OSError:
            receipt = {
                **receipt,
                "state": "crashed",
                "phase": phase,
                "crash": {"code": code, "detail": detail},
            }
        raise WorktreeInitializationError(detail, journal_path=journal, receipt=receipt) from exc


__all__ = [
    "WORKTREE_INITIALIZATION_SCHEMA",
    "WorktreeInitialization",
    "WorktreeInitializationError",
    "initialize_worktree",
]
