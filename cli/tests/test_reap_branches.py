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
import json
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


def F(**kw) -> reap.Facts:
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


def test_exact_branch_allowlist_never_broadens_scope():
    selected, missing = reap.exact_branch_allowlist(
        ["main", "landed-one", "landed-two"],
        ["landed-two", "missing", "landed-two"],
    )

    assert selected == ["landed-two"]
    assert missing == ["missing"]


def test_empty_branch_allowlist_preserves_default_scope():
    branches = ["main", "landed-one", "landed-two"]

    assert reap.exact_branch_allowlist(branches, []) == (branches, [])


def test_targeted_apply_preserves_global_state_and_ledger(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    docs = tmp_path / "docs"
    logs.mkdir()
    docs.mkdir()
    state = logs / "reap-branches-state.json"
    ledger = docs / "branch-hygiene.md"
    marker = logs / ".reap-branches-last"
    state.write_text("global-state\n", encoding="utf-8")
    ledger.write_text("global-ledger\n", encoding="utf-8")
    monkeypatch.setattr(reap, "LOG", logs / "reap-branches.jsonl")
    monkeypatch.setattr(reap, "STATE", state)
    monkeypatch.setattr(reap, "MARKER", marker)
    monkeypatch.setattr(reap, "LEDGER", ledger)
    monkeypatch.setattr(reap, "local_branches", lambda: ["target", "unrelated-livework"])
    monkeypatch.setattr(reap, "default_ref", lambda: "origin/main")
    monkeypatch.setattr(reap, "default_name", lambda _ref: "main")
    monkeypatch.setattr(reap, "checked_out_branches", set)
    monkeypatch.setattr(reap, "gh_head_states", lambda: ({}, set(), True))
    monkeypatch.setattr(reap, "gather_facts", lambda *_args: F(is_ancestor=True))
    monkeypatch.setattr(reap, "load_branch_reap_acceptance", list)
    monkeypatch.setattr(reap, "branch_reap_accepted", lambda *_args: (True, "accepted"))
    monkeypatch.setattr(
        reap,
        "_git",
        lambda args, timeout=30: subprocess.CompletedProcess(args, 0, "", ""),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["reap-branches.py", "--apply", "--force", "--branch", "target"],
    )

    assert reap.main() == 0
    assert state.read_text(encoding="utf-8") == "global-state\n"
    assert ledger.read_text(encoding="utf-8") == "global-ledger\n"
    assert not marker.exists()
    receipt = json.loads((logs / "reap-branches.jsonl").read_text())
    assert receipt["scope"] == "targeted"
    assert receipt["targets"] == ["target"]


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


def test_branch_reap_requires_acceptance(repo):
    ok, reason = reap.branch_reap_accepted("spent", "landed-ancestor", [])

    assert ok is False
    assert reason == "missing-branch-reap-acceptance"


def test_branch_reap_acceptance_matches_tip(repo):
    tip = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "refs/heads/spent"], text=True).strip()
    events = [
        {
            "accepted_at": "2026-07-06T06:30:00Z",
            "branch": "spent",
            "accepted": True,
            "reason": "landed-ancestor",
            "tip": tip,
            "archive_status": "landed_on_default_verified",
            "archive_proof": "tip is reachable from the default branch",
            "redaction_review": "not_required_landed_ref",
            "redaction_proof": "branch ref carries no additional content beyond landed git objects",
        }
    ]

    ok, reason = reap.branch_reap_accepted("spent", "landed-ancestor", events)

    assert ok is True
    assert reason == "branch-reap-accepted"


def test_branch_reap_acceptance_requires_archive_and_redaction_proof(repo):
    tip = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "refs/heads/spent"], text=True).strip()
    events = [
        {
            "accepted_at": "2026-07-06T06:30:00Z",
            "branch": "spent",
            "accepted": True,
            "reason": "landed-ancestor",
            "tip": tip,
            "archive_status": "landed_on_default_verified",
            "redaction_review": "not_required_landed_ref",
        }
    ]

    ok, reason = reap.branch_reap_accepted("spent", "landed-ancestor", events)

    assert ok is False
    assert reason == "incomplete-branch-reap-acceptance"


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


