from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class WorktreeTarget:
    path: Path
    min_age_h: float
    source: str


SKIP_DIR_NAMES = {
    ".cache",
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "vendor",
}


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"", "0", "false", "no", "off"}


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _path_list(name: str, default: Iterable[Path]) -> list[Path]:
    raw = os.environ.get(name)
    if raw is None:
        return [Path(p).expanduser() for p in default]
    return [Path(part).expanduser() for part in raw.split(os.pathsep) if part.strip()]


def default_worktrees_root() -> Path:
    """Scratch-first default for disposable lane checkouts.

    The live heartbeat and launchd generator already derive this root. Keep the Python callers on
    the same rule so an unset shell env cannot silently fall back to the laptop workspace.
    """
    explicit = os.environ.get("LIMEN_WORKTREES")
    if explicit:
        return Path(explicit).expanduser()
    scratch = Path("/Volumes/Scratch")
    if scratch.is_dir() and os.access(scratch, os.W_OK):
        return scratch / "limen-worktrees"
    workdir = Path(os.environ.get("LIMEN_WORKDIR", str(Path.home() / "Workspace"))).expanduser()
    return workdir / ".limen-worktrees"


def effective_worktree_root() -> Path:
    explicit = os.environ.get("LIMEN_WORKTREE_ROOT")
    if explicit:
        return Path(explicit).expanduser()
    return default_worktrees_root()


def _dedupe_targets(targets: Iterable[WorktreeTarget]) -> list[WorktreeTarget]:
    seen: set[str] = set()
    out: list[WorktreeTarget] = []
    for target in targets:
        try:
            key = str(target.path.resolve())
        except OSError:
            key = str(target.path)
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out


def _children(root: Path, min_age_h: float, source: str) -> list[WorktreeTarget]:
    if not root.is_dir():
        return []
    try:
        return [
            WorktreeTarget(path=path, min_age_h=min_age_h, source=source)
            for path in sorted(root.iterdir())
            if path.is_dir()
        ]
    except OSError:
        return []


def _discover_repo_local_roots(limen_root: Path) -> list[Path]:
    explicit = _path_list("LIMEN_RECLAIM_REPO_LOCAL_ROOTS", [])
    roots = [path for path in explicit if path.is_dir()]
    workspace_roots = _path_list("LIMEN_RECLAIM_WORKSPACE_ROOTS", [Path.home() / "Workspace"])
    max_depth = _int_env("LIMEN_RECLAIM_WORKSPACE_MAX_DEPTH", 5)

    def walk(path: Path, depth: int) -> None:
        if depth > max_depth or not path.is_dir():
            return
        try:
            children = sorted(path.iterdir())
        except OSError:
            return
        for child in children:
            if not child.is_dir():
                continue
            if child.name == ".worktrees":
                roots.append(child)
                continue
            if child.name in SKIP_DIR_NAMES:
                continue
            if child.name.startswith("."):
                continue
            walk(child, depth + 1)

    for workspace_root in workspace_roots:
        walk(workspace_root, 0)

    local = limen_root / ".worktrees"
    if local.is_dir():
        roots.append(local)

    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        try:
            key = str(root.resolve())
        except OSError:
            key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _git_worktree_paths(repo: Path) -> list[Path]:
    try:
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    paths: list[Path] = []
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line.split(" ", 1)[1]))
    return paths


def _registered_repo_roots(limen_root: Path) -> list[Path]:
    default_repos = [limen_root]
    portvs = Path.home() / "Workspace" / "4444J99" / "portvs"
    if portvs.is_dir():
        default_repos.append(portvs)
    repos = _path_list("LIMEN_RECLAIM_MAIN_REPOS", default_repos)
    roots: list[Path] = []
    for repo in repos:
        if not repo.is_dir():
            continue
        try:
            repo_resolved = repo.resolve()
        except OSError:
            repo_resolved = repo
        for path in _git_worktree_paths(repo):
            try:
                if path.resolve() == repo_resolved:
                    continue
            except OSError:
                pass
            roots.append(path)
    return roots


def _legacy_dispatch_roots(dispatch_root: Path) -> list[Path]:
    """Historical dispatch roots to scan/reap without making them active creation roots."""
    roots = _path_list("LIMEN_RECLAIM_LEGACY_WORKTREE_ROOTS", [Path.home() / "Workspace" / ".limen-worktrees"])
    out: list[Path] = []
    try:
        dispatch_resolved = dispatch_root.resolve()
    except OSError:
        dispatch_resolved = dispatch_root
    for root in roots:
        if not root.is_dir():
            continue
        try:
            if root.resolve() == dispatch_resolved:
                continue
        except OSError:
            pass
        out.append(root)
    return out


def iter_worktree_targets(limen_root: Path | None = None) -> list[WorktreeTarget]:
    root = limen_root or Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))

    targets: list[WorktreeTarget] = []
    dispatch_root = effective_worktree_root()
    targets.extend(_children(dispatch_root, _float_env("LIMEN_RECLAIM_MIN_AGE_H", 6), "dispatch-root"))
    broad_default = "LIMEN_WORKTREE_ROOT" not in os.environ

    if _flag("LIMEN_RECLAIM_LEGACY_DISPATCH_WT", broad_default):
        legacy_age = _float_env("LIMEN_RECLAIM_LEGACY_DISPATCH_AGE_H", _float_env("LIMEN_RECLAIM_MIN_AGE_H", 6))
        for legacy_root in _legacy_dispatch_roots(dispatch_root):
            targets.extend(_children(legacy_root, legacy_age, f"legacy-dispatch-root:{legacy_root}"))

    if _flag("LIMEN_RECLAIM_CLAUDE_WT", True):
        targets.extend(
            _children(
                root / ".claude" / "worktrees",
                _float_env("LIMEN_RECLAIM_CLAUDE_AGE_H", 24),
                "claude-worktrees",
            )
        )

    if _flag("LIMEN_RECLAIM_AGY_SCRATCH", broad_default):
        agy_scratch = Path(
            os.environ.get("LIMEN_AGY_SCRATCH_ROOT", Path.home() / ".gemini" / "antigravity-cli" / "scratch")
        )
        targets.extend(
            _children(
                agy_scratch,
                _float_env("LIMEN_AGY_SCRATCH_MIN_IDLE_H", 24),
                "agy-scratch",
            )
        )

    if _flag("LIMEN_RECLAIM_REPO_LOCAL_WT", broad_default):
        repo_age = _float_env("LIMEN_RECLAIM_REPO_LOCAL_AGE_H", 24)
        for repo_root in _discover_repo_local_roots(root):
            targets.extend(_children(repo_root, repo_age, f"repo-local:{repo_root}"))

    if _flag("LIMEN_RECLAIM_REGISTERED_WT", broad_default):
        registered_age = _float_env("LIMEN_RECLAIM_REGISTERED_AGE_H", 24)
        targets.extend(
            WorktreeTarget(path=path, min_age_h=registered_age, source="registered-worktree")
            for path in sorted(_registered_repo_roots(root))
            if path.is_dir()
        )

    return _dedupe_targets(targets)
