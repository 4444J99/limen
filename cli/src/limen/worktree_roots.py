from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class WorktreeTarget:
    path: Path
    min_age_h: float
    source: str


class WorktreeInventoryError(RuntimeError):
    """A configured lifecycle root could not be enumerated completely."""


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


def _existing_ancestor(path: Path) -> Path | None:
    probe = path.expanduser()
    for _ in range(64):
        try:
            probe.stat()
            return probe
        except FileNotFoundError:
            parent = probe.parent
            if parent == probe:
                return None
            probe = parent
        except OSError:
            return None
    return None


def _filesystem_device(path: Path) -> int | None:
    probe = _existing_ancestor(path)
    if probe is None:
        return None
    try:
        return int(probe.stat().st_dev)
    except (OSError, TypeError, ValueError):
        return None


def dispatch_clone_cache_root() -> Path | None:
    """Same-device sibling cache for repositories hydrated by local dispatch.

    Keeping it beside, rather than below, the worktree root prevents repository clones from being
    mistaken for linked worktrees. ``iter_worktree_targets`` explicitly owns each flat cache child,
    so these clones remain visible to exact-zero accounting and the accepted reaper.
    """
    worktrees = effective_worktree_root().expanduser()
    parent = worktrees.parent
    worktree_device = _filesystem_device(worktrees)
    parent_device = _filesystem_device(parent)
    if worktree_device is None or parent_device is None or worktree_device != parent_device:
        return None
    return parent / f".{worktrees.name}-repo-cache"


def _inventory_is_dir(path: Path, *, strict: bool, source: str) -> bool:
    """Return whether ``path`` is a directory, preserving inventory faults in strict mode."""
    try:
        return stat.S_ISDIR(path.stat().st_mode)
    except FileNotFoundError:
        return False
    except OSError as exc:
        if strict:
            raise WorktreeInventoryError(f"cannot stat {source} {path}: {exc}") from exc
        return False


def _dedupe_targets(targets: Iterable[WorktreeTarget], *, strict: bool = False) -> list[WorktreeTarget]:
    seen: set[str] = set()
    out: list[WorktreeTarget] = []
    for target in targets:
        try:
            key = str(target.path.resolve())
        except OSError as exc:
            if strict:
                raise WorktreeInventoryError(f"cannot resolve worktree target {target.path}: {exc}") from exc
            key = str(target.path)
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out


def _children(root: Path, min_age_h: float, source: str, *, strict: bool = False) -> list[WorktreeTarget]:
    if not _inventory_is_dir(root, strict=strict, source=source):
        return []
    try:
        children = sorted(root.iterdir())
    except OSError as exc:
        if strict:
            raise WorktreeInventoryError(f"cannot enumerate {source} {root}: {exc}") from exc
        return []
    return [
        WorktreeTarget(path=path, min_age_h=min_age_h, source=source)
        for path in children
        if _inventory_is_dir(path, strict=strict, source=f"child of {source}")
    ]


def _discover_repo_local_roots(limen_root: Path, *, strict: bool = False) -> list[Path]:
    explicit = _path_list("LIMEN_RECLAIM_REPO_LOCAL_ROOTS", [])
    roots = [path for path in explicit if _inventory_is_dir(path, strict=strict, source="explicit repo-local root")]
    workspace_roots = _path_list("LIMEN_RECLAIM_WORKSPACE_ROOTS", [Path.home() / "Workspace"])
    max_depth = _int_env("LIMEN_RECLAIM_WORKSPACE_MAX_DEPTH", 5)

    def walk(path: Path, depth: int) -> None:
        if depth > max_depth or not _inventory_is_dir(path, strict=strict, source="workspace discovery root"):
            return
        try:
            children = sorted(path.iterdir())
        except OSError as exc:
            if strict:
                raise WorktreeInventoryError(f"cannot enumerate workspace discovery root {path}: {exc}") from exc
            return
        for child in children:
            if not _inventory_is_dir(child, strict=strict, source="workspace discovery child"):
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
    if _inventory_is_dir(local, strict=strict, source="limen repo-local root"):
        roots.append(local)

    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        try:
            key = str(root.resolve())
        except OSError as exc:
            if strict:
                raise WorktreeInventoryError(f"cannot resolve repo-local root {root}: {exc}") from exc
            key = str(root)
        if key in seen:
            continue
        seen.add(key)
        out.append(root)
    return out


def _git_worktree_paths(repo: Path, *, strict: bool = False) -> list[Path]:
    try:
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        if strict:
            raise WorktreeInventoryError(f"git worktree inventory failed for {repo}: {exc}") from exc
        return []
    if proc.returncode != 0:
        if strict:
            detail = proc.stderr.strip() or f"exit {proc.returncode}"
            raise WorktreeInventoryError(f"git worktree inventory failed for {repo}: {detail}")
        return []
    paths: list[Path] = []
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            paths.append(Path(line.split(" ", 1)[1]))
    return paths


