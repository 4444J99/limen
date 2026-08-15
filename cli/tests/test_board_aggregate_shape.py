"""The two lawful board shapes, across the organs that read the public projection.

Post-cutover the public ``tasks.yaml`` is a counts-only aggregate. Two organs would
otherwise misread it in opposite, equally damaging ways:

* ``validate-task-board.py`` read it as a malformed full board ("Missing version"),
  which is what kept publication PR #2001 red.
* ``heal-board.py`` reads zero task rows as a COLLAPSE and restores the pre-cutover
  board from git HEAD — an organ undoing the architecture, every beat.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate-task-board.py"
HEAL_BOARD = ROOT / "scripts" / "heal-board.py"

AGGREGATE_DOC = """schema_version: 'limen.public_board_projection.v1'
portal:
  name: 'Universal Task Intake'
  description: 'Aggregate operational health; authenticated board details are private.'
  public_projection:
    schema_version: 'limen.public_board_projection.v1'
    generated_at: '2026-08-15T14:14:31.610Z'
    total: 3148
    completed: 1816
    active: 0
    completion_rate: 0.577
    by_status:
      done: 1357
      open: 853
    by_priority:
      high: 1304
tasks: []
"""

FULL_BOARD_DOC = """version: '1.0'
portal:
  name: 'Universal Task Intake'
  budget:
    daily: 600
    per_agent:
      codex: 100
tasks:
  - id: PUBLIC-1
    title: Public task
    status: open
    target_agent: codex
    priority: high
    created: 2026-08-10
"""


def _run(args: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "cli" / "src"), **(env_extra or {})}
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, env=env, timeout=180)


def test_validator_accepts_the_published_aggregate(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    board.write_text(AGGREGATE_DOC, encoding="utf-8")
    result = _run([str(VALIDATOR), "--tasks", str(board)])
    assert result.returncode == 0, result.stderr
    assert "aggregate valid" in result.stdout


def test_validator_accepts_a_full_board(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    board.write_text(FULL_BOARD_DOC, encoding="utf-8")
    result = _run([str(VALIDATOR), "--tasks", str(board)])
    assert result.returncode == 0, result.stderr
    assert "Schema version: 1.0" in result.stdout


def test_validator_rejects_task_material_on_the_public_surface(tmp_path: Path) -> None:
    """The aggregate arm is STRICTER, not laxer: no work attribution may cross."""

    board = tmp_path / "tasks.yaml"
    board.write_text(
        AGGREGATE_DOC.replace(
            "tasks: []\n",
            "tasks: []\nleaked:\n  repo: 4444J99/partner-private\n  title: Partner engagement\n",
        ),
        encoding="utf-8",
    )
    result = _run([str(VALIDATOR), "--tasks", str(board)])
    assert result.returncode == 1
    assert "leaks" in result.stderr


def test_validator_can_pin_an_expected_shape(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    board.write_text(FULL_BOARD_DOC, encoding="utf-8")
    result = _run([str(VALIDATOR), "--tasks", str(board), "--require-shape", "aggregate"])
    assert result.returncode == 1
    assert "expected the aggregate board shape" in result.stderr


def test_heal_board_treats_the_aggregate_as_lawful_not_collapsed(tmp_path: Path) -> None:
    """Without this arm heal-board 'restores' the partition away from git HEAD every beat."""

    board = tmp_path / "tasks.yaml"
    board.write_text(AGGREGATE_DOC, encoding="utf-8")
    custody = tmp_path / ".limen-private" / "board" / "canonical.yaml"
    custody.parent.mkdir(parents=True, exist_ok=True)
    custody.write_text(FULL_BOARD_DOC, encoding="utf-8")

    result = _run(
        [str(HEAL_BOARD), "--check"],
        {
            "LIMEN_ROOT": str(tmp_path),
            "LIMEN_TASKS": str(board),
            "LIMEN_PRIVATE_ROOT": str(tmp_path / ".limen-private"),
        },
    )
    assert "collapsed" not in result.stdout, result.stdout
    assert "public aggregate" in result.stdout, result.stdout + result.stderr
    assert str(custody) in result.stdout


def test_heal_board_without_custody_is_loud_rather_than_restoring(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    board.write_text(AGGREGATE_DOC, encoding="utf-8")

    result = _run(
        [str(HEAL_BOARD), "--check"],
        {
            "LIMEN_ROOT": str(tmp_path),
            "LIMEN_TASKS": str(board),
            "LIMEN_PRIVATE_ROOT": str(tmp_path / ".limen-private"),
        },
    )
    assert result.returncode == 1
    assert "limen board hydrate" in result.stderr
    assert "collapsed" not in result.stdout
