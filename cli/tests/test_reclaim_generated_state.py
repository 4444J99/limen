from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reclaim-generated-state.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)


def test_generated_state_reclaim_removes_only_ignored_allowlisted_dirs(tmp_path):
    mod = _load("reclaim_generated_state_uut")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    (repo / ".gitignore").write_text("node_modules/\n.venv/\n", encoding="utf-8")
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "dep.js").write_text("generated", encoding="utf-8")
    (repo / ".venv").mkdir()
    (repo / ".venv" / "python").write_text("generated", encoding="utf-8")
    (repo / "build").mkdir()
    (repo / "build" / "artifact.js").write_text("not ignored", encoding="utf-8")
    (repo / "source.py").write_text("print('keep')\n", encoding="utf-8")

    dry = mod.clean_root(repo, apply=False, timeout=10)
    assert dry["ok"] is True
    assert dry["changed_line_count"] == 2
    assert dry["reclaimable_kib"] > 0
    assert dry["reclaimed_kib"] == 0

    applied = mod.clean_root(repo, apply=True, timeout=10)
    assert applied["ok"] is True
    assert applied["changed_line_count"] == 2
    assert applied["reclaimed_kib"] > 0
    assert not (repo / "node_modules").exists()
    assert not (repo / ".venv").exists()
    assert (repo / "build" / "artifact.js").exists()
    assert (repo / "source.py").exists()


def test_generated_state_reclaim_skips_invalid_git_root(tmp_path):
    mod = _load("reclaim_generated_state_invalid_uut")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /missing/worktree\n", encoding="utf-8")

    result = mod.clean_root(repo, apply=True, timeout=10)

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["skip_reason"] == "not-a-valid-git-root"
