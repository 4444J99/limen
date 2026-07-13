from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-atom-ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("prompt_atom_sources", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _regular_lifecycle(module, rows):
    lifecycle = module.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [(str(row["source"]), Path(row["path"]), (Path(row["path"]).name,)) for row in rows]
    lifecycle.OPENCODE_DB = Path("/definitely/missing/opencode.db")
    lifecycle.AGY_CLI_CONVERSATIONS = Path("/definitely/missing/agy")
    lifecycle.HOME = Path("/definitely/missing/home")
    return lifecycle


def test_claude_tool_and_transport_surfaces_never_become_operator_input():
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    tool_result = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "content": "tool output"}],
        },
    }
    last_prompt = {"type": "last-prompt", "lastPrompt": "transport copy"}
    queued = {"type": "queue-operation", "operation": "enqueue", "content": "queued copy"}
    direct = {"type": "user", "message": {"role": "user", "content": "human turn"}}
    task = {"description": "delegated task"}

    assert sources.prompt_texts_for(lifecycle, "claude-projects", tool_result) == []
    assert sources.prompt_texts_for(lifecycle, "claude-projects", last_prompt) == ["transport copy"]
    assert sources.prompt_texts_for(lifecycle, "claude-projects", queued) == ["queued copy"]
    assert sources.prompt_texts_for(lifecycle, "claude-projects", direct) == ["human turn"]
    assert sources.provenance_for("claude-projects", direct, "direct") == (
        "operator_typed",
        "operator",
    )
    assert sources.prompt_texts_for(lifecycle, "claude-tasks", task) == ["delegated task"]
    assert sources.provenance_for("claude-tasks", task, "direct") == (
        "delegated_task_frame",
        "derived",
    )


def test_codex_session_meta_supplies_canonical_id_and_primary_precedes_echo(tmp_path: Path):
    sources = _load()
    session_id = "019f-source-session"
    path = tmp_path / f"rollout-{session_id}.jsonl"
    rows = [
        {"type": "session_meta", "payload": {"id": session_id}},
        {
            "timestamp": "2026-07-11T12:00:00.001Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "one operator turn",
                "images": [],
                "local_images": [],
                "text_elements": [],
            },
        },
        {
            "timestamp": "2026-07-11T12:00:00.002Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "one operator turn"}],
            },
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "codex-sessions", "path": path, "mtime": "2026-07-11T12:00:00Z"}],
    )

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert result["errors"] == []
    assert [event["provenance"] for event in events] == ["operator_typed", "transport_echo"]
    assert {event["session_ref"] for event in events} == {f"codex:{session_id}"}
    assert events[0]["timestamp"] == events[1]["timestamp"] == "2026-07-11T12:00:00.002Z"
    snapshot = sources.update_ledger(
        sources.LedgerPaths.for_root(tmp_path / "ledger"),
        events=events,
        cursor={
            "version": 1,
            "scope": "fixture",
            "source_manifest_digest": sources.digest({"fixture": 1}),
            "source_families": {},
            "files": {},
        },
    )
    assert snapshot["coverage"]["atoms"] == 1
    assert snapshot["coverage"]["operator_occurrences"] == 1


def test_codex_user_media_is_an_explicit_gap_instead_of_silently_losing_the_attachment(tmp_path: Path):
    sources = _load()
    session_id = "019f-media-session"
    path = tmp_path / f"rollout-{session_id}.jsonl"
    rows = [
        {"type": "session_meta", "payload": {"id": session_id}},
        {
            "timestamp": "2026-07-11T12:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Assess the attached evidence."},
                    {"type": "input_image", "detail": "auto", "image_url": "data:image/png;base64,opaque"},
                ],
            },
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    lifecycle = _regular_lifecycle(sources, [{"source": "codex-sessions", "path": path}])
    key = sources.cursor_unit_key("codex-sessions", path)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["errors"] == []
    assert result["unsupported"] == [key]
    assert result["unsupported_units"][key] == sources.file_signature(path)
    assert key not in result["files"]


@pytest.mark.parametrize(
    "unknown_block",
    [
        {"type": "input_file", "file_url": "opaque"},
        {"type": "future_media", "prompt": "A prompt-bearing field the current parser does not know."},
    ],
)
def test_codex_unknown_user_content_blocks_make_the_mixed_turn_an_explicit_gap(
    tmp_path: Path,
    unknown_block: dict,
):
    sources = _load()
    path = tmp_path / "rollout-unknown-content.jsonl"
    rows = [
        {"type": "session_meta", "payload": {"id": "unknown-content"}},
        {
            "timestamp": "2026-07-11T12:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Preserve this mixed turn."},
                    unknown_block,
                ],
            },
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    lifecycle = _regular_lifecycle(sources, [{"source": "codex-sessions", "path": path}])
    key = sources.cursor_unit_key("codex-sessions", path)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["errors"] == []
    assert result["unsupported"] == [key]
    assert key not in result["files"]


@pytest.mark.parametrize(
    "record",
    [
        {
            "timestamp": "2026-07-11T12:00:00Z",
            "type": "response_item",
            "role": "user",
            "content": [{"type": "input_text", "text": "top-level user wrapper"}],
        },
        {
            "timestamp": "2026-07-11T12:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "future_wrapper",
                "message": {"role": "user", "content": "nested payload user wrapper"},
            },
        },
        {
            "timestamp": "2026-07-11T12:00:00Z",
            "type": "future_record",
            "payload": {"message": {"role": "user", "content": "future nested user wrapper"}},
        },
        {
            "timestamp": "2026-07-11T12:00:00Z",
            "type": "event_msg",
            "payload": {"type": "user_message_v2", "message": "versioned user message"},
        },
    ],
)
def test_codex_unknown_user_wrappers_are_explicit_gaps(tmp_path: Path, record: dict):
    sources = _load()
    path = tmp_path / "rollout-unknown-wrapper.jsonl"
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    lifecycle = _regular_lifecycle(sources, [{"source": "codex-sessions", "path": path}])
    key = sources.cursor_unit_key("codex-sessions", path)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["errors"] == []
    assert result["unsupported"] == [key]
    assert key not in result["files"]


def test_codex_fork_and_unmatched_effective_context_are_not_operator_input(tmp_path: Path):
    sources = _load()
    session_id = "019f-forked-session"
    path = tmp_path / f"rollout-{session_id}.jsonl"
    rows = [
        {
            "type": "session_meta",
            "payload": {"id": session_id, "forked_from_id": "019f-parent"},
        },
        {
            "timestamp": "2026-07-11T12:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "inherited operator turn"},
                    {"type": "input_text", "text": "injected effective context"},
                ],
            },
        },
        {
            "timestamp": "2026-07-11T12:00:00Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "inherited operator turn",
                "images": [],
                "local_images": [],
                "text_elements": [],
            },
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "codex-sessions", "path": path, "mtime": "2026-07-11T12:00:00Z"}],
    )

    events, _result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert not [event for event in events if event["authority"] == "operator"]
    assert {event["body_kind"] for event in events if event["provenance"] == "continuation_summary"} == {
        "session_context"
    }
    snapshot = sources.update_ledger(
        sources.LedgerPaths.for_root(tmp_path / "ledger"),
        events=events,
        cursor={
            "version": 1,
            "scope": "fixture",
            "source_manifest_digest": sources.digest({"fixture": 1}),
            "source_families": {},
            "files": {},
        },
    )
    assert snapshot["coverage"]["atoms"] == 0


def test_codex_unmatched_effective_input_stays_unknown_not_operator():
    sources = _load()
    events = [
        {
            "source": "codex-sessions",
            "session_ref": "codex:one",
            "event_index": 0,
            "text_index": 0,
            "text": "actual turn",
            "provenance": "operator_typed",
            "authority": "operator",
            "body_kind": "direct",
        },
        {
            "source": "codex-sessions",
            "session_ref": "codex:one",
            "event_index": 1,
            "text_index": 0,
            "text": "actual turn",
            "provenance": "transport_echo",
            "authority": "derived",
            "body_kind": "direct",
        },
        {
            "source": "codex-sessions",
            "session_ref": "codex:one",
            "event_index": 2,
            "text_index": 0,
            "text": "unmatched effective input",
            "provenance": "operator_typed",
            "authority": "operator",
            "body_kind": "direct",
        },
    ]

    normalized = sources.normalize_codex_file_events("codex-sessions", events, forked=False)

    unmatched = next(event for event in normalized if event["text"] == "unmatched effective input")
    assert unmatched["provenance"] == "unknown_user_input"
    assert unmatched["authority"] == "unknown"


def test_malformed_regular_source_fails_closed_without_cursor_advance(tmp_path: Path):
    sources = _load()
    path = tmp_path / "torn.jsonl"
    path.write_text('{"display":"first"}\n{broken\n', encoding="utf-8")
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "agy-cli-history", "path": path, "mtime": "2026-07-11T12:00:00Z"}],
    )

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    key = sources.cursor_unit_key("agy-cli-history", path)
    assert events == []
    assert result["errors"]
    assert key not in result["files"]
    assert result["coverage"]["agy-cli-history"]["errors"] == 1


def test_malformed_source_keeps_all_scope_partial(tmp_path: Path, monkeypatch):
    sources = _load()
    path = tmp_path / "torn.jsonl"
    path.write_text("{broken\n", encoding="utf-8")
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "agy-cli-history", "path": path, "mtime": "2026-07-11T12:00:00Z"}],
    )
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)

    _events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=5,
    )

    assert cursor["scope"] == "partial:all"
    assert cursor["source_errors"]
    assert cursor["all_baseline_complete"] is False
    assert sources.cursor_unit_key("agy-cli-history", path) not in cursor["files"]


def test_native_scan_rejects_malformed_stored_cursor_before_discovery(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle = _regular_lifecycle(sources, [])
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    cursor_path = tmp_path / "cursor.json"
    cursor_path.write_text(json.dumps({"revision": "broken"}), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid stored source cursor"):
        sources.scan_native_sources(
            SimpleNamespace(cursor=cursor_path),
            days=None,
            max_files=1,
        )


@pytest.mark.parametrize("payload", ["{broken", "[]"])
def test_native_scan_rejects_syntax_or_nonobject_cursor(tmp_path: Path, monkeypatch, payload: str):
    sources = _load()
    lifecycle = _regular_lifecycle(sources, [])
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    cursor_path = tmp_path / "cursor.json"
    cursor_path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="invalid stored source cursor"):
        sources.scan_native_sources(
            SimpleNamespace(cursor=cursor_path),
            days=None,
            max_files=1,
        )


def _opencode_fixture(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        """
    )
    for index, session_id in enumerate(("unknown", "proved"), start=1):
        connection.execute("INSERT INTO session VALUES (?, ?, ?)", (session_id, index, index))
        message_data: dict[str, object] = {"role": "user"}
        if session_id == "proved":
            message_data["prompt_provenance"] = {
                "primary": True,
                "authority": "operator",
                "provenance": "operator_typed",
            }
        message_id = f"message-{session_id}"
        connection.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?)",
            (message_id, session_id, index, json.dumps(message_data)),
        )
        connection.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            (
                f"part-{session_id}",
                message_id,
                session_id,
                index,
                json.dumps({"type": "text", "text": f"{session_id} prompt"}),
            ),
        )
    connection.commit()
    connection.close()


def test_opencode_requires_primary_proof_and_caps_work_by_session(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    _opencode_fixture(database)
    lifecycle.OPENCODE_DB = database

    first_events, first = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    assert len(first_events) == 1
    assert first_events[0]["authority"] == "unknown"
    assert first["pending_files"] == 1
    assert len(first["processed"]) == 1

    second_events, second = sources.scan_opencode(
        lifecycle,
        {"files": first["processed"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    assert len(second_events) == 1
    assert second_events[0]["authority"] == "operator"
    assert second["pending_files"] == 0


def test_opencode_malformed_session_is_not_cursor_advanced(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        INSERT INTO session VALUES ('broken', 1, 1);
        INSERT INTO message VALUES ('message-broken', 'broken', 1, '{broken');
        """
    )
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database

    events, result = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["errors"]
    assert result["processed"] == {}


def test_opencode_unknown_user_part_is_not_cursor_advanced(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        INSERT INTO session VALUES ('future', 1, 1);
        """
    )
    connection.execute(
        "INSERT INTO message VALUES ('message-future', 'future', 1, ?)",
        (json.dumps({"role": "user"}),),
    )
    connection.execute(
        "INSERT INTO part VALUES ('part-future', 'message-future', 'future', 1, ?)",
        (json.dumps({"type": "future-user-part", "prompt": "Hidden OpenCode ask."}),),
    )
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database

    events, result = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["processed"] == {}
    assert len(result["errors"]) == 1
    assert "explicit adapter" in result["errors"][0]


def test_opencode_human_role_alias_is_not_silently_skipped(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        INSERT INTO session VALUES ('human', 1, 1);
        """
    )
    connection.execute(
        "INSERT INTO message VALUES ('message-human', 'human', 1, ?)",
        (json.dumps({"role": "human", "prompt": "Hidden human-role ask."}),),
    )
    connection.execute(
        "INSERT INTO part VALUES ('part-human', 'message-human', 'human', 1, ?)",
        (json.dumps({"type": "text", "text": "Hidden human-role ask."}),),
    )
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database

    events, result = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["processed"] == {}
    assert "unknown OpenCode user-bearing" in result["errors"][0]


@pytest.mark.parametrize(
    "part_data",
    [
        {"type": "text", "role": "human", "text": "Hidden human-role OpenCode ask."},
        {"type": "future-user", "prompt": "Hidden future OpenCode ask."},
    ],
    ids=("human-role-part", "future-prompt-part"),
)
def test_opencode_non_user_message_cannot_hide_user_bearing_part(tmp_path: Path, part_data: dict):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        INSERT INTO session VALUES ('hidden', 1, 1);
        """
    )
    connection.execute(
        "INSERT INTO message VALUES ('message-hidden', 'hidden', 1, ?)",
        (json.dumps({"role": "assistant"}),),
    )
    connection.execute(
        "INSERT INTO part VALUES ('part-hidden', 'message-hidden', 'hidden', 1, ?)",
        (json.dumps(part_data),),
    )
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database

    events, result = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["processed"] == {}
    assert result["coverage"]["opencode-db"]["converged"] == 0
    assert "user-bearing message or part" in result["errors"][0]


@pytest.mark.parametrize("orphan_kind", ["part-without-message", "message-without-session"])
def test_opencode_referential_orphans_block_family_convergence(tmp_path: Path, orphan_kind: str):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        """
    )
    if orphan_kind == "part-without-message":
        connection.execute("INSERT INTO session VALUES ('one', 1, 1)")
        connection.execute(
            "INSERT INTO part VALUES ('orphan', 'missing', 'one', 1, ?)",
            (json.dumps({"type": "text", "text": "Orphan prompt."}),),
        )
    else:
        connection.execute(
            "INSERT INTO message VALUES ('orphan', 'missing', 1, ?)",
            (json.dumps({"role": "user", "prompt": "Orphan prompt."}),),
        )
        connection.execute(
            "INSERT INTO part VALUES ('part', 'orphan', 'missing', 1, ?)",
            (json.dumps({"type": "text", "text": "Orphan prompt."}),),
        )
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database

    events, result = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["processed"] == {}
    assert result["coverage"]["opencode-db"]["errors"] == 1
    assert "canonical" in result["errors"][0]


