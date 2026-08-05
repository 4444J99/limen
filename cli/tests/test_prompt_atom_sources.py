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


VALID_CODEX_PNG_DATA_URL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _codex_session_v2_fixture(module, tmp_path: Path, rows: list[dict]):
    sessions = tmp_path / ".codex" / "sessions"
    session_id = "019f-codex-session-v2"
    path = sessions / "2026" / "07" / "13" / f"rollout-{session_id}.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    lifecycle = module.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("codex-sessions", sessions, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path
    return lifecycle, path, session_id


def _codex_media_rows(session_id: str, *, image_url: str = VALID_CODEX_PNG_DATA_URL):
    message = "[Image #1] Assess this evidence."
    placeholder = "[Image #1]"
    return [
        {"type": "session_meta", "payload": {"id": session_id}},
        {
            "timestamp": "2026-07-13T12:00:00.001Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": message},
                    {"type": "input_image", "detail": "high", "image_url": image_url},
                ],
            },
        },
        {
            "timestamp": "2026-07-13T12:00:00.002Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": message,
                "images": [],
                "local_images": ["/private/tmp/codex-input-image.png"],
                "text_elements": [
                    {
                        "placeholder": placeholder,
                        "byte_range": {"start": 0, "end": len(placeholder.encode("utf-8"))},
                    }
                ],
            },
        },
    ]


def _claude_memory_alias_fixture(module, tmp_path: Path, *, absolute: bool = False):
    projects = tmp_path / ".claude" / "projects"
    target = projects / "project" / "memory" / "fixture.md"
    alias = projects / "project" / target.name
    target.parent.mkdir(parents=True)
    target.write_text("synthetic memory fixture", encoding="utf-8")
    alias.symlink_to(target if absolute else Path("memory") / target.name)
    lifecycle = module.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    lifecycle.HOME = tmp_path
    return lifecycle, projects, alias, target


def _claude_subagent_alias_fixture(module, tmp_path: Path):
    projects = tmp_path / ".claude" / "projects"
    target = projects / "project" / "target-session" / "subagents" / "agent.jsonl"
    alias = projects / "project" / "alias-session" / "subagents" / target.name
    target.parent.mkdir(parents=True)
    alias.parent.mkdir(parents=True)
    target.write_text(
        json.dumps(
            {
                "type": "user",
                "message": {"role": "user", "content": "delegated alias target"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    alias.symlink_to(target)
    lifecycle = module.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    lifecycle.HOME = tmp_path
    return lifecycle, projects, alias, target


def _scan_claude_rows(module, tmp_path: Path, rows: list[dict]):
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    transcript.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    lifecycle = module.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"
    lifecycle.HOME = tmp_path / "missing-home"
    events, result = module.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=module.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": transcript}],
    )
    return events, result, transcript


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


def test_codex_inline_png_media_binds_to_transport_and_stays_out_of_textual_atoms(tmp_path: Path):
    sources = _load()
    session_id = "019f-codex-session-v2"
    lifecycle, path, _session_id = _codex_session_v2_fixture(
        sources,
        tmp_path,
        _codex_media_rows(session_id),
    )
    key = sources.cursor_unit_key("codex-sessions", path)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert result["source_adapter_counts"] == {"codex-session-jsonl-v2": 1}
    receipt = result["adapted_unit_receipts"][key]
    assert receipt["contract_id"] == "codex-session-jsonl-v2"
    assert sources.source_contract_receipt_applies(
        receipt["contract_id"],
        "codex-sessions",
        str(path),
        signature=sources.file_signature(path),
    )
    media = [event for event in events if event["body_kind"] == "nontext_input"]
    assert len(media) == 1
    assert media[0]["provenance"] == "operator_typed"
    assert media[0]["authority"] == "operator"
    assert media[0]["text"].startswith("codex-input-image-v1:sha256=")
    assert VALID_CODEX_PNG_DATA_URL not in media[0]["text"]

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
    media_occurrence = next(
        occurrence for occurrence in snapshot["occurrences"] if occurrence["body_kind"] == "nontext_input"
    )
    assert media_occurrence["excluded_reason"] == "nontext_prompt_input"
    assert media_occurrence["atom_ids"] == []


@pytest.mark.parametrize(
    "mutation",
    [
        "unbound",
        "ambiguous",
        "bad-base64",
        "bad-detail",
        "bad-placeholder-range",
        "noncanonical-local-path",
    ],
)
def test_codex_media_adapter_fails_closed_on_unbound_or_malformed_inputs(tmp_path: Path, mutation: str):
    sources = _load()
    session_id = "019f-codex-session-v2"
    rows = _codex_media_rows(session_id)
    if mutation == "unbound":
        rows.pop()
    elif mutation == "ambiguous":
        rows.append(dict(rows[-1]))
    elif mutation == "bad-base64":
        rows[1]["payload"]["content"][1]["image_url"] = "data:image/png;base64,not-valid!"
    elif mutation == "bad-detail":
        rows[1]["payload"]["content"][1]["detail"] = "auto"
    elif mutation == "bad-placeholder-range":
        rows[2]["payload"]["text_elements"][0]["byte_range"]["end"] += 1
    elif mutation == "noncanonical-local-path":
        rows[2]["payload"]["local_images"] = ["../image.png"]
    lifecycle, path, _session_id = _codex_session_v2_fixture(sources, tmp_path, rows)
    key = sources.cursor_unit_key("codex-sessions", path)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert key not in result["files"]
    assert key not in result["adapted_unit_receipts"]
    assert result["errors"] or result["unsupported"] == [key]


def test_codex_compacted_history_is_preserved_as_derived_context(tmp_path: Path):
    sources = _load()
    session_id = "019f-codex-session-v2"
    rows = [
        {"type": "session_meta", "payload": {"id": session_id}},
        {
            "timestamp": "2026-07-13T12:00:00Z",
            "type": "compacted",
            "payload": {
                "first_window_id": "11111111-1111-1111-1111-111111111111",
                "message": "",
                "previous_window_id": "22222222-2222-2222-2222-222222222222",
                "replacement_history": [
                    {
                        "type": "message",
                        "role": "developer",
                        "content": [{"type": "input_text", "text": "provider context"}],
                    },
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "preserved historical operator turn"},
                            {
                                "type": "input_image",
                                "detail": "high",
                                "image_url": VALID_CODEX_PNG_DATA_URL,
                            },
                        ],
                    },
                    {"type": "compaction", "id": "cmp-1", "encrypted_content": "opaque"},
                ],
                "window_id": "33333333-3333-3333-3333-333333333333",
                "window_number": 1,
            },
        },
    ]
    lifecycle, path, _session_id = _codex_session_v2_fixture(sources, tmp_path, rows)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert [event["body_kind"] for event in events] == ["session_context", "nontext_context"]
    assert {event["provenance"] for event in events} == {"continuation_summary"}
    assert {event["authority"] for event in events} == {"derived"}
    assert not [event for event in events if event["text"] == "provider context"]
    snapshot = sources.update_ledger(
        sources.LedgerPaths.for_root(tmp_path / "ledger-compacted"),
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


@pytest.mark.parametrize(
    "mutation",
    ["nonempty-message", "unknown-role", "missing-compaction", "unknown-item", "too-many-items"],
)
def test_codex_compacted_history_unknown_shapes_remain_explicit_gaps(tmp_path: Path, mutation: str):
    sources = _load()
    session_id = "019f-codex-session-v2"
    history = [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "turn"}]},
        {"type": "compaction", "encrypted_content": "opaque"},
    ]
    payload = {"message": "", "replacement_history": history}
    if mutation == "nonempty-message":
        payload["message"] = "unexpected summary"
    elif mutation == "unknown-role":
        history[0]["role"] = "assistant"
    elif mutation == "missing-compaction":
        history.pop()
    elif mutation == "unknown-item":
        history.append({"type": "future_compaction", "prompt": "must not disappear"})
    elif mutation == "too-many-items":
        limit = sources.SOURCE_ADAPTER_RULES["codex-session-jsonl-v2"]["max_compacted_history_items"]
        payload["replacement_history"] = [history[0]] * (limit + 1)
    rows = [
        {"type": "session_meta", "payload": {"id": session_id}},
        {"timestamp": "2026-07-13T12:00:00Z", "type": "compacted", "payload": payload},
    ]
    lifecycle, path, _session_id = _codex_session_v2_fixture(sources, tmp_path, rows)
    key = sources.cursor_unit_key("codex-sessions", path)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["errors"] or result["unsupported"] == [key]
    assert key not in result["files"]
    assert key not in result["adapted_unit_receipts"]


def test_codex_session_resume_metadata_uses_the_one_filename_bound_identity(tmp_path: Path):
    sources = _load()
    session_id = "019f-codex-session-v2"
    rows = [
        {"type": "session_meta", "payload": {"id": "019f-prior-session"}},
        {"type": "session_meta", "payload": {"id": session_id}},
        {
            "timestamp": "2026-07-13T12:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "resume safely"}],
            },
        },
    ]
    lifecycle, path, _session_id = _codex_session_v2_fixture(sources, tmp_path, rows)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert {event["session_ref"] for event in events} == {f"codex:{session_id}"}
    assert sources.cursor_unit_key("codex-sessions", path) in result["adapted_unit_receipts"]


def test_codex_session_ambiguous_identity_without_filename_binding_fails_closed(tmp_path: Path):
    sources = _load()
    rows = [
        {"type": "session_meta", "payload": {"id": "019f-prior-session"}},
        {"type": "session_meta", "payload": {"id": "019f-other-session"}},
    ]
    lifecycle, path, _session_id = _codex_session_v2_fixture(sources, tmp_path, rows)
    key = sources.cursor_unit_key("codex-sessions", path)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert "identity is ambiguous" in " ".join(result["errors"])
    assert key not in result["files"]
    assert key not in result["adapted_unit_receipts"]


@pytest.mark.parametrize("ceiling", ["records", "record_bytes", "file_bytes"])
def test_codex_session_streaming_adapter_enforces_independent_hard_bounds(
    tmp_path: Path,
    monkeypatch,
    ceiling: str,
):
    sources = _load()
    session_id = "019f-codex-session-v2"
    rows = [
        {"type": "session_meta", "payload": {"id": session_id}},
        {
            "timestamp": "2026-07-13T12:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "bounded turn"}],
            },
        },
    ]
    lifecycle, path, _session_id = _codex_session_v2_fixture(sources, tmp_path, rows)
    rule = sources.SOURCE_ADAPTER_RULES["codex-session-jsonl-v2"]
    if ceiling == "records":
        monkeypatch.setitem(rule, "max_records", 1)
    elif ceiling == "record_bytes":
        monkeypatch.setitem(rule, "max_record_bytes", 16)
    else:
        monkeypatch.setitem(rule, "max_probe_bytes", max(1, path.stat().st_size - 1))
    key = sources.cursor_unit_key("codex-sessions", path)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert "bounded" in " ".join(result["errors"])
    assert key not in result["files"]
    assert key not in result["adapted_unit_receipts"]


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


