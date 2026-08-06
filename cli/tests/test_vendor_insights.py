"""Tests for scripts/vendor-insights.py — the mechanical half of /vendor-insights.

Every adapter is exercised against a synthetic store built in tmp_path (never the
live vendor stores), plus the exit-code honesty of `render` and the codex
resume-grouping semantics observed live on 2026-08-06 (resumed rollout files share
the parent session_meta.session_id and must aggregate, not drop)."""

import importlib.util
import json
import sqlite3
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"

_spec = importlib.util.spec_from_file_location("vendor_insights", _SCRIPTS / "vendor-insights.py")
vi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vi)

_ispec = importlib.util.spec_from_file_location("icvi_for_tests", _SCRIPTS / "insight-cross-vendor-ingest.py")
ingest = importlib.util.module_from_spec(_ispec)
_ispec.loader.exec_module(ingest)

OLD = datetime.now(timezone.utc) - timedelta(days=365)
WINDOW = datetime.now(timezone.utc) - timedelta(days=30)


def _fake_mod(**registry) -> types.SimpleNamespace:
    return types.SimpleNamespace(VENDOR_REGISTRY=registry)


# ─── registry contract ───────────────────────────────────────────────


def test_ingest_registry_covers_every_indexable_vendor():
    # The organ imports the ingest registry as its single path source; every
    # indexer must resolve against a registered vendor entry.
    for vendor in vi.INDEXERS:
        assert vendor in ingest.VENDOR_REGISTRY, f"indexer '{vendor}' missing from VENDOR_REGISTRY"


def test_ingest_has_gemini_adapter():
    # "every vendor must appear here; silence is not allowed" — gemini was the
    # silent estate until 2026-08-06.
    assert "gemini" in ingest.ADAPTERS
    assert "gemini" in ingest.VENDOR_REGISTRY


def test_agy_alias_resolves_to_antigravity():
    assert vi._resolve_vendor("agy") == "antigravity"


# ─── claude adapter (multi-root estate) ──────────────────────────────


def _write_claude_session(proj: Path, sid: str, n_user=2, n_assistant=3, tools=1):
    proj.mkdir(parents=True, exist_ok=True)
    lines = []
    ts = datetime.now(timezone.utc).isoformat()
    for _ in range(n_user):
        lines.append({"type": "user", "timestamp": ts, "cwd": "/w", "message": {"content": "hi there"}})
    for i in range(n_assistant):
        content = [{"type": "text", "text": "reply"}]
        if i < tools:
            content.append({"type": "tool_use", "name": "Bash"})
        lines.append({"type": "assistant", "timestamp": ts, "message": {"model": "opus-5", "content": content}})
    (proj / f"{sid}.jsonl").write_text("\n".join(json.dumps(rec) for rec in lines))


def test_claude_index_walks_multiple_roots(tmp_path):
    legacy = tmp_path / "legacy"
    runtime = tmp_path / "ws" / ".agent-runtime" / "claude" / "projects"
    _write_claude_session(legacy / "proj-a", "sess-legacy")
    _write_claude_session(runtime / "proj-b", "sess-runtime")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [legacy, runtime])
    sessions = vi._index_claude(mod, WINDOW, 10)
    assert {s["id"] for s in sessions} == {"sess-legacy", "sess-runtime"}
    by_id = {s["id"]: s for s in sessions}
    assert by_id["sess-legacy"]["user_msgs"] == 2
    assert by_id["sess-legacy"]["assistant_msgs"] == 3
    assert by_id["sess-legacy"]["tool_calls"] == 1
    assert by_id["sess-legacy"]["models"] == ["opus-5"]


def test_claude_estate_roots_includes_agent_runtime_glob(tmp_path, monkeypatch):
    legacy = tmp_path / ".claude" / "projects"
    legacy.mkdir(parents=True)
    ws_root = tmp_path / "Workspace" / "limen" / ".agent-runtime" / "claude" / "projects"
    ws_root.mkdir(parents=True)
    monkeypatch.setitem(
        ingest.VENDOR_REGISTRY["claude"],
        "extra_root_globs",
        [str(tmp_path / "Workspace" / "*" / ".agent-runtime" / "claude" / "projects")],
    )
    monkeypatch.setitem(ingest.VENDOR_REGISTRY["claude"], "path", legacy)
    roots = ingest.claude_estate_roots()
    assert legacy in roots
    assert ws_root in roots


# ─── codex adapter (resume grouping) ─────────────────────────────────


