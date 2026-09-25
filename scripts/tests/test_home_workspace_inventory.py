"""Coverage and restart contracts for the bounded home inventory."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "home-workspace-inventory.py"
SPEC = importlib.util.spec_from_file_location("home_workspace_inventory", SCRIPT)
assert SPEC and SPEC.loader
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def test_nested_hidden_repositories_and_restart(tmp_path: Path) -> None:
    home = tmp_path / "home"
    nested = home / ".cache" / "app" / "repo"
    nested.mkdir(parents=True)
    (nested / ".git").mkdir()
    (home / "alias").symlink_to(nested, target_is_directory=True)
    state_path = tmp_path / "state.json"
    state = inventory.initial([home])
    inventory.advance(state, max_directories=1, max_seconds=10)
    assert not state["complete"]
    inventory.save(state_path, state)
    resumed = __import__("json").loads(state_path.read_text())
    inventory.advance(resumed, max_directories=100, max_seconds=10)
    assert resumed["complete"]
    assert any(row["path"] == str(nested) and row["kind"] == "git_checkout" for row in resumed["objects"])
    assert any(row["path"] == str(home / "alias") and row["kind"] == "symlink" for row in resumed["objects"])


def test_bare_and_copied_source_are_candidates(tmp_path: Path) -> None:
    bare = tmp_path / "recovery.git"
    bare.mkdir()
    for name in ("HEAD", "objects", "refs"):
        (bare / name).mkdir() if name != "HEAD" else (bare / name).write_text("ref: refs/heads/main\n")
    source = tmp_path / "copy"
    source.mkdir()
    (source / "pyproject.toml").write_text("[project]\nname='x'\n")
    linked = tmp_path / "linked"
    linked.mkdir()
    (linked / ".git").write_text("gitdir: ../store/worktrees/linked\n")
    state = inventory.initial([tmp_path])
    inventory.advance(state, max_directories=100, max_seconds=10)
    kinds = {row["kind"] for row in state["objects"]}
    assert "bare_git_candidate" in kinds
    assert "copied_source_candidate" in kinds
    assert "git_file_checkout_candidate" in kinds


def test_vanished_temporary_path_is_recorded_not_unmeasured(tmp_path: Path) -> None:
    state = inventory.initial([tmp_path])
    missing = tmp_path / "vanished"
    state["unmeasured"].append({"path": str(missing), "error": "FileNotFoundError"})
    inventory.advance(state, max_directories=10, max_seconds=10)
    assert state["complete"]
    assert state["unmeasured"] == []
    assert state["resolved_changes"][0]["resolution"] == "vanished_during_scan"


def test_codex_empty_git_shell_is_distinct_from_populated_store(tmp_path: Path) -> None:
    temporary = tmp_path / ".local" / "share" / "codex" / ".tmp"
    empty = temporary / "git-empty"
    populated = temporary / "git-populated"
    for path in (empty, populated):
        (path / "objects").mkdir(parents=True)
        (path / "refs").mkdir()
        (path / "HEAD").write_text("ref: refs/heads/main\n")
    (populated / "refs" / "heads").mkdir()
    state = inventory.initial([tmp_path])
    inventory.advance(state, max_directories=100, max_seconds=10)
    kinds = {row["path"]: row["kind"] for row in state["objects"]}
    assert kinds[str(empty)] == "codex_empty_git_shell_candidate"
    assert kinds[str(populated)] == "bare_git_candidate"
