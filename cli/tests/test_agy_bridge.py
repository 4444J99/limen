"""Tests for the agy/antigravity scratch-carry bridge (dispatch._bridge_agy_scratch).

agy writes its work to a long-lived, REUSED git scratch clone, not the cwd worktree. The bridge
carries that work home — but must carry ONLY agy's per-run DELTA (its uncommitted changes), never
the whole (possibly stale, off-trunk) committed tree. The old whole-tree `rsync -a` overlaid a
day-stale base onto fresh origin/main and overwrote grown files with shorter stale contents →
thousands of spurious deletions per PR (the destructive "deepen" PRs that got closed). These tests
pin the delta-only behavior so that regression can never return.
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import limen.dispatch as D
from limen.models import Task


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def test_porcelain_paths_parses_modes():
    # modified, added, renamed (R new\0old), untracked — NUL-terminated -z stream
    z = " M file_a.py\x00A  file_b.py\x00R  new_name.py\x00old_name.py\x00?? untracked.md\x00"
    assert D._porcelain_paths(z) == ["file_a.py", "file_b.py", "new_name.py", "untracked.md"]
    # the rename's OLD path (old_name.py) is consumed, never returned as a path to carry
    assert "old_name.py" not in D._porcelain_paths(z)


def _make_scratch(home: Path, repo: str) -> Path:
    scratch = home / ".gemini" / "antigravity-cli" / "scratch" / "limen"
    scratch.mkdir(parents=True)
    _git(["init", "-q"], scratch)
    _git(["remote", "add", "origin", f"https://github.com/{repo}.git"], scratch)
    # a committed base file agy did NOT touch this run — it must NEVER be carried
    (scratch / "base.py").write_text("base line 1\nbase line 2\nbase line 3\n")
    _git(["add", "-A"], scratch)
    _git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"], scratch)
    # agy's per-run delta: one modified tracked file + one new untracked file
    (scratch / "base.py").write_text("base line 1\nbase line 2\nbase line 3\nAGY-EDIT\n")
    (scratch / "agy_new.py").write_text("agy made this\n")
    return scratch


def test_bridge_carries_only_delta(tmp_path, monkeypatch):
    repo = "organvm/limen"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    _make_scratch(home, repo)

    # the worktree off FRESH main: an unrelated file agy never saw — the old whole-tree rsync
    # would have clobbered it; delta-only must leave it intact.
    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / "untouched.py").write_text("a fresh-main file agy never touched\n")

    t = Task(id="AGY1", title="x", repo=repo, target_agent="agy", created=date(2026, 6, 25))
    D._bridge_agy_scratch(t, wt)

    assert (wt / "agy_new.py").read_text() == "agy made this\n"            # agy's new file landed
    assert (wt / "base.py").read_text().endswith("AGY-EDIT\n")             # agy's edit landed
    assert (wt / "untouched.py").read_text() == "a fresh-main file agy never touched\n"  # NOT clobbered


def test_bridge_no_delta_carries_nothing(tmp_path, monkeypatch, capsys):
    # a clean scratch (agy committed or did nothing) must carry NOTHING — never the whole tree.
    repo = "organvm/limen"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    scratch = home / ".gemini" / "antigravity-cli" / "scratch" / "limen"
    scratch.mkdir(parents=True)
    _git(["init", "-q"], scratch)
    _git(["remote", "add", "origin", f"https://github.com/{repo}.git"], scratch)
    (scratch / "committed.py").write_text("committed, not a per-run change\n")
    _git(["add", "-A"], scratch)
    _git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"], scratch)

    wt = tmp_path / "wt"
    wt.mkdir()
    t = Task(id="AGY2", title="x", repo=repo, target_agent="agy", created=date(2026, 6, 25))
    D._bridge_agy_scratch(t, wt)

    assert not (wt / "committed.py").exists()         # the committed base file was NOT carried
    assert "no per-run delta" in capsys.readouterr().out
