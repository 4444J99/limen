from __future__ import annotations

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
    assert sources.prompt_texts_for(lifecycle, "claude-projects", last_prompt) == []
    assert sources.prompt_texts_for(lifecycle, "claude-projects", queued) == []
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
            "payload": {"type": "user_message", "message": "one operator turn"},
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
            "payload": {"type": "user_message", "message": "inherited operator turn"},
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

    lifecycle.LOCAL_SOURCES = [("agy-cli-history", path, (path.name,)) for path in paths]
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    cursor_path = tmp_path / "cursor.json"
    ledger_paths = SimpleNamespace(cursor=cursor_path)

    _events, first = sources.scan_native_sources(ledger_paths, days=None, max_files=1)
    assert first["scope"] == "partial:all"
    assert first["pending_files"] == 2
    cursor_path.write_text(json.dumps(first), encoding="utf-8")

    _events, second = sources.scan_native_sources(ledger_paths, days=2, max_files=1)
    assert second["scope"] == "partial:all"
    assert second["effective_horizon_days"] is None
    assert second["pending_files"] == 1
    assert any("source-1.jsonl" in key for key in second["files"])
    cursor_path.write_text(json.dumps(second), encoding="utf-8")

    _events, third = sources.scan_native_sources(ledger_paths, days=2, max_files=1)
    assert third["scope"] == "all"
    assert third["all_baseline_complete"] is True
    assert (
        len([key for key in third["files"] if key.startswith(f"scan-v{sources.SCANNER_VERSION}:agy-cli-history:")]) == 3
    )


def test_unsupported_source_is_visible_and_blocks_all_scope(tmp_path: Path, monkeypatch):
    sources = _load()
    unsupported = tmp_path / "plan.md"
    unsupported.write_text("derived plan", encoding="utf-8")
    lifecycle = _regular_lifecycle(
        sources,
        [{"source": "claude-plans", "path": unsupported, "mtime": "2026-07-11"}],
    )
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)

    _events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=5,
    )

    assert cursor["scope"] == "partial:all"
    assert cursor["unsupported_source_count"] == 1
    assert cursor["adapter_gaps"] == ["claude-plans"]
    assert cursor["source_coverage"]["claude-plans"]["unsupported"] == 1
    assert cursor["source_families"]["claude-plans"]["unsupported"] == 1

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


def test_generic_gemini_discovery_is_not_tied_to_agy_directory_names(tmp_path: Path):
    sources = _load()
    chat = tmp_path / ".gemini" / "tmp" / "renamed-provider" / "chats" / "session.jsonl"
    chat.parent.mkdir(parents=True)
    chat.write_text(json.dumps({"type": "user", "content": [{"text": "hello"}]}) + "\n")
    lifecycle = SimpleNamespace(HOME=tmp_path)

    rows = sources.generic_gemini_rows(lifecycle, days=None)

    assert [(row["source"], row["path"]) for row in rows] == [("gemini-tmp", chat)]


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
    assert "escapes isolated source home" in rows.discovery_errors[0][1]
