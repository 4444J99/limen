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
    state = inventory.initial([tmp_path])
    inventory.advance(state, max_directories=100, max_seconds=10)
    kinds = {row["kind"] for row in state["objects"]}
    assert "bare_git_candidate" in kinds
    assert "copied_source_candidate" in kinds