def _write_rollout(day_dir: Path, name: str, sid: str, n_user=1, n_assistant=2, tools=2):
    day_dir.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "session_meta", "payload": {"session_id": sid, "cwd": "/repo"}}]
    lines.append({"type": "turn_context", "payload": {"model": "gpt-5.6-sol"}})
    for _ in range(n_user):
        lines.append(
            {
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "go"}]},
            }
        )
    for _ in range(n_assistant):
        lines.append(
            {
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "ok"}]},
            }
        )
    for _ in range(tools):
        lines.append(
            {"type": "response_item", "payload": {"type": "function_call", "name": "shell", "arguments": "{}"}}
        )
    (day_dir / name).write_text("\n".join(json.dumps(rec) for rec in lines))


def _codex_mod(tmp_path: Path):
    return _fake_mod(
        codex={
            "path": tmp_path / "history.jsonl",
            "sessions_roots": [str(tmp_path / "sessions"), str(tmp_path / "archived_sessions")],
        }
    )


def test_codex_resumed_rollouts_group_into_one_logical_session(tmp_path):
    day = tmp_path / "sessions" / "2026" / "07" / "26"
    _write_rollout(day, "rollout-2026-07-26T05-00-00-aaa.jsonl", "sid-parent")
    _write_rollout(day, "rollout-2026-07-26T09-00-00-bbb.jsonl", "sid-parent")  # resume, same parent sid
    _write_rollout(day, "rollout-2026-07-26T10-00-00-ccc.jsonl", "sid-other")
    sessions = vi._index_codex(_codex_mod(tmp_path), WINDOW, 10)
    assert len(sessions) == 2
    parent = next(s for s in sessions if s["id"] == "sid-parent")
    assert parent["user_msgs"] == 2  # aggregated across both files
    assert parent["assistant_msgs"] == 4
    assert parent["tool_calls"] == 4
    assert parent["started_at"].startswith("2026-07-26T05:00:00")  # earliest file wins
    assert parent["models"] == ["gpt-5.6-sol"]


def test_codex_cat_concatenates_all_rollouts_of_a_session(tmp_path):
    day = tmp_path / "sessions" / "2026" / "07" / "26"
    _write_rollout(day, "rollout-2026-07-26T05-00-00-aaa.jsonl", "sid-parent")
    _write_rollout(day, "rollout-2026-07-26T09-00-00-bbb.jsonl", "sid-parent")
    text = vi._cat_codex(_codex_mod(tmp_path), "sid-parent", 100_000)
    assert text is not None
    assert text.count("===== rollout file:") == 2
    assert "[tool: shell]" in text


# ─── copilot adapter (authoritative session-state, stub honesty) ─────


def _copilot_mod(tmp_path: Path):
    return _fake_mod(
        copilot={"path": tmp_path / "session-store.db", "session_state_root": str(tmp_path / "session-state")}
    )


def test_copilot_index_reads_workspace_yaml_and_events(tmp_path):
    live = tmp_path / "session-state" / "sid-live"
    live.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    (live / "workspace.yaml").write_text(
        f"id: sid-live\ncwd: /repo\ncreated_at: '{now}'\nupdated_at: '{now}'\nsummary_count: 3\n"
    )
    events = [
        {"type": "session.start", "timestamp": now, "data": {"model": "gpt-x"}},
        {"type": "user.message", "timestamp": now, "data": {"content": "do the thing"}},
        {
            "type": "assistant.message",
            "timestamp": now,
            "data": {"content": "done", "model": "gpt-x", "toolRequests": [{"name": "bash"}]},
        },
        {"type": "tool.execution_start", "timestamp": now, "data": {"toolName": "bash"}},
    ]
    (live / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    stub = tmp_path / "session-state" / "sid-stub"
    stub.mkdir(parents=True)
    (stub / "workspace.yaml").write_text(
        f"id: sid-stub\ncwd: /other\ncreated_at: '{now}'\nupdated_at: '{now}'\nsummary_count: 0\n"
    )
    sessions = vi._index_copilot(_copilot_mod(tmp_path), WINDOW, 10)
    by_id = {s["id"]: s for s in sessions}
    assert set(by_id) == {"sid-live", "sid-stub"}
    assert by_id["sid-live"]["user_msgs"] == 1
    assert by_id["sid-live"]["assistant_msgs"] == 1
    assert by_id["sid-live"]["tool_calls"] == 1
    assert by_id["sid-live"]["models"] == ["gpt-x"]
    assert by_id["sid-stub"]["user_msgs"] == 0


def test_copilot_cat_reports_stub_sessions_honestly(tmp_path):
    stub = tmp_path / "session-state" / "sid-stub"
    stub.mkdir(parents=True)
    (stub / "workspace.yaml").write_text("id: sid-stub\n")
    text = vi._cat_copilot(_copilot_mod(tmp_path), "sid-stub", 1000)
    assert "stub session" in text


# ─── opencode adapter (sqlite, read-only) ────────────────────────────


def _make_opencode_db(db_path: Path):
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE session (id TEXT, directory TEXT, title TEXT, model TEXT, time_created INT, time_updated INT)"
    )
    con.execute("CREATE TABLE message (id TEXT, session_id TEXT, data TEXT, time_created INT)")
    con.execute("CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT, data TEXT, time_created INT)")
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    con.execute(
        "INSERT INTO session VALUES ('s1', '/repo', 't', ?, ?, ?)",
        (json.dumps({"providerID": "opencode", "modelID": "nemotron-3"}), now_ms, now_ms + 1000),
    )
    con.execute("INSERT INTO message VALUES ('m1', 's1', ?, ?)", (json.dumps({"role": "user"}), now_ms))
    con.execute("INSERT INTO message VALUES ('m2', 's1', ?, ?)", (json.dumps({"role": "assistant"}), now_ms + 1))
    con.execute(
        "INSERT INTO part VALUES ('p1', 'm1', 's1', ?, ?)", (json.dumps({"type": "text", "text": "hello"}), now_ms)
    )
    con.execute(
        "INSERT INTO part VALUES ('p2', 'm2', 's1', ?, ?)",
        (json.dumps({"type": "tool", "tool": "read", "state": {"status": "completed"}}), now_ms + 2),
    )
    con.commit()
    con.close()