def _opencode_task_fixture(path: Path, variants: tuple[str, ...]) -> list[str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE session (
            id TEXT PRIMARY KEY,
            parent_id TEXT,
            agent TEXT,
            model TEXT,
            time_created INTEGER,
            time_updated INTEGER
        );
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        """
    )
    prompts: list[str] = []
    for index, variant in enumerate(variants):
        parent_id = f"parent-{index}"
        child_id = f"child-{index}"
        model_id = f"model-{index}"
        provider_id = f"provider-{index}"
        agent = f"agent-{index}"
        prompt = f"synthetic delegated prompt {index}"
        prompts.append(prompt)
        connection.execute(
            "INSERT INTO session VALUES (?, NULL, ?, ?, ?, ?)",
            (
                parent_id,
                "build",
                json.dumps({"id": "parent-model", "providerID": "parent-provider", "variant": "default"}),
                index * 10 + 1,
                index * 10 + 1,
            ),
        )
        connection.execute(
            "INSERT INTO session VALUES (?, ?, ?, ?, ?, ?)",
            (
                child_id,
                parent_id,
                agent,
                json.dumps({"id": model_id, "providerID": provider_id, "variant": "default"}),
                index * 10 + 2,
                index * 10 + 2,
            ),
        )
        message_data = {
            "agent": "build",
            "cost": 0,
            "mode": "build",
            "modelID": "parent-model",
            "parentID": f"previous-{index}",
            "path": {"cwd": "/tmp", "root": "/tmp"},
            "providerID": "parent-provider",
            "role": "assistant",
            "time": {"created": index * 10 + 3},
            "tokens": {"input": 0, "output": 0, "reasoning": 0},
        }
        metadata = {
            "model": {"modelID": model_id, "providerID": provider_id},
            "parentSessionId": parent_id,
            "sessionId": child_id,
        }
        input_data = {"description": f"task {index}", "prompt": prompt, "subagent_type": agent}
        state: dict[str, object]
        if variant == "completed":
            message_data["finish"] = "tool-calls"
            metadata["truncated"] = False
            state = {
                "input": input_data,
                "metadata": metadata,
                "output": f"synthetic output {index}",
                "status": "completed",
                "time": {"start": index * 10 + 4, "end": index * 10 + 5},
                "title": f"task {index}",
            }
        else:
            if variant == "command":
                input_data["command"] = "synthetic-command"
                metadata.update({"outputPath": f"/tmp/output-{index}", "truncated": True})
            state = {
                "input": input_data,
                "metadata": metadata,
                "status": "running",
                "time": {"start": index * 10 + 4},
                "title": f"task {index}",
            }
        message_id = f"message-{index}"
        connection.execute(
            "INSERT INTO message VALUES (?, ?, ?, ?)",
            (message_id, parent_id, index * 10 + 3, json.dumps(message_data)),
        )
        connection.execute(
            "INSERT INTO part VALUES (?, ?, ?, ?, ?)",
            (
                f"part-{index}",
                message_id,
                parent_id,
                index * 10 + 4,
                json.dumps({"callID": f"call-{index}", "state": state, "tool": "task", "type": "tool"}),
            ),
        )
    connection.commit()
    connection.close()
    return prompts


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


def test_opencode_task_tool_adapter_covers_exact_live_variants_and_is_idempotent(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "home" / ".local" / "share" / "opencode" / "opencode.db"
    prompts = _opencode_task_fixture(database, ("running", "completed", "command"))
    lifecycle.OPENCODE_DB = database

    first_events, first = sources.scan_opencode(
        lifecycle,
        {"files": {}, "adapted_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=6),
    )

    assert [event["text"] for event in first_events] == prompts
    assert all(event["body_kind"] == "delegated_task_frame" for event in first_events)
    assert all(event["provenance"] == "delegated_task_frame" for event in first_events)
    assert all(event["authority"] == "derived" for event in first_events)
    assert all(event["source_segment"] == "state.input.prompt" for event in first_events)
    assert len(first["adapted_unit_receipts"]) == 3
    assert first["coverage"]["opencode-db"]["adapted"] == 3
    assert all(
        receipt["contract_id"] == "opencode-assistant-task-v1" for receipt in first["adapted_unit_receipts"].values()
    )
    assert sources.source_contract_receipt_applies(
        "opencode-assistant-task-v1",
        "opencode-db",
        f"{database}#session:{'a' * 24}",
        signature=next(iter(first["adapted_unit_receipts"].values()))["signature"],
    )

    second_events, second = sources.scan_opencode(
        lifecycle,
        {
            "files": first["processed"],
            "adapted_unit_receipts": first["adapted_unit_receipts"],
        },
        days=None,
        budget=sources.ScanBudget(limit=6),
    )

    assert second_events == []
    assert second["adapted_unit_receipts"] == first["adapted_unit_receipts"]
    assert second["attempted_files"] == 0
    assert second["errors"] == []


def test_opencode_task_tool_receipt_projects_into_native_cursor(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "home" / ".local" / "share" / "opencode" / "opencode.db"
    prompts = _opencode_task_fixture(database, ("running",))
    lifecycle.LOCAL_SOURCES = []
    lifecycle.HOME = tmp_path / "home"
    lifecycle.OPENCODE_DB = database
    lifecycle.AGY_CLI_CONVERSATIONS = lifecycle.HOME / ".gemini" / "antigravity-cli" / "conversations"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)

    events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=2,
    )

    assert [event["text"] for event in events] == prompts
    assert cursor["scope"] == "all"
    assert cursor["source_adapter_counts"]["opencode-assistant-task-v1"] == 1
    assert cursor["source_coverage"]["opencode-db"]["adapted"] == 1
    assert len(cursor["adapted_unit_receipts"]) == 1
    assert cursor["adapter_gaps"] == []
    assert sources.validate_source_adapter_cursor(cursor) == []


@pytest.mark.parametrize("failure", ["extra-state-field", "wrong-child-parent"])
def test_opencode_task_tool_adapter_fails_closed_on_structural_drift(tmp_path: Path, failure: str):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "home" / ".local" / "share" / "opencode" / "opencode.db"
    _opencode_task_fixture(database, ("running",))
    connection = sqlite3.connect(database)
    if failure == "extra-state-field":
        raw = connection.execute("SELECT data FROM part WHERE id='part-0'").fetchone()[0]
        part_data = json.loads(raw)
        part_data["state"]["future"] = True
        connection.execute("UPDATE part SET data=? WHERE id='part-0'", (json.dumps(part_data),))
    else:
        connection.execute("UPDATE session SET parent_id='wrong-parent' WHERE id='child-0'")
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database

    events, result = sources.scan_opencode(
        lifecycle,
        {"files": {}, "adapted_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
    )

    assert events == []
    assert result["adapted_unit_receipts"] == {}
    assert len(result["processed"]) == 1
    assert len(result["errors"]) == 1
    assert "OpenCode task-tool" in result["errors"][0]


def test_opencode_exact_user_summary_is_excluded_from_prompt_byte_cap_and_digest(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        INSERT INTO session VALUES ('summary', 1, 1);
        """
    )
    summary = {
        "diffs": [
            {
                "additions": 1,
                "deletions": 0,
                "file": "synthetic.txt",
                "patch": "x" * 10_000,
                "status": "added",
            }
        ]
    }
    connection.execute(
        "INSERT INTO message VALUES ('message-summary', 'summary', 1, ?)",
        (json.dumps({"role": "user", "summary": summary}),),
    )
    connection.execute(
        "INSERT INTO part VALUES ('part-summary', 'message-summary', 'summary', 1, ?)",
        (json.dumps({"type": "text", "text": "bounded user prompt"}),),
    )
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database
    limits = sources.ResourceLimits(
        max_source_bytes_per_unit=512,
        max_events_per_unit=10,
        max_discovery_units=10,
        max_classifier_input_bytes=1024,
        max_classifier_output_bytes=1024,
        max_classifier_stderr_bytes=1024,
        max_classifier_occurrences=10,
    )

    first_events, first = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        limits=limits,
    )
    first_signature = next(iter(first["processed"].values()))
    assert [event["text"] for event in first_events] == ["bounded user prompt"]
    assert first["errors"] == []
    assert database.stat().st_size > limits.max_source_bytes_per_unit

    connection = sqlite3.connect(database)
    summary["diffs"][0]["patch"] = "y" * 10_000
    connection.execute(
        "UPDATE message SET data=? WHERE id='message-summary'",
        (json.dumps({"role": "user", "summary": summary}),),
    )
    connection.commit()
    connection.close()

    second_events, second = sources.scan_opencode(
        lifecycle,
        {"files": first["processed"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
        limits=limits,
    )
    second_signature = next(iter(second["processed"].values()))
    assert second_events == []
    assert second["attempted_files"] == 0
    assert second_signature["content_sha256"] == first_signature["content_sha256"]


def test_opencode_nonuser_summary_marker_remains_in_content_digest(tmp_path: Path):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        INSERT INTO session VALUES ('summary-marker', 1, 1);
        """
    )
    connection.execute(
        "INSERT INTO message VALUES ('message-summary', 'summary-marker', 1, ?)",
        (json.dumps({"role": "assistant", "summary": True}),),
    )
    connection.commit()
    connection.close()
    lifecycle.OPENCODE_DB = database

    _first_events, first = sources.scan_opencode(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    first_signature = next(iter(first["processed"].values()))
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE message SET data=? WHERE id='message-summary'",
        (json.dumps({"role": "assistant", "summary": False}),),
    )
    connection.commit()
    connection.close()

    second_events, second = sources.scan_opencode(
        lifecycle,
        {"files": first["processed"]},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    second_signature = next(iter(second["processed"].values()))

    assert second_events == []
    assert second["errors"] == []
    assert second["attempted_files"] == 1
    assert second_signature["content_sha256"] != first_signature["content_sha256"]


@pytest.mark.parametrize("failure", ["summary-extra-field", "diff-wrong-type"])
def test_opencode_user_summary_exclusion_fails_closed_on_schema_drift(tmp_path: Path, failure: str):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    database = tmp_path / "opencode.db"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE session (id TEXT PRIMARY KEY, time_created INTEGER, time_updated INTEGER);
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER, data TEXT);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);
        INSERT INTO session VALUES ('summary', 1, 1);
        """
    )
    diff = {"additions": 1, "deletions": 0, "file": "x", "patch": "y", "status": "added"}
    summary: dict[str, object] = {"diffs": [diff]}
    if failure == "summary-extra-field":
        summary["future"] = True
    else:
        diff["additions"] = "1"
    connection.execute(
        "INSERT INTO message VALUES ('message-summary', 'summary', 1, ?)",
        (json.dumps({"role": "user", "summary": summary}),),
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
    assert "OpenCode summary" in result["errors"][0]


def test_source_contract_reset_drops_stale_unresolved_obligations(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle = _regular_lifecycle(sources, [])
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    stale_contract = {**sources.source_adapter_contract(), "digest": "0" * 64}
    stale_key = "scan-v2:opencode-db:stale-unit"
    cursor_path = tmp_path / "cursor.json"
    cursor_path.write_text(
        json.dumps(
            {
                "version": 1,
                "scanner_version": 2,
                "scope": "partial:all",
                "target_scope": "all",
                "all_baseline_complete": False,
                "source_adapter_contract": stale_contract,
                "files": {},
                "unsupported_units": {},
                "unresolved_units": [stale_key],
                "excluded_unit_receipts": {},
                "adapted_unit_receipts": {},
                "source_families": {
                    "opencode-db": {
                        "discovered": 1,
                        "converged": 0,
                        "adapted": 0,
                        "excluded": 0,
                        "pending": 0,
                        "errors": 1,
                        "unsupported": 0,
                    }
                },
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
    assert cursor["unresolved_units"] == []
    assert cursor["source_errors"] == []
    assert "opencode-db" not in cursor["adapter_gaps"]
    assert cursor["scope"] == "all"
    assert sources.validate_source_adapter_cursor(cursor) == []


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
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 14, 3, ?, NULL, NULL, NULL, NULL)",
        (prompt,),
    )
    connection.commit()
    connection.close()


def _agy_lifecycle(sources, root: Path):
    lifecycle = sources.load_lifecycle_module()
    lifecycle.AGY_CLI_CONVERSATIONS = root
    segments = (".gemini", "antigravity-cli", "conversations")
    if tuple(root.parts[-len(segments) :]) == segments:
        lifecycle.HOME = root.parents[len(segments) - 1]
    return lifecycle


def _agy_limits(sources, *, source_bytes: int = 32 * 1024 * 1024, discovery: int = 100_000):
    baseline = sources.runtime_limits({})
    return sources.ResourceLimits(
        max_source_bytes_per_unit=source_bytes,
        max_events_per_unit=baseline.max_events_per_unit,
        max_discovery_units=discovery,
        max_classifier_input_bytes=baseline.max_classifier_input_bytes,
        max_classifier_output_bytes=baseline.max_classifier_output_bytes,
        max_classifier_stderr_bytes=baseline.max_classifier_stderr_bytes,
        max_classifier_occurrences=baseline.max_classifier_occurrences,
    )


def test_agy_exact_short_prompt_is_provider_neutral_and_receipted(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "short.db"
    _agy_database(database, "ship it")

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    key = sources.cursor_unit_key("agy-cli-conversations", database)
    assert [(event["text"], event["provenance"], event["authority"]) for event in events] == [
        ("ship it", "unknown_user_input", "unknown")
    ]
    assert events[0]["source_segment"] == "step_payload"
    assert result["adapted_unit_receipts"][key]["contract_id"] == "agy-conversation-v1"
    assert result["excluded_unit_receipts"] == {}


def test_agy_short_binary_prompt_segment_is_not_lost_to_length_heuristics(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "binary-short.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload BLOB, metadata BLOB, "
        "task_details BLOB, error_details BLOB, render_info BLOB)"
    )
    # Field number zero makes this non-wire-parseable, so it exercises the legacy
    # segment contract; exact wire payloads belong to agy-step-payload-proto-v1.
    connection.execute(
        "INSERT INTO steps VALUES (1, 14, 3, ?, NULL, NULL, NULL, NULL)",
        (sqlite3.Binary(b"\x00go"),),
    )
    connection.commit()
    connection.close()

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert [event["text"] for event in events] == ["go"]
    assert result["errors"] == []


def test_agy_ambiguous_prompt_carriers_fail_closed_without_leaking_text(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "ambiguous.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    secrets = ("synthetic first private prompt", "synthetic second private prompt")
    connection.execute(
        "INSERT INTO steps VALUES (1, 14, 3, ?, ?, NULL, NULL, NULL)",
        secrets,
    )
    connection.commit()
    connection.close()

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["processed"] == {}
    assert result["adapted_unit_receipts"] == {}
    assert "multiple grounded source segments" in result["errors"][0]
    redacted_result = json.dumps(result, sort_keys=True)
    assert all(secret not in redacted_result for secret in secrets)


def test_agy_structural_nonprompt_database_has_typed_idempotent_exclusion(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "nonprompt.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 15, 3, ?, NULL, NULL, NULL, NULL)",
        (json.dumps({"outcome": "synthetic tool result"}),),
    )
    connection.commit()
    connection.close()
    lifecycle = _agy_lifecycle(sources, root)

    first_events, first = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    second_events, second = sources.scan_agy_conversations(
        lifecycle,
        {
            "files": first["processed"],
            "adapted_unit_receipts": first["adapted_unit_receipts"],
            "excluded_unit_receipts": first["excluded_unit_receipts"],
        },
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    key = sources.cursor_unit_key("agy-cli-conversations", database)
    assert first_events == second_events == []
    assert first["excluded_unit_receipts"][key]["contract_id"] == "agy-conversation-nonprompt-v1"
    assert second["excluded_unit_receipts"] == first["excluded_unit_receipts"]
    assert second["attempted_files"] == 0
    assert second["coverage"]["agy-cli-conversations"]["excluded"] == 1


def test_agy_typed_nonprompt_exclusion_validates_at_exact_all_scope(tmp_path: Path, monkeypatch):
    sources = _load()
    home = tmp_path / "home"
    root = home / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "nonprompt.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute("INSERT INTO steps VALUES (1, 15, 3, NULL, NULL, NULL, NULL, NULL)")
    connection.commit()
    connection.close()
    lifecycle = _agy_lifecycle(sources, root)
    lifecycle.HOME = home
    lifecycle.LOCAL_SOURCES = []
    lifecycle.OPENCODE_DB = home / ".local" / "share" / "opencode" / "missing.db"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")

    events, proposal = sources.scan_native_sources(paths, days=None, max_files=1)
    sources.update_ledger(paths, events=events, cursor=proposal)
    cursor = sources.load_json_strict(paths.cursor)[0]

    key = sources.cursor_unit_key("agy-cli-conversations", database)
    assert events == []
    assert cursor["scope"] == cursor["target_scope"] == "all"
    assert cursor["files"] == {}
    assert cursor["excluded_unit_receipts"][key]["contract_id"] == "agy-conversation-nonprompt-v1"
    assert sources.check_ledger(paths, require_scope="all") == []


def test_agy_exact_all_live_custody_rejects_root_symlink_swap(tmp_path: Path, monkeypatch):
    sources = _load()
    home = tmp_path / "home"
    root = home / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "nonprompt.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute("INSERT INTO steps VALUES (1, 15, 3, NULL, NULL, NULL, NULL, NULL)")
    connection.commit()
    connection.close()
    lifecycle = _agy_lifecycle(sources, root)
    lifecycle.HOME = home
    lifecycle.LOCAL_SOURCES = []
    lifecycle.OPENCODE_DB = home / ".local" / "share" / "opencode" / "missing.db"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(tmp_path / "ledger")

    events, proposal = sources.scan_native_sources(paths, days=None, max_files=1)
    assert events == []
    assert proposal["scope"] == "all"

    custody = root.with_name("conversations-custody")
    root.rename(custody)
    root.symlink_to(custody, target_is_directory=True)

    core = sys.modules["limen.prompt_corpus"]
    errors = core.validate_live_source_custody(proposal)
    assert "agy-cli-conversations: live conversation root changed to a symlink" in errors


def test_agy_root_ancestor_symlink_fails_closed(tmp_path: Path):
    sources = _load()
    home = tmp_path / "home"
    gemini = home / ".gemini"
    gemini.mkdir(parents=True)
    outside_cli = tmp_path / "outside-antigravity-cli"
    outside_root = outside_cli / "conversations"
    outside_root.mkdir(parents=True)
    _agy_database(outside_root / "escaped.db", "synthetic escaped prompt")
    (gemini / "antigravity-cli").symlink_to(outside_cli, target_is_directory=True)
    root = gemini / "antigravity-cli" / "conversations"
    lifecycle = sources.load_lifecycle_module()
    lifecycle.HOME = home
    lifecycle.AGY_CLI_CONVERSATIONS = root

    events, result = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["adapted_unit_receipts"] == {}
    assert "conversation root contains a symlink hop" in result["errors"][0]


@pytest.mark.parametrize("failure", ["noncanonical-absent", "broken-ancestor-symlink"])
def test_agy_absent_root_only_closes_cleanly_for_canonical_direct_custody(tmp_path: Path, failure: str):
    sources = _load()
    home = tmp_path / "home"
    home.mkdir()
    if failure == "noncanonical-absent":
        root = home / "missing-conversations"
    else:
        gemini = home / ".gemini"
        gemini.mkdir()
        (gemini / "antigravity-cli").symlink_to(tmp_path / "missing-target", target_is_directory=True)
        root = gemini / "antigravity-cli" / "conversations"
    lifecycle = sources.load_lifecycle_module()
    lifecycle.HOME = home
    lifecycle.AGY_CLI_CONVERSATIONS = root

    events, result = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["errors"]
    expected = {
        "noncanonical-absent": "does not match its canonical HOME-relative role",
        "broken-ancestor-symlink": "contains a symlink hop",
    }
    assert expected[failure] in result["errors"][0]


def test_agy_exact_all_live_custody_rejects_root_ancestor_symlink_swap(tmp_path: Path, monkeypatch):
    sources = _load()
    home = tmp_path / "home"
    cli_root = home / ".gemini" / "antigravity-cli"
    root = cli_root / "conversations"
    root.mkdir(parents=True)
    database = root / "nonprompt.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute("INSERT INTO steps VALUES (1, 15, 3, NULL, NULL, NULL, NULL, NULL)")
    connection.commit()
    connection.close()
    lifecycle = _agy_lifecycle(sources, root)
    lifecycle.LOCAL_SOURCES = []
    lifecycle.OPENCODE_DB = home / ".local" / "share" / "opencode" / "missing.db"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)

    events, proposal = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=1,
    )
    assert events == []
    assert proposal["scope"] == "all"

    custody = tmp_path / "antigravity-cli-custody"
    cli_root.rename(custody)
    cli_root.symlink_to(custody, target_is_directory=True)

    core = sys.modules["limen.prompt_corpus"]
    errors = core.validate_live_source_custody(proposal)
    assert "agy-cli-conversations: live conversation root containment changed after the sealed scan" in errors


@pytest.mark.parametrize(
    "failure",
    ["missing-status", "duplicate-index", "unknown-column", "view", "generated-column"],
)
def test_agy_malformed_step_envelopes_fail_closed(tmp_path: Path, failure: str):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / f"{failure}.db"
    connection = sqlite3.connect(database)
    if failure == "missing-status":
        connection.execute(
            "CREATE TABLE steps (idx INTEGER, step_type INTEGER, step_payload TEXT, metadata TEXT, "
            "task_details TEXT, error_details TEXT, render_info TEXT)"
        )
        connection.execute("INSERT INTO steps VALUES (1, 14, 'prompt', NULL, NULL, NULL, NULL)")
    elif failure == "duplicate-index":
        connection.execute(
            "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
            "task_details TEXT, error_details TEXT, render_info TEXT)"
        )
        connection.executemany(
            "INSERT INTO steps VALUES (1, 14, 3, ?, NULL, NULL, NULL, NULL)",
            [("first",), ("second",)],
        )
    elif failure == "unknown-column":
        connection.execute(
            "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
            "task_details TEXT, error_details TEXT, render_info TEXT, future_prompt_carrier TEXT)"
        )
        connection.execute("INSERT INTO steps VALUES (1, 15, 3, NULL, NULL, NULL, NULL, NULL, 'hidden prompt')")
    elif failure == "view":
        connection.execute(
            "CREATE TABLE backing_steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, "
            "metadata TEXT, task_details TEXT, error_details TEXT, render_info TEXT)"
        )
        connection.execute("INSERT INTO backing_steps VALUES (1, 14, 3, 'hidden prompt', NULL, NULL, NULL, NULL)")
        connection.execute("CREATE VIEW steps AS SELECT * FROM backing_steps")
    else:
        connection.execute(
            "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
            "task_details TEXT, error_details TEXT, "
            "render_info TEXT GENERATED ALWAYS AS (NULL) VIRTUAL)"
        )
        connection.execute(
            "INSERT INTO steps (idx, step_type, status, step_payload) VALUES (1, 14, 3, 'hidden prompt')"
        )
    connection.commit()
    connection.close()

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["processed"] == {}
    assert len(result["errors"]) == 1
    expected = {
        "missing-status": "missing required columns",
        "duplicate-index": "duplicate idx",
        "unknown-column": "unsupported columns",
        "view": "must be a concrete table",
        "generated-column": "hidden or generated columns",
    }
    assert expected[failure] in result["errors"][0]


def test_agy_invalid_utf8_does_not_join_distinct_prompt_segments(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "invalid-utf8.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload BLOB, metadata BLOB, "
        "task_details BLOB, error_details BLOB, render_info BLOB)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 14, 3, ?, NULL, NULL, NULL, NULL)",
        (sqlite3.Binary(b"first\xffsecond"),),
    )
    connection.commit()
    connection.close()

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["adapted_unit_receipts"] == {}
    assert "multiple grounded source segments" in result["errors"][0]
    assert "firstsecond" not in json.dumps(result, sort_keys=True)


@pytest.mark.parametrize("step_type", [14, 99], ids=("prompt-step", "nonprompt-step"))
def test_agy_duplicate_json_keys_reject_adaptation_and_exclusion(tmp_path: Path, step_type: int):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / f"duplicate-json-{step_type}.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    secret_values = ("synthetic first value", "synthetic second value")
    duplicate_json = f'{{"prompt":"{secret_values[0]}","prompt":"{secret_values[1]}"}}'
    connection.execute(
        "INSERT INTO steps VALUES (1, ?, 3, ?, NULL, NULL, NULL, NULL)",
        (step_type, duplicate_json),
    )
    connection.commit()
    connection.close()

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["adapted_unit_receipts"] == {}
    assert result["excluded_unit_receipts"] == {}
    assert "duplicate JSON object keys are ambiguous" in result["errors"][0]
    redacted = json.dumps(result, sort_keys=True)
    assert all(value not in redacted for value in secret_values)


@pytest.mark.parametrize("step_type", [14, 99], ids=("prompt-step", "nonprompt-step"))
def test_agy_deeply_nested_json_is_a_source_local_error(tmp_path: Path, step_type: int):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / f"deep-json-{step_type}.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    nested = "[" * 10_000 + '"synthetic nested value"' + "]" * 10_000
    connection.execute(
        "INSERT INTO steps VALUES (1, ?, 3, ?, NULL, NULL, NULL, NULL)",
        (step_type, nested),
    )
    connection.commit()
    connection.close()

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["adapted_unit_receipts"] == {}
    assert result["excluded_unit_receipts"] == {}
    assert "JSON nesting exceeds the bounded parser limit" in result["errors"][0]


@pytest.mark.parametrize("step_type", [14, 99], ids=("prompt-step", "nonprompt-step"))
@pytest.mark.parametrize(
    "payload",
    ['{"outcome":"synthetic"', '["synthetic"', '"synthetic'],
    ids=("object", "array", "string"),
)
def test_agy_malformed_json_looking_carrier_fails_closed(
    tmp_path: Path,
    step_type: int,
    payload: str,
):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / f"malformed-json-{step_type}.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, ?, 3, ?, NULL, NULL, NULL, NULL)",
        (step_type, payload),
    )
    connection.commit()
    connection.close()

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["adapted_unit_receipts"] == {}
    assert result["excluded_unit_receipts"] == {}
    assert "malformed or truncated JSON-looking carrier" in result["errors"][0]


def test_agy_json_depth_counter_ignores_brackets_inside_prompt_strings(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    prompt = "[" * 1_000 + "synthetic bracket prompt"
    _agy_database(root / "quoted-brackets.db", json.dumps({"prompt": prompt}))

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert [event["text"] for event in events] == [prompt]
    assert result["errors"] == []


@pytest.mark.parametrize(
    "marker",
    ["prompt: ship it", "INSTRUCTIONS = ship it", "role:operator content:ship it", "type:operator ship it"],
)
def test_agy_plain_prompt_markers_reject_typed_nonprompt_exclusion(tmp_path: Path, marker: str):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "plain-marker.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 99, 3, ?, NULL, NULL, NULL, NULL)",
        (marker,),
    )
    connection.commit()
    connection.close()

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["excluded_unit_receipts"] == {}
    assert "explicit prompt adapter" in result["errors"][0]


def test_agy_nested_database_path_role_fails_closed(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    nested = root / "nested"
    nested.mkdir(parents=True)
    _agy_database(nested / "conversation.db", "synthetic nested prompt")

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["adapted_unit_receipts"] == {}
    assert result["excluded_unit_receipts"] == {}
    assert result["attempted_files"] == 0
    assert "unsupported database path role" in result["errors"][0]


@pytest.mark.parametrize("leaf_kind", ["directory", "fifo"])
def test_agy_nonregular_database_leaf_fails_before_sqlite_open(tmp_path: Path, leaf_kind: str):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    leaf = root / f"{leaf_kind}.db"
    if leaf_kind == "directory":
        leaf.mkdir()
    else:
        os.mkfifo(leaf)

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["adapted_unit_receipts"] == {}
    assert result["excluded_unit_receipts"] == {}
    assert result["attempted_files"] == 0
    assert "database leaf is not a regular file" in result["errors"][0]


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_agy_nonregular_sqlite_sidecar_fails_before_sqlite_open(tmp_path: Path, suffix: str):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "conversation.db"
    _agy_database(database, "synthetic direct prompt")
    os.mkfifo(Path(f"{database}{suffix}"))

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert events == []
    assert result["adapted_unit_receipts"] == {}
    assert result["attempted_files"] == 0
    assert "SQLite sidecar is not a regular file" in result["errors"][0]


@pytest.mark.parametrize(
    ("filename", "sibling_name"),
    [
        ("question?mode=ro&x=.db", "question"),
        ("hash#fragment.db", "hash"),
        ("percent%25.db", "percent%.db"),
    ],
    ids=("question", "fragment", "percent"),
)
def test_agy_sqlite_uri_escapes_reserved_filename_characters(
    tmp_path: Path,
    filename: str,
    sibling_name: str,
):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    candidate = root / filename
    sibling = root / sibling_name
    _agy_database(candidate, "correct reserved-path prompt")
    _agy_database(sibling, "wrong sibling prompt")
    old = time.time() - 10 * 86400
    os.utime(sibling, (old, old))

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=1,
        budget=sources.ScanBudget(limit=1),
    )

    assert [event["text"] for event in events] == ["correct reserved-path prompt"]
    assert result["errors"] == []


@pytest.mark.parametrize("failure", ["nested-path", "symlink-wal"])
def test_agy_pre_custody_failure_returns_valid_partial_all_cursor(
    tmp_path: Path,
    monkeypatch,
    failure: str,
):
    sources = _load()
    home = tmp_path / "home"
    root = home / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    if failure == "nested-path":
        nested = root / "nested"
        nested.mkdir()
        _agy_database(nested / "conversation.db", "synthetic nested prompt")
    else:
        database = root / "conversation.db"
        _agy_database(database, "synthetic direct prompt")
        outside = tmp_path / "outside-wal"
        outside.write_bytes(b"synthetic non-SQLite sidecar")
        Path(f"{database}-wal").symlink_to(outside)
    lifecycle = _agy_lifecycle(sources, root)
    lifecycle.HOME = home
    lifecycle.LOCAL_SOURCES = []
    lifecycle.OPENCODE_DB = home / ".local" / "share" / "opencode" / "missing.db"
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)

    events, proposal = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=1,
    )

    assert events == []
    assert proposal["scope"] == "partial:all"
    assert proposal["source_unit_count"] == 0
    family = proposal["source_families"]["agy-cli-conversations"]
    assert family["discovered"] == 0
    assert family["errors"] == 1
    assert all(family[field] == 0 for field in ("converged", "adapted", "excluded", "pending", "unsupported"))
    assert proposal["adapter_gaps"] == ["agy-cli-conversations"]


@pytest.mark.parametrize(
    "candidate_order",
    [
        ("large.db", "second.db", "linked.db"),
        ("second.db", "linked.db", "large.db"),
    ],
)
def test_agy_discovery_overflow_fails_closed_independent_of_candidate_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidate_order: tuple[str, ...],
):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    large = root / "large.db"
    second = root / "second.db"
    linked = root / "linked.db"
    _agy_database(large, "x" * 256)
    _agy_database(second, "bounded second prompt")
    outside = tmp_path / "outside.db"
    _agy_database(outside, "outside prompt")
    linked.symlink_to(outside)
    candidates = {path.name: path for path in (large, second, linked)}
    original_rglob = Path.rglob

    def ordered_rglob(path: Path, pattern: str):
        if path == root and pattern == "*.db":
            return iter(candidates[name] for name in candidate_order)
        return original_rglob(path, pattern)

    monkeypatch.setattr(Path, "rglob", ordered_rglob)

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=3),
        limits=_agy_limits(sources, source_bytes=64, discovery=2),
    )

    assert events == []
    assert result["discovered"] == {}
    assert result["processed"] == {}
    assert result["adapted_unit_receipts"] == {}
    assert result["excluded_unit_receipts"] == {}
    assert result["attempted_files"] == 0
    assert result["pending_files"] == 1
    assert result["errors"] == ["agy-cli-conversations: database discovery exceeds bounded ceiling 2"]


