from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from limen.worktree_initialization import (
    WORKTREE_INITIALIZATION_SCHEMA,
    WorktreeInitializationError,
    initialize_worktree,
)


def _repo(root: Path) -> Path:
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    return root


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_transactional_initialization_publishes_exact_clean_checkout(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    final = tmp_path / "published"
    expected = _git(repo, "rev-parse", "HEAD").stdout.strip()

    result = initialize_worktree(
        repo,
        final,
        branch="work/fixture",
        checkout_ref="main",
        task_id="FIXTURE",
    )

    assert result.receipt["schema"] == WORKTREE_INITIALIZATION_SCHEMA
    assert result.receipt["state"] == "published"
    assert result.receipt["same_filesystem"] is True
    assert result.receipt["staging_validation"] == result.receipt["final_validation"]
    assert result.expected_head == expected
    assert final.exists()
    assert not result.staging_path.exists()
    assert _git(final, "rev-parse", "HEAD").stdout.strip() == expected
    assert _git(final, "status", "--porcelain").stdout == ""
    assert str(final) in _git(repo, "worktree", "list", "--porcelain").stdout
    assert json.loads(result.journal_path.read_text(encoding="utf-8"))["state"] == "published"


def test_staging_validation_failure_is_typed_and_preserves_dirty_root(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    final = tmp_path / "published"

    def dirty_staging(phase: str, path: Path) -> None:
        if phase == "validate-staging":
            (path / "untracked.txt").write_text("preserve me\n", encoding="utf-8")

    with pytest.raises(WorktreeInitializationError) as raised:
        initialize_worktree(
            repo,
            final,
            branch="work/dirty",
            checkout_ref="main",
            task_id="DIRTY",
            phase_hook=dirty_staging,  # type: ignore[arg-type]
        )

    error = raised.value
    assert error.receipt["state"] == "crashed"
    assert error.receipt["phase"] == "validate-staging"
    assert error.receipt["crash"]["code"] == "worktree-has-untracked-paths"
    staging = Path(error.receipt["staging_path"])
    assert (staging / "untracked.txt").read_text(encoding="utf-8") == "preserve me\n"
    assert not final.exists()


def test_crash_after_atomic_move_preserves_published_root_and_typed_phase(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    final = tmp_path / "published"

    def crash_after_move(phase: str, _path: Path) -> None:
        if phase == "move":
            raise RuntimeError("fixture-crash-after-move")

    with pytest.raises(WorktreeInitializationError) as raised:
        initialize_worktree(
            repo,
            final,
            branch="work/move-crash",
            checkout_ref="main",
            task_id="MOVE-CRASH",
            phase_hook=crash_after_move,  # type: ignore[arg-type]
        )

    error = raised.value
    assert error.receipt["state"] == "crashed"
    assert error.receipt["phase"] == "move"
    assert error.receipt["crash"]["code"] == "fixture-crash-after-move"
    assert final.exists()
    assert (final / "tracked.txt").read_text(encoding="utf-8") == "tracked\n"
    assert not Path(error.receipt["staging_path"]).exists()


def test_existing_final_path_fails_before_git_add_and_is_not_removed(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    final = tmp_path / "published"
    final.mkdir()
    sentinel = final / "owner.txt"
    sentinel.write_text("owner\n", encoding="utf-8")

    with pytest.raises(WorktreeInitializationError) as raised:
        initialize_worktree(
            repo,
            final,
            branch="work/collision",
            checkout_ref="main",
            task_id="COLLISION",
        )

    assert raised.value.receipt["state"] == "crashed"
    assert raised.value.receipt["phase"] == "preflight"
    assert raised.value.receipt["crash"]["code"] == "final-path-already-exists"
    assert sentinel.read_text(encoding="utf-8") == "owner\n"
    assert _git(repo, "show-ref", "--verify", "refs/heads/work/collision").returncode != 0


def test_branch_collision_records_add_phase_without_deleting_existing_branch(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "repo")
    subprocess.run(["git", "-C", str(repo), "branch", "work/existing"], check=True)

    with pytest.raises(WorktreeInitializationError) as raised:
        initialize_worktree(
            repo,
            tmp_path / "published",
            branch="work/existing",
            checkout_ref="main",
            task_id="BRANCH-COLLISION",
        )

    assert raised.value.receipt["state"] == "crashed"
    assert raised.value.receipt["phase"] == "add"
    assert raised.value.receipt["crash"]["code"] == "worktree-add-failed"
    assert _git(repo, "show-ref", "--verify", "refs/heads/work/existing").returncode == 0
