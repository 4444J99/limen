from pathlib import Path

import pytest
from click.testing import CliRunner

from limen.cli import main
from limen.private_board import (
    PUBLIC_AGGREGATE_SCHEMA,
    PrivateCustodyUnavailable,
    default_private_custody_path,
    load_operational_board,
    operational_board_path,
    path_is_public_aggregate,
    private_board_path,
)

AGGREGATE_DOC = f"""schema_version: '{PUBLIC_AGGREGATE_SCHEMA}'
portal:
  name: 'Universal Task Intake'
  public_projection:
    total: 3111
    completed: 1816
tasks: []
"""

FULL_BOARD_DOC = """version: '1.0'
portal:
  name: 'Universal Task Intake'
tasks:
  - id: PUBLIC-1
    title: Public task
    status: open
    target_agent: codex
    priority: high
    created: 2026-08-10
"""


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


def test_aggregate_shape_is_detected_without_parsing_the_whole_board(tmp_path: Path) -> None:
    aggregate = tmp_path / "aggregate.yaml"
    aggregate.write_text(AGGREGATE_DOC, encoding="utf-8")
    full = tmp_path / "full.yaml"
    # A task's free-text context naming the schema must NOT be read as the document's shape.
    full.write_text(
        FULL_BOARD_DOC + f"    context: mentions {PUBLIC_AGGREGATE_SCHEMA} in prose\n",
        encoding="utf-8",
    )
    assert path_is_public_aggregate(aggregate) is True
    assert path_is_public_aggregate(full) is False


def test_full_board_public_projection_is_still_its_own_custody(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LIMEN_PRIVATE_TASKS", raising=False)
    public = tmp_path / "tasks.yaml"
    public.write_text(FULL_BOARD_DOC, encoding="utf-8")
    assert operational_board_path(public) == public


def test_aggregate_public_projection_resolves_to_hydrated_custody(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LIMEN_PRIVATE_TASKS", raising=False)
    monkeypatch.setenv("LIMEN_PRIVATE_ROOT", str(tmp_path / ".limen-private"))
    public = tmp_path / "tasks.yaml"
    public.write_text(AGGREGATE_DOC, encoding="utf-8")
    custody = default_private_custody_path(public)
    custody.parent.mkdir(parents=True, exist_ok=True)
    custody.write_text(FULL_BOARD_DOC, encoding="utf-8")

    assert operational_board_path(public) == custody
    board, selected = load_operational_board(public)
    assert selected == custody
    assert [task.id for task in board.tasks] == ["PUBLIC-1"]


def test_aggregate_without_custody_raises_instead_of_reading_an_empty_board(monkeypatch, tmp_path: Path) -> None:
    """The whole safety property: after cutover, missing custody must be LOUD.

    Returning the aggregate would hand every consumer a board with zero tasks —
    indistinguishable from "there is no work", which is how a partitioned board
    silently starves the fleet.
    """

    monkeypatch.delenv("LIMEN_PRIVATE_TASKS", raising=False)
    monkeypatch.setenv("LIMEN_PRIVATE_ROOT", str(tmp_path / ".limen-private"))
    public = tmp_path / "tasks.yaml"
    public.write_text(AGGREGATE_DOC, encoding="utf-8")

    with pytest.raises(PrivateCustodyUnavailable, match="limen board hydrate"):
        operational_board_path(public)
    with pytest.raises(PrivateCustodyUnavailable):
        load_operational_board(public)


def test_board_custody_path_reports_each_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LIMEN_PRIVATE_TASKS", raising=False)
    monkeypatch.setenv("LIMEN_PRIVATE_ROOT", str(tmp_path / ".limen-private"))
    public = tmp_path / "tasks.yaml"
    public.write_text(FULL_BOARD_DOC, encoding="utf-8")
    runner = CliRunner()

    pre = runner.invoke(main, ["board", "custody-path", "--public", str(public)])
    assert pre.exit_code == 0, pre.output
    assert str(public) in pre.stdout

    public.write_text(AGGREGATE_DOC, encoding="utf-8")
    missing = runner.invoke(main, ["board", "custody-path", "--public", str(public)])
    assert missing.exit_code == 3, missing.output

    custody = default_private_custody_path(public)
    custody.parent.mkdir(parents=True, exist_ok=True)
    custody.write_text(FULL_BOARD_DOC, encoding="utf-8")
    hydrated = runner.invoke(main, ["board", "custody-path", "--public", str(public)])
    assert hydrated.exit_code == 0, hydrated.output
    assert str(custody) in hydrated.stdout


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
