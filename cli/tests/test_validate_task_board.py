from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate-task-board.py"


def run_validator(tasks_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--tasks", str(tasks_path)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_validate_task_board_rejects_duplicate_ids(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    tasks_path.write_text(
        """
tasks:
- id: DUP
  status: open
  dispatch_log: []
- id: DUP
  status: open
  dispatch_log: []
""".lstrip()
    )

    result = run_validator(tasks_path)

    assert result.returncode == 1
    assert "duplicate task id" in result.stderr
    assert "DUP" in result.stderr


def test_validate_task_board_rejects_done_reopen(tmp_path: Path) -> None:
    tasks_path = tmp_path / "tasks.yaml"
    tasks_path.write_text(
        """
tasks:
- id: REOPENED
  status: dispatched
  dispatch_log:
  - status: done
  - status: dispatched
""".lstrip()
    )

    result = run_validator(tasks_path)

    assert result.returncode == 1
    assert "reopened after a done transition" in result.stderr
    assert "REOPENED: dispatched" in result.stderr