def test_open_pr_protects_only_its_exact_local_head(repo):
    spent_tip = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "refs/heads/spent"], text=True).strip()

    exact = reap.gather_facts("spent", "main", set(), {}, {"spent": spent_tip}, "main")
    reused_name = reap.gather_facts("spent", "main", set(), {}, {"spent": "f" * 40}, "main")

    assert exact.pr_open is True
    assert reap.classify(exact).reason == "inflight"
    assert reused_name.pr_open is False
    assert reap.classify(reused_name).reason == "landed-ancestor"


def test_github_open_head_snapshot_keeps_exact_oid(monkeypatch):
    monkeypatch.delenv("LIMEN_OFFLINE", raising=False)
    monkeypatch.setattr(reap.shutil, "which", lambda _name: "/usr/bin/gh")
    payload = [
        {
            "headRefName": "same-name",
            "headRefOid": "a" * 40,
            "state": "OPEN",
            "mergedAt": None,
        }
    ]
    monkeypatch.setattr(
        reap.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, json.dumps(payload), ""),
    )

    merged, open_heads, online = reap.gh_head_states()

    assert merged == {}
    assert open_heads == {"same-name": "a" * 40}
    assert online is True


# ----------------------------------------------------------------- --check grace window
def test_landed_age_uses_merged_at():
    now = time.time()
    assert reap._landed_age_s("b", {"b": now - 120.0}, now) == pytest.approx(120.0, abs=1.0)


def test_landed_age_unknown_is_stale():
    # No gh mergedAt and no such ref → +inf: an unknowable age NEVER hides a branch.
    assert reap._landed_age_s("zz-no-such-branch-grace-test", {}, time.time()) == float("inf")


def test_lingering_excludes_young_landed_branches():
    # A branch merged 1min ago is digesting; one merged 2h ago lingers. --apply is ungraced —
    # only the --check assertion ages, so a live fleet can't redden every closeout.
    now = time.time()
    merged = {"young": now - 60.0, "old": now - 7200.0}
    rows = [("young", "landed-pr-merged"), ("old", "landed-pr-merged")]
    assert reap._lingering(rows, merged, now, grace_s=3600.0) == [("old", "landed-pr-merged")]


def test_lingering_zero_grace_keeps_strict_semantics():
    # grace=0 restores the original zero-at-any-instant assertion (age > 0 for any real branch).
    now = time.time()
    rows = [("young", "landed-pr-merged")]
    assert reap._lingering(rows, {"young": now - 60.0}, now, grace_s=0.0) == rows


def test_standing_grant_covers_landed_classes(repo):
    events = [
        {
            "standing": True,
            "branch": "*",
            "accepted": True,
            "accepted_at": "2026-07-09T13:00:00Z",
            "archive_status": "not_required_landed_ref",
            "archive_proof": "standing grant: covers only classifier-proven landed branches",
            "redaction_review": "not_required_landed_ref",
            "redaction_proof": "local ref deletion removes only a branch pointer; landed objects stay on default",
        }
    ]

    for landed_reason in ("landed-ancestor", "landed-pr-merged"):
        ok, reason = reap.branch_reap_accepted("spent", landed_reason, events)
        assert ok is True
        assert reason == "branch-reap-accepted"


def test_standing_grant_never_covers_non_landed_classes(repo):
    events = [
        {
            "standing": True,
            "branch": "*",
            "accepted": True,
            "accepted_at": "2026-07-09T13:00:00Z",
            "archive_status": "not_required_landed_ref",
            "archive_proof": "standing grant: covers only classifier-proven landed branches",
            "redaction_review": "not_required_landed_ref",
            "redaction_proof": "local ref deletion removes only a branch pointer; landed objects stay on default",
        }
    ]

    ok, reason = reap.branch_reap_accepted("spent", "livework", events)
    assert ok is False
    assert reason == "missing-branch-reap-acceptance"


def test_standing_grant_requires_proof_fields(repo):
    events = [{"standing": True, "branch": "*", "accepted": True, "accepted_at": "2026-07-09T13:00:00Z"}]

    ok, reason = reap.branch_reap_accepted("spent", "landed-ancestor", events)
    assert ok is False
    assert reason == "incomplete-branch-reap-acceptance"
