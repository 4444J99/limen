"""Tests for the two heal organs:

  scripts/sync-release.sh  — re-converge the daemon checkout to origin/main. The fix under test:
    a DIVERGED history whose local-only commits are ALL already upstream by patch-id (the observed
    "session redid work that already landed" drift) is re-converged loss-free; genuinely-unique
    divergence still stays fail-open (never force-moved).

  scripts/reclaim-worktrees.py — reap provably-dead fleet worktrees (clean +
    content-preserved-on-a-remote + idle), while keeping dirty / unique-unpushed /
    active-process-owned / recently-active ones.

Both run as real subprocesses against throwaway git repos, so the actual shell/Python ships.
"""

import json
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
    env = {**os.environ, "LIMEN_ROOT": str(clone), "LIMEN_RELEASE_BRANCH": "main", "HOME": str(clone.parent)}
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


def test_parked_on_pushed_branch_unparks(checkout, tmp_path):
    """HEAD parked on a work branch whose tip is safe on origin -> switch back to main and ff to
    the release (the 2026-06-29 jules-capfill park: 5 days pinned to a work branch, 65 behind)."""
    clone, bare = checkout
    _git("switch", "-q", "-c", "work", cwd=clone)
    work_sha = _commit(clone, "work.txt", "w\n", "work on branch")
    _git("push", "-q", "-u", "origin", "work", cwd=clone)
    release = _origin_advance(bare, tmp_path, "rel.txt", "r\n", "release advances")
    r = _run_sync(clone)
    assert r.returncode == 0
    assert "UNPARKED" in r.stdout, r.stdout + r.stderr
    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=clone).stdout.strip() == "main"
    assert _git("rev-parse", "HEAD", cwd=clone).stdout.strip() == release  # ff happened same run
    assert _git("rev-parse", "work", cwd=clone).stdout.strip() == work_sha  # branch ref survives


def test_parked_with_unpushed_commit_preserves_then_unparks(checkout, tmp_path):
    """PRESERVE-THEN-UNPARK (2026-07-09): a parked branch carrying an unpushed commit is not
    abandoned and not left stuck — the valve PUSHES the commit to origin (his push-first rule),
    then rests HEAD on the release. The old fail-open ('not safe on origin/work') stranded the
    daemon for 5 days."""
    clone, bare = checkout
    _git("switch", "-q", "-c", "work", cwd=clone)
    _git("push", "-q", "-u", "origin", "work", cwd=clone)
    local_sha = _commit(clone, "work.txt", "w\n", "unpushed work")
    _origin_advance(bare, tmp_path, "rel.txt", "r\n", "release advances")
    r = _run_sync(clone)
    assert r.returncode == 0
    assert "UNPARKED" in r.stdout, r.stdout + r.stderr
    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=clone).stdout.strip() == "main"
    _git("fetch", "-q", "origin", "work", cwd=clone)
    assert _git("rev-parse", "origin/work", cwd=clone).stdout.strip() == local_sha  # pushed, preserved


def test_parked_with_tracked_dirt_preserves_then_unparks(checkout, tmp_path):
    """Tracked dirt beyond tasks.yaml is session work — the valve COMMITS it onto the branch and
    pushes (preserve), then rests HEAD on the release. It is neither carried onto main nor dropped."""
    clone, bare = checkout
    _git("switch", "-q", "-c", "work", cwd=clone)
    _git("push", "-q", "-u", "origin", "work", cwd=clone)
    _origin_advance(bare, tmp_path, "rel.txt", "r\n", "release advances")
    (clone / "base.txt").write_text("uncommitted session work\n")  # tracked file, dirty
    r = _run_sync(clone)
    assert r.returncode == 0
    assert "UNPARKED" in r.stdout, r.stdout + r.stderr
    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=clone).stdout.strip() == "main"
    _git("fetch", "-q", "origin", "work", cwd=clone)
    preserved = _git("show", "origin/work:base.txt", cwd=clone).stdout
    assert "uncommitted session work" in preserved  # dirt committed + pushed, not dropped


def test_parked_unpark_refuses_dirty_tasks_cache_without_copy_or_restore(checkout, tmp_path):
    """A dirty remote-owned board cache blocks unpark without rewriting or carrying it."""
    clone, bare = checkout
    _commit(clone, "tasks.yaml", "queue: v0\n", "queue snapshot")
    _git("push", "-q", "origin", "main", cwd=clone)
    _git("switch", "-q", "-c", "work", cwd=clone)
    _commit(clone, "tasks.yaml", "queue: branch-snapshot\n", "branch queue snapshot")
    _git("push", "-q", "-u", "origin", "work", cwd=clone)
    release = _origin_advance(bare, tmp_path, "rel.txt", "r\n", "release advances")
    (clone / "tasks.yaml").write_text("queue: LIVE\n")  # unsanctioned local cache drift
    r = _run_sync(clone)
    assert r.returncode == 0
    assert "local tasks.yaml cache is dirty" in r.stdout
    assert "refusing to copy/restore/discard it" in r.stdout
    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=clone).stdout.strip() == "work"
    assert _git("rev-parse", "HEAD", cwd=clone).stdout.strip() != release
    assert (clone / "tasks.yaml").read_text() == "queue: LIVE\n"