def test_agy_source_byte_limit_fails_closed(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    _agy_database(root / "large.db", "x" * 256)

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        limits=_agy_limits(sources, source_bytes=64, discovery=2),
    )

    assert events == []
    assert result["processed"] == {}
    assert result["attempted_files"] == 1
    assert result["pending_files"] == 0
    assert "bounded ceiling is 64" in "\n".join(result["errors"])


def test_agy_symlink_hop_fails_closed(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    outside = tmp_path / "outside.db"
    _agy_database(outside, "outside prompt")
    (root / "linked.db").symlink_to(outside)

    events, result = sources.scan_agy_conversations(
        _agy_lifecycle(sources, root),
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        limits=_agy_limits(sources, source_bytes=64, discovery=2),
    )

    assert events == []
    assert result["processed"] == {}
    assert result["attempted_files"] == 0
    assert result["pending_files"] == 0
    assert "symlink hop" in "\n".join(result["errors"])


def test_agy_conversation_adapter_obeys_shared_work_unit_cap(tmp_path: Path):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    _agy_database(root / "one.db", "First bounded prompt with enough material to parse.")
    _agy_database(root / "two.db", "Second bounded prompt with enough material to parse.")
    lifecycle = _agy_lifecycle(sources, root)

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
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "wal.db"
    writer = sqlite3.connect(database)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    writer.execute("INSERT INTO steps VALUES (1, 14, 3, 'first prompt', NULL, NULL, NULL, NULL)")
    writer.commit()
    lifecycle = _agy_lifecycle(sources, root)

    first_events, first = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    database_before = sources.file_signature(database)
    writer.execute("INSERT INTO steps VALUES (2, 14, 3, 'second prompt', NULL, NULL, NULL, NULL)")
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
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "cache-race.db"
    writer = sqlite3.connect(database)
    assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    writer.execute("INSERT INTO steps VALUES (1, 14, 3, 'first prompt', NULL, NULL, NULL, NULL)")
    writer.commit()
    lifecycle = _agy_lifecycle(sources, root)
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
            writer.execute("INSERT INTO steps VALUES (2, 14, 3, 'racing prompt', NULL, NULL, NULL, NULL)")
            writer.commit()
        return signature

    monkeypatch.setattr(sources, "agy_storage_signature", mutate_after_first_signature)
    events, result = sources.scan_agy_conversations(
        lifecycle,
        {
            "files": first["processed"],
            "adapted_unit_receipts": first["adapted_unit_receipts"],
        },
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


def test_agy_cache_hit_rechecks_nonwal_sidecar_custody(tmp_path: Path, monkeypatch):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "cache-sidecar-race.db"
    _agy_database(database, "synthetic cached prompt")
    lifecycle = _agy_lifecycle(sources, root)
    _events, first = sources.scan_agy_conversations(
        lifecycle,
        {"files": {}, "adapted_unit_receipts": {}, "excluded_unit_receipts": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
    )
    real_signature = sources.agy_storage_signature
    calls = 0

    def add_fifo_after_initial_signature(path: Path):
        nonlocal calls
        signature = real_signature(path)
        calls += 1
        if calls == 1:
            os.mkfifo(Path(f"{database}-shm"))
        return signature

    monkeypatch.setattr(sources, "agy_storage_signature", add_fifo_after_initial_signature)
    events, result = sources.scan_agy_conversations(
        lifecycle,
        {
            "files": first["processed"],
            "adapted_unit_receipts": first["adapted_unit_receipts"],
        },
        days=None,
        budget=sources.ScanBudget(limit=1),
    )

    assert calls >= 2
    assert events == []
    assert result["processed"] == {}
    assert result["adapted_unit_receipts"] == {}
    assert any("sidecar custody changed during cache validation" in error for error in result["errors"])


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
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "future.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 99, 3, ?, NULL, NULL, NULL, NULL)",
        (json.dumps(payload),),
    )
    connection.commit()
    connection.close()
    lifecycle = _agy_lifecycle(sources, root)

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
        {"prompt": "x"},
    ],
    ids=("human-role", "operator-role", "prompt-field", "short-prompt-field"),
)
def test_unknown_agy_binary_json_prompt_carrier_is_an_explicit_source_error(
    tmp_path: Path,
    payload: dict,
):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "future-binary.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, step_payload BLOB, metadata BLOB, "
        "task_details BLOB, error_details BLOB, render_info BLOB)"
    )
    connection.execute(
        "INSERT INTO steps VALUES (1, 99, 3, ?, NULL, NULL, NULL, NULL)",
        (sqlite3.Binary(json.dumps(payload).encode("utf-8")),),
    )
    connection.commit()
    connection.close()
    lifecycle = _agy_lifecycle(sources, root)

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
        ("status", float("inf")),
        ("status", 3.5),
        ("status", "3"),
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
        "status-inf",
        "status-float",
        "status-string",
    ),
)
def test_agy_step_identity_requires_exact_nonnegative_integers(tmp_path: Path, field: str, value):
    sources = _load()
    root = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    root.mkdir(parents=True)
    database = root / "bad-identity.db"
    connection = sqlite3.connect(database)
    connection.execute(
        "CREATE TABLE steps (idx, step_type, status, step_payload TEXT, metadata TEXT, "
        "task_details TEXT, error_details TEXT, render_info TEXT)"
    )
    identity = {"idx": 1, "step_type": 14, "status": 3}
    identity[field] = value
    connection.execute(
        "INSERT INTO steps VALUES (?, ?, ?, 'A grounded prompt long enough for exact source parsing.', "
        "NULL, NULL, NULL, NULL)",
        (identity["idx"], identity["step_type"], identity["status"]),
    )
    connection.commit()
    connection.close()
    lifecycle = _agy_lifecycle(sources, root)

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