def test_opencode_content_mutation_invalidates_unchanged_session_times(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        INSERT INTO session VALUES ('one', 1, 1);
        """
    )
    connection.execute(
        "INSERT INTO message VALUES ('message-one', 'one', 1, ?)",
        (json.dumps({"role": "user"}),),
    )
    connection.execute(
        "INSERT INTO part VALUES ('part-one', 'message-one', 'one', 1, ?)",
        (json.dumps({"type": "text", "text": "alpha ask"}),),
    )
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database

    first_events, first = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    original = database.stat()
    time.sleep(0.01)
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE part SET data=? WHERE id='part-one'",
        (json.dumps({"type": "text", "text": "omega ask"}),),
    )
    connection.commit()
    connection.close()
    os.utime(database, ns=(original.st_atime_ns, original.st_mtime_ns))

    second_events, second = sources.scan_opencode(
        lifecycle,
        {"files": first["processed"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert [event["text"] for event in first_events] == ["alpha ask"]
    assert [event["text"] for event in second_events] == ["omega ask"]
    assert second["attempted_files"] == 1
    assert second["processed"] != first["processed"]


def test_opencode_generation_change_only_spends_work_on_changed_session(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        """
    )
    for index in range(6):
        session_id = f"session-{index}"
        message_id = f"message-{index}"
        connection.execute("INSERT INTO session VALUES (?, ?, ?)", (session_id, index, index))
        connection.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?)",
            (message_id, session_id, index, json.dumps({"role": "user"})),
        )
        connection.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            (
                f"part-{index}",
                message_id,
                session_id,
                index,
                json.dumps({"type": "text", "text": f"prompt {index}"}),
            ),
        )
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database

    _first_events, first = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=6),
    )
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE part SET data=? WHERE id='part-5'",
        (json.dumps({"type": "text", "text": "changed prompt 5"}),),
    )
    connection.commit()
    connection.close()

    second_events, second = sources.scan_opencode(
        lifecycle,
        {"files": first["processed"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert [event["text"] for event in second_events] == ["changed prompt 5"]
    assert second["attempted_files"] == 1
    assert second["pending_files"] == 0
    assert len(second["processed"]) == 6
    assert second["coverage"]["opencode-db"]["converged"] == 6


def test_opencode_generation_change_during_scan_never_advances_cursor(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    _opencode_fixture(database)
    lifecycle.OPENCODE_DB = database
    real_signature = sources.opencode_storage_signature
    calls = {"count": 0}

    def drifting_signature(path: Path):
        signature = real_signature(path)
        calls["count"] += 1
        if calls["count"] == 2 and signature is not None:
            signature = {**signature, "db_ctime_ns": signature["db_ctime_ns"] + 1}
        return signature

    monkeypatch.setattr(sources, "opencode_storage_signature", drifting_signature)

    events, result = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
    )

    assert events == []
    assert result["processed"] == {}
    assert result["coverage"]["opencode-db"]["converged"] == 0
    assert "changed during scan" in result["errors"][-1]


def test_tampered_cached_content_digest_is_rejected_by_checkpoint_binding(tmp_path: Path, monkeypatch):
    sources = _load()
    database = tmp_path / "opencode.db"
    _opencode_fixture(database)
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = []
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = database
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")

    events, proposal = sources.scan_native_sources(paths, days=None, max_files=2)
    sources.update_ledger(paths, events=events, cursor=proposal)
    cursor = sources.load_json_strict(paths.cursor)[0]
    opencode_key = next(key for key in cursor["files"] if ":opencode-db:" in key)
    cursor["files"][opencode_key]["content_sha256"] = "0" * 64
    paths.cursor.write_text(json.dumps(cursor), encoding="utf-8")

    with pytest.raises(ValueError, match="not bound to the current private checkpoint"):
        sources.scan_native_sources(paths, days=None, max_files=2)


def test_mutating_live_attested_scan_proposal_before_seal_is_rejected(tmp_path: Path, monkeypatch):
    sources = _load()
    database = tmp_path / "opencode.db"
    _opencode_fixture(database)
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = []
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = database
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")
    events, proposal = sources.scan_native_sources(paths, days=None, max_files=2)
    key = next(iter(proposal["files"]))
    proposal["files"][key]["db_size"] += 1

    with pytest.raises(ValueError, match="live scanner attestation"):
        sources.update_ledger(paths, events=events, cursor=proposal)

    assert not paths.cursor.exists()
    assert not paths.event_journal.exists()
    assert not paths.public_snapshot.exists()
    assert not paths.source_scan_receipts.exists()


def test_empty_opencode_container_generation_is_bound_before_exact_seal(tmp_path: Path, monkeypatch):
    sources = _load()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        """
    )
    connection.commit()
    connection.close()
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = []
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = database
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")
    real_storage_signature = sources.opencode_storage_signature
    storage_calls = 0

    def counted_storage_signature(path: Path):
        nonlocal storage_calls
        storage_calls += 1
        return real_storage_signature(path)

    monkeypatch.setattr(sources, "opencode_storage_signature", counted_storage_signature)
    events, proposal = sources.scan_native_sources(paths, days=None, max_files=1)
    assert proposal["source_unit_count"] == 0
    assert storage_calls == 2

    connection = sqlite3.connect(database)
    connection.execute("INSERT INTO session VALUES ('new', 1, 1)")
    connection.execute(
        "INSERT INTO message VALUES ('message-new', 'new', 1, ?)",
        (json.dumps({"role": "user"}),),
    )
    connection.execute(
        "INSERT INTO part VALUES ('part-new', 'message-new', 'new', 1, ?)",
        (json.dumps({"type": "text", "text": "new prompt"}),),
    )
    connection.commit()
    connection.close()

    with pytest.raises(ValueError, match="live container generation changed"):
        sources.update_ledger(paths, events=events, cursor=proposal)

    assert not paths.cursor.exists()
    assert not paths.event_journal.exists()
    assert not paths.public_snapshot.exists()
    assert not paths.source_scan_receipts.exists()


def test_all_history_exact_cas_replaces_deleted_opencode_session_custody(tmp_path: Path, monkeypatch):
    sources = _load()
    database = tmp_path / "opencode.db"
    _opencode_fixture(database)
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = []
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = database
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")

    first_events, first_proposal = sources.scan_native_sources(paths, days=None, max_files=2)
    first_snapshot = sources.update_ledger(paths, events=first_events, cursor=first_proposal)
    first_cursor = sources.load_json_strict(paths.cursor)[0]
    first_keys = {key for key in first_cursor["files"] if ":opencode-db:" in key}
    assert first_snapshot["validation"]["ok"] is True
    assert len(first_keys) == 2
    first_receipt = paths.private_dir / first_cursor["source_scan_receipt_ref"]
    assert first_receipt.stat().st_mode & 0o777 == 0o400
    assert hashlib.sha256(first_receipt.read_bytes()).hexdigest() == first_cursor["source_scan_receipt_sha256"]
    assert sources.check_ledger(paths, require_scope="all") == []

    connection = sqlite3.connect(database)
    connection.execute("DELETE FROM part WHERE session_id='unknown'")
    connection.execute("DELETE FROM message WHERE session_id='unknown'")
    connection.execute("DELETE FROM session WHERE id='unknown'")
    connection.commit()
    connection.close()

    second_events, second_proposal = sources.scan_native_sources(paths, days=None, max_files=2)
    assert second_proposal["replace_files"] is True
    assert second_proposal["source_unit_count"] == 1
    second_snapshot = sources.update_ledger(paths, events=second_events, cursor=second_proposal)
    second_cursor = sources.load_json_strict(paths.cursor)[0]
    second_keys = {key for key in second_cursor["files"] if ":opencode-db:" in key}

    assert second_snapshot["validation"]["ok"] is True
    assert len(second_keys) == 1
    assert second_keys < first_keys
    assert sources.validate_source_adapter_cursor(second_cursor) == []
    assert sources.check_ledger(paths, require_scope="all") == []


def test_all_history_accepts_last_session_deletion_from_healthy_opencode_database(
    tmp_path: Path,
    monkeypatch,
):
    sources = _load()
    database = tmp_path / "opencode.db"
    _opencode_fixture(database)
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = []
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = database
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")
    first_events, first_proposal = sources.scan_native_sources(paths, days=None, max_files=2)
    sources.update_ledger(paths, events=first_events, cursor=first_proposal)

    connection = sqlite3.connect(database)
    connection.execute("DELETE FROM part")
    connection.execute("DELETE FROM message")
    connection.execute("DELETE FROM session")
    connection.commit()
    connection.close()

    second_events, second_proposal = sources.scan_native_sources(paths, days=None, max_files=2)
    assert second_events == []
    assert second_proposal["scope"] == "all"
    assert second_proposal["source_errors"] == []
    assert second_proposal["source_unit_count"] == 0
    second_snapshot = sources.update_ledger(paths, events=second_events, cursor=second_proposal)
    second_cursor = sources.load_json_strict(paths.cursor)[0]

    assert second_snapshot["validation"]["ok"] is True
    assert second_cursor["files"] == {}
    assert sources.check_ledger(paths, require_scope="all") == []


@pytest.mark.parametrize("artifact_state", ["missing", "tampered", "writable"])
def test_exact_all_scan_receipt_must_remain_hash_matched_and_immutable(
    tmp_path: Path,
    monkeypatch,
    artifact_state: str,
):
    sources = _load()
    database = tmp_path / "opencode.db"
    _opencode_fixture(database)
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = []
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = database
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")
    events, proposal = sources.scan_native_sources(paths, days=None, max_files=2)
    sources.update_ledger(paths, events=events, cursor=proposal)
    cursor = sources.load_json_strict(paths.cursor)[0]
    receipt = paths.private_dir / cursor["source_scan_receipt_ref"]

    if artifact_state == "missing":
        receipt.unlink()
    elif artifact_state == "tampered":
        receipt.chmod(0o600)
        receipt.write_text('{"tampered":true}\n', encoding="utf-8")
        receipt.chmod(0o400)
    else:
        receipt.chmod(0o600)

    errors = sources.check_ledger(paths, require_scope="all")
    assert any("source scan receipt" in error for error in errors)
    with pytest.raises(ValueError, match="invalid stored source adapter cursor"):
        sources.update_ledger(paths)


def test_exact_all_receipt_destination_cannot_escape_private_custody(tmp_path: Path, monkeypatch):
    sources = _load()
    database = tmp_path / "opencode.db"
    _opencode_fixture(database)
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = []
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = database
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")
    paths.private_dir.mkdir(parents=True)
    outside = tmp_path / "outside-receipts"
    outside.mkdir()
    paths.source_scan_receipts.symlink_to(outside, target_is_directory=True)
    events, proposal = sources.scan_native_sources(paths, days=None, max_files=2)

    with pytest.raises(ValueError, match="receipt directory escapes private custody"):
        sources.update_ledger(paths, events=events, cursor=proposal)

    assert list(outside.iterdir()) == []
    assert not paths.cursor.exists()
    assert not paths.event_journal.exists()
    assert not paths.public_snapshot.exists()


def test_live_attested_rescan_supersedes_stale_scanner_code_receipt(tmp_path: Path, monkeypatch):
    sources = _load()
    database = tmp_path / "opencode.db"
    _opencode_fixture(database)
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = []
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = database
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")
    events, proposal = sources.scan_native_sources(paths, days=None, max_files=2)
    sources.update_ledger(paths, events=events, cursor=proposal)
    old_cursor = sources.load_json_strict(paths.cursor)[0]
    old_receipt_ref = old_cursor["source_scan_receipt_ref"]

    changed_code_digest = "e" * 64
    core = sys.modules["limen.prompt_corpus"]
    monkeypatch.setattr(core, "current_source_scanner_code_digest", lambda: changed_code_digest)
    monkeypatch.setattr(sources, "current_source_scanner_code_digest", lambda: changed_code_digest)
    replacement_events, replacement = sources.scan_native_sources(paths, days=None, max_files=2)
    sources.update_ledger(paths, events=replacement_events, cursor=replacement)
    refreshed = sources.load_json_strict(paths.cursor)[0]

    assert refreshed["source_scan_code_digest"] == changed_code_digest
    assert refreshed["source_scan_receipt_ref"] != old_receipt_ref
    assert sources.check_ledger(paths, require_scope="all") == []


def test_exact_all_live_check_rejects_new_regular_source_after_seal(tmp_path: Path, monkeypatch):
    sources = _load()
    root = tmp_path / "history"
    root.mkdir()
    first_path = root / "first.jsonl"
    first_path.write_text(json.dumps({"display": "first exact ask"}) + "\n", encoding="utf-8")
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("agy-cli-history", root, ("*.jsonl",))]
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")
    events, proposal = sources.scan_native_sources(paths, days=None, max_files=1)
    sources.update_ledger(paths, events=events, cursor=proposal)
    assert sources.check_ledger(paths, require_scope="all") == []

    second_path = root / "second.jsonl"
    second_path.write_text(json.dumps({"display": "new unsealed ask"}) + "\n", encoding="utf-8")

    assert "live source unit manifest changed after the sealed scan" in sources.check_ledger(
        paths,
        require_scope="all",
    )
    with pytest.raises(ValueError, match="live source custody changed"):
        sources.update_ledger(paths)


def test_exact_all_rechecks_live_source_at_final_commit_boundary(tmp_path: Path, monkeypatch):
    sources = _load()
    root = tmp_path / "history"
    root.mkdir()
    source_path = root / "one.jsonl"
    source_path.write_text(json.dumps({"display": "sealed ask"}) + "\n", encoding="utf-8")
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("agy-cli-history", root, ("*.jsonl",))]
    lifecycle.HOME = tmp_path / "missing-home"
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")
    events, proposal = sources.scan_native_sources(paths, days=None, max_files=1)
    core = sys.modules["limen.prompt_corpus"]
    real_atoms_from_event = core.atoms_from_event
    mutated = False

    def mutate_during_atomization(*args, **kwargs):
        nonlocal mutated
        if not mutated:
            mutated = True
            source_path.write_text(json.dumps({"display": "changed during commit"}) + "\n", encoding="utf-8")
        return real_atoms_from_event(*args, **kwargs)

    monkeypatch.setattr(core, "atoms_from_event", mutate_during_atomization)
    with pytest.raises(ValueError, match="live source signature changed"):
        sources.update_ledger(paths, events=events, cursor=proposal)

    assert mutated is True
    assert not paths.cursor.exists()
    assert not paths.event_journal.exists()
    assert not paths.raw_objects.exists()
    assert not paths.source_scan_receipts.exists()
    assert not paths.public_snapshot.exists()


def _agy_database(path: Path, prompt: str) -> None:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 14, ?, NULL, NULL, NULL, NULL)",
        (prompt,),
    )
    connection.commit()
    connection.close()


def test_agy_conversation_adapter_obeys_shared_work_unit_cap(tmp_path: Path):
    sources = _load()
    root = tmp_path / "agy"
    root.mkdir()
    _agy_database(root / "one.db", "First bounded prompt with enough material to parse.")
    _agy_database(root / "two.db", "Second bounded prompt with enough material to parse.")
    lifecycle = SimpleNamespace(
        AGY_CLI_CONVERSATIONS=root,
        blob_text_spans=lambda value: [value] if isinstance(value, str) else [],
        agy_prompt_from_spans=lambda spans: spans[0] if spans else None,
        normalize_task_body=lambda text: ("", "direct"),
        iso_from_ts=lambda value: str(value),
    )

    events, result = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert len(events) == 1
    assert len(result["processed"]) == 1
    assert result["pending_files"] == 1


def test_agy_wal_only_prompt_append_invalidates_cached_conversation(tmp_path: Path):
    sources = _load()
    root = tmp_path / "agy"
    root.mkdir()
    database = root / "wal.db"
    writer = sqlite3.connect(database)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    writer.execute("INSERT INTO steps VALUES (1, 14, 'first prompt', NULL, NULL, NULL, NULL)")
    writer.commit()
    lifecycle = SimpleNamespace(
        AGY_CLI_CONVERSATIONS=root,
        blob_text_spans=lambda value: [value] if isinstance(value, str) else [],
        agy_prompt_from_spans=lambda spans: spans[0] if spans else None,
        normalize_task_body=lambda text: ("", "direct"),
        iso_from_ts=lambda value: str(value),
    )

    first_events, first = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    database_before = sources.file_signature(database)
    writer.execute("INSERT INTO steps VALUES (2, 14, 'second prompt', NULL, NULL, NULL, NULL)")
    writer.commit()
    assert sources.file_signature(database) == database_before

    second_events, second = sources.scan_agy_conversations(
        lifecycle,
        {"files": first["processed"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    writer.close()

    assert [event["text"] for event in first_events] == ["first prompt"]
    assert [event["text"] for event in second_events] == ["first prompt", "second prompt"]
    assert second["attempted_files"] == 1
    assert second["processed"] != first["processed"]


def test_agy_cache_hit_rechecks_wal_generation_before_convergence(tmp_path: Path, monkeypatch):
    sources = _load()
    root = tmp_path / "agy"
    root.mkdir()
    database = root / "cache-race.db"
    writer = sqlite3.connect(database)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    writer.execute("INSERT INTO steps VALUES (1, 14, 'first prompt', NULL, NULL, NULL, NULL)")
    writer.commit()
    lifecycle = SimpleNamespace(
        AGY_CLI_CONVERSATIONS=root,
        blob_text_spans=lambda value: [value] if isinstance(value, str) else [],
        agy_prompt_from_spans=lambda spans: spans[0] if spans else None,
        normalize_task_body=lambda text: ("", "direct"),
        iso_from_ts=lambda value: str(value),
    )
    _events, first = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    real_signature = sources.agy_storage_signature
    calls = 0

    def mutate_after_first_signature(path: Path):
        nonlocal calls
        signature = real_signature(path)
        calls += 1
        if calls == 1:
            writer.execute("INSERT INTO steps VALUES (2, 14, 'racing prompt', NULL, NULL, NULL, NULL)")
            writer.commit()
        return signature

    monkeypatch.setattr(sources, "agy_storage_signature", mutate_after_first_signature)
    events, result = sources.scan_agy_conversations(
        lifecycle,
        {"files": first["processed"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    writer.close()

    assert calls >= 2
    assert events == []
    assert result["processed"] == {}
    assert result["attempted_files"] == 0
    assert result["coverage"]["agy-cli-conversations"]["converged"] == 0
    assert any("changed during cache validation" in error for error in result["errors"])


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "A future Agy prompt carrier."},
        {"role": "human", "content": "A human-role Agy prompt carrier."},
    ],
    ids=("prompt-field", "human-role"),
)
def test_unknown_agy_prompt_step_is_an_explicit_source_error(tmp_path: Path, payload: dict):
    sources = _load()
    root = tmp_path / "agy"
    root.mkdir()
    database = root / "future.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 99, ?, NULL, NULL, NULL, NULL)",
        (json.dumps(payload),),
    )
    connection.commit()
    connection.close()
    lifecycle = sources.load_lifecycle_module()
    lifecycle.AGY_CLI_CONVERSATIONS = root

    events, result = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["processed"] == {}
    assert len(result["errors"]) == 1
    assert "explicit prompt adapter" in result["errors"][0]


@pytest.mark.parametrize(
    "payload",
    [
        {"role": "human", "content": "A hidden human prompt carried inside a bounded binary JSON value."},
        {"role": "operator", "content": "A hidden operator prompt carried inside a bounded binary JSON value."},
        {"prompt": "A hidden future prompt carried inside a bounded binary JSON value."},
    ],
    ids=("human-role", "operator-role", "prompt-field"),
)
def test_unknown_agy_binary_json_prompt_carrier_is_an_explicit_source_error(
    tmp_path: Path,
    payload: dict,
):
    sources = _load()
    root = tmp_path / "agy"
    root.mkdir()
    database = root / "future-binary.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, step_payload BLOB, metadata BLOB, "
        "task_details BLOB, error_details BLOB, render_info BLOB)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 99, ?, NULL, NULL, NULL, NULL)",
        (sqlite3.Binary(json.dumps(payload).encode("utf-8")),),
    )
    connection.commit()
    connection.close()
    lifecycle = sources.load_lifecycle_module()
    lifecycle.AGY_CLI_CONVERSATIONS = root

    events, result = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["processed"] == {}
    assert result["coverage"]["agy-cli-conversations"]["converged"] == 0
    assert len(result["errors"]) == 1
    assert "explicit prompt adapter" in result["errors"][0]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("idx", float("inf")),
        ("idx", float("nan")),
        ("idx", 1.5),
        ("idx", "1"),
        ("step_type", float("inf")),
        ("step_type", float("nan")),
        ("step_type", 14.5),
        ("step_type", "14"),
    ],
    ids=(
        "idx-inf",
        "idx-nan",
        "idx-float",
        "idx-string",
        "type-inf",
        "type-nan",
        "type-float",
        "type-string",
    ),
)
def test_agy_step_identity_requires_exact_nonnegative_integers(tmp_path: Path, field: str, value):
    sources = _load()
    root = tmp_path / "agy"
    root.mkdir()
    database = root / "bad-identity.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx, step_type, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    identity = {"idx": 1, "step_type": 14}
    identity[field] = value
    connection.execute(
        "INSERT INTO steps VALUES (?, ?, 'A grounded prompt long enough for exact source parsing.', "
        "NULL, NULL, NULL, NULL)",
        (identity["idx"], identity["step_type"]),
    )
    connection.commit()
    connection.close()
    lifecycle = sources.load_lifecycle_module()
    lifecycle.AGY_CLI_CONVERSATIONS = root

    events, result = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["processed"] == {}
    assert result["coverage"]["agy-cli-conversations"]["converged"] == 0
    assert len(result["errors"]) == 1
    assert "malformed step identity" in result["errors"][0]


def test_partial_all_baseline_keeps_discovering_old_pending_files(tmp_path: Path, monkeypatch):
    sources = _load()
    now = time.time()
    paths = []
    for index, age_days in enumerate((10, 9, 0)):
        path = tmp_path / f"source-{index}.jsonl"
        path.write_text(json.dumps({"display": f"ask {index}"}) + "\n", encoding="utf-8")
        os.utime(path, (now - age_days * 86400, now - age_days * 86400))
        paths.append(path)

    lifecycle = _regular_lifecycle(sources, [])

    lifecycle.LOCAL_SOURCES = [("agy-cli-history", tmp_path, ("source-*.jsonl",))]
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    cursor_path = tmp_path / "cursor.json"
    ledger_paths = SimpleNamespace(cursor=cursor_path)

    _events, first = sources.scan_native_sources(ledger_paths, days=None, max_files=1)
    assert first["scope"] == "partial:all"
    assert first["pending_files"] == 2
    assert first["unresolved_unit_count"] == 2
    assert sources.validate_source_adapter_cursor(first) == []
    cursor_path.write_text(json.dumps(first), encoding="utf-8")

    _events, second = sources.scan_native_sources(ledger_paths, days=2, max_files=1)
    assert second["scope"] == "partial:all"
    assert second["effective_horizon_days"] is None
    assert second["pending_files"] == 1
    assert second["unresolved_unit_count"] == 1
    assert sources.validate_source_adapter_cursor(second) == []
    assert any("source-1.jsonl" in key for key in second["files"])
    cursor_path.write_text(json.dumps(second), encoding="utf-8")

    _events, third = sources.scan_native_sources(ledger_paths, days=2, max_files=1)
    assert third["scope"] == "all"
    assert third["all_baseline_complete"] is True
    assert third["unresolved_unit_count"] == 0
    assert sources.validate_source_adapter_cursor(third) == []
    assert (
        len([key for key in third["files"] if key.startswith(f"scan-v{sources.SCANNER_VERSION}:agy-cli-history:")]) == 3
    )


def test_recent_scan_after_exact_all_preserves_full_source_custody(tmp_path: Path, monkeypatch):
    sources = _load()
    now = time.time()
    paths = []
    for index, age_days in enumerate((40, 0)):
        path = tmp_path / f"history-{index}.jsonl"
        path.write_text(json.dumps({"display": f"ask {index}"}) + "\n", encoding="utf-8")
        os.utime(path, (now - age_days * 86400, now - age_days * 86400))
        paths.append(path)
    lifecycle = _regular_lifecycle(sources, [])
    lifecycle.LOCAL_SOURCES = [("agy-cli-history", tmp_path, ("history-*.jsonl",))]
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    cursor_path = tmp_path / "cursor.json"
    ledger_paths = SimpleNamespace(cursor=cursor_path)

    _events, first = sources.scan_native_sources(ledger_paths, days=None, max_files=2)
    assert first["scope"] == "all"
    assert first["source_unit_count"] == 2
    cursor_path.write_text(json.dumps(first), encoding="utf-8")

    events, second = sources.scan_native_sources(ledger_paths, days=14, max_files=2)

    assert events == []
    assert second["effective_horizon_days"] is None
    assert second["scope"] == "all"
    assert second["source_unit_count"] == 2
    assert second["files"] == first["files"]
    assert second["work_units_used"] == 0


def test_same_size_rewrite_with_restored_mtime_invalidates_source_cache(tmp_path: Path):
    sources = _load()
    path = (tmp_path / "history.jsonl").resolve()
    path.write_text(json.dumps({"display": "alpha ask"}) + "\n", encoding="utf-8")
    lifecycle = _regular_lifecycle(sources, [{"source": "agy-cli-history", "path": path}])

    first_events, first = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    original = path.stat()
    time.sleep(0.01)
    path.write_text(json.dumps({"display": "omega ask"}) + "\n", encoding="utf-8")
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))

    second_events, second = sources.scan_regular_sources(
        lifecycle,
        {"files": first["files"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert [event["text"] for event in first_events] == ["alpha ask"]
    assert [event["text"] for event in second_events] == ["omega ask"]
    assert second["attempted_files"] == 1
    assert second["files"] != first["files"]


def test_cached_regular_parser_rechecks_source_signature_before_convergence(tmp_path: Path, monkeypatch):
    sources = _load()
    path = (tmp_path / "history.jsonl").resolve()
    path.write_text(json.dumps({"display": "alpha ask"}) + "\n", encoding="utf-8")
    row = {"source": "agy-cli-history", "path": path}
    lifecycle = _regular_lifecycle(sources, [row])
    _events, first = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[row],
    )
    key = sources.cursor_unit_key("agy-cli-history", path)
    real_signature = sources.file_signature
    calls = 0

    def mutate_after_discovery(candidate: Path):
        nonlocal calls
        signature = real_signature(candidate)
        if candidate == path:
            calls += 1
            if calls == 1:
                path.write_text(path.read_text(encoding="utf-8") + json.dumps({"display": "racing ask"}) + "\n")
        return signature

    monkeypatch.setattr(sources, "file_signature", mutate_after_discovery)
    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": first["files"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[row],
    )

    assert calls >= 2
    assert events == []
    assert key not in result["files"]
    assert result["coverage"]["agy-cli-history"]["converged"] == 0
    assert any("cached parser validation" in error for error in result["errors"])


def test_cached_regular_exclusion_rechecks_source_signature_before_convergence(tmp_path: Path, monkeypatch):
    sources = _load()
    path = (tmp_path / ".claude" / "plans" / "generated.md").resolve()
    path.parent.mkdir(parents=True)
    path.write_text("generated plan", encoding="utf-8")
    row = {"source": "claude-plans", "path": path}
    lifecycle = _regular_lifecycle(sources, [row])
    lifecycle.LOCAL_SOURCES = [("claude-plans", path.parent, (path.name,))]
    _events, first = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[row],
    )
    key = sources.cursor_unit_key("claude-plans", path)
    receipt = first["excluded_unit_receipts"][key]
    assert sources.source_unit_receipt_matches(
        receipt,
        disposition="excluded",
        contract_id="claude-generated-plan-v1",
        contract_digest=sources.source_adapter_contract()["digest"],
        source="claude-plans",
        locator=str(path),
        signature=receipt["signature"],
        related_signatures={},
    )
    real_signature = sources.file_signature
    calls = 0

    def mutate_after_discovery(candidate: Path):
        nonlocal calls
        signature = real_signature(candidate)
        if candidate == path:
            calls += 1
            if calls == 1:
                path.write_text("generated plan changed", encoding="utf-8")
        return signature

    monkeypatch.setattr(sources, "file_signature", mutate_after_discovery)
    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}, "excluded_unit_receipts": first["excluded_unit_receipts"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[row],
    )

    assert calls >= 2
    assert events == []
    assert key not in result["excluded_unit_receipts"]
    assert result["coverage"]["claude-plans"]["excluded"] == 0
    assert any("cached exclusion validation" in error for error in result["errors"])


def test_source_contract_change_invalidates_old_all_baseline_and_forces_full_horizon(
    tmp_path: Path,
    monkeypatch,
):
    sources = _load()
    now = time.time()
    old_path = tmp_path / "old.jsonl"
    recent_path = tmp_path / "recent.jsonl"
    for path, age_days in ((old_path, 10), (recent_path, 0)):
        path.write_text(json.dumps({"display": path.stem}) + "\n", encoding="utf-8")
        os.utime(path, (now - age_days * 86400, now - age_days * 86400))
    lifecycle = _regular_lifecycle(sources, [])
    lifecycle.LOCAL_SOURCES = [
        ("agy-cli-history", old_path, (old_path.name,)),
        ("agy-cli-history", recent_path, (recent_path.name,)),
    ]
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    cursor_path = tmp_path / "cursor.json"
    stale_contract = {**sources.source_adapter_contract(), "digest": "0" * 64}
    cursor_path.write_text(
        json.dumps(
            {
                "version": 1,
                "scanner_version": sources.SCANNER_VERSION,
                "scope": "all",
                "target_scope": "all",
                "all_baseline_complete": True,
                "source_adapter_contract": stale_contract,
                "files": {
                    sources.cursor_unit_key("agy-cli-history", old_path): sources.file_signature(old_path),
                    sources.cursor_unit_key("agy-cli-history", recent_path): sources.file_signature(recent_path),
                },
            }
        ),
        encoding="utf-8",
    )

    _events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=cursor_path),
        days=2,
        max_files=1,
    )

    assert cursor["effective_horizon_days"] is None
    assert cursor["replace_files"] is True
    assert cursor["scope"] == "partial:all"
    assert cursor["all_baseline_complete"] is False
    assert cursor["pending_files"] == 1
    assert cursor["source_coverage"]["agy-cli-history"]["discovered"] == 2


def test_full_scan_carries_prior_pending_family_when_source_root_disappears(tmp_path: Path, monkeypatch):
    sources = _load()
    first_path = tmp_path / "source-1.jsonl"
    second_path = tmp_path / "source-2.jsonl"
    for path in (first_path, second_path):
        path.write_text(json.dumps({"display": path.stem}) + "\n", encoding="utf-8")
    lifecycle = _regular_lifecycle(sources, [])
    lifecycle.LOCAL_SOURCES = [
        ("agy-cli-history", first_path, (first_path.name,)),
        ("agy-cli-history", second_path, (second_path.name,)),
    ]
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    cursor_path = tmp_path / "cursor.json"

    _events, first = sources.scan_native_sources(
        SimpleNamespace(cursor=cursor_path),
        days=None,
        max_files=1,
    )
    assert first["scope"] == "partial:all"
    assert first["source_families"]["agy-cli-history"]["pending"] == 1
    cursor_path.write_text(json.dumps(first), encoding="utf-8")
    first_path.unlink()
    second_path.unlink()

    _events, second = sources.scan_native_sources(
        SimpleNamespace(cursor=cursor_path),
        days=2,
        max_files=1,
    )

    assert second["scope"] == "partial:all"
    assert second["all_baseline_complete"] is False
    assert "agy-cli-history" in second["adapter_gaps"]
    assert second["source_families"]["agy-cli-history"]["errors"] == 1
    assert any("previously tracked source obligations" in error for error in second["source_errors"])


@pytest.mark.parametrize("gap_kind", ["unsupported", "error"])
def test_full_scan_keeps_partial_family_when_one_unresolved_unit_disappears(
    tmp_path: Path,
    monkeypatch,
    gap_kind: str,
):
    sources = _load()
    projects = tmp_path / ".claude" / "projects"
    good = projects / "project" / "good.jsonl"
    bad = projects / "project" / "bad.jsonl"
    good.parent.mkdir(parents=True)
    good.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "valid retained turn"}}) + "\n",
        encoding="utf-8",
    )
    if gap_kind == "unsupported":
        bad.write_text(
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [{"type": "image", "source": {"type": "base64", "data": "opaque"}}],
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        bad.write_text("{malformed\n", encoding="utf-8")
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    cursor_path = tmp_path / "cursor.json"
    ledger_paths = SimpleNamespace(cursor=cursor_path)

    _events, first = sources.scan_native_sources(
        ledger_paths,
        days=None,
        max_files=0,
        unbounded=True,
    )
    assert first["scope"] == "partial:all"
    assert first["unresolved_unit_count"] == 1
    assert len(first["unresolved_units"]) == 1
    assert sources.validate_source_adapter_cursor(first) == []
    assert first["source_families"]["claude-projects"][gap_kind + "s" if gap_kind == "error" else gap_kind] == 1
    cursor_path.write_text(json.dumps(first), encoding="utf-8")
    bad.unlink()

    _events, second = sources.scan_native_sources(
        ledger_paths,
        days=None,
        max_files=0,
        unbounded=True,
    )

    assert second["scope"] == "partial:all"
    assert second["all_baseline_complete"] is False
    assert second["source_families"]["claude-projects"]["discovered"] == 1
    assert second["source_families"]["claude-projects"]["errors"] == 1
    assert "claude-projects" in second["adapter_gaps"]
    assert any("previously tracked source obligations" in error for error in second["source_errors"])
    assert sources.validate_source_adapter_cursor(second) == []
    cursor_path.write_text(json.dumps(second), encoding="utf-8")

    _events, third = sources.scan_native_sources(
        ledger_paths,
        days=None,
        max_files=0,
        unbounded=True,
    )

    assert third["scope"] == "partial:all"
    assert third["all_baseline_complete"] is False
    assert third["unresolved_units"] == second["unresolved_units"]
    assert third["unresolved_units_digest"] == second["unresolved_units_digest"]
    assert third["source_errors"] == second["source_errors"]
    assert third["source_manifest_digest"] == second["source_manifest_digest"]
    assert third["adapter_gap_routes"] == second["adapter_gap_routes"]
    assert third["work_units_used"] == 0
    assert sources.validate_source_adapter_cursor(third) == []


def test_all_history_prune_does_not_resurrect_last_stale_source_receipts(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle = _regular_lifecycle(sources, [])
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    contract = sources.source_adapter_contract()
    signature = {"size": 12, "mtime_ns": 34}
    excluded_key = sources.cursor_unit_key("claude-plans", tmp_path / "deleted-plan.md")
    adapted_key = sources.cursor_unit_key("claude-projects", tmp_path / "deleted-adapter.json")
    cursor_path = tmp_path / "cursor.json"
    cursor_path.write_text(
        json.dumps(
            {
                "version": 1,
                "scanner_version": sources.SCANNER_VERSION,
                "scope": "partial:all",
                "target_scope": "all",
                "all_baseline_complete": False,
                "source_adapter_contract": contract,
                "files": {adapted_key: signature},
                "excluded_unit_receipts": {
                    excluded_key: {
                        "version": sources.SOURCE_ADAPTER_CONTRACT_VERSION,
                        "disposition": "excluded",
                        "contract_id": "claude-generated-plan-v1",
                        "contract_digest": contract["digest"],
                        "signature": signature,
                        "related_signatures": {},
                    }
                },
                "adapted_unit_receipts": {
                    adapted_key: {
                        "version": sources.SOURCE_ADAPTER_CONTRACT_VERSION,
                        "disposition": "adapted",
                        "contract_id": "claude-remote-task-command-v1",
                        "contract_digest": contract["digest"],
                        "signature": signature,
                        "related_signatures": {},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    _events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=cursor_path),
        days=None,
        max_files=5,
    )

    assert cursor["excluded_unit_receipts"] == {}
    assert cursor["adapted_unit_receipts"] == {}
    assert cursor["excluded_source_count"] == 0
    assert cursor["adapted_source_count"] == 0


def test_unsupported_source_is_visible_and_blocks_all_scope(tmp_path: Path, monkeypatch):
    sources = _load()
    projects = tmp_path / ".claude" / "projects"
    unsupported = projects / "project" / "rogue.md"
    unsupported.parent.mkdir(parents=True)
    unsupported.write_text("unknown markdown", encoding="utf-8")
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "claude-projects", "path": unsupported, "mtime": "2026-07-11"}],
    )
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)

    _events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=5,
    )

    assert cursor["scope"] == "partial:all"
    assert cursor["unsupported_source_count"] == 1
    assert cursor["adapter_gaps"] == ["claude-projects"]
    assert cursor["source_coverage"]["claude-projects"]["unsupported"] == 1
    assert cursor["source_families"]["claude-projects"]["unsupported"] == 1

    cursor_path = tmp_path / "cursor.json"
    cursor_path.write_text(json.dumps(cursor), encoding="utf-8")
    _events, repeated = sources.scan_native_sources(
        SimpleNamespace(cursor=cursor_path),
        days=2,
        max_files=1,
    )
    assert repeated["scope"] == "partial:all"
    assert repeated["unsupported_source_count"] == 1
    assert repeated["work_units_used"] == 0


def test_structural_non_prompt_exclusions_precede_extension_and_cache(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    tasks = tmp_path / ".claude" / "tasks"
    plans = tmp_path / ".claude" / "plans"
    history = tmp_path / ".claude" / "file-history"
    tool_result = projects / "project" / "session" / "tool-results" / "trap.json"
    workflow_script = projects / "project" / "session" / "workflows" / "scripts" / "generated.js"
    memory = projects / "project" / "memory" / "rule.md"
    memory_mirror = projects / "project" / "rule.md"
    lock = tasks / "session" / ".lock"
    watermark = tasks / "session" / ".highwatermark"
    plan = plans / "generated.md"
    snapshot = history / "session" / "0123456789abcdef@v3"
    for path in (
        tool_result,
        workflow_script,
        memory,
        memory_mirror,
        lock,
        watermark,
        plan,
        snapshot,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    tool_result.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "must stay excluded"}}),
        encoding="utf-8",
    )
    workflow_script.write_text("throw new Error('derived');", encoding="utf-8")
    memory.write_text("derived memory", encoding="utf-8")
    memory_mirror.write_text("derived memory", encoding="utf-8")
    lock.write_bytes(b"")
    watermark.write_text("42\n", encoding="ascii")
    plan.write_text("assistant plan", encoding="utf-8")
    snapshot.write_text("source snapshot", encoding="utf-8")
    lifecycle.LOCAL_SOURCES = [
        ("claude-projects", projects, ("*",)),
        ("claude-tasks", tasks, ("*",)),
        ("claude-plans", plans, ("*",)),
        ("claude-file-history", history, ("*",)),
    ]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    rows = sources.regular_source_rows(lifecycle, None)
    tool_key = sources.cursor_unit_key("claude-projects", tool_result)
    mirror_key = sources.cursor_unit_key("claude-projects", memory_mirror)
    tool_signature = sources.file_signature(tool_result)
    budget = sources.ScanBudget(limit=8)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {
            "files": {tool_key: tool_signature},
            "unsupported_units": {tool_key: tool_signature},
            "excluded_unit_receipts": {
                tool_key: {
                    "version": sources.SOURCE_ADAPTER_CONTRACT_VERSION,
                    "disposition": "excluded",
                    "contract_id": "claude-project-tool-result-v1",
                    "contract_digest": "stale-contract-digest",
                    "signature": tool_signature,
                    "related_signatures": {},
                }
            },
        },
        days=None,
        budget=budget,
        rows=rows,
    )

    assert events == []
    assert result["errors"] == []
    assert result["unsupported"] == []
    assert budget.used == 8
    assert len(result["excluded_unit_receipts"]) == 8
    assert tool_key not in result["files"]
    assert tool_key not in result["unsupported_units"]
    assert result["coverage"]["claude-projects"]["excluded"] == 4
    assert result["source_exclusion_counts"]["claude-project-tool-result-v1"] == 1
    mirror_receipt = result["excluded_unit_receipts"][mirror_key]
    mirror_evidence = mirror_receipt["related_evidence"]["memory_sibling"]
    expected_sibling = memory_mirror.parent / "memory" / memory_mirror.name
    assert mirror_evidence["locator_sha256"] == hashlib.sha256(str(expected_sibling).encode()).hexdigest()
    assert mirror_evidence["primary_content_sha256"] == mirror_evidence["related_content_sha256"]

    cached_budget = sources.ScanBudget(limit=8)
    cached_events, cached = sources.scan_regular_sources(
        lifecycle,
        result,
        days=None,
        budget=cached_budget,
        rows=rows,
    )

    assert cached_events == []
    assert cached["errors"] == []
    assert cached["unsupported"] == []
    assert cached_budget.used == 0
    assert cached["excluded_unit_receipts"] == result["excluded_unit_receipts"]
    assert cached["source_exclusion_counts"] == result["source_exclusion_counts"]


def test_structural_exclusion_near_misses_remain_adapter_gaps(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    tasks = tmp_path / ".claude" / "tasks"
    history = tmp_path / ".claude" / "file-history"
    rogue_memory = projects / "project" / "rogue.md"
    rogue_memory_sibling = projects / "project" / "memory" / "rogue.md"
    nonempty_lock = tasks / "session" / ".lock"
    malformed_watermark = tasks / "session" / ".highwatermark"
    malformed_snapshot = history / "session" / "not-a-versioned-snapshot"
    for path in (
        rogue_memory,
        rogue_memory_sibling,
        nonempty_lock,
        malformed_watermark,
        malformed_snapshot,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
    rogue_memory.write_text("unknown markdown", encoding="utf-8")
    rogue_memory_sibling.write_text("different provider memory", encoding="utf-8")
    nonempty_lock.write_text("not empty", encoding="utf-8")
    malformed_watermark.write_text("forty-two", encoding="ascii")
    malformed_snapshot.write_text("unknown snapshot", encoding="utf-8")
    lifecycle.LOCAL_SOURCES = [
        ("claude-projects", projects, ("*",)),
        ("claude-tasks", tasks, ("*",)),
        ("claude-file-history", history, ("*",)),
    ]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=10),
        rows=[
            {"source": "claude-projects", "path": rogue_memory},
            {"source": "claude-tasks", "path": nonempty_lock},
            {"source": "claude-tasks", "path": malformed_watermark},
            {"source": "claude-file-history", "path": malformed_snapshot},
        ],
    )

    assert events == []
    assert result["errors"] == []
    assert len(result["unsupported"]) == 3
    nonempty_lock_key = sources.cursor_unit_key("claude-tasks", nonempty_lock)
    assert nonempty_lock_key in result["excluded_unit_receipts"]
    assert result["excluded_unit_receipts"][nonempty_lock_key]["contract_id"] == "claude-task-artifact-v1"
    rogue_key = sources.cursor_unit_key("claude-projects", rogue_memory)
    assert result["unsupported_units"][rogue_key] == sources.file_signature(rogue_memory)
    assert rogue_key not in result["files"]
    assert {row["unsupported"] for row in result["coverage"].values()} == {1}


def test_claude_remote_task_command_adapts_despite_old_file_cache_and_cached_rerun_is_free(
    tmp_path: Path,
    monkeypatch,
):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    remote_task = projects / "project" / "session" / "remote-agents" / "task.json"
    remote_task.parent.mkdir(parents=True)
    remote_task.write_text(
        json.dumps(
            {
                "command": "Audit the owner receipt and report the failing predicate.",
                "remoteTaskType": "task",
                "sessionId": "session-remote",
                "spawnedAt": 1783785600000,
                "taskId": "task-remote",
                "title": "Audit owner receipt",
                "toolUseId": "tool-remote",
            }
        ),
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    key = sources.cursor_unit_key("claude-projects", remote_task)
    signature = sources.file_signature(remote_task)
    first_budget = sources.ScanBudget(limit=1)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {key: signature}},
        days=None,
        budget=first_budget,
        rows=[{"source": "claude-projects", "path": remote_task}],
    )

    assert first_budget.used == 1
    assert result["errors"] == []
    assert result["unsupported"] == []
    assert len(events) == 1
    assert events[0]["text"] == "Audit the owner receipt and report the failing predicate."
    assert events[0]["provenance"] == "delegated_task_frame"
    assert events[0]["authority"] == "derived"
    assert result["adapted_unit_receipts"][key]["contract_id"] == "claude-remote-task-command-v1"
    assert result["coverage"]["claude-projects"]["adapted"] == 1

    cached_budget = sources.ScanBudget(limit=1)
    cached_events, cached = sources.scan_regular_sources(
        lifecycle,
        result,
        days=None,
        budget=cached_budget,
        rows=[{"source": "claude-projects", "path": remote_task}],
    )

    assert cached_events == []
    assert cached_budget.used == 0
    assert cached["errors"] == []
    assert cached["unsupported"] == []
    assert cached["adapted_unit_receipts"] == result["adapted_unit_receipts"]
    assert cached["source_adapter_counts"] == {"claude-remote-task-command-v1": 1}

    real_signature = sources.file_signature
    calls = 0

    def mutate_after_discovery(path: Path):
        nonlocal calls
        observed = real_signature(path)
        if path == remote_task:
            calls += 1
            if calls == 1:
                payload = json.loads(remote_task.read_text(encoding="utf-8"))
                payload["command"] = "Changed while the adapted cache was being validated."
                remote_task.write_text(json.dumps(payload), encoding="utf-8")
        return observed

    monkeypatch.setattr(sources, "file_signature", mutate_after_discovery)
    raced_events, raced = sources.scan_regular_sources(
        lifecycle,
        result,
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": remote_task}],
    )

    assert calls >= 2
    assert raced_events == []
    assert key not in raced["adapted_unit_receipts"]
    assert key not in raced["files"]
    assert raced["coverage"]["claude-projects"]["converged"] == 0
    assert any("cached adapter validation" in error for error in raced["errors"])


def test_claude_remote_task_command_enforces_its_hashed_adapter_byte_ceiling(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    remote_task = projects / "project" / "session" / "remote-agents" / "task.json"
    remote_task.parent.mkdir(parents=True)
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    limit = sources.SOURCE_ADAPTER_RULES["claude-remote-task-command-v1"]["max_probe_bytes"]
    record = {
        "command": "",
        "remoteTaskType": "task",
        "sessionId": "session-remote",
        "spawnedAt": 1783785600000,
        "taskId": "task-remote",
        "title": "Audit owner receipt",
        "toolUseId": "tool-remote",
    }

    def encoded_at_size(size: int) -> str:
        record["command"] = ""
        empty = json.dumps(record, separators=(",", ":"))
        record["command"] = "x" * (size - len(empty.encode("utf-8")))
        encoded = json.dumps(record, separators=(",", ":"))
        assert len(encoded.encode("utf-8")) == size
        return encoded

    remote_task.write_text(encoded_at_size(limit), encoding="utf-8")
    records, error, supported = sources.strict_native_records(
        lifecycle,
        "claude-projects",
        remote_task,
        sources.file_signature(remote_task),
    )
    assert supported is True
    assert error is None
    assert len(records) == 1

    remote_task.write_text(encoded_at_size(limit + 1), encoding="utf-8")
    records, error, supported = sources.strict_native_records(
        lifecycle,
        "claude-projects",
        remote_task,
        sources.file_signature(remote_task),
    )
    assert supported is True
    assert records == []
    assert f"adapter ceiling {limit}" in str(error)


def test_claude_subagent_and_workflow_paths_force_derived_authority_without_sidechain_flag(
    tmp_path: Path,
):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    subagent = projects / "project" / "session" / "subagents" / "agent.jsonl"
    workflow = projects / "project" / "session" / "workflows" / "run.jsonl"
    for path in (subagent, workflow):
        path.parent.mkdir(parents=True, exist_ok=True)
    subagent.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "delegated subagent instruction"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    workflow.write_text(
        json.dumps(
            {
                "type": "user",
                "isSidechain": False,
                "message": {"role": "user", "content": "delegated workflow instruction"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "claude-projects", "path": subagent},
            {"source": "claude-projects", "path": workflow},
        ],
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert {event["text"] for event in events} == {
        "delegated subagent instruction",
        "delegated workflow instruction",
    }
    assert {event["provenance"] for event in events} == {"delegated_task_frame"}
    assert {event["authority"] for event in events} == {"derived"}


def test_only_exact_main_claude_session_path_is_operator_eligible(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    main = projects / "project" / "session.jsonl"
    generated = projects / "project" / "session" / "generated" / "child.jsonl"
    for path, text in ((main, "main operator turn"), (generated, "unclassified generated turn")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"type": "user", "message": {"role": "user", "content": text}}) + "\n",
            encoding="utf-8",
        )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "claude-projects", "path": main},
            {"source": "claude-projects", "path": generated},
        ],
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    by_text = {event["text"]: event for event in events}
    assert by_text["main operator turn"]["authority"] == "operator"
    assert by_text["main operator turn"]["provenance"] == "operator_typed"
    assert by_text["unclassified generated turn"]["authority"] == "unknown"
    assert by_text["unclassified generated turn"]["provenance"] == "unknown_user_input"


def test_claude_subagent_and_workflow_metadata_preserve_prompt_segments_as_derived_adapters(
    tmp_path: Path,
):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    subagent = projects / "project" / "session" / "subagents" / "agent.json"
    workflow = projects / "project" / "session" / "workflows" / "run.json"
    for path in (subagent, workflow):
        path.parent.mkdir(parents=True, exist_ok=True)
    subagent.write_text(
        json.dumps(
            {
                "description": "Trace the authoritative owner receipt.",
                "toolUseId": "tool-use-1",
            }
        ),
        encoding="utf-8",
    )
    workflow.write_text(
        json.dumps(
            {
                "args": "Audit the prompt-corpus control plane.",
                "agentType": "Workflow",
                "phases": [{"title": "Inspect", "detail": "Find every unsupported source."}],
                "workflowProgress": [{"promptPreview": "Verify exact source grounding."}],
            }
        ),
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    budget = sources.ScanBudget(limit=2)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=budget,
        rows=[
            {"source": "claude-projects", "path": subagent},
            {"source": "claude-projects", "path": workflow},
        ],
    )

    assert budget.used == 2
    assert result["errors"] == []
    assert result["unsupported"] == []
    assert [event["text"] for event in events] == [
        "Trace the authoritative owner receipt.",
        "Audit the prompt-corpus control plane.",
        "Inspect",
        "Find every unsupported source.",
        "Verify exact source grounding.",
    ]
    assert {event["provenance"] for event in events} == {"delegated_task_frame"}
    assert {event["authority"] for event in events} == {"derived"}
    assert result["source_adapter_counts"] == {
        "claude-subagent-metadata-v1": 1,
        "claude-workflow-metadata-v1": 1,
    }
    assert len(result["adapted_unit_receipts"]) == 2

    cached_budget = sources.ScanBudget(limit=2)
    cached_events, cached = sources.scan_regular_sources(
        lifecycle,
        result,
        days=None,
        budget=cached_budget,
        rows=[
            {"source": "claude-projects", "path": subagent},
            {"source": "claude-projects", "path": workflow},
        ],
    )
    assert cached_events == []
    assert cached_budget.used == 0
    assert cached["adapted_unit_receipts"] == result["adapted_unit_receipts"]


def test_unknown_claude_jsonl_record_type_remains_explicit_unsupported(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    unknown = projects / "project" / "session" / "unknown.jsonl"
    unknown.parent.mkdir(parents=True)
    unknown.write_text(
        json.dumps(
            {
                "type": "future-provider-record",
                "message": {"role": "user", "content": "possibly prompt-bearing future shape"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    key = sources.cursor_unit_key("claude-projects", unknown)
    signature = sources.file_signature(unknown)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": unknown}],
    )

    assert events == []
    assert result["errors"] == []
    assert result["unsupported"] == [key]
    assert result["unsupported_units"][key] == signature
    assert key not in result["files"]


@pytest.mark.parametrize(
    "row",
    [
        {"type": "user", "content": "future provider moved the prompt"},
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "image", "source": {"type": "base64", "data": "opaque"}}],
            },
        },
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Do not silently drop the attached evidence."},
                    {"type": "document", "source": {"type": "base64", "data": "opaque"}},
                ],
            },
        },
        {"type": "attachment", "attachment": {"type": "future_prompt_carrier", "prompt": "hidden"}},
        {
            "type": "attachment",
            "attachment": {
                "type": "hook_additional_context",
                "content": "known injected context",
                "prompt": "future prompt carrier must not be dropped",
            },
        },
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "future_delegation", "prompt": "hidden"}],
            },
        },
    ],
)
def test_known_claude_record_types_with_unknown_nested_schema_remain_unsupported(
    tmp_path: Path,
    row: dict,
):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    unknown = projects / "project" / "session" / "unknown.jsonl"
    unknown.parent.mkdir(parents=True)
    unknown.write_text(json.dumps(row) + "\n", encoding="utf-8")
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    key = sources.cursor_unit_key("claude-projects", unknown)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": unknown}],
    )

    assert events == []
    assert result["errors"] == []
    assert result["unsupported"] == [key]
    assert key not in result["files"]


def test_unmatched_claude_queued_command_attachment_remains_unknown_input(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session" / "transcript.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {
                "type": "attachment",
                "attachment": {
                    "type": "queued_command",
                    "commandMode": "command",
                    "prompt": "Continue with the exact owner receipt.",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert [event["text"] for event in events] == ["Continue with the exact owner receipt."]
    assert events[0]["provenance"] == "unknown_user_input"
    assert events[0]["authority"] == "unknown"


def test_unmatched_claude_goal_status_condition_remains_unknown_input(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {
                "type": "attachment",
                "sessionId": "session",
                "attachment": {
                    "type": "goal_status",
                    "condition": "Finish only after exact-head proof.",
                    "met": False,
                    "reason": "Still running predicates.",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert [event["text"] for event in events] == ["Finish only after exact-head proof."]
    assert events[0]["provenance"] == "unknown_user_input"
    assert events[0]["authority"] == "unknown"


def test_claude_assistant_delegation_fields_are_preserved_as_exact_derived_segments(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session" / "transcript.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Agent",
                            "input": {
                                "prompt": "Inspect the exact owner evidence.",
                                "instructions": "Preserve global Agent instructions.",
                                "description": "Review owner evidence",
                            },
                        },
                        {
                            "type": "tool_use",
                            "name": "SendMessage",
                            "input": {"message": "Return only blocker findings."},
                        },
                        {
                            "type": "tool_use",
                            "name": "MysteryTool",
                            "input": {"instructions": "Preserve the future tool instruction."},
                        },
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert [event["text"] for event in events] == [
        "Inspect the exact owner evidence.",
        "Preserve global Agent instructions.",
        "Review owner evidence",
        "Return only blocker findings.",
        "Preserve the future tool instruction.",
    ]
    assert {event["provenance"] for event in events} == {"delegated_task_frame"}
    assert {event["authority"] for event in events} == {"derived"}


def test_claude_meta_compact_and_tool_originated_user_rows_never_gain_operator_authority(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    rows = [
        {
            "type": "user",
            "isMeta": True,
            "message": {"role": "user", "content": "Injected meta context."},
        },
        {
            "type": "user",
            "isCompactSummary": True,
            "message": {"role": "user", "content": "Compacted continuation context."},
        },
        {
            "type": "user",
            "sourceToolAssistantUUID": "tool-origin",
            "message": {"role": "user", "content": "Tool-originated context."},
        },
    ]
    transcript.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert not [event for event in events if event["authority"] == "operator"]
    assert [event["provenance"] for event in events] == [
        "delegated_task_frame",
        "continuation_summary",
        "delegated_task_frame",
    ]


def test_claude_tool_result_with_extra_prompt_carrier_is_an_explicit_gap(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "tool-one",
                            "content": "ordinary tool output",
                            "prompt": "Hidden prompt carrier.",
                        }
                    ],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    key = sources.cursor_unit_key("claude-projects", transcript)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert events == []
    assert result["unsupported"] == [key]
    assert key not in result["files"]


def test_claude_hook_additional_context_is_preserved_as_derived_input(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {
                "type": "attachment",
                "attachment": {
                    "type": "hook_additional_context",
                    "content": "Injected hook instruction with explicit derived lineage.",
                    "hookEvent": "UserPromptSubmit",
                    "hookName": "fixture",
                    "toolUseID": "tool-fixture",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert result["unsupported"] == []
    assert [event["text"] for event in events] == ["Injected hook instruction with explicit derived lineage."]
    assert events[0]["provenance"] == "delegated_task_frame"
    assert events[0]["authority"] == "derived"


def test_unmatched_claude_queue_operation_content_remains_unknown_input(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session" / "transcript.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        json.dumps(
            {
                "type": "queue-operation",
                "operation": "enqueue",
                "content": "Continue after the current exact-head check.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert [event["text"] for event in events] == ["Continue after the current exact-head check."]
    assert events[0]["provenance"] == "unknown_user_input"
    assert events[0]["authority"] == "unknown"


def test_queue_content_exactly_matching_same_file_operator_input_becomes_transport_echo(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    text = "Continue after the current exact-head check."
    transcript.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {"type": "queue-operation", "operation": "enqueue", "content": text},
                {"type": "user", "message": {"role": "user", "content": text}},
            )
        ),
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert result["errors"] == []
    assert [event["provenance"] for event in events] == ["transport_echo", "operator_typed"]
    assert [event["authority"] for event in events] == ["derived", "operator"]


def test_queue_hash_match_in_different_session_does_not_become_transport_echo(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    text = "Same text, different session provenance."
    transcript.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {
                    "type": "queue-operation",
                    "operation": "enqueue",
                    "content": text,
                    "sessionId": "session-a",
                },
                {
                    "type": "user",
                    "sessionId": "session-b",
                    "message": {"role": "user", "content": text},
                },
            )
        ),
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert result["errors"] == []
    assert [event["session_ref"] for event in events] == ["claude:session-a", "claude:session-b"]
    assert [event["provenance"] for event in events] == ["unknown_user_input", "operator_typed"]


def test_last_prompt_uses_same_file_operator_lineage_and_preserves_unmatched_input(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    matched = "Exact same-file operator prompt."
    unmatched = "Prompt retained only by the last-prompt record."
    transcript.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {
                    "type": "last-prompt",
                    "lastPrompt": matched,
                    "leafUuid": "leaf-1",
                    "sessionId": "session",
                },
                {
                    "type": "user",
                    "sessionId": "session",
                    "message": {"role": "user", "content": matched},
                },
                {
                    "type": "last-prompt",
                    "lastPrompt": unmatched,
                    "leafUuid": "leaf-2",
                    "sessionId": "session",
                },
            )
        ),
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )

    assert result["errors"] == []
    assert [(event["text"], event["provenance"]) for event in events] == [
        (matched, "transport_echo"),
        (matched, "operator_typed"),
        (unmatched, "unknown_user_input"),
    ]


def test_unknown_workflow_nested_prompt_key_remains_explicit_gap(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    workflow = projects / "project" / "session" / "workflows" / "run.json"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        json.dumps(
            {
                "runId": "run-1",
                "phases": [{"instructions": "A future hidden delegated prompt."}],
            }
        ),
        encoding="utf-8",
    )
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    key = sources.cursor_unit_key("claude-projects", workflow)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": workflow}],
    )

    assert events == []
    assert result["errors"] == []
    assert result["unsupported"] == [key]
    assert key not in result["files"]


def test_source_contract_digest_covers_complete_rule_descriptors(monkeypatch):
    sources = _load()
    prompt_sources = sys.modules["limen.prompt_sources"]
    original = sources.source_adapter_contract()
    path_rule = prompt_sources.SOURCE_EXCLUSION_RULES["claude-generated-plan-v1"]["path"]

    monkeypatch.setitem(path_rule, "suffix", ".renamed")

    changed = sources.source_adapter_contract()
    assert changed["version"] == original["version"]
    assert changed["digest"] != original["digest"]


def _codex_attachment_fixture(
    sources,
    tmp_path: Path,
    *,
    body: str = "Bounded synthetic attachment request.",
    parent_texts: list[str] | None = None,
    duplicate_reference: bool = False,
    forked: bool = False,
):
    attachments = tmp_path / ".codex" / "attachments"
    attachment = attachments / "fixture-container" / "pasted-text-1.txt"
    attachment.parent.mkdir(parents=True, exist_ok=True)
    attachment.write_text(body, encoding="utf-8")
    sessions = tmp_path / ".codex" / "sessions"
    session = sessions / "2026" / "07" / "13" / "rollout-fixture.jsonl"
    session.parent.mkdir(parents=True, exist_ok=True)
    reference = sources.codex_attachment_reference_line(attachment)
    active_parent_texts = [reference] if parent_texts is None else parent_texts
    if duplicate_reference:
        active_parent_texts = [f"{reference}\n{reference}"]
    metadata = {"id": "fixture-thread"}
    if forked:
        metadata["forked_from_id"] = "fixture-parent"
    rows = [{"type": "session_meta", "payload": metadata}]
    rows.extend(
        {
            "timestamp": f"2026-07-13T01:00:0{index}Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }
        for index, text in enumerate(active_parent_texts, start=1)
    )
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [
        ("codex-sessions", sessions, ("*",)),
        ("codex-attachments", attachments, ("*",)),
    ]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path
    return lifecycle, session, attachment


@pytest.mark.parametrize(
    ("forked", "expected_provenance", "expected_authority"),
    [
        (False, "operator_typed", "operator"),
        (True, "continuation_summary", "derived"),
    ],
)
def test_codex_pasted_text_attachment_binds_to_one_parent_and_inherits_authority(
    tmp_path: Path,
    forked: bool,
    expected_provenance: str,
    expected_authority: str,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path, forked=forked)
    key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    attachment_events = [event for event in events if event["source"] == "codex-attachments"]
    parent_events = [event for event in events if event["source"] == "codex-sessions"]
    assert result["errors"] == []
    assert result["unsupported"] == []
    assert len(attachment_events) == len(parent_events) == 1
    assert attachment_events[0]["text"] == "Bounded synthetic attachment request."
    assert attachment_events[0]["session_ref"] == parent_events[0]["session_ref"]
    assert attachment_events[0]["timestamp"] == parent_events[0]["timestamp"]
    assert attachment_events[0]["provenance"] == expected_provenance
    assert attachment_events[0]["authority"] == expected_authority
    receipt = result["adapted_unit_receipts"][key]
    assert receipt["contract_id"] == "codex-pasted-text-attachment-v1"
    assert set(receipt["related_signatures"]) == {"parent_session"}
    assert set(receipt["related_evidence"]) == {"parent_event"}
    assert sources.source_contract_receipt_applies(
        receipt["contract_id"],
        "codex-attachments",
        str(attachment),
        signature=sources.file_signature(attachment),
        related_signatures=receipt["related_signatures"],
        related_evidence=receipt["related_evidence"],
    )
    assert result["source_adapter_counts"] == {"codex-pasted-text-attachment-v1": 1}
    assert result["coverage"]["codex-attachments"]["adapted"] == 1


@pytest.mark.parametrize("ambiguity", ["missing", "multiple-events", "duplicate-reference"])
def test_codex_attachment_missing_or_ambiguous_parent_fails_closed(
    tmp_path: Path,
    ambiguity: str,
):
    sources = _load()
    parent_texts = [] if ambiguity == "missing" else None
    lifecycle, session, attachment = _codex_attachment_fixture(
        sources,
        tmp_path,
        parent_texts=parent_texts,
        duplicate_reference=ambiguity == "duplicate-reference",
    )
    if ambiguity == "multiple-events":
        reference = sources.codex_attachment_reference_line(attachment)
        lifecycle, session, attachment = _codex_attachment_fixture(
            sources,
            tmp_path,
            parent_texts=[reference, reference],
        )
    key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert result["errors"] == []
    assert result["unsupported"] == [key]
    assert result["unsupported_units"][key] == sources.file_signature(attachment)
    assert key not in result["files"]
    assert key not in result["adapted_unit_receipts"]


def test_codex_attachment_traversal_reference_does_not_bind(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path, parent_texts=[])
    relative_alias = attachment.parent / ".." / attachment.parent.name / attachment.name
    traversal_reference = f"pasted text file: {relative_alias}. Read this file before continuing."
    lifecycle, session, attachment = _codex_attachment_fixture(
        sources,
        tmp_path,
        parent_texts=[traversal_reference],
    )
    key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert result["unsupported"] == [key]
    assert key not in result["adapted_unit_receipts"]


@pytest.mark.parametrize("symlink_kind", ["file", "directory"])
def test_codex_attachment_symlink_never_receives_adapter_custody(tmp_path: Path, symlink_kind: str):
    sources = _load()
    attachments = tmp_path / ".codex" / "attachments"
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_attachment = outside / "pasted-text-1.txt"
    outside_attachment.write_text("Synthetic outside body.", encoding="utf-8")
    if symlink_kind == "file":
        attachment = attachments / "fixture-container" / "pasted-text-1.txt"
        attachment.parent.mkdir(parents=True)
        attachment.symlink_to(outside_attachment)
    else:
        attachments.mkdir(parents=True)
        linked_parent = attachments / "fixture-container"
        linked_parent.symlink_to(outside, target_is_directory=True)
        attachment = linked_parent / "pasted-text-1.txt"
    sessions = tmp_path / ".codex" / "sessions"
    session = sessions / "rollout-fixture.jsonl"
    session.parent.mkdir(parents=True)
    session.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-13T01:00:00Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": sources.codex_attachment_reference_line(attachment)}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [
        ("codex-sessions", sessions, ("*",)),
        ("codex-attachments", attachments, ("*",)),
    ]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert result["adapted_unit_receipts"] == {}
    assert len(result["errors"]) == 1
    assert "symlink hop" in result["errors"][0]


def test_codex_attachment_enforces_byte_and_encoding_bounds(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    limit = sources.SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]["max_probe_bytes"]
    attachment.write_bytes(b"x" * (limit + 1))

    events, oversized = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert "bounded byte ceiling" in " ".join(oversized["errors"])
    assert oversized["adapted_unit_receipts"] == {}

    attachment.write_bytes(b"\xff\xfe\xfa")
    events, malformed = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert "strict UTF-8" in " ".join(malformed["errors"])
    assert malformed["adapted_unit_receipts"] == {}


def test_codex_attachment_streams_parent_larger_than_the_regular_source_limit(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    limits = sources.runtime_limits({"resource_limits": {"max_source_bytes_per_unit": 256}})
    key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        limits=limits,
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    attachment_events = [event for event in events if event["source"] == "codex-attachments"]
    assert len(attachment_events) == 1
    assert attachment_events[0]["provenance"] == "operator_typed"
    assert result["adapted_unit_receipts"][key]["contract_id"] == "codex-pasted-text-attachment-v1"
    assert result["coverage"]["codex-sessions"]["errors"] == 1
    assert "bounded ceiling" in " ".join(result["errors"])


def test_codex_attachment_streaming_parent_caps_fail_closed(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle, session, _attachment = _codex_attachment_fixture(sources, tmp_path)
    signature = sources.file_signature(session)
    assert signature is not None
    rule = sources.SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]
    monkeypatch.setitem(rule, "max_parent_records", 1)

    events, error = sources.bounded_codex_attachment_parent_events_from_path(
        lifecycle,
        session,
        signature,
        limits=sources.runtime_limits({}),
    )

    assert events == []
    assert error is not None and "record count exceeds" in error

    monkeypatch.setitem(rule, "max_parent_records", 100)
    monkeypatch.setitem(rule, "max_parent_probe_bytes", 1)
    events, error = sources.bounded_codex_attachment_parent_events_from_path(
        lifecycle,
        session,
        signature,
        limits=sources.runtime_limits({}),
    )
    assert events == []
    assert error is not None and "byte ceiling" in error


def test_codex_attachment_malformed_parent_reference_fails_closed(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    reference = sources.codex_attachment_reference_line(attachment)
    session.write_text(
        '{"type":"response_item","payload":{"type":"message","role":"user",'
        f'"content":[{{"type":"input_text","text":"{reference}"}}]'
        "\n",
        encoding="utf-8",
    )
    key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert key not in result["adapted_unit_receipts"]
    assert result["unsupported"] == [key]
    assert result["coverage"]["codex-sessions"]["errors"] == 1


def test_codex_attachment_malformed_parent_metadata_fails_closed(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    rows[0]["payload"] = "invalid"
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert key not in result["adapted_unit_receipts"]
    assert result["unsupported"] == [key]
    assert "session metadata is malformed" in " ".join(result["errors"])


def test_codex_attachment_malformed_transport_echo_downgrades_authority(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    rows.insert(
        1,
        {
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": sources.codex_attachment_reference_line(attachment),
            },
        },
    )
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )

    attachment_events = [event for event in events if event["source"] == "codex-attachments"]
    assert len(attachment_events) == 1
    assert attachment_events[0]["provenance"] == "unknown_user_input"
    assert attachment_events[0]["authority"] == "unknown"
    assert result["coverage"]["codex-sessions"]["unsupported"] == 1


def test_codex_attachment_parent_replay_invalidates_cached_receipt(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [
        {"source": "codex-sessions", "path": session},
        {"source": "codex-attachments", "path": attachment},
    ]
    _events, first = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=rows,
    )
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)
    reference = sources.codex_attachment_reference_line(attachment)
    existing = session.read_text(encoding="utf-8")
    replay = {
        "timestamp": "2026-07-13T01:00:09Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": reference}],
        },
    }
    session.write_text(existing + json.dumps(replay) + "\n", encoding="utf-8")

    events, second = sources.scan_regular_sources(
        lifecycle,
        first,
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=rows,
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert second["unsupported"] == [attachment_key]
    assert attachment_key not in second["adapted_unit_receipts"]
    assert attachment_key not in second["files"]


def test_codex_attachment_cached_second_pass_is_zero_growth(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [
        {"source": "codex-sessions", "path": session},
        {"source": "codex-attachments", "path": attachment},
    ]
    first_budget = sources.ScanBudget(limit=2)
    first_events, first = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=first_budget,
        rows=rows,
    )
    first_receipts = json.dumps(first["adapted_unit_receipts"], sort_keys=True)

    second_budget = sources.ScanBudget(limit=2)
    second_events, second = sources.scan_regular_sources(
        lifecycle,
        first,
        days=None,
        budget=second_budget,
        rows=rows,
    )

    assert len(first_events) == 2
    assert first_budget.used == 2
    assert second_events == []
    assert second_budget.used == 0
    assert second["errors"] == []
    assert second["unsupported"] == []
    assert json.dumps(second["adapted_unit_receipts"], sort_keys=True) == first_receipts


def test_codex_attachment_native_ledger_second_pass_changes_no_canonical_bytes(
    tmp_path: Path,
    monkeypatch,
):
    sources = _load()
    lifecycle, _session, _attachment = _codex_attachment_fixture(sources, tmp_path)
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    root = tmp_path / "ledger"
    paths = sources.LedgerPaths.for_root(
        root,
        policy=ROOT / "docs" / "prompt-corpus-policy.json",
    )

    first_events, first_cursor = sources.scan_native_sources(
        paths,
        days=None,
        max_files=2,
    )
    first_snapshot = sources.update_ledger(paths, events=first_events, cursor=first_cursor)

    def canonical_bytes() -> dict[str, str]:
        files = [
            paths.event_journal,
            paths.outcome_journal,
            paths.cursor,
            paths.private_snapshot,
            paths.public_snapshot,
            paths.public_markdown,
            *sorted(path for path in paths.raw_objects.rglob("*") if path.is_file()),
            *sorted(path for path in paths.source_scan_receipts.rglob("*") if path.is_file()),
        ]
        return {
            str(index): hashlib.sha256(path.read_bytes()).hexdigest()
            for index, path in enumerate(files)
            if path.exists()
        }

    first_bytes = canonical_bytes()
    second_events, second_cursor = sources.scan_native_sources(
        paths,
        days=None,
        max_files=2,
    )
    second_snapshot = sources.update_ledger(paths, events=second_events, cursor=second_cursor)

    assert first_cursor["scope"] == "all"
    assert first_cursor["adapter_gaps"] == []
    assert first_cursor["work_units_used"] == 2
    assert first_snapshot["appended"]["occurrences"] == 2
    assert second_events == []
    assert second_cursor["work_units_used"] == 0
    assert second_snapshot["write_changed"] is False
    assert second_snapshot["appended"] == {
        "occurrences": 0,
        "atoms": 0,
        "outcomes": 0,
        "reclassified": 0,
    }
    assert canonical_bytes() == first_bytes


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("pasted-text-1.txt", "potentially prompt-bearing attachment"),
        (
            "detached.json",
            json.dumps(
                {
                    "timestamp": "2026-07-12T12:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "detached JSON prompt"}],
                    },
                }
            ),
        ),
        (
            "detached.jsonl",
            json.dumps(
                {
                    "timestamp": "2026-07-12T12:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "detached JSONL prompt"}],
                    },
                }
            )
            + "\n",
        ),
    ],
)
def test_detached_codex_attachment_remains_an_explicit_gap(tmp_path: Path, name: str, body: str):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    attachments = tmp_path / ".codex" / "attachments"
    attachment = attachments / "opaque-parent" / name
    attachment.parent.mkdir(parents=True)
    attachment.write_text(body, encoding="utf-8")
    lifecycle.LOCAL_SOURCES = [("codex-attachments", attachments, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    row = {"source": "codex-attachments", "path": attachment}
    key = sources.cursor_unit_key("codex-attachments", attachment)
    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}, "unsupported_units": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[row],
    )

    assert events == []
    assert result["errors"] == []
    assert result["unsupported"] == [key]
    assert result["unsupported_units"][key] == sources.file_signature(attachment)
    assert result["excluded_unit_receipts"] == {}
    assert result["coverage"]["codex-attachments"]["excluded"] == 0
    assert result["coverage"]["codex-attachments"]["unsupported"] == 1
    assert "codex-attachment-v1" not in sources.source_adapter_contract()["exclusion_ids"]


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("pasted-text-1.txt", "potentially prompt-bearing attachment"),
        (
            "detached.json",
            json.dumps(
                {
                    "timestamp": "2026-07-12T12:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "detached JSON prompt"}],
                    },
                }
            ),
        ),
        (
            "detached.jsonl",
            json.dumps(
                {
                    "timestamp": "2026-07-12T12:00:00Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "detached JSONL prompt"}],
                    },
                }
            )
            + "\n",
        ),
    ],
)
def test_detached_codex_attachment_keeps_all_scope_partial(
    tmp_path: Path,
    monkeypatch,
    name: str,
    body: str,
):
    sources = _load()
    attachments = tmp_path / ".codex" / "attachments"
    attachment = attachments / "opaque-parent" / name
    attachment.parent.mkdir(parents=True)
    attachment.write_text(body, encoding="utf-8")
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("codex-attachments", attachments, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    key = sources.cursor_unit_key("codex-attachments", attachment)

    events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=1,
    )

    assert events == []
    assert cursor["scope"] == "partial:all"
    assert cursor["unsupported_source_count"] == 1
    assert cursor["unsupported_units"][key] == sources.file_signature(attachment)
    assert cursor["adapter_gaps"] == ["codex-attachments"]
    assert cursor["excluded_unit_receipts"] == {}
    assert key not in cursor["files"]
    assert sources.validate_source_adapter_cursor(cursor) == []


def test_removed_codex_attachment_contract_resets_stale_cursor_to_gap(tmp_path: Path, monkeypatch):
    sources = _load()
    attachments = tmp_path / ".codex" / "attachments"
    attachment = attachments / "opaque-parent" / "detached.json"
    attachment.parent.mkdir(parents=True)
    attachment.write_text(json.dumps({"role": "user", "content": "detached prompt"}), encoding="utf-8")
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("codex-attachments", attachments, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    key = sources.cursor_unit_key("codex-attachments", attachment)
    signature = sources.file_signature(attachment)
    assert signature is not None
    stale_contract = json.loads(json.dumps(sources.source_adapter_contract()))
    stale_contract["digest"] = "a" * 64
    stale_contract["exclusion_ids"] = sorted([*stale_contract["exclusion_ids"], "codex-attachment-v1"])
    stale_contract["exclusion_sources"]["codex-attachment-v1"] = "codex-attachments"
    cursor_path = tmp_path / "cursor.json"
    cursor_path.write_text(
        json.dumps(
            {
                "version": 1,
                "scanner_version": sources.SCANNER_VERSION,
                "scope": "partial:all",
                "target_scope": "all",
                "all_baseline_complete": False,
                "source_adapter_contract": stale_contract,
                "files": {},
                "unsupported_units": {},
                "unresolved_units": [],
                "excluded_unit_receipts": {
                    key: {
                        "version": sources.SOURCE_ADAPTER_CONTRACT_VERSION,
                        "disposition": "excluded",
                        "contract_id": "codex-attachment-v1",
                        "contract_digest": stale_contract["digest"],
                        "signature": signature,
                        "related_signatures": {},
                    }
                },
                "adapted_unit_receipts": {},
            }
        ),
        encoding="utf-8",
    )

    events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=cursor_path),
        days=None,
        max_files=1,
    )

    assert events == []
    assert cursor["replace_files"] is True
    assert cursor["excluded_unit_receipts"] == {}
    assert cursor["unsupported_units"][key] == signature
    assert cursor["scope"] == "partial:all"
    assert cursor["adapter_gaps"] == ["codex-attachments"]
    assert sources.validate_source_adapter_cursor(cursor) == []


@pytest.mark.parametrize(
    ("relative", "payload", "expected_contract"),
    [
        ("artifact.bin", b"provider artifact", None),
        ("session/artifact.bin", b"provider artifact", "claude-task-artifact-v1"),
        ("session/.lock", b"", "claude-task-lock-v1"),
        ("session/.highwatermark", b"42\n", "claude-task-watermark-v1"),
        ("session/nested/.lock", b"", "claude-task-artifact-v1"),
        ("session/nested/.highwatermark", b"42\n", "claude-task-artifact-v1"),
    ],
)
def test_claude_task_exclusion_candidate_matches_receipt_depth(
    tmp_path: Path,
    relative: str,
    payload: bytes,
    expected_contract: str | None,
):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    tasks = tmp_path / ".claude" / "tasks"
    artifact = tasks / relative
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(payload)
    lifecycle.LOCAL_SOURCES = [("claude-tasks", tasks, ("*",))]
    signature = sources.file_signature(artifact)
    assert signature is not None

    candidate = sources.source_exclusion_candidate_id(
        lifecycle,
        "claude-tasks",
        artifact,
        signature,
    )

    assert candidate == expected_contract
    if expected_contract is None:
        assert not sources.source_contract_receipt_applies(
            "claude-task-artifact-v1",
            "claude-tasks",
            str(artifact),
            signature=signature,
        )
    else:
        assert sources.source_contract_receipt_applies(
            expected_contract,
            "claude-tasks",
            str(artifact),
            signature=signature,
        )


def test_symlinked_exclusion_never_receives_a_contract_receipt(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    plans = tmp_path / ".claude" / "plans"
    outside = tmp_path / "outside.md"
    linked = plans / "generated.md"
    plans.mkdir(parents=True)
    outside.write_text("not structurally owned by the plans root", encoding="utf-8")
    linked.symlink_to(outside)
    lifecycle.LOCAL_SOURCES = [("claude-plans", plans, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-plans", "path": linked}],
    )

    assert events == []
    assert result["excluded_unit_receipts"] == {}
    assert result["unsupported"] == []
    assert len(result["errors"]) == 1


def test_live_non_claude_source_symlink_is_never_ingested(tmp_path: Path):
    sources = _load()
    outside = tmp_path / "outside.jsonl"
    outside.write_text(json.dumps({"display": "Outside prompt."}) + "\n", encoding="utf-8")
    root = tmp_path / "history"
    root.mkdir()
    linked = root / "history.jsonl"
    linked.symlink_to(outside)
    lifecycle = _regular_lifecycle(sources, [])
    lifecycle.LOCAL_SOURCES = [("agy-cli-history", root, ("history.jsonl",))]
    key = sources.cursor_unit_key("agy-cli-history", linked)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "agy-cli-history", "path": linked}],
    )

    assert events == []
    assert len(result["errors"]) == 1
    assert "symlink hop" in result["errors"][0]
    assert key not in result["files"]


def test_generic_gemini_discovery_is_not_tied_to_agy_directory_names(tmp_path: Path):
    sources = _load()
    chat = tmp_path / ".gemini" / "tmp" / "renamed-provider" / "chats" / "session.jsonl"
    chat.parent.mkdir(parents=True)
    chat.write_text(json.dumps({"type": "user", "content": [{"text": "hello"}]}) + "\n")
    lifecycle = SimpleNamespace(HOME=tmp_path)

    rows = sources.generic_gemini_rows(lifecycle, days=None)

    assert [(row["source"], row["path"]) for row in rows] == [("gemini-tmp", chat)]


def test_unknown_gemini_user_prompt_schema_is_an_explicit_gap(tmp_path: Path):
    sources = _load()
    chat = tmp_path / ".gemini" / "tmp" / "provider" / "chats" / "session.jsonl"
    chat.parent.mkdir(parents=True)
    chat.write_text(
        json.dumps({"type": "human", "prompt": "A future Gemini prompt carrier."}) + "\n",
        encoding="utf-8",
    )
    lifecycle = _regular_lifecycle(sources, [{"source": "gemini-tmp", "path": chat}])
    key = sources.cursor_unit_key("gemini-tmp", chat)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "gemini-tmp", "path": chat}],
    )

    assert events == []
    assert result["unsupported"] == [key]
    assert key not in result["files"]


def test_gemini_tmp_agy_activates_its_own_fair_lane_without_stealing_gemini_share(tmp_path: Path):
    sources = _load()
    opencode = tmp_path / "opencode.db"
    opencode.touch()
    lifecycle = SimpleNamespace(
        OPENCODE_DB=opencode,
        AGY_CLI_CONVERSATIONS=tmp_path / "missing-agy",
    )
    rows = [
        {"source": "codex-sessions"},
        {"source": "claude-projects"},
        {"source": "gemini-tmp"},
        {"source": "gemini-tmp-agy"},
    ]

    assert sources.regular_lane("gemini-tmp") == "gemini"
    assert sources.regular_lane("gemini-tmp-agy") == "agy"
    active = sources.active_scan_lanes(lifecycle, rows)
    assert active == {"codex", "claude", "gemini", "opencode", "agy"}
    budgets = sources.fair_scan_budgets(5, rotation=0, active_lanes=active)
    assert {lane: budget.limit for lane, budget in budgets.items()} == {
        "codex": 1,
        "claude": 1,
        "gemini": 1,
        "opencode": 1,
        "agy": 1,
    }


def test_regular_sources_fail_closed_on_byte_event_and_discovery_caps(tmp_path: Path):
    sources = _load()
    oversized = tmp_path / "oversized.jsonl"
    oversized.write_text(json.dumps({"display": "x" * 2048}) + "\n", encoding="utf-8")
    byte_limits = sources.runtime_limits({"resource_limits": {"max_source_bytes_per_unit": 128}})
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "agy-cli-history", "path": oversized}],
    )

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        limits=byte_limits,
    )

    assert events == []
    assert "bounded ceiling" in " ".join(result["errors"])
    assert result["files"] == {}

    many = tmp_path / "many.jsonl"
    many.write_text(
        "".join(json.dumps({"display": f"ask {index}"}) + "\n" for index in range(3)),
        encoding="utf-8",
    )
    event_limits = sources.runtime_limits({"resource_limits": {"max_events_per_unit": 2}})
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "agy-cli-history", "path": many}],
    )
    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        limits=event_limits,
    )
    assert events == []
    assert "record count exceeds" in " ".join(result["errors"])

    paths = []
    for index in range(3):
        path = tmp_path / f"discover-{index}.jsonl"
        path.write_text(json.dumps({"display": f"ask {index}"}) + "\n", encoding="utf-8")
        paths.append(path)
    discovery_limits = sources.runtime_limits({"resource_limits": {"max_discovery_units": 2}})
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "agy-cli-history", "path": path} for path in paths],
    )
    rows = sources.regular_source_rows(lifecycle, None, limits=discovery_limits)
    assert len(rows) == 2
    assert rows.truncated_source == "agy-cli-history"


def test_work_unit_unbounded_mode_is_explicit_and_negative_values_never_bypass():
    sources = _load()

    with pytest.raises(ValueError, match="positive"):
        sources.fair_scan_budgets(0, rotation=0)
    with pytest.raises(ValueError, match="negative"):
        sources.fair_scan_budgets(-1, rotation=0, unbounded=True)

    budgets = sources.fair_scan_budgets(0, rotation=0, unbounded=True)
    assert all(budget.limit is None for budget in budgets.values())


def test_isolated_source_home_rejects_symlink_escape(tmp_path: Path, monkeypatch):
    sources = _load()
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text(json.dumps({"display": "private outside prompt"}) + "\n")
    linked = home / "linked.jsonl"
    linked.symlink_to(outside)
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "agy-cli-history", "path": linked}],
    )
    monkeypatch.setattr(sources, "SOURCE_HOME_OVERRIDE", home)

    rows = sources.regular_source_rows(lifecycle, None)

    assert rows == []
    assert rows.discovery_errors
    assert any(marker in rows.discovery_errors[0][1] for marker in ("symlink hop", "escapes isolated source home"))
