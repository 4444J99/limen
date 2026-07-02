"""test_reap_clones.py — proves the clone-reap gate is LOSS-FREE.

The organ deletes clones autonomically, so a wrong 'reap' verdict destroys work. These tests build
real git repos (a bare 'origin' + clones) and assert the gate reaps ONLY a pure pushed mirror and
KEEPS every clone with unpushed commits, untracked/dirty files, an active task, core status, no
origin, or (absent disk pressure) a fresh mtime. This is the executable predicate for the organ.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location("reap_clones", SCRIPTS / "reap-clones.py")
reap = importlib.util.module_from_spec(_spec)
sys.modules["reap_clones"] = reap  # dataclass needs the module discoverable during exec
_spec.loader.exec_module(reap)


# ---------------------------------------------------------------- git helpers
def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


def _init_origin_and_clone(tmp: Path, name: str) -> Path:
    """A bare origin with one pushed commit, cloned into tmp/name — a PURE PUSHED MIRROR."""
    origin = tmp / f"{name}.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    seed = tmp / f"{name}-seed"
    seed.mkdir()
    _git(seed, "init", "-q", "-b", "main")
    _git(seed, "config", "user.email", "t@t.t")
    _git(seed, "config", "user.name", "t")
    _git(seed, "remote", "add", "origin", str(origin))
    (seed / "README.md").write_text("hello\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "seed")
    _git(seed, "push", "-q", "-u", "origin", "main")
    clone = tmp / name
    subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True, capture_output=True)
    _git(clone, "config", "user.email", "t@t.t")
    _git(clone, "config", "user.name", "t")
    return clone


def _verdict(repo: Path, *, active=None, idle_days=2.0, pressure=False, age_days=None):
    now = time.time()
    if age_days is not None:  # backdate the repo dir mtime to simulate idle age
        old = now - age_days * 86400
        os.utime(repo, (old, old))
    return reap.classify(repo, active or set(), now, idle_days, pressure)


# ---------------------------------------------------------------- the loss-free gate
def test_pure_pushed_mirror_is_reaped_when_idle(tmp_path):
    clone = _init_origin_and_clone(tmp_path, "mirror")
    v = _verdict(clone, age_days=10)
    assert v.reap is True
    assert v.reason == "pushed-mirror"


def test_fresh_mirror_is_kept_without_pressure(tmp_path):
    clone = _init_origin_and_clone(tmp_path, "fresh")
    v = _verdict(clone, age_days=0)  # just touched
    assert v.reap is False
    assert v.reason == "fresh"


def test_fresh_mirror_is_reaped_under_pressure(tmp_path):
    clone = _init_origin_and_clone(tmp_path, "freshpress")
    v = _verdict(clone, age_days=0, pressure=True)
    assert v.reap is True
    assert v.reason == "pushed-mirror-under-pressure"


def test_unpushed_commit_is_never_reaped(tmp_path):
    clone = _init_origin_and_clone(tmp_path, "unpushed")
    (clone / "local.txt").write_text("local work\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "unpushed local commit")
    v = _verdict(clone, age_days=99, pressure=True)  # even old + under pressure
    assert v.reap is False
    assert v.reason == "unpushed-commits"


def test_untracked_file_is_never_reaped(tmp_path):
    """The '7 genesis screenshots' rule: hand-dropped untracked files are DATA, never deleted."""
    clone = _init_origin_and_clone(tmp_path, "untracked")
    (clone / "genesis-screenshot.png").write_text("pretend image bytes\n")
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "dirty-or-untracked"


def test_dirty_tracked_edit_is_never_reaped(tmp_path):
    clone = _init_origin_and_clone(tmp_path, "dirty")
    (clone / "README.md").write_text("edited, uncommitted\n")
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "dirty-or-untracked"


def test_active_task_repo_is_kept(tmp_path):
    clone = _init_origin_and_clone(tmp_path, "activerepo")
    slug = reap.origin_slug(clone)
    v = _verdict(clone, active={slug}, age_days=99)
    assert v.reap is False
    assert v.reason == "active-task"


def test_core_repo_is_kept(tmp_path, monkeypatch):
    clone = _init_origin_and_clone(tmp_path, "coremerepo")
    monkeypatch.setattr(reap, "CORE", {"coremerepo"})
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "core"


def test_live_root_is_kept(tmp_path, monkeypatch):
    clone = _init_origin_and_clone(tmp_path, "liveroot")
    monkeypatch.setattr(reap, "LIMEN_ROOT", clone.resolve())
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "live-root"


def test_registered_worktree_is_not_a_clone(tmp_path):
    """A linked worktree has a .git FILE — reap-clones must never rmtree it (worktree reaper owns it)."""
    clone = _init_origin_and_clone(tmp_path, "wtparent")
    wt = tmp_path / "wt-linked"
    _git(clone, "worktree", "add", "-q", str(wt), "-b", "sidebranch")
    assert (wt / ".git").is_file()  # sanity: linked worktrees use a .git file
    v = _verdict(wt, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "not-a-clone"


def test_no_origin_repo_is_kept(tmp_path):
    """A local-only repo (no canonical home) can't be re-cloned — never reaped."""
    repo = tmp_path / "orphan"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t.t")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("x\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "local only")
    v = _verdict(repo, age_days=99, pressure=True)
    assert v.reap is False
    # its own commits are on no remote → caught by the push guard before the origin check
    assert v.reason in {"unpushed-commits", "no-origin", "head-not-on-remote"}


