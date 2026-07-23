from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen import worktree_debt as wd
from limen import worktree_roots as wr
from limen.worktree_debt import worktree_debt_report


def test_reachable_from_remote_uses_single_contains_query(tmp_path: Path, monkeypatch):
    calls: list[list[str]] = []

    def fake_git(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert cwd == tmp_path
        assert timeout == 30
        if args == [
            "for-each-ref",
            "--contains=abc123",
            "--format=%(refname)",
            "refs/remotes",
        ]:
            return subprocess.CompletedProcess(
                ["git", *args],
                0,
                "refs/remotes/origin/main\nrefs/remotes/origin/feature\n",
                "",
            )
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(wd, "_git", fake_git)

    assert wd._reachable_from_remote(tmp_path, "abc123") is True
    assert calls == [
        [
            "for-each-ref",
            "--contains=abc123",
            "--format=%(refname)",
            "refs/remotes",
        ]
    ]


def test_documented_non_source_residue_is_visible_but_not_debt(tmp_path: Path, monkeypatch):
    worktrees = tmp_path / ".limen-worktrees"
    documented = worktrees / "cache-only-root"
    undocumented = worktrees / "unknown-root"
    documented.mkdir(parents=True)
    undocumented.mkdir()
    (documented / "metadata.json").write_text("{}", encoding="utf-8")
    (undocumented / "metadata.json").write_text("{}", encoding="utf-8")
    receipts = tmp_path / "docs" / "worktree-preservation-receipts.json"
    receipts.parent.mkdir()
    receipts.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "cache-only-root",
                        "lane": "documented-residue",
                        "status": "cache_only_residue",
                        "classification": "documented non-source residue",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")

    report = worktree_debt_report(tmp_path)
    by_name = {item["name"]: item for item in report["items"]}

    assert by_name["cache-only-root"]["reason"] == "documented-residue"
    assert by_name["cache-only-root"]["debt"] is False
    assert by_name["unknown-root"]["reason"] == "not-a-git-dir"
    assert by_name["unknown-root"]["debt"] is True
    assert report["debt"] == 1


def test_generated_log_shell_is_visible_but_not_debt(tmp_path: Path, monkeypatch):
    worktrees = tmp_path / ".limen-worktrees"
    shell = worktrees / "generated-log-shell"
    (shell / "logs").mkdir(parents=True)
    (shell / "logs" / "session-lifecycle-pressure.md").write_text("generated\n", encoding="utf-8")
    (shell / "logs" / "session-lifecycle-pressure.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")

    report = worktree_debt_report(tmp_path)

    assert report["items"][0]["name"] == "generated-log-shell"
    assert report["items"][0]["reason"] == "generated-log-shell"
    assert report["items"][0]["debt"] is False
    assert report["debt"] == 0


def test_antigravity_scratch_is_managed_by_bridge_not_worktree_debt(tmp_path: Path, monkeypatch):
    worktrees = tmp_path / ".limen-worktrees"
    worktrees.mkdir()
    scratch = tmp_path / "agy-scratch"
    root = scratch / "clean-merged-root"
    root.mkdir(parents=True)
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_AGY_SCRATCH", "1")
    monkeypatch.setenv("LIMEN_AGY_SCRATCH_ROOT", str(scratch))

    report = worktree_debt_report(tmp_path)

    assert report["items"][0]["name"] == "clean-merged-root"
    assert report["items"][0]["reason"] == "antigravity-scratch-managed"
    assert report["items"][0]["debt"] is False
    assert report["items"][0]["reapable"] is False
    assert report["debt"] == 0
    assert report["reapable"] == 0


def test_remote_superseded_receipt_is_visible_but_not_debt(tmp_path: Path, monkeypatch):
    worktrees = tmp_path / ".limen-worktrees"
    root = worktrees / "superseded-root"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    (root / "README.md").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)
    (root / "README.md").write_text("dirty but superseded upstream\n", encoding="utf-8")
    receipts = tmp_path / "docs" / "worktree-preservation-receipts.json"
    receipts.parent.mkdir()
    receipts.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "superseded-root",
                        "lane": "remote-superseded",
                        "status": "superseded_on_origin_main",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")

    report = worktree_debt_report(tmp_path)

    assert report["items"][0]["name"] == "superseded-root"
    assert report["items"][0]["reason"] == "remote-superseded"
    assert report["items"][0]["debt"] is False
    assert report["debt"] == 0


