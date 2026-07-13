from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.worktree_roots import (
    WorktreeInventoryError,
    WorktreeTarget,
    _children,
    _dedupe_targets,
    _discover_repo_local_roots,
    _flag,
    _float_env,
    _git_worktree_paths,
    _int_env,
    _legacy_dispatch_roots,
    _path_list,
    _registered_repo_roots,
    dispatch_clone_cache_root,
    iter_worktree_targets,
)


# ---------------------------------------------------------------- helpers
def test_flag_default_true():
    assert _flag("UNSET_VAR_THAT_DOES_NOT_EXIST", True) is True


def test_flag_default_false():
    assert _flag("UNSET_VAR_THAT_DOES_NOT_EXIST", False) is False


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("1", True),
        ("true", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_flag_variants(monkeypatch, raw, expected):
    monkeypatch.setenv("TEST_FLAG", raw)
    assert _flag("TEST_FLAG", True) is expected


def test_float_env_missing(monkeypatch):
    monkeypatch.delenv("TEST_FLOAT", raising=False)
    assert _float_env("TEST_FLOAT", 3.5) == 3.5


def test_float_env_set(monkeypatch):
    monkeypatch.setenv("TEST_FLOAT", "7.25")
    assert _float_env("TEST_FLOAT", 3.5) == 7.25


def test_float_env_bad_value(monkeypatch):
    monkeypatch.setenv("TEST_FLOAT", "not-a-float")
    assert _float_env("TEST_FLOAT", 3.5) == 3.5


def test_int_env_missing(monkeypatch):
    monkeypatch.delenv("TEST_INT", raising=False)
    assert _int_env("TEST_INT", 42) == 42


def test_int_env_set(monkeypatch):
    monkeypatch.setenv("TEST_INT", "99")
    assert _int_env("TEST_INT", 42) == 99


def test_int_env_bad_value(monkeypatch):
    monkeypatch.setenv("TEST_INT", "boom")
    assert _int_env("TEST_INT", 42) == 42


def test_path_list_missing(monkeypatch):
    monkeypatch.delenv("TEST_PATHS", raising=False)
    result = _path_list("TEST_PATHS", [Path("/a"), Path("/b")])
    assert result == [Path("/a"), Path("/b")]


def test_path_list_set(monkeypatch):
    monkeypatch.setenv("TEST_PATHS", "/foo:/bar/baz")
    result = _path_list("TEST_PATHS", [])
    assert Path("/foo") in result
    assert Path("/bar/baz") in result


def test_path_list_skips_empty_parts(monkeypatch):
    monkeypatch.setenv("TEST_PATHS", "/a::/b")
    result = _path_list("TEST_PATHS", [])
    assert result == [Path("/a"), Path("/b")]


# ---------------------------------------------------------------- _dedupe_targets
def test_dedupe_targets_deduplicates_by_resolved_path(tmp_path):
    a = tmp_path / "alpha"
    b = tmp_path / "beta"
    a.mkdir()
    b.mkdir()
    link = tmp_path / "link-to-alpha"
    try:
        link.symlink_to(a)
        has_symlink = True
    except OSError:
        has_symlink = False

    targets = [
        WorktreeTarget(path=a, min_age_h=1.0, source="src1"),
        WorktreeTarget(path=a, min_age_h=2.0, source="src2"),
        WorktreeTarget(path=b, min_age_h=1.0, source="src1"),
    ]
    if has_symlink:
        targets.append(WorktreeTarget(path=link, min_age_h=1.0, source="symlink"))
    deduped = _dedupe_targets(targets)
    names = {t.path.name for t in deduped}
    assert "beta" in names
    assert "alpha" in names
    # Symlinks resolve to the same path as the target, so still 2
    assert len(deduped) == 2


def test_dedupe_preserves_first_source(tmp_path):
    a = tmp_path / "dup"
    a.mkdir()
    targets = [
        WorktreeTarget(path=a, min_age_h=1.0, source="first"),
        WorktreeTarget(path=a, min_age_h=99.0, source="second"),
    ]
    deduped = _dedupe_targets(targets)
    assert len(deduped) == 1
    assert deduped[0].source == "first"


def test_dedupe_empty():
    assert _dedupe_targets([]) == []


# ---------------------------------------------------------------- _children
def test_children_returns_subdirs(tmp_path):
    (tmp_path / "sub1").mkdir()
    (tmp_path / "sub2").mkdir()
    (tmp_path / "file.txt").write_text("")
    kids = _children(tmp_path, 6.0, "test")
    names = {k.path.name for k in kids}
    assert names == {"sub1", "sub2"}
    assert all(k.min_age_h == 6.0 for k in kids)
    assert all(k.source == "test" for k in kids)


def test_children_empty_if_not_dir(tmp_path):
    assert _children(tmp_path / "nonexistent", 1.0, "x") == []


def test_children_handles_permission_denied(monkeypatch, tmp_path):
    def boom(_):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "iterdir", boom)
    assert _children(tmp_path, 1.0, "x") == []