def _registered_repo_roots(limen_root: Path, *, strict: bool = False) -> list[Path]:
    default_repos = [limen_root]
    portvs = Path.home() / "Workspace" / "4444J99" / "portvs"
    if _inventory_is_dir(portvs, strict=strict, source="default registered repo"):
        default_repos.append(portvs)
    repos = _path_list("LIMEN_RECLAIM_MAIN_REPOS", default_repos)
    roots: list[Path] = []
    for repo in repos:
        if not _inventory_is_dir(repo, strict=strict, source="registered repo"):
            continue
        try:
            repo_resolved = repo.resolve()
        except OSError as exc:
            if strict:
                raise WorktreeInventoryError(f"cannot resolve registered repo {repo}: {exc}") from exc
            repo_resolved = repo
        for path in _git_worktree_paths(repo, strict=strict):
            try:
                if path.resolve() == repo_resolved:
                    continue
            except OSError as exc:
                if strict:
                    raise WorktreeInventoryError(f"cannot resolve registered worktree {path}: {exc}") from exc
            roots.append(path)
    return roots


def _legacy_dispatch_roots(dispatch_root: Path, *, strict: bool = False) -> list[Path]:
    """Historical dispatch roots to scan/reap without making them active creation roots."""
    roots = _path_list("LIMEN_RECLAIM_LEGACY_WORKTREE_ROOTS", [Path.home() / "Workspace" / ".limen-worktrees"])
    out: list[Path] = []
    try:
        dispatch_resolved = dispatch_root.resolve()
    except OSError as exc:
        if strict:
            raise WorktreeInventoryError(f"cannot resolve dispatch root {dispatch_root}: {exc}") from exc
        dispatch_resolved = dispatch_root
    for root in roots:
        if not _inventory_is_dir(root, strict=strict, source="legacy dispatch root"):
            continue
        try:
            if root.resolve() == dispatch_resolved:
                continue
        except OSError as exc:
            if strict:
                raise WorktreeInventoryError(f"cannot resolve legacy dispatch root {root}: {exc}") from exc
        out.append(root)
    return out


def iter_worktree_targets(limen_root: Path | None = None, *, strict: bool = False) -> list[WorktreeTarget]:
    """Enumerate lifecycle targets.

    The accepted reaper uses the default best-effort mode so one unavailable auxiliary root cannot
    stop cleanup of healthy roots. Admission and fixed-point completion use ``strict=True``: an
    unreadable configured scope or failed registered-repo query means inventory is incomplete and
    must block new local creation or a false zero-debt verdict.
    """
    root = limen_root or Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))

    targets: list[WorktreeTarget] = []
    dispatch_root = effective_worktree_root()
    targets.extend(
        _children(
            dispatch_root,
            _float_env("LIMEN_RECLAIM_MIN_AGE_H", 6),
            "dispatch-root",
            strict=strict,
        )
    )
    clone_cache = dispatch_clone_cache_root()
    if clone_cache is not None:
        targets.extend(
            _children(
                clone_cache,
                _float_env("LIMEN_RECLAIM_MIN_AGE_H", 6),
                "dispatch-clone-cache",
                strict=strict,
            )
        )
    broad_default = "LIMEN_WORKTREE_ROOT" not in os.environ

    if _flag("LIMEN_RECLAIM_LEGACY_DISPATCH_WT", broad_default):
        legacy_age = _float_env("LIMEN_RECLAIM_LEGACY_DISPATCH_AGE_H", _float_env("LIMEN_RECLAIM_MIN_AGE_H", 6))
        for legacy_root in _legacy_dispatch_roots(dispatch_root, strict=strict):
            targets.extend(
                _children(
                    legacy_root,
                    legacy_age,
                    f"legacy-dispatch-root:{legacy_root}",
                    strict=strict,
                )
            )

    if _flag("LIMEN_RECLAIM_CLAUDE_WT", True):
        targets.extend(
            _children(
                root / ".claude" / "worktrees",
                _float_env("LIMEN_RECLAIM_CLAUDE_AGE_H", 24),
                "claude-worktrees",
                strict=strict,
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
                strict=strict,
            )
        )

    if _flag("LIMEN_RECLAIM_REPO_LOCAL_WT", broad_default):
        repo_age = _float_env("LIMEN_RECLAIM_REPO_LOCAL_AGE_H", 24)
        for repo_root in _discover_repo_local_roots(root, strict=strict):
            targets.extend(_children(repo_root, repo_age, f"repo-local:{repo_root}", strict=strict))

    if _flag("LIMEN_RECLAIM_REGISTERED_WT", broad_default):
        registered_age = _float_env("LIMEN_RECLAIM_REGISTERED_AGE_H", 24)
        targets.extend(
            WorktreeTarget(path=path, min_age_h=registered_age, source="registered-worktree")
            for path in sorted(_registered_repo_roots(root, strict=strict))
            if _inventory_is_dir(path, strict=strict, source="registered worktree")
        )

    return _dedupe_targets(targets, strict=strict)