def test_remote_merged_receipt_is_visible_but_not_debt(tmp_path: Path, monkeypatch):
    worktrees = tmp_path / ".limen-worktrees"
    root = worktrees / "merged-pr-root"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    (root / "README.md").write_text("merged work\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "merged work"], cwd=root, check=True)
    receipts = tmp_path / "docs" / "worktree-preservation-receipts.json"
    receipts.parent.mkdir()
    receipts.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "merged-pr-root",
                        "lane": "remote-merged",
                        "status": "merged_pr_preserved",
                        "pr_state": "MERGED",
                        "pr_url": "https://github.com/example/repo/pull/7",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "0")

    report = worktree_debt_report(tmp_path)

    assert report["items"][0]["name"] == "merged-pr-root"
    assert report["items"][0]["reason"] == "receipt-remote-merged+clean+idle"
    assert report["items"][0]["debt"] is False
    assert report["items"][0]["reapable"] is True
    assert report["debt"] == 0
    assert report["reapable"] == 1


def test_remote_pr_open_receipt_is_visible_but_not_debt(tmp_path: Path, monkeypatch):
    worktrees = tmp_path / ".limen-worktrees"
    root = worktrees / "open-pr-root"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    (root / "README.md").write_text("open pr work\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "open pr work"], cwd=root, check=True)
    receipts = tmp_path / "docs" / "worktree-preservation-receipts.json"
    receipts.parent.mkdir()
    receipts.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "open-pr-root",
                        "lane": "remote-pr-open",
                        "status": "open_pr_preserved",
                        "pr_state": "OPEN",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "0")

    report = worktree_debt_report(tmp_path)

    assert report["items"][0]["name"] == "open-pr-root"
    assert report["items"][0]["reason"] == "remote-pr-open"
    assert report["items"][0]["debt"] is False
    assert report["debt"] == 0


def test_owner_blocker_private_receipt_is_visible_but_not_debt(tmp_path: Path, monkeypatch):
    worktrees = tmp_path / ".limen-worktrees"
    root = worktrees / "owner-blocked-root"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    (root / "README.md").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)
    (root / "README.md").write_text("private patch preserved\n", encoding="utf-8")
    receipts = tmp_path / "docs" / "worktree-preservation-receipts.json"
    receipts.parent.mkdir()
    receipts.write_text(
        json.dumps(
            {
                "receipts": [
                    {
                        "root": "owner-blocked-root",
                        "lane": "owner-blocker",
                        "status": "private_patch_preserved",
                        "private_receipt": ".limen-private/session-corpus/lifecycle/worktree-preserve/demo/receipt.json",
                        "private_patch_sha256": "abc123",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "0")

    report = worktree_debt_report(tmp_path)

    assert report["items"][0]["name"] == "owner-blocked-root"
    assert report["items"][0]["reason"] == "owner-blocker"
    assert report["items"][0]["debt"] is False
    assert report["debt"] == 0


def test_clean_git_root_still_classifies_without_receipt(tmp_path: Path, monkeypatch):
    worktrees = tmp_path / ".limen-worktrees"
    root = worktrees / "git-root"
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    (root / "README.md").write_text("ok\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True)
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "0")

    report = worktree_debt_report(tmp_path)

    assert report["items"][0]["name"] == "git-root"
    assert report["items"][0]["reason"] == "unpushed-commits"
    assert report["items"][0]["debt"] is True
    assert report["items"][0]["reapable"] is False


def test_default_worktree_root_uses_limen_worktrees_env(tmp_path: Path, monkeypatch):
    scratch = tmp_path / "scratch" / "limen-worktrees"
    monkeypatch.delenv("LIMEN_WORKTREE_ROOT", raising=False)
    monkeypatch.setenv("LIMEN_WORKTREES", str(scratch))

    assert wr.effective_worktree_root() == scratch


def test_clean_pushed_unmerged_root_is_debt(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=source, check=True)
    (source / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=source, check=True)
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)], cwd=tmp_path, check=True)
    main = tmp_path / "main"
    subprocess.run(["git", "clone", "-q", str(bare), str(main)], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=main, check=True)

    worktrees = tmp_path / ".limen-worktrees"
    branch = worktrees / "pushed-branch"
    worktrees.mkdir()
    subprocess.run(["git", "worktree", "add", "-q", str(branch), "-b", "feature"], cwd=main, check=True)
    (branch / "feature.txt").write_text("feature\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.txt"], cwd=branch, check=True)
    subprocess.run(["git", "commit", "-qm", "feature"], cwd=branch, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:feature"], cwd=branch, check=True)
    subprocess.run(["git", "fetch", "-q", "origin", "feature:refs/remotes/origin/feature"], cwd=branch, check=True)

    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_PUSHED_OK", "0")

    report = worktree_debt_report(tmp_path)

    assert report["debt"] == 1
    assert report["reapable"] == 0
    assert report["items"][0]["reason"] == "not-merged-to-default"
    assert report["items"][0]["debt"] is True
    assert report["items"][0]["reapable"] is False


def test_clean_pushed_unmerged_root_matches_reaper_when_escape_hatch_is_enabled(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=source, check=True)
    (source / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=source, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=source, check=True)
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(source), str(bare)], cwd=tmp_path, check=True)
    main = tmp_path / "main"
    subprocess.run(["git", "clone", "-q", str(bare), str(main)], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=main, check=True)

    worktrees = tmp_path / ".limen-worktrees"
    branch = worktrees / "pushed-branch"
    worktrees.mkdir()
    subprocess.run(["git", "worktree", "add", "-q", str(branch), "-b", "feature"], cwd=main, check=True)
    (branch / "feature.txt").write_text("feature\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature.txt"], cwd=branch, check=True)
    subprocess.run(["git", "commit", "-qm", "feature"], cwd=branch, check=True)
    subprocess.run(["git", "push", "-q", "origin", "HEAD:feature"], cwd=branch, check=True)
    subprocess.run(["git", "fetch", "-q", "origin", "feature:refs/remotes/origin/feature"], cwd=branch, check=True)

    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(worktrees))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_MIN_AGE_H", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_PUSHED_OK", "1")
    report = worktree_debt_report(tmp_path)

    assert report["debt"] == 0
    assert report["reapable"] == 1
    assert report["items"][0]["reason"] == "clean+pushed+idle"


