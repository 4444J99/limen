from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen import cli as cli_mod  # noqa: E402


def _unset_root_env(monkeypatch) -> None:
    """The autouse conftest fixture restores the environment but does not clear these."""
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    monkeypatch.delenv("LIMEN_TASKS", raising=False)


def test_explicit_limen_root_is_taken_as_asserted(tmp_path: Path, monkeypatch) -> None:
    _unset_root_env(monkeypatch)
    board = tmp_path / "explicit"
    board.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LIMEN_ROOT", str(board))
    # An explicit root is an assertion, not a discovery: it is not probed for a board.
    assert cli_mod.resolve_root() == board.resolve()


def test_cwd_board_wins_over_every_fallback(tmp_path: Path, monkeypatch) -> None:
    _unset_root_env(monkeypatch)
    (tmp_path / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cli_mod.resolve_root() == tmp_path.resolve()


def test_resolves_from_a_directory_that_holds_no_board(tmp_path: Path, monkeypatch) -> None:
    """The regression: a board-reading verb exited 2 from any unrelated cwd.

    `limen workstream` already self-located via resolve_limen_repo_root()'s
    __file__-relative candidate; `limen dispatch` refused instead of using it.
    """
    _unset_root_env(monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    assert not (elsewhere / "tasks.yaml").exists()

    resolved = cli_mod.resolve_root()

    assert resolved == Path(cli_mod.__file__).resolve().parents[3]
    assert (resolved / "tasks.yaml").exists()


def test_limen_tasks_names_its_own_root(tmp_path: Path, monkeypatch) -> None:
    _unset_root_env(monkeypatch)
    projection = tmp_path / "projection"
    projection.mkdir()
    (projection / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("LIMEN_TASKS", str(projection / "tasks.yaml"))

    assert cli_mod.resolve_root() == projection.resolve()


def test_exits_2_and_names_every_candidate_it_probed(tmp_path: Path, monkeypatch, capsys) -> None:
    _unset_root_env(monkeypatch)
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    # Starve the two non-cwd candidates, or the real repo satisfies discovery and the
    # failure branch is unreachable — the assertion would pass without proving anything.
    stub = tmp_path / "pkg" / "a" / "b" / "c" / "cli.py"
    stub.parent.mkdir(parents=True)
    monkeypatch.setattr(cli_mod, "__file__", str(stub))
    monkeypatch.setattr(cli_mod.Path, "home", staticmethod(lambda: tmp_path / "no-home"))

    with pytest.raises(SystemExit) as excinfo:
        cli_mod.resolve_root()

    assert excinfo.value.code == 2
    message = capsys.readouterr().err
    assert "no tasks.yaml found in" in message
    assert str(empty) in message
