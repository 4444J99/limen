from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "heal-board.py"
CLI_SRC = ROOT / "cli" / "src"


def run_heal_board(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "LIMEN_ROOT": str(tmp_path),
        "LIMEN_TASKS": str(tmp_path / "tasks.yaml"),
        "LIMEN_BOARD_SHRINK_FLOOR": "0",
        "PYTHONPATH": str(CLI_SRC),
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_heal_board_repairs_reopened_done_task(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "REOPENED-DONE",
                        "title": "Already completed",
                        "target_agent": "codex",
                        "status": "open",
                        "created": "2026-06-30",
                        "dispatch_log": [
                            {
                                "timestamp": "2026-06-30T00:00:00+00:00",
                                "agent": "codex",
                                "session_id": "prior",
                                "status": "done",
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        )
    )

    check = run_heal_board(tmp_path, "--check")
    assert check.returncode == 1
    assert "need repair" in check.stdout

    applied = run_heal_board(tmp_path)
    assert applied.returncode == 0
    assert "restored 1 reopened completed" in applied.stdout

    data = yaml.safe_load(tasks.read_text())
    task = data["tasks"][0]
    assert task["status"] == "done"
    assert task["dispatch_log"][-1]["status"] == "done"
    assert task["dispatch_log"][-1]["session_id"] == "heal-board"
