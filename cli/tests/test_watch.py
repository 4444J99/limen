from collections import Counter
from pathlib import Path

from click.testing import CliRunner
from limen.cli import main

SAMPLE_BOARD = """\
version: "1.0"
portal:
  name: "Universal Task Intake"
  budget:
    daily: 100
    unit: "runs"
    per_agent: {}
    track:
      date: "2026-06-30"
      spent: 12
      per_agent: {}
tasks:
  - id: "TEST-001"
    title: "Test done task"
    target_agent: "opencode"
    status: done
    created: "2026-06-30"
  - id: "TEST-002"
    title: "Test open task"
    target_agent: "codex"
    status: open
    created: "2026-06-30"
  - id: "TEST-003"
    title: "Test in-flight task"
    target_agent: "claude"
    status: in_progress
    created: "2026-06-30"
"""


def test_watch_once_renders_without_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "tasks.yaml").write_text(SAMPLE_BOARD)

    import limen.watch

    monkeypatch.setattr(limen.watch, "proc_counts", lambda: Counter())

    result = CliRunner().invoke(main, ["watch", "--once"])

    assert result.exit_code == 0, result.output
    assert "LIMEN" in result.output
    assert "opencode" in result.output


def test_watch_compact_renders(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    (tmp_path / "tasks.yaml").write_text(SAMPLE_BOARD)

    import limen.watch

    monkeypatch.setattr(limen.watch, "proc_counts", lambda: Counter())

    result = CliRunner().invoke(main, ["watch", "--once", "--compact"])

    assert result.exit_code == 0, result.output
    assert "LIMEN" in result.output
    assert "opencode:" in result.output