def test_claude_memory_alias_to_exact_in_root_sibling_is_excluded(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle, _projects, alias, target = _claude_memory_alias_fixture(sources, tmp_path)
    rows = sources.regular_source_rows(lifecycle, None)
    monkeypatch.setattr(
        sources,
        "_bounded_file_bytes",
        lambda *_args, **_kwargs: pytest.fail("alias classification must stay metadata-only"),
    )

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=rows,
    )

    alias_key = sources.cursor_unit_key("claude-projects", alias)
    target_key = sources.cursor_unit_key("claude-projects", target)
    alias_receipt = result["excluded_unit_receipts"][alias_key]
    assert events == []
    assert result["errors"] == []
    assert result["source_alias_blocker_counts"] == {}
    assert result["source_exclusion_counts"][sources.CLAUDE_PROJECT_MEMORY_ALIAS_ID] == 1
    assert alias_receipt["contract_id"] == sources.CLAUDE_PROJECT_MEMORY_ALIAS_ID
    assert alias_receipt["signature"] == sources.source_unit_signature(lifecycle, "claude-projects", alias)
    assert alias_receipt["related_signatures"]["memory_target"] == sources.file_signature(target)
    assert result["excluded_unit_receipts"][target_key]["contract_id"] == "claude-project-memory-v1"


