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


def _out(repo: Path, *args: str) -> str:
    """Run a git command via the module's own runner and return trimmed stdout (for guard assertions)."""
    return reap._run(["git", "-C", str(repo), *args])


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


def test_process_owned_repo_is_kept(tmp_path, monkeypatch):
    clone = _init_origin_and_clone(tmp_path, "process-owned")
    nested_cwd = clone / "src"
    nested_cwd.mkdir()
    monkeypatch.setattr(reap, "_ACTIVE_PROCESS_CWDS", {nested_cwd.resolve(): 4242})

    v = _verdict(clone, age_days=99, pressure=True)

    assert v.reap is False
    assert v.reason == "active-process-cwd:4242"


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


def test_clone_reap_requires_acceptance_event(tmp_path, monkeypatch):
    # pin the standing grant OFF so this exercises the per-clone ledger gate (the grant is covered
    # by test_clone_reap_standing_grant_accepts_pushed_mirror below).
    monkeypatch.setattr(reap, "CLONE_REAP_STANDING", False)
    clone = _init_origin_and_clone(tmp_path, "needsaccept")
    slug = reap.origin_slug(clone)

    ok, reason = reap.clone_reap_accepted(clone, slug, "pushed-mirror", [])

    assert ok is False
    assert reason == "missing-clone-reap-acceptance"


def test_clone_reap_standing_grant_accepts_pushed_mirror(tmp_path, monkeypatch):
    """Standing grant (2026-07-09): the loss-free pushed-mirror class is pre-accepted with no ledger."""
    monkeypatch.setattr(reap, "CLONE_REAP_STANDING", True)
    clone = _init_origin_and_clone(tmp_path, "standingmirror")
    slug = reap.origin_slug(clone)

    ok, reason = reap.clone_reap_accepted(clone, slug, "pushed-mirror", [])
    assert ok is True
    assert reason == "standing-grant-2026-07-09"

    # a non-loss-free reason is NOT covered by the grant → still needs the ledger
    ok2, reason2 = reap.clone_reap_accepted(clone, slug, "dirty-or-untracked", [])
    assert ok2 is False


def test_clone_reap_acceptance_matches_remote_mirror(tmp_path, monkeypatch):
    monkeypatch.setattr(reap, "CLONE_REAP_STANDING", False)
    clone = _init_origin_and_clone(tmp_path, "acceptedmirror")
    slug = reap.origin_slug(clone)
    events = [
        {
            "accepted_at": "2026-07-06T06:00:00Z",
            "root": "acceptedmirror",
            "slug": slug,
            "accepted": True,
            "reason": "pushed-mirror",
            "archive_status": "not_required_clean_remote_mirror",
            "archive_proof": "fresh fetch proved the clone is remote-reachable",
            "redaction_review": "not_required_remote_only",
            "redaction_proof": "clean clone cache; no private-only data present",
        }
    ]

    ok, reason = reap.clone_reap_accepted(clone, slug, "pushed-mirror", events)

    assert ok is True
    assert reason == "clone-reap-accepted"


def test_clone_reap_acceptance_requires_archive_and_redaction_proofs(tmp_path, monkeypatch):
    monkeypatch.setattr(reap, "CLONE_REAP_STANDING", False)
    clone = _init_origin_and_clone(tmp_path, "proofrequired")
    slug = reap.origin_slug(clone)
    base_event = {
        "accepted_at": "2026-07-06T06:00:00Z",
        "root": "proofrequired",
        "slug": slug,
        "accepted": True,
        "reason": "pushed-mirror",
        "archive_status": "not_required_clean_remote_mirror",
        "archive_proof": "fresh fetch proved the clone is remote-reachable",
        "redaction_review": "not_required_remote_only",
        "redaction_proof": "clean clone cache; no private-only data present",
    }

    for required_field in reap.REQUIRED_ACCEPTANCE_PROOF_FIELDS:
        event = dict(base_event)
        event.pop(required_field)

        ok, reason = reap.clone_reap_accepted(clone, slug, "pushed-mirror", [event])

        assert ok is False
        assert reason == "missing-clone-reap-acceptance"


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


# ----------------------------------------------------- LOSS-FREE HARDENING (2026-07-01 adversarial audit)
# A 14-path red-team reproduced un-mirrored data that the original denylist-shaped gate would rmtree.
# Each test below rebuilds one path as a real git repo and asserts the hardened gate now KEEPS it
# (classify) or refuses it at the network belt (confirm_recloneable). These are the regression locks.