def test_nested_live_checkout_child_is_not_independent_worktree_debt(tmp_path: Path, monkeypatch):
    root = tmp_path / "limen"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=root, check=True)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)

    nested = root / ".claude" / "worktrees" / "session-log-only"
    (nested / "logs").mkdir(parents=True)
    docs = root / "docs"
    docs.mkdir()
    (docs / "conductor-tranche.md").write_text("generated receipt drift\n", encoding="utf-8")
    central = tmp_path / ".limen-worktrees"
    central.mkdir()
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(central))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "1")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_AGE_H", "0")

    report = worktree_debt_report(root)

    assert report["items"][0]["name"] == "session-log-only"
    assert report["items"][0]["reason"] == "self/live-checkout"
    assert report["items"][0]["debt"] is False
    assert report["debt"] == 0


def test_repo_local_worktrees_are_scanned_when_enabled(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "Workspace"
    repo_local = workspace / "4444J99" / "portvs" / ".worktrees" / "triptych-story"
    repo_local.mkdir(parents=True)
    central = tmp_path / ".limen-worktrees"
    central.mkdir()
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(central))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "1")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_WORKSPACE_ROOTS", str(workspace))

    report = worktree_debt_report(tmp_path)
    by_name = {item["name"]: item for item in report["items"]}

    assert by_name["triptych-story"]["path"] == str(repo_local)
    assert by_name["triptych-story"]["reason"] == "not-a-git-dir"
    assert by_name["triptych-story"]["debt"] is True


def test_registered_sibling_worktrees_are_scanned_when_enabled(tmp_path: Path, monkeypatch):
    main = tmp_path / "limen-main"
    sibling = tmp_path / "limen-main-trench-20260628"
    main.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=main, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=main, check=True)
    (main / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=main, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=main, check=True)
    subprocess.run(["git", "worktree", "add", "-q", str(sibling), "-b", "work/main-trench"], cwd=main, check=True)
    central = tmp_path / ".limen-worktrees"
    central.mkdir()
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(central))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REPO_LOCAL_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "1")
    monkeypatch.setenv("LIMEN_RECLAIM_MAIN_REPOS", str(main))
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_AGE_H", "0")

    report = worktree_debt_report(tmp_path)
    by_name = {item["name"]: item for item in report["items"]}

    assert by_name["limen-main-trench-20260628"]["path"] == str(sibling)
    assert by_name["limen-main-trench-20260628"]["reason"] == "unpushed-commits"
    assert by_name["limen-main-trench-20260628"]["debt"] is True


# ── Marginal live worktree-lifecycle admission ─────────────────────────────
#
# Impact is binary and derives from lane locality only. Gate authority is fail-closed resource +
# VITALS + reaper truth — never a fixed worktree count. Fixtures use arbitrary root counts to prove
# no count is a policy authority.


def _live_snapshot(**over) -> wd.WorktreeAdmissionSnapshot:
    base = dict(
        active=True,
        block_new_local=False,
        reason="",
        resource_blocked=False,
        vitals_shed=False,
        reaper_blocked=False,
        free_gib=500.0,
        floor_gib=60,
        reserved_gib=0.0,
        room_gib=440.0,
        targets_present=False,
        debt=None,
        vitals_action="ok",
    )
    base.update(over)
    return wd.WorktreeAdmissionSnapshot(**base)