def test_opencode_index_and_cat(tmp_path):
    db = tmp_path / "opencode.db"
    _make_opencode_db(db)
    mod = _fake_mod(opencode={"path": db})
    sessions = vi._index_opencode(mod, WINDOW, 10)
    assert len(sessions) == 1
    s = sessions[0]
    assert (s["user_msgs"], s["assistant_msgs"], s["tool_calls"]) == (1, 1, 1)
    assert s["models"] == ["nemotron-3"]
    text = vi._cat_opencode(mod, "s1", 10_000)
    assert "hello" in text
    assert "[tool: read]" in text


# ─── gemini adapter ──────────────────────────────────────────────────


def _write_gemini_session(slug_dir: Path, sid: str):
    chats = slug_dir / "chats"
    chats.mkdir(parents=True)
    (slug_dir / ".project_root").write_text("/real/cwd\n")
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        {"sessionId": sid, "projectHash": "ab" * 32, "startTime": now, "lastUpdated": now, "kind": "main"},
        {"id": "u1", "type": "user", "timestamp": now, "content": [{"text": "question"}]},
        {
            "id": "g1",
            "type": "gemini",
            "timestamp": now,
            "content": "answer",
            "model": "gemini-3.5-flash",
            "toolCalls": [{"id": "t1", "name": "read_file", "args": {}, "status": "success"}],
        },
    ]
    (chats / f"session-{sid}.jsonl").write_text("\n".join(json.dumps(rec) for rec in lines))


def test_gemini_index_and_cat(tmp_path):
    _write_gemini_session(tmp_path / "proj-slug", "gsid")
    mod = _fake_mod(gemini={"path": tmp_path})
    sessions = vi._index_gemini(mod, WINDOW, 10)
    assert len(sessions) == 1
    s = sessions[0]
    assert s["id"] == "gsid"
    assert s["cwd"] == "/real/cwd"
    assert (s["user_msgs"], s["assistant_msgs"], s["tool_calls"]) == (1, 1, 1)
    assert s["models"] == ["gemini-3.5-flash"]
    text = vi._cat_gemini(mod, "gsid", 10_000)
    assert "question" in text
    assert "[tool: read_file]" in text


# ─── antigravity adapter ─────────────────────────────────────────────


def _make_agy_estate(root: Path, cid: str):
    conv = root / "conversations"
    conv.mkdir(parents=True)
    con = sqlite3.connect(conv / f"{cid}.db")
    con.execute(
        "CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, metadata BLOB)"
    )
    # type 14 = task init, 15 = assistant wrapper, 8 = view_file result, 132 = send_message
    msg_blob = b"\x08\x01xxgbT3kOOYsend_message" + json.dumps({"Message": "final answer"}).encode() + b"\x00"
    con.execute("INSERT INTO steps VALUES (1, 14, 3, ?, ?)", (b"Task Objective: do it", b""))
    con.execute("INSERT INTO steps VALUES (2, 15, 3, ?, ?)", (b"wrapper", b""))
    con.execute("INSERT INTO steps VALUES (3, 8, 3, ?, ?)", (b"file bytes", b""))
    con.execute("INSERT INTO steps VALUES (4, 132, 3, ?, ?)", (msg_blob, b""))
    con.commit()
    con.close()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    hist = [
        {"display": "please do it", "timestamp": now_ms, "workspace": "/agy/repo", "conversationId": cid},
        {"display": "and again", "timestamp": now_ms + 1000, "workspace": "/agy/repo", "conversationId": cid},
    ]
    (root / "history.jsonl").write_text("\n".join(json.dumps(h) for h in hist))


