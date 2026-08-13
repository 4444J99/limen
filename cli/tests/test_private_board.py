from pathlib import Path

import pytest
from click.testing import CliRunner

from limen.cli import main
from limen.private_board import load_operational_board, private_board_path


def test_private_board_path_rejects_the_public_projection(monkeypatch, tmp_path: Path) -> None:
    public = tmp_path / "tasks.yaml"
    public.write_text("portal: {}\ntasks: []\n")
    monkeypatch.setenv("LIMEN_PRIVATE_TASKS", str(public))
    with pytest.raises(ValueError, match="must not point at the public"):
        private_board_path(public)


def test_operational_board_requires_explicit_private_custody(monkeypatch, tmp_path: Path) -> None:
    public = tmp_path / "tasks.yaml"
    public.write_text("portal: {}\ntasks: []\n")
    private = tmp_path / "private-board.yaml"
    private.write_text(
        "portal: {}\ntasks:\n  - id: PRIVATE-1\n    title: Private task\n    target_agent: codex\n    created: 2026-08-10\n"
    )
    monkeypatch.setenv("LIMEN_PRIVATE_TASKS", str(private))
    board, selected = load_operational_board(public)
    assert selected == private.resolve()
    assert board.tasks[0].id == "PRIVATE-1"


def test_board_initialize_normalizes_yaml_dates_before_json_transport(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.yaml"
    source.write_text(
        "portal: {}\ntasks:\n  - id: PRIVATE-1\n    created: 2026-08-10\n",
        encoding="utf-8",
    )
    captured: dict = {}

    class FakeClient:
        def initialize_private_board(self, board):
            captured["board"] = board
            return {"initialized": True}

    monkeypatch.setattr("limen.cli.client_from_env", lambda: FakeClient())
    result = CliRunner().invoke(main, ["board", "initialize", str(source)])

    assert result.exit_code == 0, result.output
    assert captured["board"]["tasks"][0]["created"] == "2026-08-10"