def _isolate(tmp_path: Path, monkeypatch, *, floor="1") -> Path:
    wtroot = tmp_path / ".limen-worktrees"
    wtroot.mkdir()
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "1")
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(wtroot))
    monkeypatch.setenv("LIMEN_DISK_FLOOR_GIB", floor)
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    monkeypatch.setenv("LIMEN_RECLAIM", "1")
    monkeypatch.setenv("LIMEN_RECLAIM_APPLY", "1")
    monkeypatch.setenv("LIMEN_RECLAIM_STANDING_ACCEPTANCE", "1")
    monkeypatch.setenv("LIMEN_RECLAIM_EVERY_MIN", "30")
    monkeypatch.setenv("LIMEN_BEAT_DRAIN", "3")
    monkeypatch.setenv("LIMEN_LOOP_MAX", "1800")
    monkeypatch.setenv("LIMEN_RECLAIM_TIMEOUT", "300")
    monkeypatch.setattr(wd, "_vitals_action", lambda: "ok")
    return wtroot


# ---- admission_blocks: the pure per-candidate decision ----


def test_impact_constants_are_binary() -> None:
    assert wd.IMPACT_REMOTE == "remote"
    assert wd.IMPACT_DEBT_CREATING == "debt-creating"
    assert not hasattr(wd, "IMPACT_DEBT_REDUCING")
    assert not hasattr(wd, "IMPACT_NON_INCREASING")


def test_admission_blocks_local_when_block_new_local() -> None:
    snap = _live_snapshot(block_new_local=True, reason="no custody")
    assert wd.admission_blocks(wd.IMPACT_DEBT_CREATING, snap) == (True, "no custody")


def test_admission_allows_local_when_custody_available() -> None:
    assert wd.admission_blocks(wd.IMPACT_DEBT_CREATING, _live_snapshot(), 1.0) == (False, "")


def test_admission_unknown_checkout_estimate_fails_closed_local() -> None:
    blocked, reason = wd.admission_blocks(wd.IMPACT_DEBT_CREATING, _live_snapshot(), None)
    assert blocked is True
    assert "tracked HEAD checkout size is unknown" in reason


def test_admission_zero_checkout_estimate_fails_closed() -> None:
    blocked, reason = wd.admission_blocks(wd.IMPACT_DEBT_CREATING, _live_snapshot(), 0.0)
    assert blocked is True
    assert "checkout size is invalid" in reason


def test_admission_at_floor_cannot_admit_tiny_unavoidable_checkout() -> None:
    snapshot = _live_snapshot(free_gib=60.0, floor_gib=60.0, room_gib=0.0)
    blocked, reason = wd.admission_blocks(wd.IMPACT_DEBT_CREATING, snapshot, 4096 / (1024**3))
    assert blocked is True
    assert "only 0.000 GiB remains above floor" in reason


def test_admission_reserves_cumulative_room_for_selected_local_candidates() -> None:
    snapshot = _live_snapshot(free_gib=61.5, floor_gib=60.0, reserved_gib=0.0, room_gib=1.5)

    assert wd.admission_blocks(wd.IMPACT_DEBT_CREATING, snapshot, 1.0, reserve=True) == (False, "")
    assert snapshot["reserved_gib"] == 1.0
    assert snapshot["room_gib"] == 0.5

    blocked, reason = wd.admission_blocks(wd.IMPACT_DEBT_CREATING, snapshot, 0.6, reserve=True)
    assert blocked is True
    assert "only 0.500 GiB remains" in reason
    assert snapshot["reserved_gib"] == 1.0
    assert snapshot["room_gib"] == 0.5


def test_admission_never_blocks_remote_even_when_blocked() -> None:
    snap = _live_snapshot(block_new_local=True, reason="critical")
    assert wd.admission_blocks(wd.IMPACT_REMOTE, snap) == (False, "")


def test_remote_admission_never_consumes_local_checkout_room() -> None:
    snapshot = _live_snapshot(free_gib=60.1, floor_gib=60.0, reserved_gib=0.0, room_gib=0.1)
    for _ in range(20):
        assert wd.admission_blocks(wd.IMPACT_REMOTE, snapshot, None, reserve=True) == (False, "")
    assert snapshot["reserved_gib"] == 0.0
    assert snapshot["room_gib"] == 0.1


def test_admission_inactive_blocks_nothing() -> None:
    snap = _live_snapshot(active=False, block_new_local=True, reason="x")
    assert wd.admission_blocks(wd.IMPACT_DEBT_CREATING, snap) == (False, "")
    assert wd.admission_blocks(wd.IMPACT_REMOTE, snap) == (False, "")


# ---- take_admission_snapshot: resource custody (fail closed on unknown) ----


def test_snapshot_operator_override_gate_off(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "0")
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["active"] is False and snap["block_new_local"] is False


def test_gate_active_uses_registered_default_when_override_absent(monkeypatch) -> None:
    monkeypatch.delenv("LIMEN_WORKTREE_DEBT_GATE", raising=False)
    assert wd._gate_active() is True


def test_gate_active_only_explicit_zero_or_false_disables(monkeypatch) -> None:
    for value in ("0", "false", "FALSE"):
        monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", value)
        assert wd._gate_active() is False