def test_children_permission_denied_is_error_in_strict_inventory(monkeypatch, tmp_path):
    def denied(_path):
        raise PermissionError("configured root is unreadable")

    monkeypatch.setattr(Path, "iterdir", denied)
    with pytest.raises(WorktreeInventoryError, match="cannot enumerate x"):
        _children(tmp_path, 1.0, "x", strict=True)


# ---------------------------------------------------------------- _discover_repo_local_roots
def test_discover_repo_local_roots_finds_worktrees(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_RECLAIM_WORKSPACE_ROOTS", str(tmp_path))
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_ROOTS", "")
    worktrees_dir = tmp_path / "my-proj" / ".worktrees"
    worktrees_dir.mkdir(parents=True)
    roots = _discover_repo_local_roots(tmp_path)
    assert worktrees_dir in roots


def test_discover_repo_local_roots_finds_explicit(tmp_path, monkeypatch):
    explicit = tmp_path / "custom-wt"
    explicit.mkdir()
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_ROOTS", str(explicit))
    monkeypatch.setenv("LIMEN_RECLAIM_WORKSPACE_ROOTS", "")
    roots = _discover_repo_local_roots(tmp_path)
    assert explicit in roots


def test_discover_repo_local_roots_deduplicates(tmp_path, monkeypatch):
    explicit = tmp_path / "same-dir"
    explicit.mkdir()
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_ROOTS", str(explicit))
    monkeypatch.setenv("LIMEN_RECLAIM_WORKSPACE_ROOTS", "")
    roots1 = _discover_repo_local_roots(tmp_path)
    roots2 = _discover_repo_local_roots(tmp_path)
    assert len(roots1) == 1
    assert roots1 == roots2


def test_discover_respects_max_depth(tmp_path, monkeypatch):
    deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / ".worktrees"
    deep.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_RECLAIM_WORKSPACE_ROOTS", str(tmp_path))
    monkeypatch.setenv("LIMEN_RECLAIM_WORKSPACE_MAX_DEPTH", "3")
    roots = _discover_repo_local_roots(tmp_path)
    assert deep not in roots


# ---------------------------------------------------------------- _git_worktree_paths
def test_git_worktree_paths_parses_porcelain(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "init", "--allow-empty"], cwd=tmp_path, check=True)
    wt = tmp_path / "worktree-dir"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "test-branch"], cwd=tmp_path, check=True)
    paths = _git_worktree_paths(tmp_path)
    assert wt in paths


def test_git_worktree_paths_includes_main_and_sibling(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "init", "--allow-empty"], cwd=tmp_path, check=True)
    sibling = tmp_path / "sibling-wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(sibling), "-b", "work/sibling"],
        cwd=tmp_path,
        check=True,
    )
    paths = _git_worktree_paths(tmp_path)
    assert tmp_path in paths
    assert sibling in paths


def test_git_worktree_paths_not_a_repo(tmp_path):
    assert _git_worktree_paths(tmp_path / "nope") == []


def test_git_worktree_paths_failed_configured_repo_is_error_in_strict_mode(tmp_path):
    nonrepo = tmp_path / "configured-but-not-a-repo"
    nonrepo.mkdir()

    assert _git_worktree_paths(nonrepo) == []
    with pytest.raises(WorktreeInventoryError, match="git worktree inventory failed"):
        _git_worktree_paths(nonrepo, strict=True)


# ---------------------------------------------------------------- _registered_repo_roots
def test_registered_repo_roots_finds_sibling_worktrees(tmp_path, monkeypatch):
    main = tmp_path / "main-repo"
    main.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=main, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=main,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=main,
        check=True,
    )
    subprocess.run(["git", "commit", "-qm", "base", "--allow-empty"], cwd=main, check=True)
    sibling = tmp_path / "main-repo-feat"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(sibling), "-b", "work/feat"],
        cwd=main,
        check=True,
    )
    monkeypatch.setenv("LIMEN_RECLAIM_MAIN_REPOS", str(main))
    roots = _registered_repo_roots(tmp_path)
    assert sibling in roots


def test_registered_repo_roots_none_found(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_RECLAIM_MAIN_REPOS", str(tmp_path / "no-exist"))
    assert _registered_repo_roots(tmp_path) == []


# ---------------------------------------------------------------- _legacy_dispatch_roots
def test_legacy_dispatch_roots_skips_current_dispatch_root(tmp_path, monkeypatch):
    dispatch = tmp_path / "scratch" / "limen-worktrees"
    legacy = tmp_path / "Workspace" / ".limen-worktrees"
    dispatch.mkdir(parents=True)
    legacy.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_RECLAIM_LEGACY_WORKTREE_ROOTS", f"{dispatch}:{legacy}")

    roots = _legacy_dispatch_roots(dispatch)

    assert legacy in roots
    assert dispatch not in roots


# ---------------------------------------------------------------- iter_worktree_targets
def test_iter_worktree_targets_dispatch_root_children(tmp_path, monkeypatch):
    dispatch = tmp_path / ".limen-worktrees"
    wt = dispatch / "active-task"
    wt.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(dispatch))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "1")
    targets = iter_worktree_targets(tmp_path)
    names = {t.path.name for t in targets}
    assert "active-task" in names


