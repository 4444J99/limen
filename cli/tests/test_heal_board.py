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
    assert task["dispatch_log"][-1]["session_id"] == "heal-board-lifecycle-repair"
    assert task["dispatch_log"][-1]["conduct_event_id"]


def test_heal_board_reconciles_needs_human_label(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "GH-organvm-limen-999",
                        "title": "needs-human (L-EXAMPLE): a human-gated lever",
                        "target_agent": "any",
                        "status": "open",
                        "labels": ["needs-human"],
                        "created": "2026-07-01",
                    },
                    {
                        "id": "NORMAL-OPEN",
                        "title": "ordinary dispatchable work",
                        "target_agent": "codex",
                        "status": "open",
                        "labels": ["enhancement"],
                        "created": "2026-07-01",
                    },
                ],
            },
            sort_keys=False,
        )
    )

    check = run_heal_board(tmp_path, "--check")
    assert check.returncode == 1
    assert "needs-human" in check.stdout and "reconcile" in check.stdout

    applied = run_heal_board(tmp_path)
    assert applied.returncode == 0
    assert "reconciled 1 needs-human" in applied.stdout

    data = yaml.safe_load(tasks.read_text())
    by_id = {t["id"]: t for t in data["tasks"]}
    assert by_id["GH-organvm-limen-999"]["status"] == "needs_human"
    assert by_id["GH-organvm-limen-999"]["dispatch_log"][-1]["status"] == "needs_human"
    assert by_id["GH-organvm-limen-999"]["dispatch_log"][-1]["lifecycle_repair"] == "human-gate-reconcile"
    # an ordinary open task is untouched
    assert by_id["NORMAL-OPEN"]["status"] == "open"

    # idempotent: a second pass is a clean no-op
    again = run_heal_board(tmp_path)
    assert again.returncode == 0
    assert "OK" in again.stdout


def test_heal_board_reconciles_log_mismatch(tmp_path: Path) -> None:
    # A task returned to `open` after a timeout, but its latest canonical dispatch_log
    # status is still `dispatched` — the wedge that fails `verify` (validate-task-board's
    # log_mismatches) on every PR based on the snapshot. GH-organvm-limen-872 in the wild.
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "STALE-DISPATCH",
                        "title": "released to open after a timeout, log head never reconciled",
                        "target_agent": "codex",
                        "status": "open",
                        "created": "2026-07-01",
                        "dispatch_log": [
                            {
                                "timestamp": "2026-07-01T00:00:00+00:00",
                                "agent": "codex",
                                "session_id": "prior",
                                "status": "dispatched",
                            }
                        ],
                    },
                    {
                        "id": "ALIGNED-OPEN",
                        "title": "open with an aligned open log head — untouched",
                        "target_agent": "codex",
                        "status": "open",
                        "created": "2026-07-01",
                        "dispatch_log": [
                            {
                                "timestamp": "2026-07-01T00:00:00+00:00",
                                "agent": "codex",
                                "session_id": "prior",
                                "status": "open",
                            }
                        ],
                    },
                ],
            },
            sort_keys=False,
        )
    )

    check = run_heal_board(tmp_path, "--check")
    assert check.returncode == 1
    assert "dispatch_log head" in check.stdout and "STALE-DISPATCH" in check.stdout

    applied = run_heal_board(tmp_path)
    assert applied.returncode == 0
    assert "reconciled 1 log-mismatch" in applied.stdout

    data = yaml.safe_load(tasks.read_text())
    by_id = {t["id"]: t for t in data["tasks"]}
    # the log head now restates the authoritative open status; the invariant holds
    assert by_id["STALE-DISPATCH"]["status"] == "open"
    assert by_id["STALE-DISPATCH"]["dispatch_log"][-1]["status"] == "open"
    assert by_id["STALE-DISPATCH"]["dispatch_log"][-1]["session_id"] == "heal-board-lifecycle-repair"
    assert by_id["STALE-DISPATCH"]["dispatch_log"][-1]["logical_session_id"] == "heal-board"
    # an already-aligned open task gains no spurious event
    assert len(by_id["ALIGNED-OPEN"]["dispatch_log"]) == 1

    # idempotent: a second pass is a clean no-op
    again = run_heal_board(tmp_path)
    assert again.returncode == 0
    assert "OK" in again.stdout


def test_heal_board_appends_canonical_route_without_rewriting_legacy_history(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks.yaml"
    original = {
        "timestamp": "2026-07-01T00:00:00+00:00",
        "agent": "codex",
        "session_id": "prior",
        "status": "timeout->jules",
        "output": "legacy timeout",
    }
    tasks.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "tasks": [
                    {
                        "id": "LEGACY-ROUTE",
                        "title": "legacy composite route",
                        "target_agent": "jules",
                        "status": "open",
                        "created": "2026-07-01",
                        "dispatch_log": [original],
                    }
                ],
            },
            sort_keys=False,
        )
    )

    check = run_heal_board(tmp_path, "--check")
    assert check.returncode == 1
    assert "dispatch_log head" in check.stdout

    applied = run_heal_board(tmp_path)
    assert applied.returncode == 0
    data = yaml.safe_load(tasks.read_text())
    log = data["tasks"][0]["dispatch_log"]
    # Pydantic/YAML normalizes the UTC timestamp spelling, but the historical
    # event remains first and its facts are not replaced or repurposed.
    assert log[0]["agent"] == original["agent"]
    assert log[0]["session_id"] == original["session_id"]
    assert log[0]["status"] == original["status"]
    assert log[0]["output"] == original["output"]
    assert log[-1]["status"] == "open"
    assert log[-1]["route_to"] == "jules"

    again = run_heal_board(tmp_path)
    assert again.returncode == 0
    assert "OK" in again.stdout
