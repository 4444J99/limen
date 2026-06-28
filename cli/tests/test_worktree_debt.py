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
