from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.worktree_debt import worktree_debt_report


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