def test_claude_memory_alias_accepts_only_normalized_exact_sibling(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle, _projects, alias, _target = _claude_memory_alias_fixture(sources, tmp_path, absolute=True)
    custody = sources.source_path_custody(lifecycle, "claude-projects", alias)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": alias}],
    )

    assert custody.alias_contract_id == sources.CLAUDE_PROJECT_MEMORY_ALIAS_ID
    assert custody.error is None
    assert events == []
    assert result["errors"] == []
    assert result["source_exclusion_counts"] == {sources.CLAUDE_PROJECT_MEMORY_ALIAS_ID: 1}

    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    _events, partial = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=1,
    )
    assert partial["scope"] == "partial:all"
    assert partial["pending_files"] == 1
    assert sources.validate_source_adapter_cursor(partial) == []


def test_claude_memory_alias_to_other_in_root_file_is_blocked(tmp_path: Path):
    sources = _load()
    lifecycle, _projects, alias, target = _claude_memory_alias_fixture(sources, tmp_path)
    other = target.with_name("other.md")
    other.write_text("synthetic alternate fixture", encoding="utf-8")
    alias.unlink()
    alias.symlink_to(Path("memory") / other.name)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": alias}],
    )

    assert events == []
    assert len(result["errors"]) == 1
    assert result["source_alias_blocker_counts"] == {"alias_target_mismatch": 1}
    assert result["excluded_unit_receipts"] == {}


def test_claude_memory_alias_escape_is_blocked(tmp_path: Path):
    sources = _load()
    lifecycle, _projects, alias, _target = _claude_memory_alias_fixture(sources, tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("synthetic outside fixture", encoding="utf-8")
    alias.unlink()
    alias.symlink_to(outside)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": alias}],
    )

    assert events == []
    assert len(result["errors"]) == 1
    assert result["source_alias_blocker_counts"] == {"alias_target_mismatch": 1}
    assert result["excluded_unit_receipts"] == {}


def test_claude_memory_alias_chain_is_blocked(tmp_path: Path):
    sources = _load()
    lifecycle, _projects, alias, target = _claude_memory_alias_fixture(sources, tmp_path)
    terminal = target.with_name("terminal.md")
    terminal.write_text("synthetic terminal fixture", encoding="utf-8")
    target.unlink()
    target.symlink_to(terminal.name)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": alias}],
    )

    assert events == []
    assert result["source_alias_blocker_counts"] == {"alias_link_chain": 1}
    assert result["excluded_unit_receipts"] == {}


def test_claude_memory_alias_dangling_target_is_blocked(tmp_path: Path):
    sources = _load()
    lifecycle, _projects, alias, target = _claude_memory_alias_fixture(sources, tmp_path)
    target.unlink()

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": alias}],
    )

    assert events == []
    assert result["source_alias_blocker_counts"] == {"alias_dangling_target": 1}
    assert result["excluded_unit_receipts"] == {}


def test_claude_memory_alias_cycle_is_blocked(tmp_path: Path):
    sources = _load()
    lifecycle, _projects, alias, target = _claude_memory_alias_fixture(sources, tmp_path)
    target.unlink()
    target.symlink_to(Path("..") / alias.name)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": alias}],
    )

    assert events == []
    assert result["source_alias_blocker_counts"] == {"alias_link_chain": 1}
    assert result["excluded_unit_receipts"] == {}


def test_claude_memory_alias_wrong_target_type_is_blocked(tmp_path: Path):
    sources = _load()
    lifecycle, _projects, alias, target = _claude_memory_alias_fixture(sources, tmp_path)
    target.unlink()
    target.mkdir()

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": alias}],
    )

    assert events == []
    assert result["source_alias_blocker_counts"] == {"alias_target_not_regular": 1}
    assert result["excluded_unit_receipts"] == {}


def test_claude_memory_alias_below_symlinked_directory_is_blocked(tmp_path: Path):
    sources = _load()
    projects = tmp_path / ".claude" / "projects"
    projects.mkdir(parents=True)
    external_project = tmp_path / "external-project"
    target = external_project / "memory" / "fixture.md"
    alias = external_project / target.name
    target.parent.mkdir(parents=True)
    target.write_text("synthetic memory fixture", encoding="utf-8")
    alias.symlink_to(Path("memory") / target.name)
    (projects / "project").symlink_to(external_project, target_is_directory=True)
    lexical_alias = projects / "project" / alias.name
    lifecycle = sources.load_lifecycle_module()
    lifecycle.LOCAL_SOURCES = [("claude-projects", projects, ("*",))]
    lifecycle.OPENCODE_DB = tmp_path / "missing-opencode.db"
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / "missing-agy"

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": lexical_alias}],
    )

    assert events == []
    assert result["source_alias_blocker_counts"] == {"alias_ancestor_symlink": 1}
    assert result["excluded_unit_receipts"] == {}


def test_claude_memory_alias_retarget_race_never_advances_cursor(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle, _projects, alias, target = _claude_memory_alias_fixture(sources, tmp_path)
    other = target.with_name("other.md")
    other.write_text("synthetic alternate fixture", encoding="utf-8")
    real_signature = sources.source_unit_signature
    mutated = False

    def mutate_after_signature(*args, **kwargs):
        nonlocal mutated
        signature = real_signature(*args, **kwargs)
        if Path(args[2]) == alias and not mutated:
            mutated = True
            alias.unlink()
            alias.symlink_to(Path("memory") / other.name)
        return signature

    monkeypatch.setattr(sources, "source_unit_signature", mutate_after_signature)
    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": alias}],
    )

    key = sources.cursor_unit_key("claude-projects", alias)
    assert events == []
    assert result["source_alias_blocker_counts"] == {"alias_target_mismatch": 1}
    assert key not in result["files"]
    assert key not in result["excluded_unit_receipts"]


def test_exact_live_custody_rejects_memory_alias_changed_after_seal(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle, _projects, alias, target = _claude_memory_alias_fixture(sources, tmp_path)
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    _events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=2,
    )
    assert cursor["scope"] == "all"

    other = target.with_name("other.md")
    other.write_text("synthetic alternate fixture", encoding="utf-8")
    alias.unlink()
    alias.symlink_to(Path("memory") / other.name)

    from limen.prompt_corpus import validate_live_source_custody

    errors = validate_live_source_custody(cursor)
    assert any("containment changed" in error or "alias changed" in error for error in errors)


def test_memory_alias_second_pass_is_zero_growth_byte_identical_and_public_safe(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle, projects, alias, target = _claude_memory_alias_fixture(sources, tmp_path)
    rows = sources.regular_source_rows(lifecycle, None)
    first_budget = sources.ScanBudget(limit=2)
    first_events, first = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=first_budget,
        rows=rows,
    )
    first_bytes = json.dumps(first["excluded_unit_receipts"], sort_keys=True, separators=(",", ":")).encode()
    second_budget = sources.ScanBudget(limit=2)
    second_events, second = sources.scan_regular_sources(
        lifecycle,
        first,
        days=None,
        budget=second_budget,
        rows=rows,
    )
    second_bytes = json.dumps(second["excluded_unit_receipts"], sort_keys=True, separators=(",", ":")).encode()

    assert first_events == second_events == []
    assert second_budget.used == 0
    assert first_bytes == second_bytes
    assert second["source_alias_blocker_counts"] == {}
    alias_key = sources.cursor_unit_key("claude-projects", alias)
    target_key = sources.cursor_unit_key("claude-projects", target)
    assert alias_key != target_key
    assert set(second["excluded_unit_receipts"]) == {alias_key, target_key}

    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    _events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=2,
    )
    from limen.prompt_corpus import DEFAULT_POLICY, build_snapshot, public_projection

    snapshot = build_snapshot([], [], [], DEFAULT_POLICY, cursor)
    public = public_projection(snapshot)
    encoded = json.dumps(public, sort_keys=True)
    assert public["source_scope"]["source_exclusion_counts"][sources.CLAUDE_PROJECT_MEMORY_ALIAS_ID] == 1
    assert public["source_scope"]["source_alias_blocker_counts"] == {}
    assert str(projects) not in encoded
    assert alias.name not in encoded


def test_claude_subagent_cross_session_alias_is_excluded_with_independent_target_custody(
    tmp_path: Path,
    monkeypatch,
):
    sources = _load()
    lifecycle, _projects, alias, target = _claude_subagent_alias_fixture(sources, tmp_path)
    rows = sources.regular_source_rows(lifecycle, None)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=None),
        rows=rows,
    )

    alias_key = sources.cursor_unit_key("claude-projects", alias)
    target_key = sources.cursor_unit_key("claude-projects", target)
    receipt = result["excluded_unit_receipts"][alias_key]
    assert [event["text"] for event in events] == ["delegated alias target"]
    assert {event["authority"] for event in events} == {"derived"}
    assert result["errors"] == []
    assert result["unsupported"] == []
    assert result["source_alias_blocker_counts"] == {}
    assert receipt["contract_id"] == sources.CLAUDE_SUBAGENT_SESSION_ALIAS_ID
    assert receipt["related_signatures"]["subagent_target"] == sources.file_signature(target)
    assert receipt["related_evidence"]["subagent_target"]["target_locator"] == str(target)
    assert result["files"][target_key] == sources.file_signature(target)
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    _events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=10,
    )
    assert cursor["scope"] == "all"
    assert sources.validate_source_adapter_cursor(cursor) == []
    from limen.prompt_corpus import (
        DEFAULT_POLICY,
        build_snapshot,
        public_projection,
        validate_live_source_custody,
    )

    assert validate_live_source_custody(cursor) == []
    public = public_projection(build_snapshot([], [], [], DEFAULT_POLICY, cursor))
    encoded = json.dumps(public, sort_keys=True)
    assert str(alias) not in encoded
    assert str(target) not in encoded

    missing_target = json.loads(json.dumps(cursor))
    missing_target["source_units"].remove(target_key)
    missing_target["source_unit_count"] -= 1
    missing_target["source_units_digest"] = sources.digest(missing_target["source_units"])
    missing_target["files"].pop(target_key)
    assert any(
        "subagent-session alias target lacks independent custody" in error
        for error in sources.validate_source_adapter_cursor(missing_target)
    )


