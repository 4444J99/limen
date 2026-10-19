from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from limen.session_sources import (
    SessionSource,
    child_identity_environment,
    discover_sources,
    opencode_session_table,
    read_session_records,
    resolve_opencode_db,
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


def _legacy_and_live(home: Path) -> tuple[Path, Path]:
    legacy = home / ".local" / "share" / "opencode" / "opencode.db"
    live = home / "Workspace" / "limen" / ".agent-runtime" / "opencode" / "data" / "opencode" / "opencode.db"
    return legacy, live


def test_resolve_opencode_db_prefers_the_runtime_store_over_the_legacy_copy(tmp_path: Path) -> None:
    legacy, live = _legacy_and_live(tmp_path)
    _open_code_db(legacy)
    _open_code_db(live)

    assert resolve_opencode_db(tmp_path) == live


def test_resolve_opencode_db_falls_back_to_legacy_and_reports_a_missing_store(tmp_path: Path) -> None:
    legacy, _live = _legacy_and_live(tmp_path)

    assert resolve_opencode_db(tmp_path) == legacy
    assert not legacy.exists(), "a missing store must be returned as missing, never invented"
    _open_code_db(legacy)
    assert resolve_opencode_db(tmp_path) == legacy


def test_explicit_home_ignores_the_process_environment(tmp_path: Path, monkeypatch) -> None:
    legacy, _live = _legacy_and_live(tmp_path)
    monkeypatch.setenv("LIMEN_OPENCODE_DB", "/nonexistent/real-host.db")
    monkeypatch.setenv("LIMEN_AGENT_RUNTIME_ROOT", "/nonexistent/real-runtime")

    assert resolve_opencode_db(tmp_path) == legacy

    custom = tmp_path / "custom.db"
    assert resolve_opencode_db(tmp_path, {"LIMEN_OPENCODE_DB": str(custom)}) == custom


def test_no_arguments_consults_the_process_environment(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "rt"
    live = runtime / "opencode" / "data" / "opencode" / "opencode.db"
    _open_code_db(live)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("LIMEN_OPENCODE_DB", raising=False)
    monkeypatch.setenv("LIMEN_AGENT_RUNTIME_ROOT", str(runtime))

    assert resolve_opencode_db() == live

    pinned = tmp_path / "pinned.db"
    monkeypatch.setenv("LIMEN_OPENCODE_DB", str(pinned))
    assert resolve_opencode_db() == pinned


def test_discover_sources_reads_the_live_opencode_store_not_the_legacy_copy(tmp_path: Path) -> None:
    legacy, live = _legacy_and_live(tmp_path)
    _open_code_db(legacy)
    _open_code_db(live)
    with sqlite3.connect(live) as db:
        db.execute("UPDATE session SET id = 'live-run', time_updated = 900")

    source = discover_sources(tmp_path)["opencode"]

    assert source is not None and source.session_id == "live-run"
    assert str(live) in source.locator


def _open_code_v2_db(path: Path, *, legacy_has_v2_rows: bool = True) -> None:
    """A store shaped like OpenCode 2.x: legacy tables frozen, ``session_v2`` a superset of ``session``."""
    _open_code_db(path)  # legacy: session 'open-run' (time_updated 500) with one message and part
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE session_v2 (id TEXT PRIMARY KEY, time_updated INTEGER);
            CREATE TABLE session_message (
              id TEXT PRIMARY KEY, session_id TEXT, type TEXT, seq INTEGER, time_created INTEGER, data TEXT
            );
            """
        )
        db.execute("INSERT INTO session_v2 VALUES ('open-run', 500), ('v2-only-run', 900)")
        turns = [
            ("v2-a", "v2-only-run", "user", 1, 900, {"text": "V2 ask", "time": {"created": 900}}),
            (
                "v2-b",
                "v2-only-run",
                "assistant",
                2,
                901,
                {
                    "content": [
                        {"type": "text", "text": "V2 answer"},
                        {"type": "tool", "state": {"input": "SECRET-TOOL-ARGUMENTS"}},
                    ],
                    "time": {"created": 901},
                },
            ),
            ("v2-c", "v2-only-run", "idle", 3, 902, {"time": {"created": 902}}),
        ]
        if legacy_has_v2_rows:
            turns.append(("v2-d", "open-run", "user", 1, 500, {"text": "Migrated ask", "time": {"created": 500}}))
        for row_id, session_id, kind, seq, created, data in turns:
            db.execute(
                "INSERT INTO session_message VALUES (?, ?, ?, ?, ?, ?)",
                (row_id, session_id, kind, seq, created, json.dumps(data)),
            )


def test_opencode_session_table_prefers_v2_only_when_both_v2_tables_exist(tmp_path: Path) -> None:
    legacy_only, v2, half = tmp_path / "a.db", tmp_path / "b.db", tmp_path / "c.db"
    _open_code_db(legacy_only)
    _open_code_v2_db(v2)
    _open_code_db(half)
    with sqlite3.connect(half) as db:
        db.execute("CREATE TABLE session_v2 (id TEXT PRIMARY KEY, time_updated INTEGER)")
    names = {}
    for label, path in (("legacy", legacy_only), ("v2", v2), ("half", half)):
        with sqlite3.connect(path) as db:
            names[label] = opencode_session_table(db)

    assert names == {"legacy": "session", "v2": "session_v2", "half": "session"}


def test_v2_store_discovers_the_newest_session_across_the_superset(tmp_path: Path) -> None:
    _open_code_v2_db(tmp_path / ".local" / "share" / "opencode" / "opencode.db")

    source = discover_sources(tmp_path)["opencode"]

    assert source is not None and source.session_id == "v2-only-run", "a v2-only session must be found"
    assert source.updated_ns == 900 * 1_000_000


def test_v2_store_renders_user_and_assistant_turns_and_skips_the_rest(tmp_path: Path) -> None:
    path = tmp_path / "opencode.db"
    _open_code_v2_db(path)
    source = SessionSource("opencode", f"{path}#session:v2-only-run", "v2-only-run", "opencode-sqlite", 0)

    records = read_session_records(source)

    assert [record["role"] for record in records] == ["user", "assistant"], "idle rows are not conversation turns"
    assert records[0]["content"] == ["V2 ask"]
    assert records[1]["content"] == ["V2 answer"]
    assert "SECRET-TOOL-ARGUMENTS" not in json.dumps(records), "tool block state must not leak into rendered text"
    assert records[0]["timestamp"] == 900


def test_v2_store_reads_a_migrated_session_from_session_message(tmp_path: Path) -> None:
    path = tmp_path / "opencode.db"
    _open_code_v2_db(path)
    source = SessionSource("opencode", f"{path}#session:open-run", "open-run", "opencode-sqlite", 0)

    records = read_session_records(source)

    assert records and records[0]["content"] == ["Migrated ask"], "v2 rows win once the store is v2"


def test_v2_store_falls_back_to_legacy_messages_when_a_session_has_no_v2_rows(tmp_path: Path) -> None:
    path = tmp_path / "opencode.db"
    _open_code_v2_db(path, legacy_has_v2_rows=False)
    source = SessionSource("opencode", f"{path}#session:open-run", "open-run", "opencode-sqlite", 0)

    records = read_session_records(source)

    assert "OpenCode ask" in json.dumps(records), "a session with no session_message rows keeps its v1 messages"


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