def test_parked_unpark_clears_untracked_release_collision(checkout, tmp_path):
    """An UNTRACKED local file that the release now TRACKS blocks the switch exactly like the ff
    (censor/precedents.jsonl on the 2026-07-04 live heal): release-owned, so it is backed up and
    the released version wins — the unpark must still complete."""
    clone, bare = checkout
    _git("switch", "-q", "-c", "work", cwd=clone)
    _commit(clone, "work.txt", "w\n", "work on branch")
    _git("push", "-q", "-u", "origin", "work", cwd=clone)
    release = _origin_advance(bare, tmp_path, "conf.json", "RELEASE\n", "release adds conf.json")
    (clone / "conf.json").write_text("LOCAL-STALE\n")  # untracked here, tracked by the release
    (clone / "usage.json").write_text("{}\n")  # untracked runtime the release does NOT track
    r = _run_sync(clone)
    assert r.returncode == 0
    assert "UNPARKED" in r.stdout, r.stdout + r.stderr
    assert _git("rev-parse", "HEAD", cwd=clone).stdout.strip() == release
    assert (clone / "conf.json").read_text() == "RELEASE\n"  # released version won
    backup = clone / "logs" / ".sync-collision" / "conf.json"
    assert backup.exists() and backup.read_text() == "LOCAL-STALE\n"  # backed up, never lost
    assert (clone / "usage.json").exists()  # non-release runtime untouched


def test_parked_on_branch_held_elsewhere_fails_open(checkout, tmp_path):
    """If the release branch is checked out in ANOTHER worktree, git refuses the switch; the valve
    must fail open (loudly) and leave the parked checkout intact."""
    clone, bare = checkout
    _git("switch", "-q", "-c", "work", cwd=clone)
    work_sha = _commit(clone, "work.txt", "w\n", "work on branch")
    _git("push", "-q", "-u", "origin", "work", cwd=clone)
    _origin_advance(bare, tmp_path, "rel.txt", "r\n", "release advances")
    _git("worktree", "add", "-q", str(tmp_path / "holder"), "main", cwd=clone)  # holds main hostage
    r = _run_sync(clone)
    assert r.returncode == 0
    assert "refused" in r.stdout, r.stdout + r.stderr
    assert _git("rev-parse", "--abbrev-ref", "HEAD", cwd=clone).stdout.strip() == "work"
    assert _git("rev-parse", "HEAD", cwd=clone).stdout.strip() == work_sha


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


def _run_reclaim(wtroot: Path, limen_root: Path, apply=True, extra_env=None, extra_args=None):
    env = {
        **os.environ,
        "LIMEN_WORKTREE_ROOT": str(wtroot),
        "LIMEN_ROOT": str(limen_root),
        "LIMEN_RECLAIM_MIN_AGE_H": "1",
        "LIMEN_RECLAIM_REPO_LOCAL_WT": "0",
        "LIMEN_RECLAIM_REGISTERED_WT": "0",
        "LIMEN_RECLAIM_EVERY_MIN": "0",
    }
    if extra_env:
        env.update(extra_env)
    args = ["python3", str(RECLAIM)]
    if extra_args:
        args += list(extra_args)
    if not apply:
        return subprocess.run(args, capture_output=True, text=True, env=env)

    check = subprocess.run(
        ["python3", str(RECLAIM), "--check", "--json"],
        capture_output=True,
        text=True,
        env=env,
    )
    if check.returncode != 0:
        return check
    plan_sha = json.loads(check.stdout)["plan_sha256"]
    args += ["--apply", "--force", "--expected-plan-sha", plan_sha]
    return subprocess.run(args, capture_output=True, text=True, env=env)


def _age(path: Path, hours: float):
    t = time.time() - hours * 3600
    os.utime(path, (t, t))


