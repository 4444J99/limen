"""test_reap_branches.py — proves the branch-reap gate is LOSS-FREE.

The organ deletes local branches autonomically (git branch -D), so a wrong 'reap' verdict would
drop a ref. `git branch -D` is reflog-recoverable, but the gate must still only reap branches it can
PROVE are landed on the default branch. These tests exhaust the pure classify() matrix and drive
gather_facts() against real temp git repos to confirm:
  • a merged/fast-forwarded branch (tip is an ancestor of default) → reap,
  • a squash-merged branch (PR MERGED, tip not advanced past mergedAt) → reap,
  • a merged branch ADVANCED past its merge (post-merge commits) → KEEP (unpushed work),
  • an unmerged branch, a checked-out branch, an open-PR branch, a trunk → KEEP.
This is the executable predicate for the organ.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location("reap_branches", SCRIPTS / "reap-branches.py")
reap = importlib.util.module_from_spec(_spec)
sys.modules["reap_branches"] = reap  # dataclasses need the module discoverable during exec
_spec.loader.exec_module(reap)


def F(**kw) -> "reap.Facts":
    """Build a Facts with everything False except the overrides."""
    base = dict(
        is_ancestor=False,
        pr_merged_safe=False,
        pr_merged_raw=False,
        pr_open=False,
        checked_out=False,
        protected=False,
    )
    base.update(kw)
    return reap.Facts(**base)


# ----------------------------------------------------------------- pure classify() matrix
def test_ancestor_is_reaped():
    v = reap.classify(F(is_ancestor=True))
    assert v.action == "reap" and v.reason == "landed-ancestor" and v.landed is True


def test_squash_merged_safe_is_reaped():
    v = reap.classify(F(pr_merged_safe=True, pr_merged_raw=True))
    assert v.action == "reap" and v.reason == "landed-pr-merged" and v.landed is True


def test_merged_but_advanced_is_kept():
    # MERGED per gh but the tip advanced past the merge → unpushed post-merge work → never deleted.
    v = reap.classify(F(pr_merged_raw=True, pr_merged_safe=False))
    assert v.action == "keep" and v.reason == "pr-merged-but-advanced" and v.landed is False


def test_unmerged_is_livework():
    v = reap.classify(F())
    assert v.action == "keep" and v.reason == "livework" and v.landed is False


def test_protected_never_reaped_even_if_ancestor():
    v = reap.classify(F(protected=True, is_ancestor=True))
    assert v.action == "keep" and v.reason == "protected" and v.landed is False


def test_checked_out_never_reaped_even_if_landed():
    # In active use in a worktree — reaped only once its worktree frees; not a fixed-point failure.
    v = reap.classify(F(checked_out=True, is_ancestor=True, pr_merged_safe=True))
    assert v.action == "keep" and v.reason == "checked-out" and v.landed is False


def test_open_pr_beats_a_landed_proof():
    # A reopened/duplicated head that is also an ancestor: an OPEN PR wins → never yank it.
    v = reap.classify(F(pr_open=True, is_ancestor=True))
    assert v.action == "keep" and v.reason == "inflight" and v.landed is False


def test_numeric_env_knobs_fall_back(monkeypatch):
    monkeypatch.setenv("LIMEN_BRANCH_REAP_MAX", "bad")
    monkeypatch.setenv("LIMEN_BRANCH_REAP_EVERY_MIN", "nan")

    assert reap._int_env("LIMEN_BRANCH_REAP_MAX", 100, minimum=1) == 100
    assert reap._float_env("LIMEN_BRANCH_REAP_EVERY_MIN", 30.0, minimum=0.0) == 30.0

    monkeypatch.setenv("LIMEN_BRANCH_REAP_MAX", "0")
    monkeypatch.setenv("LIMEN_BRANCH_REAP_EVERY_MIN", "-1")
    assert reap._int_env("LIMEN_BRANCH_REAP_MAX", 100, minimum=1) == 100
    assert reap._float_env("LIMEN_BRANCH_REAP_EVERY_MIN", 30.0, minimum=0.0) == 30.0


def test_ancestor_reported_before_pr_merged():
    v = reap.classify(F(is_ancestor=True, pr_merged_safe=True))
    assert v.reason == "landed-ancestor"


# ----------------------------------------------------------------- gather_facts() on real repos
def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A repo with main@C2, a 'spent' branch at C1 (ancestor of main), a 'divergent' branch off main,
    and a 'livework' branch with unique commits. gather_facts() reads reap.LIMEN_ROOT, so point it here."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@t.t")
    _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("1\n")
    _git(r, "add", "a.txt")
    _git(r, "commit", "-q", "-m", "C1")
    _git(r, "branch", "spent")  # spent@C1 — will become an ancestor once main advances
    (r / "a.txt").write_text("2\n")
    _git(r, "commit", "-qam", "C2")  # main@C2
    # a divergent commit (simulates a squash-merged branch: NOT an ancestor of main)
    _git(r, "branch", "divergent")
    _git(r, "checkout", "-q", "divergent")
    (r / "b.txt").write_text("x\n")
    _git(r, "add", "b.txt")
    _git(r, "commit", "-q", "-m", "D1")
    # genuine live work, also divergent
    _git(r, "checkout", "-q", "main")
    _git(r, "branch", "livework")
    _git(r, "checkout", "-q", "livework")
    (r / "c.txt").write_text("y\n")
    _git(r, "add", "c.txt")
    _git(r, "commit", "-q", "-m", "L1")
    _git(r, "checkout", "-q", "main")
    monkeypatch.setattr(reap, "LIMEN_ROOT", r)
    return r


def test_spent_branch_is_ancestor_and_reaped(repo):
    f = reap.gather_facts("spent", "main", set(), {}, set(), "main")
    assert f.is_ancestor is True
    assert reap.classify(f).action == "reap"


def test_livework_branch_is_kept(repo):
    f = reap.gather_facts("livework", "main", set(), {}, set(), "main")
    assert f.is_ancestor is False and f.pr_merged_raw is False
    assert reap.classify(f).reason == "livework"


def test_squash_merged_within_time_is_reaped(repo):
    # 'divergent' is not an ancestor, but its PR merged in the (far) future relative to its commit.
    future = time.time() + 100_000
    f = reap.gather_facts("divergent", "main", set(), {"divergent": future}, set(), "main")
    assert f.is_ancestor is False
    assert f.pr_merged_safe is True
    assert reap.classify(f).reason == "landed-pr-merged"


def test_merged_but_advanced_past_mergedat_is_kept(repo):
    # PR merged long ago (2001) but the local tip is recent → post-merge commits → KEEP.
    old = 1_000_000_000.0
    f = reap.gather_facts("divergent", "main", set(), {"divergent": old}, set(), "main")
    assert f.pr_merged_raw is True and f.pr_merged_safe is False
    assert reap.classify(f).reason == "pr-merged-but-advanced"


def test_merged_with_unknown_mergedat_fails_safe(repo):
    # Unknown merge time (mergedAt=None) → cannot prove not-advanced → KEEP.
    f = reap.gather_facts("divergent", "main", set(), {"divergent": None}, set(), "main")
    assert f.pr_merged_raw is True and f.pr_merged_safe is False
    assert reap.classify(f).action == "keep"


def test_checked_out_ancestor_is_kept(repo):
    f = reap.gather_facts("spent", "main", {"spent"}, {}, set(), "main")
    assert f.is_ancestor is True and f.checked_out is True
    assert reap.classify(f).reason == "checked-out"


def test_default_branch_is_protected(repo):
    f = reap.gather_facts("main", "main", set(), {}, set(), "main")
    assert f.protected is True
    assert reap.classify(f).action == "keep"