@pytest.mark.parametrize("near_miss", ["relative", "other-project", "same-session", "link-chain"])
def test_claude_subagent_alias_near_misses_remain_fail_closed(tmp_path: Path, near_miss: str):
    sources = _load()
    lifecycle, projects, alias, target = _claude_subagent_alias_fixture(sources, tmp_path)
    alias.unlink()
    if near_miss == "relative":
        alias.symlink_to(Path("..") / ".." / "target-session" / "subagents" / target.name)
    elif near_miss == "other-project":
        other = projects / "other-project" / "target-session" / "subagents" / target.name
        other.parent.mkdir(parents=True)
        other.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        alias.symlink_to(other)
    elif near_miss == "same-session":
        other = alias.with_name("other.jsonl")
        other.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        alias.symlink_to(other)
    else:
        chained = target.with_name("chained.jsonl")
        chained.symlink_to(target)
        alias.symlink_to(chained)

    events, result = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=1),
        rows=[{"source": "claude-projects", "path": alias}],
    )

    assert events == []
    assert len(result["errors"]) == 1
    assert sum(result["source_alias_blocker_counts"].values()) == 1
    assert result["excluded_unit_receipts"] == {}


def test_claude_subagent_directory_alias_is_metadata_only_and_not_a_source_unit(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle, projects, _alias, _target = _claude_subagent_alias_fixture(sources, tmp_path)
    target_dir = projects / "project" / "target-session" / "subagents" / "agent" / "nested"
    alias_dir = projects / "project" / "alias-session" / "subagents" / "agent" / "nested"
    target_dir.mkdir(parents=True)
    alias_dir.parent.mkdir(parents=True, exist_ok=True)
    alias_dir.symlink_to(target_dir, target_is_directory=True)

    rows = sources.regular_source_rows(lifecycle, None)

    assert not rows.discovery_errors
    assert all(Path(row["path"]) != alias_dir for row in rows)
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    _events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=10,
    )
    from limen.prompt_corpus import validate_live_source_custody

    assert cursor["scope"] == "all"
    assert validate_live_source_custody(cursor) == []


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


def test_claude_jsonl_uses_its_hashed_source_ceiling_without_unbounding_other_families(
    tmp_path: Path,
    monkeypatch,
):
    sources = _load()
    lifecycle = sources.load_lifecycle_module()
    projects = tmp_path / ".claude" / "projects"
    transcript = projects / "project" / "session.jsonl"
    transcript.parent.mkdir(parents=True)
    schema = sources.SOURCE_RECORD_SCHEMAS["claude-project-jsonl-v1"]
    monkeypatch.setitem(schema, "max_probe_bytes", 4096)
    monkeypatch.setitem(schema, "max_records", 3)
    limits = sources.ResourceLimits(
        max_source_bytes_per_unit=1,
        max_events_per_unit=1,
        max_discovery_units=10,
        max_classifier_input_bytes=1024,
        max_classifier_output_bytes=1024,
        max_classifier_stderr_bytes=1024,
        max_classifier_occurrences=10,
    )
    rows = [{"type": "system"}, {"type": "system"}, {"type": "system"}]
    transcript.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    records, error, supported = sources.strict_native_records(
        lifecycle,
        "claude-projects",
        transcript,
        sources.file_signature(transcript),
        limits=limits,
    )
    assert supported is True
    assert error is None
    assert len(records) == 3

    transcript.write_text("".join(json.dumps(row) + "\n" for row in [*rows, {"type": "system"}]), encoding="utf-8")
    records, error, supported = sources.strict_native_records(
        lifecycle,
        "claude-projects",
        transcript,
        sources.file_signature(transcript),
        limits=limits,
    )
    assert supported is True
    assert records == []
    assert "record count exceeds bounded ceiling 3" in str(error)

    transcript.write_text("x" * 4097, encoding="utf-8")
    records, error, supported = sources.strict_native_records(
        lifecycle,
        "claude-projects",
        transcript,
        sources.file_signature(transcript),
        limits=limits,
    )
    assert supported is True
    assert records == []
    assert "bounded ceiling is 4096" in str(error)


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


@pytest.mark.parametrize("keyset_index", range(5))
def test_claude_derived_tool_result_prompt_shapes_are_preserved_exactly(
    tmp_path: Path,
    keyset_index: int,
):
    sources = _load()
    keyset = sources.CLAUDE_DERIVED_TOOL_RESULT_PROMPT_KEYSETS[keyset_index]
    result = {}
    for field in keyset:
        if field in {"canReadOutputFile", "isAsync"}:
            result[field] = True
        elif field in sources.CLAUDE_DERIVED_TOOL_RESULT_INTEGER_FIELDS:
            result[field] = 1
        elif field == "content":
            result[field] = []
        elif field in {"toolStats", "usage"}:
            result[field] = {}
        else:
            result[field] = "derived prompt" if field == "prompt" else f"fixture-{field}"
    row = {
        "type": "user",
        "sourceToolAssistantUUID": "assistant-source",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "tool-one",
                    "content": "ordinary result body",
                }
            ],
        },
        "toolUseResult": result,
    }

    events, scan, _transcript = _scan_claude_rows(sources, tmp_path, [row])

    assert scan["errors"] == []
    assert scan["unsupported"] == []
    assert [event["text"] for event in events] == ["derived prompt"]
    assert {event["provenance"] for event in events} == {"delegated_task_frame"}
    assert {event["authority"] for event in events} == {"derived"}


@pytest.mark.parametrize("near_miss", ["extra-key", "nontext-prompt", "missing-marker", "boolean-total"])
def test_claude_derived_tool_result_prompt_near_misses_stay_unsupported(
    tmp_path: Path,
    near_miss: str,
):
    sources = _load()
    result = {
        "agentId": "agent",
        "canReadOutputFile": True,
        "description": "fixture",
        "isAsync": True,
        "outputFile": "fixture",
        "prompt": "derived prompt",
        "resolvedModel": "fixture",
        "status": "done",
    }
    row = {
        "type": "user",
        "sourceToolAssistantUUID": "assistant-source",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tool-one", "content": "result"}],
        },
        "toolUseResult": result,
    }
    if near_miss == "extra-key":
        result["futureCarrier"] = "unknown"
    elif near_miss == "nontext-prompt":
        result["prompt"] = ["not exact text"]
    elif near_miss == "missing-marker":
        row.pop("sourceToolAssistantUUID")
    else:
        result.clear()
        result.update(
            {
                "agentId": "agent",
                "agentType": "fixture",
                "content": [],
                "prompt": "derived prompt",
                "resolvedModel": "fixture",
                "status": "done",
                "totalDurationMs": True,
                "totalTokens": 1,
                "totalToolUseCount": 1,
                "usage": {},
            }
        )

    events, scan, transcript = _scan_claude_rows(sources, tmp_path, [row])

    key = sources.cursor_unit_key("claude-projects", transcript)
    assert events == []
    assert scan["unsupported"] == [key]
    assert key not in scan["files"]


def test_claude_derived_tool_result_jobs_are_preserved_as_exact_derived_segments(tmp_path: Path):
    sources = _load()
    row = {
        "type": "user",
        "sourceToolAssistantUUID": "assistant-source",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tool-one", "content": "result"}],
        },
        "toolUseResult": {
            "jobs": [
                {
                    "cron": "0 9 * * *",
                    "durable": True,
                    "humanSchedule": "daily at nine",
                    "id": "job-one",
                    "prompt": "first derived job prompt",
                    "recurring": True,
                },
                {
                    "cron": "",
                    "durable": False,
                    "humanSchedule": "once",
                    "id": "job-two",
                    "prompt": "second derived job prompt",
                    "recurring": False,
                },
            ]
        },
    }

    events, scan, _transcript = _scan_claude_rows(sources, tmp_path, [row])

    assert scan["errors"] == []
    assert scan["unsupported"] == []
    assert [event["text"] for event in events] == [
        "first derived job prompt",
        "second derived job prompt",
    ]
    assert {event["provenance"] for event in events} == {"delegated_task_frame"}
    assert {event["authority"] for event in events} == {"derived"}


@pytest.mark.parametrize(
    "near_miss",
    ["extra-job-key", "nontext-prompt", "missing-marker", "nonboolean-durable", "extra-result-key"],
)
def test_claude_derived_tool_result_jobs_near_misses_stay_unsupported(
    tmp_path: Path,
    near_miss: str,
):
    sources = _load()
    job = {
        "cron": "0 9 * * *",
        "durable": True,
        "humanSchedule": "daily at nine",
        "id": "job-one",
        "prompt": "derived job prompt",
        "recurring": True,
    }
    row = {
        "type": "user",
        "sourceToolAssistantUUID": "assistant-source",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tool-one", "content": "result"}],
        },
        "toolUseResult": {"jobs": [job]},
    }
    if near_miss == "extra-job-key":
        job["futureCarrier"] = "unknown"
    elif near_miss == "nontext-prompt":
        job["prompt"] = ["not exact text"]
    elif near_miss == "missing-marker":
        row.pop("sourceToolAssistantUUID")
    elif near_miss == "nonboolean-durable":
        job["durable"] = 1
    else:
        row["toolUseResult"]["status"] = "unknown"

    events, scan, transcript = _scan_claude_rows(sources, tmp_path, [row])

    key = sources.cursor_unit_key("claude-projects", transcript)
    assert events == []
    assert scan["unsupported"] == [key]
    assert key not in scan["files"]


def test_claude_exit_plan_allowed_prompts_are_exact_derived_segments(tmp_path: Path):
    sources = _load()
    row = {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "ExitPlanMode",
                    "input": {
                        "allowedPrompts": [
                            {"prompt": "Run the exact focused predicate.", "tool": "Bash"},
                            {"prompt": "Inspect the bounded receipt.", "tool": "Read"},
                        ],
                        "plan": "generated plan body",
                        "planFilePath": "private plan path",
                    },
                }
            ],
        },
    }

    events, scan, _transcript = _scan_claude_rows(sources, tmp_path, [row])

    assert scan["unsupported"] == []
    assert [event["text"] for event in events] == [
        "Run the exact focused predicate.",
        "Inspect the bounded receipt.",
    ]
    assert {event["authority"] for event in events} == {"derived"}


@pytest.mark.parametrize("near_miss", ["wrong-tool", "extra-item-key", "nontext-prompt"])
def test_claude_allowed_prompt_near_misses_stay_unsupported(tmp_path: Path, near_miss: str):
    sources = _load()
    item = {"prompt": "Run the exact focused predicate.", "tool": "Bash"}
    tool_use = {
        "type": "tool_use",
        "name": "ExitPlanMode",
        "input": {
            "allowedPrompts": [item],
            "plan": "generated plan body",
            "planFilePath": "private plan path",
        },
    }
    if near_miss == "wrong-tool":
        tool_use["name"] = "FuturePlanMode"
    elif near_miss == "extra-item-key":
        item["future"] = "unknown"
    else:
        item["prompt"] = ["not exact text"]
    row = {
        "type": "assistant",
        "message": {"role": "assistant", "content": [tool_use]},
    }

    events, scan, transcript = _scan_claude_rows(sources, tmp_path, [row])

    assert events == []
    assert scan["unsupported"] == [sources.cursor_unit_key("claude-projects", transcript)]


def test_claude_list_valued_text_attachments_converge_but_media_stays_explicit(tmp_path: Path):
    sources = _load()
    textual_rows = [
        {
            "type": "attachment",
            "attachment": {
                "type": "hook_additional_context",
                "content": ["first derived context", "second derived context"],
            },
        },
        {
            "type": "attachment",
            "attachment": {
                "type": "queued_command",
                "prompt": [{"type": "text", "text": "queued exact text"}],
            },
        },
    ]
    events, scan, _transcript = _scan_claude_rows(sources, tmp_path / "textual", textual_rows)

    assert scan["unsupported"] == []
    assert [event["text"] for event in events] == [
        "first derived context",
        "second derived context",
        "queued exact text",
    ]
    assert [event["provenance"] for event in events] == [
        "delegated_task_frame",
        "delegated_task_frame",
        "unknown_user_input",
    ]

    media_row = {
        "type": "attachment",
        "attachment": {
            "type": "queued_command",
            "prompt": [
                {"type": "text", "text": "must not be partially extracted"},
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/png", "data": "cGl4ZWw="},
                },
            ],
        },
    }
    media_events, media_scan, media_path = _scan_claude_rows(sources, tmp_path / "media", [media_row])
    assert media_events == []
    assert media_scan["unsupported"] == [sources.cursor_unit_key("claude-projects", media_path)]