def test_gate_active_invalid_values_fail_closed_active(monkeypatch) -> None:
    for value in ("", "bogus", "off", "true"):
        monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", value)
        assert wd._gate_active() is True


def test_snapshot_resource_blocks_below_floor(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch, floor="45")
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 3.0)
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["resource_blocked"] is True and snap["block_new_local"] is True
    assert "45 GiB floor" in snap["reason"]


def test_snapshot_resource_unknown_free_fails_closed(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: None)
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["resource_blocked"] is True and snap["block_new_local"] is True
    assert "unknown" in snap["reason"]


def test_snapshot_floor_from_registered_parameter(tmp_path: Path, monkeypatch) -> None:
    # No env floor → the LIMEN_DISK_FLOOR_GIB panel default (parameter authority) is used, not 45.
    _isolate(tmp_path, monkeypatch)
    monkeypatch.delenv("LIMEN_DISK_FLOOR_GIB", raising=False)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["floor_gib"] == 60  # parameters.yaml default
    assert snap["resource_blocked"] is False


def test_disk_floor_accepts_positive_override(monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_DISK_FLOOR_GIB", "45.5")
    assert wd._disk_floor_gib() == 45.5


def test_disk_floor_rejects_nonpositive_nonfinite_and_invalid(monkeypatch) -> None:
    for value in ("-1", "0", "nan", "inf", "bogus", ""):
        monkeypatch.setenv("LIMEN_DISK_FLOOR_GIB", value)
        assert wd._disk_floor_gib() is None


def test_snapshot_invalid_disk_floor_fails_closed_local(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    for value in ("-1", "0", "nan", "bogus"):
        monkeypatch.setenv("LIMEN_DISK_FLOOR_GIB", value)
        snap = wd.take_admission_snapshot(tmp_path)
        assert snap["floor_gib"] is None
        assert snap["resource_blocked"] is True and snap["block_new_local"] is True


# ---- VITALS fold ----


def test_snapshot_vitals_shed_blocks_local(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    monkeypatch.setattr(wd, "_vitals_action", lambda: "shed")
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["vitals_shed"] is True and snap["block_new_local"] is True
    assert "VITALS" in snap["reason"]


def test_snapshot_vitals_throttle_does_not_block(tmp_path: Path, monkeypatch) -> None:
    # throttle is served by the separate reduced-concurrency ceiling, not by admission (no score).
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    monkeypatch.setattr(wd, "_vitals_action", lambda: "throttle")
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["vitals_shed"] is False and snap["block_new_local"] is False


# ---- Reaper fold (cheap file state, no heavy scan) ----


def _seed_debt(wtroot: Path, n: int) -> None:
    for i in range(n):  # non-git residue roots → debt
        (wtroot / f"residue-{i}").mkdir()


def _write_reaper_receipt(
    root: Path,
    ts: float,
    *,
    completed_ts: object = None,
    apply: object = True,
    deferred: object = None,
    marker_ts: object = None,
    mtime: float | None = None,
    extra: dict[str, object] | None = None,
) -> tuple[Path, Path]:
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    completed = ts if completed_ts is None else completed_ts
    event: dict[str, object] = {
        "ts": ts,
        "completed_ts": completed,
        "apply": apply,
        "deferred_over_cap": [] if deferred is None else deferred,
    }
    event.update(extra or {})
    log = logs / "reclaim-worktrees.jsonl"
    log.write_text(json.dumps(event) + "\n", encoding="utf-8")
    marker = logs / ".reclaim-last"
    marker.write_text(str(completed if marker_ts is None else marker_ts), encoding="utf-8")
    durable_at = float(completed) if mtime is None else mtime
    os.utime(log, (durable_at, durable_at))
    os.utime(marker, (durable_at, durable_at))
    return marker, log


def test_reaper_coherent_apply_receipt_admits_even_with_zero_removals_failures_and_skips(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    monkeypatch.setattr(wd.time, "time", lambda: now)
    _write_reaper_receipt(
        tmp_path,
        now - 60,
        extra={
            "removed": [],
            "skipped": {"owned": "not-merged-to-default"},
            "failed": {"other": "git timeout"},
            "generated_reclaim": {"failed": ["cache"]},
        },
    )
    assert wd._reaper_blocks_new_local(tmp_path, True) == (False, "")


def test_reaper_does_not_use_acceptance_ledger_as_generic_authority(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "worktree-reclaim-acceptance.jsonl").write_text('{"root":"x"}\n')
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "receipt missing" in reason


def test_reaper_deferred_over_cap_blocks_and_must_be_a_list(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    monkeypatch.setattr(wd.time, "time", lambda: now)
    _write_reaper_receipt(tmp_path, now - 60, deferred=["a", "b"])
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "deferred 2" in reason
    _write_reaper_receipt(tmp_path, now - 60, deferred=0)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "not a list" in reason


def test_reaper_missing_marker_or_log_blocks(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "receipt missing" in reason
    now = 2_000_000_000.0
    _write_reaper_receipt(tmp_path, now - 60)
    (tmp_path / "logs" / ".reclaim-last").unlink()
    monkeypatch.setattr(wd.time, "time", lambda: now)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "missing or unreadable" in reason


def test_reaper_malformed_final_nonblank_line_blocks_without_falling_back(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    marker, log = _write_reaper_receipt(tmp_path, now - 60)
    with log.open("a", encoding="utf-8") as handle:
        handle.write('{"ts":')
    os.utime(log, (now - 60, now - 60))
    os.utime(marker, (now - 60, now - 60))
    monkeypatch.setattr(wd.time, "time", lambda: now)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "malformed or truncated" in reason


def test_reaper_marker_must_exactly_match_event_timestamp(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    monkeypatch.setattr(wd.time, "time", lambda: now)
    _write_reaper_receipt(tmp_path, now - 60, marker_ts=now - 59, mtime=now - 50)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "does not match" in reason


def test_reaper_apply_false_blocks(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    _write_reaper_receipt(tmp_path, now - 60, apply=False)
    monkeypatch.setattr(wd.time, "time", lambda: now)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "not an apply run" in reason


def test_reaper_legacy_receipt_without_completed_ts_fails_strict_cutover(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    _marker, log = _write_reaper_receipt(tmp_path, now - 60)
    event = json.loads(log.read_text(encoding="utf-8"))
    event.pop("completed_ts")
    log.write_text(json.dumps(event) + "\n", encoding="utf-8")
    os.utime(log, (now - 60, now - 60))
    monkeypatch.setattr(wd.time, "time", lambda: now)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "strict receipt missing" in reason and "next apply run" in reason


def test_reaper_stale_and_boundary_use_scheduler_derived_window(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    # max(2*30, 3*1800/60 + 300/60) = 95 minutes; equality is fresh.
    monkeypatch.setattr(wd.time, "time", lambda: now)
    _write_reaper_receipt(tmp_path, now - 95 * 60)
    assert wd._reaper_blocks_new_local(tmp_path, True) == (False, "")
    _write_reaper_receipt(tmp_path, now - 95 * 60 - 0.001)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "stale" in reason


def test_reaper_freshness_uses_durable_completion_not_old_run_start(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    monkeypatch.setattr(wd.time, "time", lambda: now)
    # A long bounded reclaim may start before the 95-minute scheduler window but complete now.
    _write_reaper_receipt(tmp_path, now - 120 * 60, completed_ts=now - 1, mtime=now - 1)
    assert wd._reaper_blocks_new_local(tmp_path, True) == (False, "")


def test_reaper_touching_old_receipt_does_not_replay_freshness(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    monkeypatch.setattr(wd.time, "time", lambda: now)
    _write_reaper_receipt(tmp_path, now - 120 * 60, mtime=now - 1)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "stale" in reason


def test_reaper_future_and_invalid_chronology_block(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    monkeypatch.setattr(wd.time, "time", lambda: now)
    _write_reaper_receipt(tmp_path, now + 1)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "future-dated" in reason
    _write_reaper_receipt(tmp_path, now - 60, mtime=now - 120)
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "chronology" in reason


def test_reaper_nan_and_nonpositive_timestamps_block(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(wd.time, "time", lambda: 2_000_000_000.0)
    for bad in (float("nan"), 0.0, -1.0):
        _write_reaper_receipt(tmp_path, bad, mtime=1_900_000_000.0)
        blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
        assert blocked is True and "finite and positive" in reason
    _write_reaper_receipt(
        tmp_path,
        1_900_000_000.0,
        completed_ts=float("nan"),
        mtime=1_900_000_001.0,
    )
    blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
    assert blocked is True and "completion timestamp is not finite" in reason


def test_reaper_requires_live_reclaim_and_apply_toggles(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    for switch in (
        "LIMEN_RECLAIM",
        "LIMEN_RECLAIM_APPLY",
    ):
        monkeypatch.setenv(switch, "0")
        blocked, reason = wd._reaper_blocks_new_local(tmp_path, False)
        assert blocked is True and switch in reason
        monkeypatch.setenv(switch, "1")


def test_reaper_standing_acceptance_is_policy_not_liveness(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    monkeypatch.setenv("LIMEN_RECLAIM_STANDING_ACCEPTANCE", "0")
    monkeypatch.setattr(wd.time, "time", lambda: now)
    _write_reaper_receipt(tmp_path, now - 60)
    assert wd._reaper_blocks_new_local(tmp_path, True) == (False, "")


def test_reaper_scheduler_parameters_must_be_finite_and_positive(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    now = 2_000_000_000.0
    monkeypatch.setattr(wd.time, "time", lambda: now)
    _write_reaper_receipt(tmp_path, now - 60)
    for name in (
        "LIMEN_RECLAIM_EVERY_MIN",
        "LIMEN_BEAT_DRAIN",
        "LIMEN_LOOP_MAX",
        "LIMEN_RECLAIM_TIMEOUT",
    ):
        for bad in ("nan", "0", "-1"):
            monkeypatch.setenv(name, bad)
            blocked, reason = wd._reaper_blocks_new_local(tmp_path, True)
            assert blocked is True and "scheduler parameters are invalid" in reason
        monkeypatch.setenv(
            name,
            {
                "LIMEN_RECLAIM_EVERY_MIN": "30",
                "LIMEN_BEAT_DRAIN": "3",
                "LIMEN_LOOP_MAX": "1800",
                "LIMEN_RECLAIM_TIMEOUT": "300",
            }[name],
        )


def test_reaper_zero_targets_need_enablement_but_no_marker_or_log(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    assert wd._reaper_blocks_new_local(tmp_path, False) == (False, "")


def test_reclaim_tail_reads_only_final_chunk_when_last_line_is_short(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "large.jsonl"
    log.write_bytes(b"x" * 100_000 + b"\n" + b'{"ts": 7}\n\n')
    monkeypatch.setattr(Path, "read_text", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("whole read")))
    assert wd._last_nonblank_line(log, chunk_size=64) == b'{"ts": 7}'


def _write_cached_debt(root: Path, debt: object) -> None:
    logs = root / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "session-lifecycle-pressure.json").write_text(
        json.dumps({"worktrees": {"debt": debt}}),
        encoding="utf-8",
    )


def test_snapshot_zero_targets_need_no_receipt_after_live_switches(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)  # empty direct inventory
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["targets_present"] is False
    assert snap["debt"] is None
    assert snap["reaper_blocked"] is False and snap["block_new_local"] is False


def test_snapshot_does_not_call_full_worktree_debt_report(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    monkeypatch.setattr(wd, "worktree_debt_report", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["targets_present"] is False
    assert snap["debt"] is None
    assert snap["block_new_local"] is False


def test_snapshot_unknown_target_inventory_fails_closed(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    monkeypatch.setattr(wd, "iter_worktree_targets", lambda *_a, **_k: (_ for _ in ()).throw(OSError("boom")))
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["targets_present"] is None
    assert snap["reaper_blocked"] is True and snap["block_new_local"] is True
    assert "target inventory unknown" in snap["reason"]


def test_snapshot_unreadable_configured_root_fails_closed_via_strict_inventory(tmp_path: Path, monkeypatch) -> None:
    worktrees = _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    original_iterdir = Path.iterdir

    def deny_configured_root(path: Path):
        if path == worktrees:
            raise PermissionError("configured worktree root is unreadable")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", deny_configured_root)
    snap = wd.take_admission_snapshot(tmp_path)

    assert snap["targets_present"] is None
    assert snap["reaper_blocked"] is True
    assert snap["block_new_local"] is True
    assert "target inventory unknown" in snap["reason"]


def test_snapshot_null_target_inventory_fails_closed(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    monkeypatch.setattr(wd, "iter_worktree_targets", lambda *_a, **_k: None)
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["targets_present"] is None
    assert snap["reaper_blocked"] is True and "target inventory unknown" in snap["reason"]


def test_snapshot_any_target_requires_durable_receipt_even_when_cached_debt_is_zero(
    tmp_path: Path, monkeypatch
) -> None:
    wtroot = _isolate(tmp_path, monkeypatch)
    _seed_debt(wtroot, 1)
    _write_cached_debt(tmp_path, 0)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["targets_present"] is True and snap["debt"] == 0
    assert snap["reaper_blocked"] is True and "receipt missing" in snap["reason"]


def test_snapshot_cached_debt_is_diagnostic_not_admission_authority(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)  # no direct targets
    _write_cached_debt(tmp_path, 999)
    monkeypatch.setattr(wd, "_worktree_disk_free_gib", lambda _p: 500.0)
    snap = wd.take_admission_snapshot(tmp_path)
    assert snap["targets_present"] is False and snap["debt"] == 999
    assert snap["reaper_blocked"] is False and snap["block_new_local"] is False


# ---- No fixed-count authority anywhere ----


def test_no_count_cap_authority_in_module() -> None:
    src = (ROOT / "cli" / "src" / "limen" / "worktree_debt.py").read_text()
    assert "LIMEN_WORKTREE_DEBT_MAX" not in src
    assert "worktree_debt_exceeded(" not in src  # retired; only mentioned in a comment
    assert "live_threshold" not in src
    assert "_compute_live_admission_score" not in src


def test_worktree_debt_zero_is_the_completion_predicate(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / ".limen-worktrees"
    empty.mkdir()
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_WORKTREE_ROOT", str(empty))
    monkeypatch.setenv("LIMEN_RECLAIM_CLAUDE_WT", "0")
    complete, report = wd.worktree_debt_zero(tmp_path)
    assert complete is True and report["debt"] == 0
    (empty / "residue").mkdir()  # one non-git root → debt
    complete2, report2 = wd.worktree_debt_zero(tmp_path)
    assert complete2 is False and report2["debt"] >= 1


def test_strict_completion_preserves_unreadable_inventory_failure(tmp_path: Path, monkeypatch) -> None:
    dispatch_root = _isolate(tmp_path, monkeypatch)
    original_iterdir = Path.iterdir

    def deny_dispatch(path: Path):
        if path == dispatch_root:
            raise PermissionError("configured dispatch root is unreadable")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", deny_dispatch)

    assert wd.worktree_debt_report(tmp_path)["debt"] == 0
    with pytest.raises(wr.WorktreeInventoryError, match="dispatch-root"):
        wd.worktree_debt_report(tmp_path, strict=True)
    with pytest.raises(wr.WorktreeInventoryError, match="dispatch-root"):
        wd.worktree_debt_zero(tmp_path, strict=True)


def test_strict_completion_preserves_registered_git_inventory_failure(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    configured_nonrepo = tmp_path / "configured-nonrepo"
    configured_nonrepo.mkdir()
    monkeypatch.setenv("LIMEN_RECLAIM_REGISTERED_WT", "1")
    monkeypatch.setenv("LIMEN_RECLAIM_MAIN_REPOS", str(configured_nonrepo))

    assert wd.worktree_debt_report(tmp_path)["debt"] == 0
    with pytest.raises(wr.WorktreeInventoryError, match="git worktree inventory failed"):
        wd.worktree_debt_zero(tmp_path, strict=True)


def test_worktree_debt_cli_strict_fails_closed_on_incomplete_inventory(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    configured_nonrepo = tmp_path / "configured-nonrepo"
    configured_nonrepo.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "LIMEN_ROOT": str(tmp_path),
            "LIMEN_RECLAIM_REGISTERED_WT": "1",
            "LIMEN_RECLAIM_MAIN_REPOS": str(configured_nonrepo),
        }
    )

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "worktree-debt.py"), "--strict", "--fail-on-debt"],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )

    assert result.returncode == 2
    assert "worktree lifecycle inventory incomplete" in result.stderr
    assert "git worktree inventory failed" in result.stderr


# ── --trend tests (IF-AMALGAMATION distance_metric) ───────────────────────────────────────────────


def test_trend_append_and_stable(tmp_path: Path) -> None:
    """Single sample is always stable (no trend to measure)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("wdt", ROOT / "scripts" / "worktree-debt.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    trend_path = tmp_path / "debt-trend.jsonl"
    ledger = mod._append_trend(100, "2026-07-15T01:00:00Z", trend_path)
    assert len(ledger) == 1
    assert ledger[0] == {"stamp": "2026-07-15T01:00:00Z", "debt": 100}
    assert not mod._trend_rising(ledger, 10)


def test_trend_rising_detected(tmp_path: Path) -> None:
    """Strictly ascending window is flagged as rising."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("wdt", ROOT / "scripts" / "worktree-debt.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    trend_path = tmp_path / "debt-trend.jsonl"
    stamps = [f"2026-07-15T0{i}:00:00Z" for i in range(1, 6)]
    for i, s in enumerate(stamps):
        mod._append_trend(100 + i * 10, s, trend_path)
    ledger = [json.loads(ln) for ln in trend_path.read_text().splitlines() if ln.strip()]
    assert mod._trend_rising(ledger, 5)


def test_trend_flat_not_rising(tmp_path: Path) -> None:
    """Flat (equal) sequence is not rising."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("wdt", ROOT / "scripts" / "worktree-debt.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    trend_path = tmp_path / "debt-trend.jsonl"
    for _ in range(4):
        mod._append_trend(300, None, trend_path)
    ledger = [json.loads(ln) for ln in trend_path.read_text().splitlines() if ln.strip()]
    assert not mod._trend_rising(ledger, 4)


def test_trend_cli_stable_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--trend with a single sample exits 0 and prints 'stable'."""
    _isolate(tmp_path, monkeypatch)
    trend_path = tmp_path / "logs" / "debt-trend.jsonl"
    env = os.environ.copy()
    env["LIMEN_ROOT"] = str(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "worktree-debt.py"),
            "--trend",
            "--stamp",
            "2026-07-15T10:00:00Z",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert trend_path.exists()
    records = [json.loads(ln) for ln in trend_path.read_text().splitlines() if ln.strip()]
    assert len(records) == 1
    assert records[0]["stamp"] == "2026-07-15T10:00:00Z"
    assert "stable" in result.stdout
