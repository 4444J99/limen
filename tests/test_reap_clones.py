"""tests/test_reap_clones.py — Automated regression testing suite for reap-clones.py.

Verifies the loss-free clone-reaper tooling and safety gates:
a. Non-restrictive remote reachability query succeeds against standard remotes with HEAD.
b. Reachability fails closed if remote is unreachable or empty bare repo without HEAD.
c. Prevention and diagnosis of the `-h HEAD` defect (empty stdout / exit code 2 when -h is passed).
d. Rejection of unpushed commits (ahead > 0 on main and topic branches).
e. Rejection of dirty working trees (modified tracked files, staged index, untracked files, irreplaceable ignored data).
f. Rejection of stashes (unpushed local-only objects).
g. Detection of linked worktrees to avoid orphan states.
h. Clean dry-run CLI execution without crashes or unrecognized arguments.

Hermetic test suite: Uses synthetic bare git repositories over local filesystem file:// protocol.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ------------------------------------------------------------------------------
# Module Loading
# ------------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
REAP_CLONES_PATH = SCRIPTS_DIR / "reap-clones.py"

_spec = importlib.util.spec_from_file_location("reap_clones", REAP_CLONES_PATH)
reap = importlib.util.module_from_spec(_spec)
sys.modules["reap_clones"] = reap
_spec.loader.exec_module(reap)


# ------------------------------------------------------------------------------
# Synthetic Git Fixture Helpers
# ------------------------------------------------------------------------------
def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_synthetic_repo(tmp_path: Path, name: str = "repo") -> tuple[Path, Path]:
    """Create a bare origin repo and a clone with 1 seed commit pushed."""
    origin = tmp_path / f"{name}_origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
        text=True,
    )
    seed = tmp_path / f"{name}_seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test User")
    _git(seed, "config", "tag.gpgSign", "false")
    (seed / "README.md").write_text("initial commit\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "initial commit")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "-u", "origin", "main")

    clone = tmp_path / name
    subprocess.run(
        ["git", "clone", "-q", str(origin), str(clone)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(clone, "config", "user.email", "test@example.com")
    _git(clone, "config", "user.name", "Test User")
    _git(clone, "config", "tag.gpgSign", "false")
    return clone, origin


def _classify_clone(
    repo: Path,
    *,
    pressure: bool = True,
    age_days: float = 10.0,
    active: set[str] | None = None,
) -> reap.Verdict:
    """Helper to classify clone with custom pressure, age, and active task slugs."""
    now = time.time()
    old = now - age_days * 86400
    os.utime(repo, (old, old))
    return reap.classify(repo, active or set(), now, 2.0, pressure)


# ==============================================================================
# a. Non-restrictive remote reachability query succeeds against standard remotes with HEAD
# ==============================================================================
def test_remote_reachability_succeeds_against_standard_remote(tmp_path: Path) -> None:
    """Verify non-restrictive ls-remote succeeds on a standard repo with origin HEAD."""
    clone, _ = _init_synthetic_repo(tmp_path, "standard_reach")

    # Direct plumbing query verification
    res = subprocess.run(
        ["git", "-C", str(clone), "ls-remote", "--exit-code", "origin", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "HEAD" in res.stdout
    assert len(res.stdout.strip().split()) >= 2  # <sha>\tHEAD

    # confirm_recloneable() must return True
    assert reap.confirm_recloneable(clone) is True


# ==============================================================================
# b. Reachability fails closed if remote is unreachable or empty bare repo without HEAD
# ==============================================================================
def test_remote_reachability_fails_closed_when_origin_deleted(tmp_path: Path) -> None:
    """If origin remote is deleted, confirm_recloneable fails closed (returns False)."""
    clone, origin = _init_synthetic_repo(tmp_path, "deleted_origin")
    shutil.rmtree(origin)

    assert reap.confirm_recloneable(clone) is False


def test_remote_reachability_fails_closed_on_invalid_origin_url(tmp_path: Path) -> None:
    """If origin points to an invalid/non-existent destination, confirm_recloneable returns False."""
    clone, _ = _init_synthetic_repo(tmp_path, "invalid_url")
    _git(clone, "remote", "set-url", "origin", str(tmp_path / "non_existent.git"))

    assert reap.confirm_recloneable(clone) is False


def test_remote_reachability_fails_closed_on_empty_bare_remote_without_head(tmp_path: Path) -> None:
    """An empty bare repo without any commits has no HEAD ref; query must exit 2 and fail closed."""
    clone, _ = _init_synthetic_repo(tmp_path, "empty_remote_test")
    empty_origin = tmp_path / "empty_origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(empty_origin)],
        check=True,
        capture_output=True,
        text=True,
    )
    _git(clone, "remote", "set-url", "origin", str(empty_origin))

    # Query with --exit-code exits 2 when no matching ref exists
    res = subprocess.run(
        ["git", "-C", str(clone), "ls-remote", "--exit-code", "origin", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 2
    assert res.stdout.strip() == ""

    # confirm_recloneable must fail closed
    assert reap.confirm_recloneable(clone) is False


# ==============================================================================
# c. Prevention and diagnosis of the -h HEAD defect
# ==============================================================================
def test_diagnosis_and_prevention_of_minus_h_head_defect(tmp_path: Path) -> None:
    """Diagnose the -h HEAD defect:

    - Passing -h restricts matching to refs/heads/*, excluding root symbolic ref HEAD.
    - git ls-remote -h origin HEAD produces empty output ("").
    - git ls-remote --exit-code -h origin HEAD exits with code 2.
    - git ls-remote --exit-code origin HEAD (without -h) succeeds with exit code 0.
    """
    clone, _ = _init_synthetic_repo(tmp_path, "h_head_defect")

    # 1. Defect: -h without --exit-code exits 0 but produces empty stdout
    res_h = subprocess.run(
        ["git", "-C", str(clone), "ls-remote", "-h", "origin", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_h.returncode == 0
    assert res_h.stdout.strip() == ""  # Defect demonstrated: empty stdout

    # 2. Defect: -h with --exit-code exits 2 because refs/heads/HEAD does not exist
    res_h_exit = subprocess.run(
        ["git", "-C", str(clone), "ls-remote", "--exit-code", "-h", "origin", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_h_exit.returncode == 2
    assert res_h_exit.stdout.strip() == ""

    # 3. Fix: Non-restrictive query (without -h) succeeds with exit 0 and non-empty stdout
    res_fixed = subprocess.run(
        ["git", "-C", str(clone), "ls-remote", "--exit-code", "origin", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res_fixed.returncode == 0
    assert res_fixed.stdout.strip() != ""
    assert "HEAD" in res_fixed.stdout

    # 4. confirm_recloneable() succeeds because it does not pass -h
    assert reap.confirm_recloneable(clone) is True


# ==============================================================================
# d. Rejection of unpushed commits (ahead > 0)
# ==============================================================================
def test_rejection_of_unpushed_commits_on_main(tmp_path: Path) -> None:
    """Unpushed commits on main must be preserved (classified as unpushed-commits)."""
    clone, _ = _init_synthetic_repo(tmp_path, "unpushed_main")
    (clone / "new_work.txt").write_text("unpushed local content\n")
    _git(clone, "add", "new_work.txt")
    _git(clone, "commit", "-qm", "local unpushed commit")

    v = _classify_clone(clone, pressure=True)
    assert v.reap is False
    assert v.reason == "unpushed-commits"
    assert reap.confirm_recloneable(clone) is False


def test_rejection_of_unpushed_commits_on_feature_branch(tmp_path: Path) -> None:
    """Unpushed commits on a feature branch must be preserved."""
    clone, _ = _init_synthetic_repo(tmp_path, "unpushed_branch")
    _git(clone, "checkout", "-q", "-b", "feat/awesome-idea")
    (clone / "feature.txt").write_text("feature content\n")
    _git(clone, "add", "feature.txt")
    _git(clone, "commit", "-qm", "feature branch commit")

    v = _classify_clone(clone, pressure=True)
    assert v.reap is False
    assert v.reason == "unpushed-commits"
    assert reap.confirm_recloneable(clone) is False

    # Once pushed to origin, the rejection is cleared
    _git(clone, "push", "-q", "-u", "origin", "feat/awesome-idea")
    # Switch back or stay, check classification
    v_pushed = _classify_clone(clone, pressure=True)
    assert v_pushed.reap is True
    assert reap.confirm_recloneable(clone) is True


# ==============================================================================
# e. Rejection of dirty working trees
# ==============================================================================
def test_rejection_of_dirty_working_tree_modified_tracked_file(tmp_path: Path) -> None:
    """Uncommitted modifications to tracked files must prevent reaping."""
    clone, _ = _init_synthetic_repo(tmp_path, "dirty_modified")
    (clone / "README.md").write_text("modified uncommitted\n")

    v = _classify_clone(clone, pressure=True)
    assert v.reap is False
    assert v.reason == "dirty-or-untracked"


def test_rejection_of_dirty_working_tree_staged_index(tmp_path: Path) -> None:
    """Staged changes in index must prevent reaping."""
    clone, _ = _init_synthetic_repo(tmp_path, "dirty_staged")
    (clone / "README.md").write_text("modified staged\n")
    _git(clone, "add", "README.md")

    v = _classify_clone(clone, pressure=True)
    assert v.reap is False
    assert v.reason == "dirty-or-untracked"


def test_rejection_of_dirty_working_tree_untracked_file(tmp_path: Path) -> None:
    """Untracked files ('7 genesis screenshots' rule) must prevent reaping."""
    clone, _ = _init_synthetic_repo(tmp_path, "dirty_untracked")
    (clone / "genesis_screenshot.png").write_bytes(b"PNGDATA")

    v = _classify_clone(clone, pressure=True)
    assert v.reap is False
    assert v.reason == "dirty-or-untracked"


def test_rejection_of_irreplaceable_gitignored_data(tmp_path: Path) -> None:
    """Gitignored files that are irreplaceable (.env, *.db, data/) must prevent reaping."""
    clone, _ = _init_synthetic_repo(tmp_path, "ignored_secret")
    (clone / ".gitignore").write_text(".env\n*.db\n")
    _git(clone, "add", ".gitignore")
    _git(clone, "commit", "-qm", "add gitignore")
    _git(clone, "push", "-q", "origin", "main")

    # Create irreplaceable local state
    (clone / ".env").write_text("STRIPE_SECRET=sk_live_123456\n")

    v = _classify_clone(clone, pressure=True)
    assert v.reap is False
    assert v.reason == "ignored-data"


# ==============================================================================
# f. Rejection of stashes (unpushed local-only objects)
# ==============================================================================
def test_rejection_of_stashes(tmp_path: Path) -> None:
    """Local stash entries must prevent reaping (caught by unpushed-objects guard)."""
    clone, _ = _init_synthetic_repo(tmp_path, "stash_test")
    (clone / "README.md").write_text("stashed experiment\n")
    _git(clone, "stash", "push", "-m", "experiment")

    # Working tree is clean according to git status
    status = _git(clone, "status", "--porcelain")
    assert status.stdout.strip() == ""

    # But stash entry exists
    stash_list = _git(clone, "stash", "list")
    assert "stash@{" in stash_list.stdout

    # Must be caught by unpushed-objects guard
    assert reap._has_local_only_objects(clone) is True
    v = _classify_clone(clone, pressure=True)
    assert v.reap is False
    assert v.reason == "unpushed-objects"
    assert reap.confirm_recloneable(clone) is False


# ==============================================================================
# g. Detection of linked worktrees to avoid orphan states
# ==============================================================================
def test_detection_of_linked_worktrees(tmp_path: Path) -> None:
    """Clones with active linked worktrees must not be reaped to prevent orphan worktrees."""
    clone, _ = _init_synthetic_repo(tmp_path, "linked_wt_parent")
    wt_path = tmp_path / "linked_wt_child"
    _git(clone, "worktree", "add", str(wt_path), "-b", "feat/worktree-branch")

    # Nested context guard detects linked worktrees
    reason = reap._nested_context_reason(clone)
    assert reason == "has-linked-worktrees"

    v = _classify_clone(clone, pressure=True)
    assert v.reap is False
    assert v.reason == "has-linked-worktrees"

    # Once worktree is removed and pruned, safety gate clears
    _git(clone, "worktree", "remove", str(wt_path))
    _git(clone, "worktree", "prune")

    assert reap._nested_context_reason(clone) is None
    v_clean = _classify_clone(clone, pressure=True)
    assert v_clean.reap is True


# ==============================================================================
# h. Clean dry-run execution without crashes or unrecognized arguments
# ==============================================================================
def test_dry_run_flag_execution_clean() -> None:
    """reap-clones.py must accept --dry-run without unrecognized argument errors."""
    res = subprocess.run(
        [sys.executable, str(REAP_CLONES_PATH), "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "mode=dry-run" in res.stdout
    assert "[reap-clones]" in res.stdout


def test_dry_run_flag_with_pressure_and_max() -> None:
    """reap-clones.py accepts --dry-run combined with other flags."""
    res = subprocess.run(
        [sys.executable, str(REAP_CLONES_PATH), "--dry-run", "--pressure", "--max", "2"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "mode=dry-run" in res.stdout
    assert "pressure=ON" in res.stdout


def test_dry_run_suppresses_apply() -> None:
    """Passing --dry-run alongside --apply suppresses apply and runs in dry-run mode."""
    res = subprocess.run(
        [sys.executable, str(REAP_CLONES_PATH), "--apply", "--dry-run"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "mode=dry-run" in res.stdout
    assert "WOULD reap" in res.stdout or "would reap" in res.stdout


def test_cli_help_documents_dry_run() -> None:
    """--help output must document the --dry-run flag."""
    res = subprocess.run(
        [sys.executable, str(REAP_CLONES_PATH), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "--dry-run" in res.stdout