def test_dispatch_clone_cache_root_requires_same_device_parent(tmp_path, monkeypatch):
    worktrees = tmp_path / "scratch" / "worktrees"
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setattr(
        "limen.worktree_roots._filesystem_device",
        lambda path: 2 if path == worktrees else 1,
    )
    assert dispatch_clone_cache_root() is None


def test_iter_worktree_targets_owns_flat_dispatch_clone_cache_children(tmp_path, monkeypatch):
    dispatch = tmp_path / "worktrees"
    cache = tmp_path / ".worktrees-repo-cache"
    clone = cache / "owner--repo-deadbeef"
    dispatch.mkdir()
    clone.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(dispatch))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "2")

    targets = iter_worktree_targets(tmp_path)
    target = next(item for item in targets if item.path == clone)
    assert target.source == "dispatch-clone-cache"
    assert target.min_age_h == 2.0


def test_inventory_modes_diverge_on_unreadable_configured_dispatch_root(tmp_path, monkeypatch):
    dispatch = tmp_path / ".limen-worktrees"
    dispatch.mkdir()
    original_iterdir = Path.iterdir

    def deny_dispatch(path: Path):
        if path == dispatch:
            raise PermissionError("configured dispatch root is unreadable")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", deny_dispatch)
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(dispatch))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")

    # Operational reaping remains best-effort and can still drain every readable scope.
    assert iter_worktree_targets(tmp_path) == []
    # Admission cannot prove the inventory is empty, so the strict mode preserves the fault.
    with pytest.raises(WorktreeInventoryError, match="dispatch-root"):
        iter_worktree_targets(tmp_path, strict=True)


def test_iter_worktree_targets_scans_legacy_dispatch_root_when_scratch_is_default(tmp_path, monkeypatch):
    scratch = tmp_path / "Scratch" / "limen-worktrees"
    legacy = tmp_path / "Workspace" / ".limen-worktrees"
    (scratch / "new-task").mkdir(parents=True)
    (legacy / "old-task").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LIMEN_WORKTREE_ROOT", raising=False)
    monkeypatch.setenv("LIMEN_WORKTREES", str(scratch))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_AGY_SCRATCH", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")

    targets = iter_worktree_targets(tmp_path)
    by_name = {target.path.name: target for target in targets}

    assert by_name["new-task"].source == "dispatch-root"
    assert by_name["old-task"].source.startswith("legacy-dispatch-root:")


def test_iter_worktree_targets_explicit_dispatch_root_suppresses_legacy_default(tmp_path, monkeypatch):
    scratch = tmp_path / "Scratch" / "limen-worktrees"
    legacy = tmp_path / "Workspace" / ".limen-worktrees"
    (scratch / "new-task").mkdir(parents=True)
    (legacy / "old-task").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(scratch))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_AGY_SCRATCH", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")

    names = {target.path.name for target in iter_worktree_targets(tmp_path)}

    assert "new-task" in names
    assert "old-task" not in names


def test_iter_worktree_targets_claude_worktrees(tmp_path, monkeypatch):
    claude_wt = tmp_path / ".claude" / "worktrees"
    (claude_wt / "session-1").mkdir(parents=True)
    dispatch = tmp_path / ".limen-worktrees"
    dispatch.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(dispatch))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "1")
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_AGE_H", "2")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "1")
    targets = iter_worktree_targets(tmp_path)
    names = {t.path.name for t in targets}
    assert "session-1" in names
    session = next(t for t in targets if t.path.name == "session-1")
    assert session.min_age_h == 2.0
    assert session.source == "claude-worktrees"


def test_iter_worktree_targets_agy_scratch_children(tmp_path, monkeypatch):
    agy_scratch = tmp_path / "agy-scratch"
    (agy_scratch / "mirror-mirror").mkdir(parents=True)
    dispatch = tmp_path / ".limen-worktrees"
    dispatch.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(dispatch))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_AGY_SCRATCH", "1")
    monkeypatch.setenv("LIMEN_AGY_SCRATCH_ROOT", str(agy_scratch))
    monkeypatch.setenv("LIMEN_AGY_SCRATCH_MIN_IDLE_H", "3")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")
    targets = iter_worktree_targets(tmp_path)
    target = next(t for t in targets if t.path.name == "mirror-mirror")
    assert target.min_age_h == 3.0
    assert target.source == "agy-scratch"


def test_iter_worktree_targets_deduplicates(tmp_path, monkeypatch):
    dispatch = tmp_path / ".limen-worktrees"
    shared = dispatch / "shared"
    shared.mkdir(parents=True)
    claude_wt = tmp_path / ".claude" / "worktrees"
    claude_wt.mkdir(parents=True)
    # Symlink the same dir under claude worktrees
    try:
        (claude_wt / "shared").symlink_to(shared)
        has_symlink = True
    except OSError:
        has_symlink = False

    if not has_symlink:
        pytest.skip("filesystem does not support symlinks — dedup scenario cannot be constructed")

    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(dispatch))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "1")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "1")
    targets = iter_worktree_targets(tmp_path)
    shared_count = sum(1 for t in targets if t.path.name == "shared")
    assert shared_count == 1
