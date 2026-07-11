from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANARY = ROOT / "scripts" / "prompt-atom-canary.py"


def _write_claude_source(path: Path, index: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "type": "user",
        "uuid": f"claude-event-{index}",
        "timestamp": f"2026-07-11T12:00:0{index}Z",
        "message": {
            "role": "user",
            "content": f"Implement isolated canary request number {index} and verify it.",
        },
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def _write_opencode_sources(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            session_id TEXT,
            time_created INTEGER,
            data TEXT
        );
        """
    )
    for index in (1, 2):
        session_id = f"opencode-{index}"
        connection.execute(
            "INSERT INTO session VALUES (?, ?, ?)",
            (session_id, index, index),
        )
        message_id = f"message-{index}"
        message = {
            "role": "user",
            "prompt_provenance": {
                "primary": True,
                "authority": "operator",
                "provenance": "operator_typed",
            },
        }
        connection.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?)",
            (message_id, session_id, index, json.dumps(message)),
        )
        connection.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            (
                f"part-{index}",
                message_id,
                session_id,
                index,
                json.dumps(
                    {
                        "type": "text",
                        "text": f"Implement isolated OpenCode canary request {index}.",
                    }
                ),
            ),
        )
    connection.commit()
    connection.close()


def _write_agy_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 14, ?, NULL, NULL, NULL, NULL)",
        ("Complete task: implement the isolated Agy canary request and verify its predicate.",),
    )
    connection.commit()
    connection.close()


def _fixture_home(root: Path, *, regular_sources: int = 2) -> Path:
    home = root / "home"
    for index in range(regular_sources):
        _write_claude_source(
            home / ".claude" / "projects" / "isolated" / f"session-{index}.jsonl",
            index,
        )
    _write_opencode_sources(home / ".local" / "share" / "opencode" / "opencode.db")
    _write_agy_source(home / ".gemini" / "antigravity-cli" / "conversations" / "one.db")
    return home


def _command(root: Path, home: Path) -> tuple[list[str], Path]:
    receipt = root / "receipts" / "canary.json"
    return (
        [
            sys.executable,
            str(CANARY),
            "--sandbox-root",
            str(root),
            "--home",
            str(home),
            "--private-root",
            str(root / "private"),
            "--public-snapshot",
            str(root / "public" / "prompt-atoms.json"),
            "--public-markdown",
            str(root / "public" / "prompt-atoms.md"),
            "--receipt",
            str(receipt),
            "--label",
            "fixture-five-units",
            "--timeout",
            "30",
        ],
        receipt,
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("LIMEN_PROMPT_CLASSIFIER_CMD", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def test_five_source_canary_proves_second_pass_byte_identity(tmp_path: Path) -> None:
    home = _fixture_home(tmp_path)
    command, receipt_path = _command(tmp_path, home)

    result = _run(command)

    assert result.returncode == 0, result.stderr
    assert "prompt-atom-canary: PASS" in result.stdout
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "pass"
    assert receipt["work_unit_cap"] == 5
    assert receipt["nice_priority_requested"] == 10
    assert receipt["first_pass"]["work_units_used"] == 5
    assert receipt["first_pass"]["pending_units"] == 0
    assert receipt["first_pass"]["source_errors"] == 0
    assert receipt["first_pass"]["adapter_gaps"] == 0
    assert receipt["second_pass"] == {
        "atom_delta": 0,
        "event_row_delta": 0,
        "outcome_delta": 0,
        "reclassification_delta": 0,
    }
    assert receipt["artifacts_after_first"] == receipt["artifacts_after_second"]
    assert receipt["verification"]["returncode"] == 0

    serialized = json.dumps(receipt, sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "Implement isolated" not in serialized


def test_more_than_five_sources_fails_partial_without_second_pass(tmp_path: Path) -> None:
    # Allocation at rotation zero is regular=2, OpenCode=2, Agy=1.  A third
    # regular source makes six discovered work units and must remain explicit.
    home = _fixture_home(tmp_path, regular_sources=3)
    command, receipt_path = _command(tmp_path, home)

    result = _run(command)

    assert result.returncode == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "fail"
    assert receipt["first_pass"]["work_units_used"] == 5
    assert receipt["first_pass"]["scope"] == "partial:all"
    assert receipt["first_pass"]["pending_units"] == 1
    assert "first_pass_scope_not_all" in receipt["failures"]
    assert "first_pass_has_pending_units" in receipt["failures"]
    assert [row["name"] for row in receipt["passes"]] == ["first"]
    assert "second_pass" not in receipt


def test_canary_requires_declared_sandbox_root(tmp_path: Path) -> None:
    home = _fixture_home(tmp_path)
    command, _receipt_path = _command(tmp_path, home)
    sandbox_index = command.index("--sandbox-root")
    del command[sandbox_index : sandbox_index + 2]

    result = _run(command)

    assert result.returncode == 2
    assert "--sandbox-root" in result.stderr


def test_canary_rejects_live_repo_output_and_symlink_escape(tmp_path: Path) -> None:
    home = _fixture_home(tmp_path)
    command, receipt_path = _command(tmp_path, home)
    public_index = command.index("--public-snapshot") + 1
    command[public_index] = str(ROOT / "AGENTS.md")

    live_result = _run(command)

    assert live_result.returncode == 2
    assert "public_snapshot_escapes_sandbox" in live_result.stderr
    assert not receipt_path.exists()

    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    escape = tmp_path / "escape"
    escape.symlink_to(outside, target_is_directory=True)
    command, receipt_path = _command(tmp_path, home)
    receipt_index = command.index("--receipt") + 1
    command[receipt_index] = str(escape / "canary.json")

    symlink_result = _run(command)

    assert symlink_result.returncode == 2
    assert "receipt_escapes_sandbox" in symlink_result.stderr
    assert not receipt_path.exists()