def test_claude_mixed_user_text_and_media_never_partially_converges(tmp_path: Path):
    sources = _load()
    row = {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {"type": "text", "text": "must remain bound to media"},
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": "cGRm",
                    },
                },
            ],
        },
    }

    events, scan, transcript = _scan_claude_rows(sources, tmp_path, [row])

    assert events == []
    assert scan["unsupported"] == [sources.cursor_unit_key("claude-projects", transcript)]


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
    lifecycle.AGY_CLI_CONVERSATIONS = tmp_path / ".gemini" / "antigravity-cli" / "conversations"
    lifecycle.HOME = tmp_path
    return lifecycle, session, attachment


def _codex_attachment_compacted_row(reference: str, *, envelope: str) -> dict[str, object]:
    """Build only production-exact compacted envelopes used by scanner v4."""

    payload: dict[str, object] = {
        "message": "",
        "replacement_history": [
            {
                "type": "message",
                "role": "developer",
                "content": [{"type": "input_text", "text": "Synthetic provider context."}],
            },
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": reference}],
                "internal_chat_message_metadata_passthrough": {"turn_id": f"turn-{envelope}"},
            },
            {"type": "compaction", "id": f"cmp-{envelope}", "encrypted_content": "opaque"},
        ],
    }
    if envelope == "legacy":
        payload["window_id"] = 41
    elif envelope == "current":
        payload.update(
            {
                "first_window_id": "11111111-1111-1111-1111-111111111111",
                "previous_window_id": "22222222-2222-2222-2222-222222222222",
                "window_id": "33333333-3333-3333-3333-333333333333",
                "window_number": 41,
            }
        )
    else:
        raise AssertionError(f"unknown compacted envelope: {envelope}")
    return {
        "type": "compacted",
        "timestamp": "2026-07-13T01:00:00Z",
        "payload": payload,
    }


def _add_exact_codex_media_parent(sources, session: Path, attachment: Path) -> list[dict]:
    """Attach one strict PNG to the canonical reference and its exact transport row."""

    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    reference = sources.codex_attachment_reference_line(attachment)
    message = f"[Image #1]\n{reference}"
    rows[1]["payload"]["content"] = [
        {"type": "input_text", "text": message},
        {"type": "input_image", "detail": "high", "image_url": VALID_CODEX_PNG_DATA_URL},
    ]
    placeholder = "[Image #1]"
    rows.append(
        {
            "timestamp": "2026-07-13T01:00:02Z",
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": message,
                "images": [],
                "local_images": ["/private/tmp/codex-integration-image.png"],
                "text_elements": [
                    {
                        "placeholder": placeholder,
                        "byte_range": {"start": 0, "end": len(placeholder.encode("utf-8"))},
                    }
                ],
            },
        }
    )
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return rows


def _scan_codex_attachment_pair(sources, lifecycle, session: Path, attachment: Path):
    return sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=[
            {"source": "codex-sessions", "path": session},
            {"source": "codex-attachments", "path": attachment},
        ],
    )