def test_antigravity_index_and_cat(tmp_path):
    root = tmp_path / "antigravity-cli"
    _make_agy_estate(root, "cid-1")
    mod = _fake_mod(antigravity={"path": root})
    sessions = vi._index_antigravity(mod, WINDOW, 10)
    assert len(sessions) == 1
    s = sessions[0]
    assert s["id"] == "cid-1"
    assert s["user_msgs"] == 2  # from history.jsonl
    assert s["assistant_msgs"] == 1  # send_message steps
    assert s["cwd"] == "/agy/repo"
    text = vi._cat_antigravity(mod, "cid-1", 10_000)
    assert "please do it" in text
    assert "final answer" in text
    assert "[tool: view_file]" in text


# ─── render: exit-code honesty + section rendering ───────────────────


def test_render_exits_2_without_facets_or_narrative(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path)
    (tmp_path / "codex").mkdir()
    (tmp_path / "codex" / "index.json").write_text(json.dumps({"vendor": "codex", "window": {}, "sessions": []}))
    assert vi.cmd_render("codex") == 2
    assert "skill half hasn't run" in capsys.readouterr().err


def test_render_missing_index_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path)
    assert vi.cmd_render("codex") == 2


def test_render_writes_report_with_sections_and_coverage_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path)
    vdir = tmp_path / "codex"
    (vdir / "facets").mkdir(parents=True)
    index = {
        "vendor": "codex",
        "window": {"start": "2026-07-07T00:00:00", "end": "2026-08-06T00:00:00"},
        "sessions": [
            {"id": "a", "user_msgs": 3, "assistant_msgs": 9, "tool_calls": 12, "models": ["gpt-5.6-sol"]},
            {"id": "b", "user_msgs": 1, "assistant_msgs": 2, "tool_calls": 3, "models": []},
        ],
    }
    (vdir / "index.json").write_text(json.dumps(index))
    facet = {
        "session_id": "a",
        "outcome": "fully_achieved",
        "session_type": "multi_task",
        "friction_counts": {"buggy_code": 1},
        "user_satisfaction_counts": {"likely_satisfied": 2},
        "goal_categories": {"debugging_or_fixing": 1},
    }
    (vdir / "facets" / "a.json").write_text(json.dumps(facet))
    narrative = {
        "tldr": "one line",
        "at_a_glance": {"whats_working": "capsules"},
        "areas": [{"name": "Campaign", "session_count": 2, "description": "desc"}],
        "friction": [{"category": "churn", "description": "d", "examples": ["e1"]}],
        "suggestions": [{"title": "t", "detail": "d"}],
    }
    (vdir / "narrative.json").write_text(json.dumps(narrative))
    assert vi.cmd_render("codex") == 0
    html_text = (vdir / "report.html").read_text()
    for expected in ("one line", "Campaign", "fully_achieved", "buggy_code", "likely_satisfied", "churn"):
        assert expected in html_text
    # No silent caps: 1 of 2 sessions faceted must be named in coverage notes.
    assert "1 of 2 indexed sessions were not faceted" in html_text
    # Absent narrative sections are named, not hidden.
    assert "interaction_style" in html_text


def test_render_escapes_html_in_narrative(tmp_path, monkeypatch):
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path)
    vdir = tmp_path / "codex"
    vdir.mkdir()
    (vdir / "index.json").write_text(json.dumps({"vendor": "codex", "window": {}, "sessions": []}))
    (vdir / "narrative.json").write_text(json.dumps({"tldr": "<script>alert(1)</script>"}))
    assert vi.cmd_render("codex") == 0
    html_text = (vdir / "report.html").read_text()
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;" in html_text


# ─── ingest gemini adapter (counts only) ─────────────────────────────


def test_ingest_gemini_counts_sessions_and_flags_no_reply(tmp_path, monkeypatch):
    slug = tmp_path / "proj" / "chats"
    slug.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    header = {"sessionId": "x", "startTime": now, "lastUpdated": now}
    user_only = [header, {"type": "user", "timestamp": now, "content": [{"text": "q"}]}]
    (slug / "session-x.jsonl").write_text("\n".join(json.dumps(r) for r in user_only))
    monkeypatch.setitem(ingest.VENDOR_REGISTRY["gemini"], "path", tmp_path)
    packet = ingest._ingest_gemini(WINDOW)
    assert packet["sessions_seen"] == 1
    signals = {s["signal"]: s["count"] for s in packet["friction_signals"]}
    assert signals.get("no_reply_sessions") == 1
