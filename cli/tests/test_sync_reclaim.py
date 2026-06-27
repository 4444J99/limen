"""Tests for the two heal organs:

  scripts/sync-release.sh  — re-converge the daemon checkout to origin/main. The fix under test:
    a DIVERGED history whose local-only commits are ALL already upstream by patch-id (the observed
    "session redid work that already landed" drift) is re-converged loss-free; genuinely-unique
    divergence still stays fail-open (never force-moved).

  scripts/reclaim-worktrees.py — reap provably-dead fleet worktrees (clean + pushed +
    merged-to-default + idle), while keeping dirty / unpushed / unmerged / recently-active ones.

Both run as real subprocesses against throwaway git repos, so the actual shell/Python ships.
"""
import os
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SYNC = ROOT / "scripts" / "sync-release.sh"
RECLAIM = ROOT / "scripts" / "reclaim-worktrees.py"


def _git(*args, cwd, check=True, env=None):
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, env=env)
    if check and r.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} -> {r.returncode}\n{r.stderr}")
    return r


def _init_repo(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", "-b", "main", cwd=path)
    _git("config", "user.email", "t@t", cwd=path)
    _git("config", "user.name", "t", cwd=path)
    return path


def _commit(repo: Path, name: str, content: str, msg: str):
    (repo / name).write_text(content)
    _git("add", name, cwd=repo)
    _git("commit", "-q", "-m", msg, cwd=repo)
    return _git("rev-parse", "HEAD", cwd=repo).stdout.strip()


@pytest.fixture
def checkout(tmp_path):
    """A bare 'origin' + a clone on main tracking origin/main, with one shared base commit."""
    origin = _init_repo(tmp_path / "src")
    _commit(origin, "base.txt", "base\n", "base")
    bare = tmp_path / "origin.git"
    _git("clone", "-q", "--bare", str(origin), str(bare), cwd=tmp_path)
    clone = tmp_path / "clone"
    _git("clone", "-q", str(bare), str(clone), cwd=tmp_path)
    _git("config", "user.email", "t@t", cwd=clone)
    _git("config", "user.name", "t", cwd=clone)
    return clone, bare


def _run_sync(clone: Path):
    env = {**os.environ, "LIMEN_ROOT": str(clone), "LIMEN_RELEASE_BRANCH": "main",
           "HOME": str(clone.parent)}
    return subprocess.run(["bash", str(SYNC)], capture_output=True, text=True, env=env)


def _origin_advance(bare: Path, tmp_path: Path, name, content, msg):
    """Land a commit on origin/main by pushing from a scratch clone, return its sha."""
    scratch = tmp_path / f"scratch-{name}"
    _git("clone", "-q", str(bare), str(scratch), cwd=tmp_path)
    _git("config", "user.email", "t@t", cwd=scratch)
    _git("config", "user.name", "t", cwd=scratch)
    sha = _commit(scratch, name, content, msg)
    _git("push", "-q", "origin", "main", cwd=scratch)
    return sha


def test_behind_fast_forwards(checkout, tmp_path):
    clone, bare = checkout
    sha = _origin_advance(bare, tmp_path, "f.txt", "feature\n", "feat")
    r = _run_sync(clone)
    assert r.returncode == 0
    assert _git("rev-parse", "HEAD", cwd=clone).stdout.strip() == sha
    assert "ff" in r.stdout or "release deployed" in r.stdout


def test_identical_noop(checkout, tmp_path):
    clone, bare = checkout
    r = _run_sync(clone)
    assert "at release" in r.stdout


def test_diverged_but_all_upstream_reconverges(checkout, tmp_path):
    """Local replays the SAME change that also landed upstream (different SHA, equal patch-id).
    Diverged, but nothing unique to lose -> must re-converge to origin."""
    clone, bare = checkout
    up_sha = _origin_advance(bare, tmp_path, "shared.txt", "the-change\n", "land upstream")
    # local makes the identical change as its own commit (diverges, but patch-id matches upstream)
    (clone / "shared.txt").write_text("the-change\n")
    _git("add", "shared.txt", cwd=clone)
    _git("commit", "-q", "-m", "redo the same work locally", cwd=clone)
    # daemon-owned runtime that must survive
    (clone / "tasks.yaml").write_text("live: queue\n")
    (clone / "usage.json").write_text("{}\n")  # untracked runtime
    assert _git("rev-parse", "HEAD", cwd=clone).stdout.strip() != up_sha
    r = _run_sync(clone)
    assert r.returncode == 0
    assert _git("rev-parse", "HEAD", cwd=clone).stdout.strip() == up_sha, r.stdout + r.stderr
    assert "re-converged" in r.stdout
    assert (clone / "tasks.yaml").read_text() == "live: queue\n"  # live queue preserved
    assert (clone / "usage.json").exists()  # untracked runtime untouched


def test_diverged_with_unique_work_fails_open(checkout, tmp_path):
    """A genuinely-unique local commit must NEVER be force-moved away."""
    clone, bare = checkout
    _origin_advance(bare, tmp_path, "up.txt", "upstream-only\n", "upstream")
    local_sha = _commit(clone, "mine.txt", "unique-local-work\n", "unique local")
    r = _run_sync(clone)
    assert r.returncode == 0
    assert _git("rev-parse", "HEAD", cwd=clone).stdout.strip() == local_sha  # unchanged
    assert "UNIQUE local work" in r.stdout
    assert (clone / "mine.txt").exists()


def test_untracked_collision_with_release_is_cleared(checkout, tmp_path):
    """An UNTRACKED local file colliding with a path the release now TRACKS must not block the ff:
    the released version wins, the stale local copy is backed up (never lost), and untracked runtime
    the release does NOT track is left untouched. (The .claude/settings.json drift, 2026-06-24.)"""
    clone, bare = checkout
    sha = _origin_advance(bare, tmp_path, "conf.json", "RELEASE\n", "release adds conf.json")
    # that same path exists locally UNTRACKED with stale content -> would block a naive ff
    (clone / "conf.json").write_text("LOCAL-STALE\n")
    # untracked runtime the release does NOT track -> must be left alone (the no-`git add -A` invariant)
    (clone / "usage.json").write_text("{}\n")
    r = _run_sync(clone)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git("rev-parse", "HEAD", cwd=clone).stdout.strip() == sha, r.stdout  # ff happened
    assert (clone / "conf.json").read_text() == "RELEASE\n"  # released version won
    backup = clone / "logs" / ".sync-collision" / "conf.json"
    assert backup.exists() and backup.read_text() == "LOCAL-STALE\n", r.stdout  # backed up, not lost
    assert (clone / "usage.json").exists()  # untracked non-release runtime untouched


# ---------------- reclaim-worktrees.py ----------------

def _wt_root_with(tmp_path):
    """Build a parent repo (pushed to a bare origin) and a worktree root holding several worktrees."""
    origin = _init_repo(tmp_path / "proj")
    _commit(origin, "a.txt", "a\n", "init")
    bare = tmp_path / "proj.git"
    _git("clone", "-q", "--bare", str(origin), str(bare), cwd=tmp_path)
    main = tmp_path / "proj-main"
    _git("clone", "-q", str(bare), str(main), cwd=tmp_path)
    _git("config", "user.email", "t@t", cwd=main)
    _git("config", "user.name", "t", cwd=main)
    wtroot = tmp_path / ".limen-worktrees"
    wtroot.mkdir()
    return main, bare, wtroot


def _add_wt(main: Path, wtroot: Path, name: str, branch_from="origin/main"):
    path = wtroot / name
    _git("worktree", "add", "-q", "--detach", str(path), branch_from, cwd=main)
    return path


def _run_reclaim(wtroot: Path, limen_root: Path, apply=True):
    env = {**os.environ, "LIMEN_WORKTREE_ROOT": str(wtroot), "LIMEN_ROOT": str(limen_root),
           "LIMEN_RECLAIM_MIN_AGE_H": "1", "LIMEN_RECLAIM_EVERY_MIN": "0"}
    args = ["python3", str(RECLAIM)]
    if apply:
        args += ["--apply", "--force"]
    return subprocess.run(args, capture_output=True, text=True, env=env)


def _age(path: Path, hours: float):
    t = time.time() - hours * 3600
    os.utime(path, (t, t))


def test_reclaim_removes_clean_pushed_idle(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    dead = _add_wt(main, wtroot, "dead-task")  # clean, on origin/main, will be aged
    _age(dead, 5)
    (main / "logs").mkdir(exist_ok=True)
    r = _run_reclaim(wtroot, main, apply=True)
    assert r.returncode == 0, r.stderr
    assert not dead.exists(), r.stdout
    assert "reclaimed" in r.stdout


def test_reclaim_keeps_dirty_unpushed_and_active(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    (main / "logs").mkdir(exist_ok=True)

    dirty = _add_wt(main, wtroot, "dirty")
    _age(dirty, 5)
    (dirty / "scratch.txt").write_text("uncommitted\n")  # untracked -> dirty

    unpushed = _add_wt(main, wtroot, "unpushed")
    _git("checkout", "-q", "-b", "feat", cwd=unpushed)
    (unpushed / "new.txt").write_text("x\n")
    _git("add", "new.txt", cwd=unpushed)
    _git("commit", "-q", "-m", "unpushed", cwd=unpushed)
    _age(unpushed, 5)

    active = _add_wt(main, wtroot, "active")  # clean+pushed but freshly touched (recent mtime)

    r = _run_reclaim(wtroot, main, apply=True)
    assert r.returncode == 0, r.stderr
    assert dirty.exists() and unpushed.exists() and active.exists(), r.stdout
    assert "dirty" in r.stdout and "unpushed-commits" in r.stdout and "active" in r.stdout


def test_reclaim_keeps_clean_pushed_unmerged_branch(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    (main / "logs").mkdir(exist_ok=True)

    branch = _add_wt(main, wtroot, "pushed-unmerged")
    _git("checkout", "-q", "-b", "feature", cwd=branch)
    _commit(branch, "feature.txt", "unique work\n", "feature")
    _git("push", "-q", "origin", "HEAD:feature", cwd=branch)
    _age(branch, 5)

    r = _run_reclaim(wtroot, main, apply=True)

    assert r.returncode == 0, r.stderr
    assert branch.exists(), r.stdout
    assert "not-merged-to-default" in r.stdout


def test_reclaim_dry_run_removes_nothing(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    dead = _add_wt(main, wtroot, "dead")
    _age(dead, 5)
    (main / "logs").mkdir(exist_ok=True)
    r = _run_reclaim(wtroot, main, apply=False)
    assert r.returncode == 0
    assert dead.exists()  # dry-run never deletes
    assert "dry-run" in r.stdout
