from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CANARY = ROOT / "scripts" / "prompt-atom-canary.py"


def _load_canary():
    spec = importlib.util.spec_from_file_location("prompt_atom_canary_fixture", CANARY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _write_codex_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    session_id = "019f-canary-codex"
    rows = [
        {"type": "session_meta", "payload": {"id": session_id}},
        {
            "timestamp": "2026-07-11T12:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Implement the isolated Codex canary request."}],
            },
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _write_gemini_source(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "type": "user",
        "content": [{"text": "Implement the isolated Gemini canary request."}],
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
    for index in (1,):
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
        ("Complete task implement the isolated Agy canary request and verify its predicate.",),
    )
    connection.commit()
    connection.close()


def _fixture_home(root: Path, *, claude_sources: int = 1) -> Path:
    home = root / "home"
    _write_codex_source(home / ".codex" / "sessions" / "2026" / "07" / "11" / "rollout.jsonl")
    for index in range(claude_sources):
        _write_claude_source(
            home / ".claude" / "projects" / "isolated" / f"session-{index}.jsonl",
            index,
        )
    _write_gemini_source(home / ".gemini" / "tmp" / "fixture-provider" / "chats" / "session.jsonl")
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
            "--allow-dirty-code",
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


def test_five_family_canary_proves_second_pass_byte_identity(tmp_path: Path) -> None:
    home = _fixture_home(tmp_path)
    command, receipt_path = _command(tmp_path, home)

    result = _run(command)

    assert result.returncode == 0, result.stderr
    assert "prompt-atom-canary: PASS" in result.stdout
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "pass"
    assert receipt["work_unit_cap"] == 5
    assert receipt["nice_priority_requested"] == 10
    assert len(receipt["git_head"]) in {40, 64}
    assert len(receipt["code_sha256"]) == 64
    assert isinstance(receipt["code_matches_git_head"], bool)
    assert receipt["first_pass"]["work_units_used"] == 5
    assert receipt["first_pass"]["pending_units"] == 0
    assert receipt["first_pass"]["source_errors"] == 0
    assert receipt["first_pass"]["adapter_gaps"] == 0
    assert receipt["first_pass"]["source_families"] == {
        "agy-cli-conversations": {"converged": 1, "discovered": 1},
        "claude-projects": {"converged": 1, "discovered": 1},
        "codex-sessions": {"converged": 1, "discovered": 1},
        "gemini-tmp": {"converged": 1, "discovered": 1},
        "opencode-db": {"converged": 1, "discovered": 1},
    }
    assert receipt["second_pass"] == {
        "atom_delta": 0,
        "event_row_delta": 0,
        "outcome_delta": 0,
        "reclassification_delta": 0,
        "work_units_used": 0,
    }
    assert receipt["artifacts_after_first"] == receipt["artifacts_after_second"]
    assert receipt["artifacts_after_first"]["private_source_scan_receipts"]["files"] == 1
    assert receipt["verification"]["returncode"] == 0
    assert receipt["code_identity_reverified"] is True

    serialized = json.dumps(receipt, sort_keys=True)
    assert str(tmp_path) not in serialized
    assert "Implement isolated" not in serialized


def test_more_than_five_sources_fails_partial_without_second_pass(tmp_path: Path) -> None:
    # Five active families receive one unit each. A second Claude source is a
    # sixth discovered unit and must remain explicit instead of borrowing.
    home = _fixture_home(tmp_path, claude_sources=2)
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


def test_five_units_from_one_family_cannot_impersonate_five_family_canary(tmp_path: Path) -> None:
    home = tmp_path / "home"
    for index in range(5):
        _write_claude_source(
            home / ".claude" / "projects" / "isolated" / f"session-{index}.jsonl",
            index,
        )
    command, receipt_path = _command(tmp_path, home)

    result = _run(command)

    assert result.returncode == 1
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["first_pass"]["work_units_used"] == 5
    assert receipt["first_pass"]["scope"] == "all"
    assert "first_pass_required_family_coverage_mismatch" in receipt["failures"]
    assert [row["name"] for row in receipt["passes"]] == ["first"]


def test_canary_rejects_reused_canonical_outputs_before_running_again(tmp_path: Path) -> None:
    home = _fixture_home(tmp_path)
    command, receipt_path = _command(tmp_path, home)
    first = _run(command)
    assert first.returncode == 0, first.stderr
    assert receipt_path.exists()

    second_receipt = tmp_path / "receipts" / "second-canary.json"
    second_command = list(command)
    second_command[second_command.index("--receipt") + 1] = str(second_receipt)
    second = _run(second_command)

    assert second.returncode == 2
    assert "canary_outputs_must_be_fresh" in second.stderr
    assert not second_receipt.exists()


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


def test_exact_head_identity_compares_working_blobs_to_head(monkeypatch) -> None:
    canary = _load_canary()
    canary.CANARY_CODE_PATHS = (CANARY,)
    head = "a" * 40

    def fake_run(command, **_kwargs):
        if command == ["git", "rev-parse", "--verify", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout=head + "\n", stderr="")
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, stdout="b" * 40 + "\n", stderr="")
        if command[:3] == ["git", "hash-object", "--no-filters"]:
            return subprocess.CompletedProcess(command, 0, stdout="c" * 40 + "\n", stderr="")
        raise AssertionError(command)

    monkeypatch.setattr(canary.subprocess, "run", fake_run)

    identity = canary.exact_head_code_identity()

    assert identity["git_head"] == head
    assert identity["matches_git_head"] is False


def _direct_main_args(root: Path, home: Path) -> list[str]:
    return [
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
        str(root / "receipts" / "canary.json"),
        "--label",
        "direct-main-fixture",
        "--timeout",
        "30",
    ]


def test_canary_main_rejects_non_head_code_without_escape_hatch(tmp_path: Path, monkeypatch) -> None:
    canary = _load_canary()
    home = _fixture_home(tmp_path)
    identity = {"git_head": "a" * 40, "code_sha256": "b" * 64, "matches_git_head": False}
    monkeypatch.setattr(canary, "exact_head_code_identity", lambda: dict(identity))

    result = canary.main(_direct_main_args(tmp_path, home))

    assert result == 2
    assert not (tmp_path / "receipts" / "canary.json").exists()


def test_dirty_code_escape_hatch_keeps_receipt_honest(tmp_path: Path, monkeypatch) -> None:
    canary = _load_canary()
    home = _fixture_home(tmp_path)
    identity = {"git_head": "a" * 40, "code_sha256": "b" * 64, "matches_git_head": False}
    monkeypatch.setattr(canary, "exact_head_code_identity", lambda: dict(identity))

    result = canary.main([*_direct_main_args(tmp_path, home), "--allow-dirty-code"])

    assert result == 0
    receipt = json.loads((tmp_path / "receipts" / "canary.json").read_text(encoding="utf-8"))
    assert receipt["code_matches_git_head"] is False
    assert receipt["code_identity_reverified"] is True