def _write_reclaim_acceptance(
    limen_root: Path,
    root: str,
    action: str = "remove-worktree",
    reason: str | None = None,
    archive_status: str = "not_required_clean_merged_remote",
    redaction_review: str = "not_required_remote_only",
) -> None:
    path = limen_root / "docs" / "worktree-reclaim-acceptance.jsonl"
    path.parent.mkdir(exist_ok=True)
    event = {
        "accepted_at": "2026-07-06T05:30:00Z",
        "root": root,
        "action": action,
        "accepted": True,
        "archive_status": archive_status,
        "archive_proof": f"{archive_status} accepted for {root}",
        "redaction_review": redaction_review,
        "redaction_proof": f"{redaction_review} accepted for {root}",
    }
    if reason:
        event["reason"] = reason
    path.write_text(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def test_reclaim_standing_grant_removes_clean_pushed_idle(tmp_path):
    # covenant standing grant 2026-07-09: the loss-free class needs no ledger event
    main, bare, wtroot = _wt_root_with(tmp_path)
    dead = _add_wt(main, wtroot, "dead-task")  # clean, on origin/main, will be aged
    _age(dead, 5)
    (main / "logs").mkdir(exist_ok=True)
    r = _run_reclaim(wtroot, main, apply=True)
    assert r.returncode == 0, r.stderr
    assert not dead.exists(), r.stdout
    assert "reclaimed" in r.stdout


def test_reclaim_requires_acceptance_when_standing_grant_disabled(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    dead = _add_wt(main, wtroot, "dead-task")  # clean, on origin/main, will be aged
    _age(dead, 5)
    (main / "logs").mkdir(exist_ok=True)
    r = _run_reclaim(wtroot, main, apply=True, extra_env={"LIMEN_RECLAIM_STANDING_ACCEPTANCE": "0"})
    assert r.returncode == 0, r.stderr
    assert dead.exists(), r.stdout
    assert "missing-reclaim-acceptance" in r.stdout


def test_reclaim_removes_clean_pushed_idle_with_acceptance(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    dead = _add_wt(main, wtroot, "dead-task")  # clean, on origin/main, will be aged
    _age(dead, 5)
    (main / "logs").mkdir(exist_ok=True)
    _write_reclaim_acceptance(main, "dead-task", reason="clean+merged+idle")
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

    active = _add_wt(main, wtroot, "active")  # clean but freshly touched (recent mtime)

    r = _run_reclaim(wtroot, main, apply=True)
    assert r.returncode == 0, r.stderr
    assert dirty.exists() and unpushed.exists() and active.exists(), r.stdout
    assert "dirty" in r.stdout and "unpushed-commits" in r.stdout and "active" in r.stdout


def test_reclaim_reaps_clean_pushed_unmerged_branch_by_default(tmp_path):
    # Remote custody is enough to rehydrate the clean branch; the local worktree is disposable.
    main, bare, wtroot = _wt_root_with(tmp_path)
    (main / "logs").mkdir(exist_ok=True)

    branch = _add_wt(main, wtroot, "pushed-unmerged")
    _git("checkout", "-q", "-b", "feature", cwd=branch)
    _commit(branch, "feature.txt", "unique work\n", "feature")
    _git("push", "-q", "origin", "HEAD:feature", cwd=branch)
    _age(branch, 5)

    r = _run_reclaim(wtroot, main, apply=True)

    assert r.returncode == 0, r.stderr
    assert not branch.exists(), r.stdout
    assert "clean+pushed+idle" in r.stdout


def test_reclaim_keeps_pushed_unmerged_when_pushed_reap_disabled(tmp_path):
    # The explicit opt-out restores the conservative merged-only gate.
    main, bare, wtroot = _wt_root_with(tmp_path)
    (main / "logs").mkdir(exist_ok=True)

    branch = _add_wt(main, wtroot, "pushed-unmerged-off")
    _git("checkout", "-q", "-b", "feature-off", cwd=branch)
    _commit(branch, "feature.txt", "unique work\n", "feature")
    _git("push", "-q", "origin", "HEAD:feature-off", cwd=branch)
    _age(branch, 5)

    r = _run_reclaim(
        wtroot,
        main,
        apply=True,
        extra_env={"LIMEN_RECLAIM_PUSHED_OK": "0"},
    )

    assert r.returncode == 0, r.stderr
    assert branch.exists(), r.stdout
    assert "not-merged-to-default" in r.stdout


def test_reclaim_removes_clean_idle_remote_merged_receipt_under_standing_grant(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    (main / "logs").mkdir(exist_ok=True)
    receipts = main / "docs" / "worktree-preservation-receipts.json"
    receipts.parent.mkdir(exist_ok=True)

    merged = _add_wt(main, wtroot, "receipt-merged")
    _git("checkout", "-q", "-b", "merged-pr", cwd=merged)
    _commit(merged, "squashed.txt", "merged elsewhere\n", "local pre-squash commit")
    _age(merged, 5)

    receipts.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "receipt-merged",
                        "lane": "remote-merged",
                        "status": "merged_pr_preserved",
                        "pr_state": "MERGED",
                        "pr_url": "https://github.com/organvm/example/pull/1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    r = _run_reclaim(wtroot, main, apply=True)

    assert r.returncode == 0, r.stderr
    assert not merged.exists(), r.stdout
    assert "receipt-remote-merged+clean+idle" in r.stdout


def test_reclaim_keeps_dirty_remote_merged_receipt(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    (main / "logs").mkdir(exist_ok=True)
    receipts = main / "docs" / "worktree-preservation-receipts.json"
    receipts.parent.mkdir(exist_ok=True)

    dirty = _add_wt(main, wtroot, "dirty-receipt-merged")
    _age(dirty, 5)
    (dirty / "local-only.txt").write_text("uncommitted local data\n", encoding="utf-8")

    receipts.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "dirty-receipt-merged",
                        "lane": "remote-merged",
                        "status": "merged_pr_preserved",
                        "pr_state": "MERGED",
                        "pr_url": "https://github.com/organvm/example/pull/2",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    r = _run_reclaim(wtroot, main, apply=True)

    assert r.returncode == 0, r.stderr
    assert dirty.exists(), r.stdout
    assert "dirty" in r.stdout


def test_reclaim_removes_patch_equivalent_local_replay(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    (main / "logs").mkdir(exist_ok=True)

    replay = _add_wt(main, wtroot, "patch-equivalent")
    _git("checkout", "-q", "-b", "replay", cwd=replay)

    upstream = tmp_path / "upstream-replay"
    _git("clone", "-q", str(bare), str(upstream), cwd=tmp_path)
    _git("config", "user.email", "t@t", cwd=upstream)
    _git("config", "user.name", "t", cwd=upstream)
    _commit(upstream, "same.txt", "same change\n", "land same patch")
    _git("push", "-q", "origin", "main", cwd=upstream)

    _commit(replay, "same.txt", "same change\n", "local replay of same patch")
    _git("fetch", "-q", "origin", cwd=replay)
    _age(replay, 5)
    _write_reclaim_acceptance(main, "patch-equivalent", reason="clean+merged+idle")

    r = _run_reclaim(wtroot, main, apply=True)

    assert r.returncode == 0, r.stderr
    assert not replay.exists(), r.stdout
    assert "reclaimed" in r.stdout


def test_reclaim_dry_run_removes_nothing(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    dead = _add_wt(main, wtroot, "dead")
    _age(dead, 5)
    (main / "logs").mkdir(exist_ok=True)
    r = _run_reclaim(wtroot, main, apply=False)
    assert r.returncode == 0
    assert dead.exists()  # dry-run never deletes
    assert "dry-run" in r.stdout


def test_reclaim_check_json_reports_reapable_candidates_without_deleting(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    dead = _add_wt(main, wtroot, "dead")
    _age(dead, 5)
    (main / "logs").mkdir(exist_ok=True)

    r = _run_reclaim(wtroot, main, apply=False, extra_args=["--check", "--json"])

    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert dead.exists()
    assert payload["mode"] == "check"
    assert payload["reapable_count"] == 1
    assert payload["would_reclaim"][0]["root"] == "dead"
    assert payload["would_reclaim"][0]["reason"] == "clean+merged+idle"


def test_reclaim_removes_generated_log_shell(tmp_path):
    limen_root = tmp_path / "limen"
    (limen_root / "logs").mkdir(parents=True)
    wtroot = tmp_path / ".limen-worktrees"
    shell = wtroot / "generated-log-shell"
    (shell / "logs").mkdir(parents=True)
    (shell / "logs" / "session-lifecycle-pressure.md").write_text("generated\n", encoding="utf-8")
    (shell / "logs" / "session-lifecycle-pressure.json").write_text("{}", encoding="utf-8")
    _write_reclaim_acceptance(
        limen_root,
        "generated-log-shell",
        action="remove-residue",
        reason="generated-log-shell",
        archive_status="not_required_generated_residue",
        redaction_review="not_required_generated_residue",
    )

    r = _run_reclaim(wtroot, limen_root, apply=True)

    assert r.returncode == 0, r.stderr
    assert not shell.exists(), r.stdout
    assert "generated-log-shell" in r.stdout


def test_reclaim_malformed_numeric_env_fails_open(tmp_path):
    main, bare, wtroot = _wt_root_with(tmp_path)
    dead = _add_wt(main, wtroot, "dead")
    _age(dead, 5)
    (main / "logs").mkdir(exist_ok=True)

    r = _run_reclaim(
        wtroot,
        main,
        apply=False,
        extra_env={"LIMEN_RECLAIM_MAX": "not-int", "LIMEN_RECLAIM_EVERY_MIN": "not-float"},
    )

    assert r.returncode == 0, r.stderr
    assert dead.exists()
    assert "dry-run" in r.stdout
