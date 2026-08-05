from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from limen.session_sources import (
    child_identity_environment,
    discover_sources,
    read_session_records,
    resolve_session,
)


def _jsonl(path: Path, record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _open_code_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE session (id TEXT PRIMARY KEY, time_updated INTEGER);
            CREATE TABLE message (
              id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT
            );
            CREATE TABLE part (
              id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
              time_created INTEGER, data TEXT
            );
            """
        )
        db.execute("INSERT INTO session VALUES ('open-run', 500)")
        db.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?)",
            ("message-1", "open-run", 500, json.dumps({"role": "user", "time": {"created": 500}})),
        )
        db.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            ("part-1", "message-1", "open-run", 500, json.dumps({"type": "text", "text": "OpenCode ask"})),
        )


def _agy_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(
            """
            CREATE TABLE conversation_summaries (
              conversation_id TEXT PRIMARY KEY,
              title TEXT,
              preview TEXT,
              last_modified_time DATETIME,
              last_user_input_time DATETIME
            )
            """
        )
        db.execute(
            "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?)",
            ("agy-run", "Agy title", "Agy ask", "2026-07-18T12:00:00Z", "2026-07-18T12:00:00Z"),
        )


def test_all_primary_native_session_adapters_are_readable(tmp_path: Path) -> None:
    _jsonl(
        tmp_path / ".codex" / "sessions" / "codex.jsonl",
        {"role": "user", "content": "Codex ask"},
    )
    _jsonl(
        tmp_path / ".claude" / "projects" / "limen" / "claude.jsonl",
        {"type": "user", "message": {"role": "user", "content": "Claude ask"}},
    )
    _jsonl(
        tmp_path / ".copilot" / "session-state" / "copilot" / "events.jsonl",
        {"type": "user.message", "data": {"role": "user", "content": "Copilot ask"}},
    )
    _open_code_db(tmp_path / ".local" / "share" / "opencode" / "opencode.db")
    _agy_db(tmp_path / ".gemini" / "antigravity-cli" / "conversation_summaries.db")

    sources = discover_sources(tmp_path)

    assert set(sources) == {"agy", "claude", "codex", "copilot", "opencode"}
    assert all(source is not None for source in sources.values())
    text_by_agent = {
        agent: json.dumps(read_session_records(source)) for agent, source in sources.items() if source is not None
    }
    assert "Codex ask" in text_by_agent["codex"]
    assert "Claude ask" in text_by_agent["claude"]
    assert "Copilot ask" in text_by_agent["copilot"]
    assert "OpenCode ask" in text_by_agent["opencode"]
    assert "Agy ask" in text_by_agent["agy"]
    assert resolve_session(None, source_agent="opencode", home=tmp_path).session_id == "open-run"


def test_child_identity_replaces_initiator_and_preserves_lineage() -> None:
    env = child_identity_environment(
        executor_agent="opencode",
        initiator_agent="claude",
        conductor_agent="agy",
        root_run_id="root",
        parent_run_id="parent",
        run_id="child",
    )

    assert env == {
        "LIMEN_AGENT": "opencode",
        "LIMEN_INITIATOR_AGENT": "claude",
        "LIMEN_CONDUCTOR_AGENT": "agy",
        "LIMEN_ROOT_RUN_ID": "root",
        "LIMEN_PARENT_RUN_ID": "parent",
        "LIMEN_RUN_ID": "child",
    }


def test_child_identity_includes_actual_lease_and_execution_envelope() -> None:
    env = child_identity_environment(
        executor_agent="copilot",
        initiator_agent="opencode",
        conductor_agent="claude",
        root_run_id="run-root",
        parent_run_id="run-plan",
        run_id="run-exec",
        task_id="CSF-ABC-EXEC",
        lease_id="lease-3",
        lease_generation=3,
        execution_hash="execution-hash",
        capability_token="secret-token",
    )

    assert env == {
        "LIMEN_AGENT": "copilot",
        "LIMEN_INITIATOR_AGENT": "opencode",
        "LIMEN_CONDUCTOR_AGENT": "claude",
        "LIMEN_ROOT_RUN_ID": "run-root",
        "LIMEN_PARENT_RUN_ID": "run-plan",
        "LIMEN_RUN_ID": "run-exec",
        "LIMEN_TASK_ID": "CSF-ABC-EXEC",
        "LIMEN_LEASE_ID": "lease-3",
        "LIMEN_LEASE_GENERATION": "3",
        "LIMEN_EXECUTION_HASH": "execution-hash",
        "LIMEN_LEASE_TOKEN": "secret-token",
    }