# --- Category A: local-only refs outside refs/heads (invisible to --branches) -------------------------
def test_stash_wip_is_never_reaped(tmp_path):
    """`git stash` stores WIP as commits under refs/stash — invisible to --branches AND to porcelain."""
    clone = _init_origin_and_clone(tmp_path, "stashwip")
    (clone / "README.md").write_text("hello\nwip: top_secret_algorithm()\n")  # edit a tracked file
    _git(clone, "stash")  # working tree reverts to HEAD (porcelain clean); WIP hides in refs/stash
    assert _out(clone, "status", "--porcelain") == ""  # sanity: the guard the old gate trusted is empty
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "unpushed-objects"


def test_reflog_orphan_commit_is_never_reaped(tmp_path):
    """A hard-reset leaves the abandoned commit reachable only via the reflog — still un-mirrored work."""
    clone = _init_origin_and_clone(tmp_path, "reflogorphan")
    (clone / "secret.py").write_text("private_key = 'supersecret'\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "WIP secrets")
    _git(clone, "reset", "--hard", "HEAD~1")  # HEAD back on the pushed base; commit orphaned in reflog
    assert _out(clone, "log", "--branches", "--not", "--remotes", "--oneline") == ""  # old guard: blind
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "unpushed-objects"


def test_local_only_tag_is_never_reaped(tmp_path):
    """A local tag on an orphaned commit is real work on no remote — refs/tags is outside --branches."""
    clone = _init_origin_and_clone(tmp_path, "localtag")
    (clone / "release.bin").write_text("release artifact v1.0\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "release v1.0")
    _git(clone, "tag", "v1.0-local")  # local only, never pushed
    _git(clone, "reset", "--hard", "HEAD~1")  # orphan the tagged commit off refs/heads
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "unpushed-objects"


def test_git_notes_are_never_reaped(tmp_path):
    """refs/notes/* holds annotations that live on no remote — must not be silently destroyed."""
    clone = _init_origin_and_clone(tmp_path, "gitnotes")
    _git(clone, "notes", "add", "-m", "Security review: signed off", "HEAD")
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "unpushed-objects"


# --- Category B: working-tree data invisible to `git status --porcelain` ------------------------------
def test_gitignored_data_is_never_reaped(tmp_path):
    """A gitignored `.env` / local `*.db` lives on no remote; porcelain hides it → must KEEP."""
    clone = _init_origin_and_clone(tmp_path, "ignoreddata")
    (clone / ".gitignore").write_text(".env\n*.db\ndata/\n")
    _git(clone, "add", ".gitignore")
    _git(clone, "commit", "-qm", "add gitignore")
    _git(clone, "push", "-q", "origin", "main")
    (clone / ".env").write_text("AWS_SECRET_ACCESS_KEY=xyz\n")
    (clone / "local.db").write_text("sqlite session records\n")
    assert _out(clone, "status", "--porcelain") == ""  # ignored files are invisible to the old guard
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "ignored-data"


def test_regenerable_ignored_files_still_reap(tmp_path):
    """The organ must NOT over-suppress: node_modules/__pycache__ are provably regenerable → still reap."""
    clone = _init_origin_and_clone(tmp_path, "regenignored")
    (clone / ".gitignore").write_text("node_modules/\n__pycache__/\n")
    _git(clone, "add", ".gitignore")
    _git(clone, "commit", "-qm", "add gitignore")
    _git(clone, "push", "-q", "origin", "main")
    (clone / "node_modules").mkdir()
    (clone / "node_modules" / "dep.js").write_text("module.exports = {}\n")
    (clone / "__pycache__").mkdir()
    (clone / "__pycache__" / "m.pyc").write_text("bytecode\n")
    v = _verdict(clone, age_days=10)
    assert v.reap is True
    assert v.reason == "pushed-mirror"


def test_skip_worktree_hidden_edit_is_never_reaped(tmp_path):
    """A skip-worktree bit hides a local edit to a tracked file from porcelain → the override is data."""
    clone = _init_origin_and_clone(tmp_path, "skipwt")
    (clone / "config.yml").write_text("debug: false\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "add config")
    _git(clone, "push", "-q", "origin", "main")
    _git(clone, "update-index", "--skip-worktree", "config.yml")
    (clone / "config.yml").write_text("debug: true\nlocal_secret: hunter2\n")
    assert _out(clone, "status", "--porcelain") == ""  # skip-worktree hides it
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "hidden-modifications"


# --- Category E: nested git contexts outside the parent's ref graph -----------------------------------
def test_submodule_parent_is_never_reaped(tmp_path):
    """A submodule's object store (.git/modules/*) can hold unpushed commits no parent guard can see."""
    parent = _init_origin_and_clone(tmp_path, "subparent")
    _init_origin_and_clone(tmp_path, "submodsrc")  # a seeded bare origin to use as the submodule source
    _git(parent, "-c", "protocol.file.allow=always", "submodule", "add", str(tmp_path / "submodsrc.git"), "vendor")
    assert (parent / ".git" / "modules").is_dir()
    v = _verdict(parent, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "has-submodule"


def test_lfs_object_store_is_never_reaped(tmp_path):
    """git-LFS blobs live in .git/lfs/objects and may not be on the LFS remote → never reap the clone."""
    clone = _init_origin_and_clone(tmp_path, "lfsrepo")
    shard = clone / ".git" / "lfs" / "objects" / "87" / "96"
    shard.mkdir(parents=True)
    (shard / "8796e18b0682e0b400976a09523f295066d36e36cbd28422c0b916af878b212a").write_bytes(b"\x00" * 4096)
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "has-lfs-objects"


def test_linked_worktree_parent_is_never_reaped(tmp_path):
    """A linked worktree's unpushed detached-HEAD commit lives in THIS clone's .git/objects — keep it."""
    clone = _init_origin_and_clone(tmp_path, "wtparent2")
    wt = tmp_path / "linked-wt"
    _git(clone, "worktree", "add", "--detach", str(wt), "HEAD")
    (wt / "findings.txt").write_text("detached-HEAD work, never pushed\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-qm", "detached wip")
    v = _verdict(clone, age_days=99, pressure=True)
    assert v.reap is False
    assert v.reason == "has-linked-worktrees"


# --- Category C: stale / directional remote check (the belt's fetch --prune closes these) -------------
def test_belt_refuses_force_pushed_orphan(tmp_path):
    """Origin force-rewound past our HEAD to a disjoint commit; a stale tracking ref hid it from classify.
    The belt fetches the live remote and sees HEAD is not reachable from it → refuse."""
    clone = _init_origin_and_clone(tmp_path, "forcepush")
    (clone / "work.txt").write_text("important user work\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "B: user work")
    _git(clone, "push", "-q", "origin", "main")  # origin main = B; clone tracking ref = B
    attacker = tmp_path / "attacker"
    subprocess.run(
        ["git", "clone", "-q", str(tmp_path / "forcepush.git"), str(attacker)], check=True, capture_output=True
    )
    _git(attacker, "config", "user.email", "a@a.a")
    _git(attacker, "config", "user.name", "a")
    _git(attacker, "checkout", "-q", "--orphan", "rogue")
    (attacker / "rogue.txt").write_text("disjoint history\n")
    _git(attacker, "add", "-A")
    _git(attacker, "commit", "-qm", "C: orphan")
    _git(attacker, "push", "-q", "--force", str(tmp_path / "forcepush.git"), "rogue:main")
    # victim never fetched → refs/remotes/origin/main is stale (= B); only the live belt catches it
    assert reap.confirm_recloneable(clone) is False


def test_belt_refuses_ahead_of_origin(tmp_path):
    """Clone AHEAD of origin (a commit made after classify sampled clean — the TOCTOU-commit race).
    The belt's post-fetch reachability proof refuses it even if classify were bypassed."""
    clone = _init_origin_and_clone(tmp_path, "ahead")
    (clone / "precious.txt").write_text("precious unpushed data\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "WIP: never pushed")
    assert reap.confirm_recloneable(clone) is False


def test_belt_refuses_deleted_branch_with_stale_tracking_ref(tmp_path):
    """Our branch was deleted on origin by someone else; our tracking ref is stale so classify passes.
    fetch --prune expires the stale ref and the belt sees the branch's commits are un-mirrored → refuse."""
    clone = _init_origin_and_clone(tmp_path, "delbranch")
    _git(clone, "checkout", "-q", "-b", "feature")
    (clone / "feat.txt").write_text("unmerged feature work\n")
    _git(clone, "add", "-A")
    _git(clone, "commit", "-qm", "D: feature")
    _git(clone, "push", "-q", "-u", "origin", "feature")
    _git(clone, "checkout", "-q", "main")
    # delete feature directly on the bare origin so THIS clone's tracking ref stays stale (not pruned)
    subprocess.run(
        ["git", "-C", str(tmp_path / "delbranch.git"), "branch", "-D", "feature"], check=True, capture_output=True
    )
    # classify is stale-permissive here (the tracking ref still advertises D) — the belt is what saves it
    assert _verdict(clone, age_days=99, pressure=True).reap is True
    assert reap.confirm_recloneable(clone) is False


# --- Category D: TOCTOU — work landing between the check and the delete -------------------------------
def test_pristine_recheck_detects_raced_write(tmp_path):
    """The last-instant belt re-samples porcelain + stash immediately before rmtree fires."""
    clone = _init_origin_and_clone(tmp_path, "raced")
    assert reap._pristine_now(clone) is True
    (clone / "src").mkdir()
    (clone / "src" / "creds-2026-07-01.json").write_text('{"api_key": "sk-irreplaceable"}\n')
    assert reap._pristine_now(clone) is False
