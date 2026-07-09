from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen import worktree_debt as wd  # noqa: E402
from limen import worktree_roots as wr  # noqa: E402
from limen.worktree_debt import worktree_debt_report  # noqa: E402


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
    assert report["items"][0]["reason"] == "remote-merged"
    assert report["items"][0]["debt"] is False
    assert report["debt"] == 0


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

    report = worktree_debt_report(tmp_path)

    assert report["debt"] == 1
    assert report["reapable"] == 0
    assert report["items"][0]["reason"] == "not-merged-to-default"
    assert report["items"][0]["debt"] is True
    assert report["items"][0]["reapable"] is False


def test_clean_pushed_unmerged_root_is_debt_without_escape_hatch(tmp_path: Path, monkeypatch):
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
    report = worktree_debt_report(tmp_path)

    assert report["debt"] == 1
    assert report["reapable"] == 0
    assert report["items"][0]["reason"] == "not-merged-to-default"


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