@pytest.mark.parametrize("envelope", ["legacy", "current"])
def test_codex_attachment_scanner_v4_compacted_replay_is_never_a_second_parent(
    tmp_path: Path,
    envelope: str,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    rows.insert(
        1,
        _codex_attachment_compacted_row(
            sources.codex_attachment_reference_line(attachment),
            envelope=envelope,
        ),
    )
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = _scan_codex_attachment_pair(sources, lifecycle, session, attachment)

    attachment_events = [event for event in events if event["source"] == "codex-attachments"]
    assert result["errors"] == []
    assert result["unsupported"] == []
    assert len(attachment_events) == 1
    assert attachment_events[0]["authority"] == "operator"
    assert result["adapted_unit_receipts"][attachment_key]["contract_id"] == ("codex-pasted-text-attachment-v1")
    assert result["parent_completeness_unknown"] == []


@pytest.mark.parametrize("mutation", ["extra-payload-key", "unknown-role", "unknown-content"])
def test_codex_attachment_scanner_v4_malformed_compacted_replay_fails_closed(
    tmp_path: Path,
    mutation: str,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    replay = _codex_attachment_compacted_row(
        sources.codex_attachment_reference_line(attachment),
        envelope="current",
    )
    payload = replay["payload"]
    assert isinstance(payload, dict)
    history = payload["replacement_history"]
    assert isinstance(history, list) and isinstance(history[1], dict)
    if mutation == "extra-payload-key":
        payload["unknown"] = True
    elif mutation == "unknown-role":
        history[1]["role"] = "assistant"
    else:
        content = history[1]["content"]
        assert isinstance(content, list) and isinstance(content[0], dict)
        content[0]["unknown"] = True
    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    rows.insert(1, replay)
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    session_key = sources.cursor_unit_key("codex-sessions", session)
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = _scan_codex_attachment_pair(sources, lifecycle, session, attachment)

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert result["errors"]
    assert session_key not in result["files"]
    assert attachment_key in result["unsupported_units"]
    assert attachment_key not in result["adapted_unit_receipts"]
    assert result["parent_completeness_unknown"] == [session_key]


def test_codex_attachment_scanner_v4_replay_only_reference_stays_unbound(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path, parent_texts=[])
    replay = _codex_attachment_compacted_row(
        sources.codex_attachment_reference_line(attachment),
        envelope="current",
    )
    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    rows.append(replay)
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = _scan_codex_attachment_pair(sources, lifecycle, session, attachment)

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert result["errors"] == []
    assert attachment_key in result["unsupported_units"]
    assert attachment_key not in result["adapted_unit_receipts"]
    assert result["parent_completeness_unknown"] == []


def test_codex_attachment_scanner_v4_valid_png_and_reference_bind_together(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    _add_exact_codex_media_parent(sources, session, attachment)
    session_key = sources.cursor_unit_key("codex-sessions", session)
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = _scan_codex_attachment_pair(sources, lifecycle, session, attachment)

    attachment_events = [event for event in events if event["source"] == "codex-attachments"]
    media_events = [event for event in events if event["body_kind"] == "nontext_input"]
    assert result["errors"] == []
    assert result["unsupported"] == []
    assert len(attachment_events) == 1
    assert len(media_events) == 1
    assert media_events[0]["text"].startswith("codex-input-image-v1:sha256=")
    assert VALID_CODEX_PNG_DATA_URL not in media_events[0]["text"]
    assert result["adapted_unit_receipts"][session_key]["contract_id"] == "codex-session-jsonl-v2"
    assert result["adapted_unit_receipts"][attachment_key]["contract_id"] == ("codex-pasted-text-attachment-v1")


@pytest.mark.parametrize("mutation", ["extra-key", "bad-detail", "bad-base64"])
def test_codex_attachment_scanner_v4_malformed_coexisting_media_fails_closed(
    tmp_path: Path,
    mutation: str,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = _add_exact_codex_media_parent(sources, session, attachment)
    image = rows[1]["payload"]["content"][1]
    if mutation == "extra-key":
        image["unknown"] = True
    elif mutation == "bad-detail":
        image["detail"] = "auto"
    else:
        image["image_url"] = "data:image/png;base64,not-valid!"
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    session_key = sources.cursor_unit_key("codex-sessions", session)
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = _scan_codex_attachment_pair(sources, lifecycle, session, attachment)

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert result["errors"]
    assert session_key not in result["files"]
    assert attachment_key in result["unsupported_units"]
    assert attachment_key not in result["adapted_unit_receipts"]


def test_codex_attachment_scanner_v4_accepts_bounded_large_nonuser_row(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    rows.insert(
        1,
        {
            "type": "response_item",
            "timestamp": "2026-07-13T01:00:00Z",
            "payload": {
                "type": "function_call_output",
                "output": "x" * (1024 * 1024 + 4096),
            },
        },
    )
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)

    events, result = _scan_codex_attachment_pair(sources, lifecycle, session, attachment)

    assert result["errors"] == []
    assert result["unsupported"] == []
    assert len([event for event in events if event["source"] == "codex-attachments"]) == 1
    assert attachment_key in result["adapted_unit_receipts"]
    assert result["parent_completeness_unknown"] == []


def test_codex_attachment_scanner_v4_invalidates_v3_cached_receipts(tmp_path: Path, monkeypatch):
    sources = _load()
    assert sources.SCANNER_VERSION == 4
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    missing = tmp_path / "missing-cursor.json"
    first_events, first = sources.scan_native_sources(
        SimpleNamespace(cursor=missing),
        days=None,
        max_files=2,
    )
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)
    assert first_events
    assert attachment_key in first["adapted_unit_receipts"]
    stale = json.loads(json.dumps(first))
    stale["scanner_version"] = 3
    cursor_path = tmp_path / "scanner-v3-cursor.json"
    cursor_path.write_text(json.dumps(stale), encoding="utf-8")

    replacement_events, replacement = sources.scan_native_sources(
        SimpleNamespace(cursor=cursor_path),
        days=None,
        max_files=2,
    )

    assert replacement_events
    assert replacement["scanner_version"] == 4
    assert replacement["work_units_used"] == 2
    assert attachment_key in replacement["adapted_unit_receipts"]
    assert replacement["source_errors"] == []
    assert replacement["unsupported_source_count"] == 0


def test_codex_attachment_scanner_v4_integrated_second_pass_is_byte_identical(
    tmp_path: Path,
    monkeypatch,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = _add_exact_codex_media_parent(sources, session, attachment)
    rows.insert(
        1,
        _codex_attachment_compacted_row(
            sources.codex_attachment_reference_line(attachment),
            envelope="current",
        ),
    )
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    paths = sources.LedgerPaths.for_root(
        tmp_path / "ledger",
        policy=ROOT / "docs" / "prompt-corpus-policy.json",
    )

    first_events, first_cursor = sources.scan_native_sources(paths, days=None, max_files=2)
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
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.exists()}

    first_bytes = canonical_bytes()
    second_events, second_cursor = sources.scan_native_sources(paths, days=None, max_files=2)
    second_snapshot = sources.update_ledger(paths, events=second_events, cursor=second_cursor)

    assert first_cursor["scanner_version"] == 4
    assert first_cursor["scope"] == "all"
    assert first_cursor["adapter_gaps"] == []
    assert first_cursor["source_errors"] == []
    assert first_cursor["unsupported_source_count"] == 0
    assert first_snapshot["appended"]["occurrences"] > 0
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
    assert result["source_adapter_counts"] == {
        "codex-pasted-text-attachment-v1": 1,
        "codex-session-jsonl-v2": 1,
    }
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
        json.dumps({"type": "session_meta", "payload": {"id": "fixture-thread"}})
        + "\n"
        + json.dumps(
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
    key = sources.cursor_unit_key("codex-attachments", attachment)
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
    assert key not in oversized["adapted_unit_receipts"]
    assert {receipt["contract_id"] for receipt in oversized["adapted_unit_receipts"].values()} == {
        "codex-session-jsonl-v2"
    }

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
    assert key not in malformed["adapted_unit_receipts"]
    assert {receipt["contract_id"] for receipt in malformed["adapted_unit_receipts"].values()} == {
        "codex-session-jsonl-v2"
    }


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
    assert result["coverage"]["codex-sessions"]["errors"] == 0
    assert result["errors"] == []


def test_codex_attachment_reordered_oversized_echo_fails_closed_in_regular_and_streaming_modes(
    tmp_path: Path,
    monkeypatch,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    rows.insert(
        1,
        {
            "payload": {
                "message": "x" * 12000,
                "local_images": [],
                "text_elements": [],
                "type": "user_message",
            },
            "timestamp": "2026-07-13T01:00:00Z",
            "type": "event_msg",
        },
    )
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    signature = sources.file_signature(session)
    assert signature is not None
    rule = sources.SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]
    monkeypatch.setitem(rule, "max_parent_record_bytes", 1024)
    limits = sources.runtime_limits({})

    regular_events, regular_error, regular_completeness_unknown = sources.targeted_codex_attachment_parent_events(
        lifecycle,
        session,
        rows,
        limits=limits,
    )
    streaming_events, streaming_error, streaming_completeness_unknown = (
        sources.bounded_codex_attachment_parent_events_from_path(
            lifecycle,
            session,
            signature,
            limits=limits,
        )
    )

    assert regular_events == streaming_events == []
    assert regular_error == streaming_error
    assert regular_error is not None and "completeness is unknown" in regular_error
    assert regular_completeness_unknown is streaming_completeness_unknown is True

    projections = []
    session_key = sources.cursor_unit_key("codex-sessions", session)
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)
    scan_rows = [
        {"source": "codex-sessions", "path": session},
        {"source": "codex-attachments", "path": attachment},
    ]
    for max_source_bytes in (1048576, 128):
        events, result = sources.scan_regular_sources(
            lifecycle,
            {"files": {}},
            days=None,
            budget=sources.ScanBudget(limit=2),
            limits=sources.runtime_limits({"resource_limits": {"max_source_bytes_per_unit": max_source_bytes}}),
            rows=scan_rows,
        )
        assert not [event for event in events if event["source"] == "codex-attachments"]
        assert result["parent_completeness_unknown"] == [session_key]
        assert result["unsupported"] == [attachment_key]
        assert attachment_key not in result["adapted_unit_receipts"]
        projections.append((result["errors"], result["unsupported"], result["parent_completeness_unknown"]))
    assert projections[0] == projections[1]


@pytest.mark.parametrize("max_source_bytes", [1048576, 128])
def test_codex_attachment_multi_session_identity_fails_regular_and_streaming(
    tmp_path: Path,
    max_source_bytes: int,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    rows.insert(1, {"type": "session_meta", "payload": {"id": "fixture-second-thread"}})
    session.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    limits = sources.runtime_limits({"resource_limits": {"max_source_bytes_per_unit": max_source_bytes}})
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

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert key not in result["adapted_unit_receipts"]
    assert result["unsupported"] == [key]
    assert "session identity is ambiguous" in " ".join(result["errors"])


def test_codex_attachment_actual_bytes_reject_stale_signature_growth(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle, session, _attachment = _codex_attachment_fixture(sources, tmp_path)
    stale_signature = sources.file_signature(session)
    assert stale_signature is not None
    rule = sources.SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]
    byte_ceiling = int(stale_signature["size"]) + 16
    monkeypatch.setitem(rule, "max_parent_probe_bytes", byte_ceiling)
    with session.open("ab") as handle:
        handle.write(b" " * 64)

    events, error, parent_completeness_unknown = sources.bounded_codex_attachment_parent_events_from_path(
        lifecycle,
        session,
        stale_signature,
        limits=sources.runtime_limits({}),
    )

    assert events == []
    assert error is not None and f"byte ceiling {byte_ceiling}" in error
    assert parent_completeness_unknown is True


def test_codex_attachment_streaming_parent_caps_fail_closed(tmp_path: Path, monkeypatch):
    sources = _load()
    lifecycle, session, _attachment = _codex_attachment_fixture(sources, tmp_path)
    signature = sources.file_signature(session)
    assert signature is not None
    rule = sources.SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]
    monkeypatch.setitem(rule, "max_parent_records", 1)

    events, error, parent_completeness_unknown = sources.bounded_codex_attachment_parent_events_from_path(
        lifecycle,
        session,
        signature,
        limits=sources.runtime_limits({}),
    )

    assert events == []
    assert error is not None and "record count exceeds" in error
    assert parent_completeness_unknown is True

    monkeypatch.setitem(rule, "max_parent_records", 100)
    monkeypatch.setitem(rule, "max_parent_probe_bytes", 1)
    events, error, parent_completeness_unknown = sources.bounded_codex_attachment_parent_events_from_path(
        lifecycle,
        session,
        signature,
        limits=sources.runtime_limits({}),
    )
    assert events == []
    assert error is not None and "byte ceiling" in error
    assert parent_completeness_unknown is True


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


def test_codex_attachment_malformed_transport_echo_fails_parent_completeness_closed(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    rows.insert(
        1,
        {
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "message": "Synthetic malformed transport envelope.",
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

    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)
    session_key = sources.cursor_unit_key("codex-sessions", session)
    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert result["parent_completeness_unknown"] == [session_key]
    assert result["unsupported"] == [attachment_key]
    assert attachment_key not in result["adapted_unit_receipts"]
    assert "unknown Codex user record envelope" in " ".join(result["errors"])


def _append_oversized_incomplete_codex_parent_row(
    sources,
    session: Path,
    attachment: Path,
    mutation: str,
    *,
    padding_size: int = 4096,
) -> bytes:
    if mutation == "hidden-second-session-meta":
        row = {
            "type": "session_meta",
            "payload": {
                "padding": "x" * padding_size,
                "id": "fixture-hidden-second-thread",
            },
        }
        encoded = json.dumps(row).encode("utf-8")
        assert encoded.index(b"fixture-hidden-second-thread") > 1024
    elif mutation == "unicode-escaped-second-reference":
        reference = sources.codex_attachment_reference_line(attachment)
        row = {
            "timestamp": "2026-07-13T01:00:09Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_text", "text": reference},
                    {"type": "input_text", "text": "x" * padding_size},
                ],
            },
        }
        serialized = json.dumps(row)
        escaped_reference = "".join(f"\\u{ord(character):04x}" for character in reference)
        serialized = serialized.replace(json.dumps(reference), f'"{escaped_reference}"', 1)
        encoded = serialized.encode("utf-8")
        assert b"pasted text file: " not in encoded
    else:
        raise AssertionError(f"unknown mutation fixture: {mutation}")
    assert len(encoded) > 1024
    with session.open("ab") as handle:
        handle.write(encoded + b"\n")
    return encoded


@pytest.mark.parametrize(
    "mutation",
    ["hidden-second-session-meta", "unicode-escaped-second-reference"],
)
def test_codex_attachment_unknown_parent_completeness_invalidates_cached_receipt(
    tmp_path: Path,
    monkeypatch,
    mutation: str,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rule = sources.SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]
    monkeypatch.setitem(rule, "max_parent_record_bytes", 1024)
    scan_rows = [
        {"source": "codex-sessions", "path": session},
        {"source": "codex-attachments", "path": attachment},
    ]
    _events, first = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=scan_rows,
    )
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)
    session_key = sources.cursor_unit_key("codex-sessions", session)
    assert attachment_key in first["adapted_unit_receipts"]

    _append_oversized_incomplete_codex_parent_row(sources, session, attachment, mutation)
    signature = sources.file_signature(session)
    assert signature is not None
    parent_events, parent_error, parent_completeness_unknown = sources.bounded_codex_attachment_parent_events_from_path(
        lifecycle,
        session,
        signature,
        limits=sources.runtime_limits({}),
    )
    assert parent_events == []
    assert parent_error is not None and "completeness is unknown" in parent_error
    assert parent_completeness_unknown is True

    events, second = sources.scan_regular_sources(
        lifecycle,
        first,
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=scan_rows,
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert second["parent_completeness_unknown"] == [session_key]
    assert second["unsupported"] == [attachment_key]
    assert attachment_key not in second["adapted_unit_receipts"]
    assert attachment_key not in second["files"]
    assert second["files"].get(session_key) != sources.file_signature(session)


@pytest.mark.parametrize(
    "mutation",
    ["hidden-second-session-meta", "unicode-escaped-second-reference"],
)
def test_codex_attachment_unknown_parent_completeness_keeps_receipt_unresolved_and_all_scope_partial(
    tmp_path: Path,
    monkeypatch,
    mutation: str,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rule = sources.SOURCE_ADAPTER_RULES["codex-pasted-text-attachment-v1"]
    _append_oversized_incomplete_codex_parent_row(
        sources,
        session,
        attachment,
        mutation,
        padding_size=int(rule["max_parent_record_bytes"]) + 4096,
    )
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)
    session_key = sources.cursor_unit_key("codex-sessions", session)

    events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=2,
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert cursor["scope"] == "partial:all"
    assert cursor["target_scope"] == "all"
    assert cursor["all_baseline_complete"] is False
    assert {attachment_key, session_key}.issubset(cursor["unresolved_units"])
    assert cursor["unsupported_units"][attachment_key] == sources.file_signature(attachment)
    assert attachment_key not in cursor["adapted_unit_receipts"]
    assert {"codex-attachments", "codex-sessions"}.issubset(cursor["adapter_gaps"])
    assert "bounded byte ceiling" in " ".join(cursor["source_errors"])
    assert sources.validate_source_adapter_cursor(cursor) == []


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


def test_codex_attachment_session_identity_ambiguity_invalidates_cached_receipt(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    scan_rows = [
        {"source": "codex-sessions", "path": session},
        {"source": "codex-attachments", "path": attachment},
    ]
    _events, first = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=scan_rows,
    )
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)
    assert attachment_key in first["adapted_unit_receipts"]
    session_rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    session_rows.insert(1, {"type": "session_meta", "payload": {"id": "fixture-second-thread"}})
    session.write_text("".join(json.dumps(row) + "\n" for row in session_rows), encoding="utf-8")

    events, second = sources.scan_regular_sources(
        lifecycle,
        first,
        days=None,
        budget=sources.ScanBudget(limit=2),
        rows=scan_rows,
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert second["unsupported"] == [attachment_key]
    assert attachment_key not in second["adapted_unit_receipts"]
    assert attachment_key not in second["files"]
    assert "session identity is ambiguous" in " ".join(second["errors"])


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


def test_codex_attachment_bounded_scan_converges_over_three_passes(tmp_path: Path):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    rows = [
        {"source": "codex-sessions", "path": session},
        {"source": "codex-attachments", "path": attachment},
    ]
    session_key = sources.cursor_unit_key("codex-sessions", session)
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)

    first_budget = sources.ScanBudget(limit=1)
    first_events, first = sources.scan_regular_sources(
        lifecycle,
        {"files": {}},
        days=None,
        budget=first_budget,
        rows=rows,
    )

    assert len(first_events) == 1
    assert first_events[0]["source"] == "codex-sessions"
    assert first_budget.used == 1
    assert first["pending_files"] == 1
    assert first["coverage"]["codex-attachments"]["pending"] == 1
    assert session_key in first["files"]
    assert attachment_key not in first["files"]
    assert attachment_key not in first["adapted_unit_receipts"]

    second_budget = sources.ScanBudget(limit=1)
    second_events, second = sources.scan_regular_sources(
        lifecycle,
        first,
        days=None,
        budget=second_budget,
        rows=rows,
    )
    second_receipts = json.dumps(second["adapted_unit_receipts"], sort_keys=True)

    assert len(second_events) == 1
    assert second_events[0]["source"] == "codex-attachments"
    assert second_budget.used == 1
    assert second["pending_files"] == 0
    assert second["errors"] == []
    assert second["unsupported"] == []
    assert attachment_key in second["files"]
    assert attachment_key in second["adapted_unit_receipts"]

    third_budget = sources.ScanBudget(limit=1)
    third_events, third = sources.scan_regular_sources(
        lifecycle,
        second,
        days=None,
        budget=third_budget,
        rows=rows,
    )

    assert third_events == []
    assert third_budget.used == 0
    assert third["pending_files"] == 0
    assert third["errors"] == []
    assert third["unsupported"] == []
    assert json.dumps(third["adapted_unit_receipts"], sort_keys=True) == second_receipts


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


def test_codex_attachment_ambiguous_session_identity_keeps_all_scope_partial(
    tmp_path: Path,
    monkeypatch,
):
    sources = _load()
    lifecycle, session, attachment = _codex_attachment_fixture(sources, tmp_path)
    session_rows = [json.loads(line) for line in session.read_text(encoding="utf-8").splitlines()]
    session_rows.insert(1, {"type": "session_meta", "payload": {"id": "fixture-second-thread"}})
    session.write_text("".join(json.dumps(row) + "\n" for row in session_rows), encoding="utf-8")
    monkeypatch.setattr(sources, "load_lifecycle_module", lambda: lifecycle)
    attachment_key = sources.cursor_unit_key("codex-attachments", attachment)

    events, cursor = sources.scan_native_sources(
        SimpleNamespace(cursor=tmp_path / "missing-cursor.json"),
        days=None,
        max_files=2,
    )

    assert not [event for event in events if event["source"] == "codex-attachments"]
    assert cursor["scope"] == "partial:all"
    assert cursor["all_baseline_complete"] is False
    assert attachment_key in cursor["unresolved_units"]
    assert attachment_key not in cursor["adapted_unit_receipts"]
    assert {"codex-attachments", "codex-sessions"}.issubset(cursor["adapter_gaps"])


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