def test_confirm_recloneable_true_when_origin_holds_head(tmp_path):
    clone = _init_origin_and_clone(tmp_path, "reachable")
    assert reap.confirm_recloneable(clone) is True


def _advance_origin(tmp_path: Path, name: str, msg: str) -> None:
    """Push a new commit to origin/main via the seed working copy, leaving the clone BEHIND."""
    seed = tmp_path / f"{name}-seed"
    (seed / "more.txt").write_text(msg + "\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", msg)
    _git(seed, "push", "-q", "origin", "main")


def test_confirm_recloneable_true_when_behind_origin(tmp_path):
    """A pure mirror merely BEHIND origin (the fleet advanced the branch) is STILL re-cloneable — the
    belt must not require HEAD to be a current tip. This is the remote-unreachable=80 regression: exact-
    tip matching stranded several GB of behind-origin mirrors that re-clone would trivially restore."""
    clone = _init_origin_and_clone(tmp_path, "behind")
    _advance_origin(tmp_path, "behind", "origin advances past the clone")
    # clone HEAD is now an ANCESTOR of origin/main, not a tip — must still be re-cloneable
    assert reap.confirm_recloneable(clone) is True


def test_behind_origin_mirror_is_reaped_end_to_end(tmp_path):
    """classify() + belt together: a clean clone behind origin/main reaps as a pushed mirror."""
    clone = _init_origin_and_clone(tmp_path, "behindfull")
    _advance_origin(tmp_path, "behindfull", "fleet moved main forward")
    v = _verdict(clone, age_days=10)
    assert v.reap is True and v.reason == "pushed-mirror"
    assert reap.confirm_recloneable(clone) is True


def test_confirm_recloneable_false_when_our_branch_deleted_on_origin(tmp_path):
    """Repo alive but OUR branch was deleted on origin (possible unmerged local-only work) → keep."""
    clone = _init_origin_and_clone(tmp_path, "branchgone")
    _git(clone, "checkout", "-q", "-b", "sidework")
    (clone / "wip.txt").write_text("local branch work\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "wip on a branch")
    _git(clone, "push", "-q", "-u", "origin", "sidework")  # pushed → not "unpushed"
    _git(clone, "push", "-q", "origin", "--delete", "sidework")  # then deleted on origin
    # HEAD is on local 'sidework' which origin no longer advertises → not re-confirmable → keep
    assert reap.confirm_recloneable(clone) is False


def test_confirm_recloneable_false_when_origin_deleted(tmp_path):
    """Origin gone from GitHub → local clone is the only copy → NEVER reap (fail-safe)."""
    clone = _init_origin_and_clone(tmp_path, "goneorigin")
    shutil = __import__("shutil")
    shutil.rmtree(tmp_path / "goneorigin.git")  # simulate the remote being deleted/renamed
    assert reap.confirm_recloneable(clone) is False


def test_confirm_recloneable_opt_out(tmp_path, monkeypatch):
    clone = _init_origin_and_clone(tmp_path, "trustlocal")
    shutil = __import__("shutil")
    shutil.rmtree(tmp_path / "trustlocal.git")  # unreachable, but opt-out trusts local refs
    monkeypatch.setenv("LIMEN_REAP_VERIFY_REMOTE", "0")
    assert reap.confirm_recloneable(clone) is True


def test_excluded_worktree_root_is_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(reap, "LIMEN_ROOT", (tmp_path / "elsewhere").resolve())
    parent = tmp_path / ".claude" / "worktrees"
    parent.mkdir(parents=True)
    clone = _init_origin_and_clone(parent, "cell")
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "excluded-root"
