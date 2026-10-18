"""Tests for scripts/vendor-insights.py — the mechanical half of /vendor-insights.

Every adapter is exercised against a synthetic store built in tmp_path (never the
live vendor stores), plus the exit-code honesty of `render` and the codex
resume-grouping semantics observed live on 2026-08-06 (resumed rollout files share
the parent session_meta.session_id and must aggregate, not drop)."""

import base64
import glob
import importlib.util
import json
import sqlite3
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"

_spec = importlib.util.spec_from_file_location("vendor_insights", _SCRIPTS / "vendor-insights.py")
vi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vi)

_ispec = importlib.util.spec_from_file_location("icvi_for_tests", _SCRIPTS / "insight-cross-vendor-ingest.py")
ingest = importlib.util.module_from_spec(_ispec)
_ispec.loader.exec_module(ingest)

OLD = datetime.now(timezone.utc) - timedelta(days=365)
WINDOW = datetime.now(timezone.utc) - timedelta(days=30)
TRUNCATED = "[... truncated at max-chars ...]\n"


def _fake_mod(**registry) -> types.SimpleNamespace:
    """Stand-in for the ingest organ.

    The adapters resolve stores through the ingest module's shared resolvers
    (opencode_estate_stores / gemini_estate_roots) rather than reading a fixed
    path, so the fixture models that contract — including the optional
    extra_root_globs — instead of handing the adapters a bare registry.
    """
    mod = types.SimpleNamespace(VENDOR_REGISTRY=registry)

    def gemini_estate_roots() -> list[Path]:
        meta = registry.get("gemini", {})
        roots = [meta["path"]] if meta.get("path") is not None and meta["path"].is_dir() else []
        for extra in meta.get("extra_root_globs", []):
            hits = sorted(glob.glob(extra))
            roots.extend(Path(p) for p in hits if Path(p).is_dir())
        return roots

    def opencode_estate_stores() -> list[Path]:
        meta = registry.get("opencode", {})
        stores: list[Path] = []
        primary = meta.get("path")
        if primary is not None and Path(primary).exists():
            stores.append(Path(primary))
        for extra in meta.get("extra_root_globs", []):
            for hit in sorted(glob.glob(extra)):
                db = Path(hit) / "opencode.db"
                if db.exists() and db not in stores:
                    stores.append(db)
        return stores

    mod.gemini_estate_roots = gemini_estate_roots
    mod.opencode_estate_stores = opencode_estate_stores
    return mod


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
    sessions = vi._index_claude(mod, WINDOW, 10).sessions
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


def _write_rollout_messages(day_dir: Path, name: str, sid: str, messages: list[tuple[str, str]]):
    """A rollout holding exactly the given (role, text) response_item messages."""
    day_dir.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "session_meta", "payload": {"session_id": sid, "cwd": "/repo"}}]
    for role, text in messages:
        lines.append(
            {
                "type": "response_item",
                "payload": {"type": "message", "role": role, "content": [{"type": "input_text", "text": text}]},
            }
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
    sessions = vi._index_codex(_codex_mod(tmp_path), WINDOW, 10).sessions
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


# A genuine zstd frame holding one session_meta (id "sid-zst"), one user turn and one assistant turn, so
# the reader is exercised against real compressed bytes without needing an encoder at test time.
_ZST_ROLLOUT_B64 = (
    "KLUv/WCOAPUFAGILIh1wJ2oDgHjVLwnTlqbYEeKzxatKPlEiojnS6vTBBMRahRWgpL7AdA3xb5WQ"
    "Hou76ObZ438K6wYMiT8iQ7zKGqV7TMzJ2g9jTcKcFQZeY5eUSGDFbXpTD+Uviiobzm+EvGj4qelW"
    "xFqnyUqAOfYHAAj+8GDFIUeV5qQzwp01MlLx98+Kc2r2DgETAKA2GMounDJ6oGw5ZGS4UszqlQCA"
    "uWeq9TNGFK+HUMuQvsAU6EthT83GSC3LXKyvTTI="
)


def _write_zst_rollout(dir_: Path, name: str, payload: bytes | None = None):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / name).write_bytes(base64.b64decode(_ZST_ROLLOUT_B64) if payload is None else payload)


def _force_decoder(monkeypatch, decoder: str):
    """Pin which zstd decoder the reader may use. A decoder this interpreter/host lacks is a visible skip,
    never a silent pass: python needs 3.14+, cli needs the zstd binary, none removes both."""
    if decoder == "python":
        if vi._zstd_module() is None:
            pytest.skip("compression.zstd needs Python 3.14+ (this interpreter predates it)")
        monkeypatch.setattr(vi, "_zstd_binary", lambda: None)
    elif decoder == "cli":
        if vi._zstd_binary() is None:
            pytest.skip("the zstd binary is not installed on this host")
        monkeypatch.setattr(vi, "_zstd_module", lambda: None)
    else:
        monkeypatch.setattr(vi, "_zstd_module", lambda: None)
        monkeypatch.setattr(vi, "_zstd_binary", lambda: None)


@pytest.mark.parametrize("decoder", ["python", "cli"])
@pytest.mark.parametrize("named_by_sid", [True, False], ids=["name-carries-sid", "header-match"])
def test_codex_cat_reads_a_zst_compressed_rollout(tmp_path, monkeypatch, decoder, named_by_sid):
    # Codex compresses old sessions to rollout-*.jsonl.zst. The reader globbed only *.jsonl, so 8 of 85
    # indexed codex sessions read as "not found" (limen#3083). A resumed session's file name carries its
    # own id, so the header-match case must decompress to find the parent session_id.
    _force_decoder(monkeypatch, decoder)
    name = (
        "rollout-2026-10-10T12-48-38-sid-zst.jsonl.zst" if named_by_sid else "rollout-2026-10-10T12-48-38-aaa.jsonl.zst"
    )
    _write_zst_rollout(tmp_path / "archived_sessions", name)
    text = vi._cat_codex(_codex_mod(tmp_path), "sid-zst", 10_000)
    assert "--- user ---\nwhy was the history reported missing?" in text
    assert "it was compressed to jsonl.zst" in text


@pytest.mark.parametrize("decoder", ["python", "cli"])
def test_codex_cat_corrupt_zst_fails_loudly_never_renders_empty(tmp_path, monkeypatch, decoder):
    _force_decoder(monkeypatch, decoder)
    _write_zst_rollout(
        tmp_path / "archived_sessions", "rollout-2026-10-10T12-48-38-sid-zst.jsonl.zst", b"this is not a zstd frame"
    )
    with pytest.raises(RuntimeError, match="zstd could not decompress"):
        vi._cat_codex(_codex_mod(tmp_path), "sid-zst", 10_000)


def test_codex_cat_zst_without_a_decompressor_fails_loudly(tmp_path, monkeypatch):
    _force_decoder(monkeypatch, "none")
    _write_zst_rollout(tmp_path / "archived_sessions", "rollout-2026-10-10T12-48-38-sid-zst.jsonl.zst")
    with pytest.raises(RuntimeError, match="no decompressor is available"):
        vi._cat_codex(_codex_mod(tmp_path), "sid-zst", 10_000)


def test_codex_uninspectable_zst_neighbour_does_not_break_a_plain_session(tmp_path, monkeypatch):
    # Without a decompressor an unrelated archived file cannot be header-peeked; that must not turn an
    # ordinary plain-text session into an error.
    _force_decoder(monkeypatch, "none")
    _write_rollout(
        tmp_path / "sessions" / "2026" / "10" / "18", "rollout-2026-10-18T05-00-00-sid-plain.jsonl", "sid-plain"
    )
    _write_zst_rollout(tmp_path / "archived_sessions", "rollout-2026-10-10T12-48-38-other.jsonl.zst")
    text = vi._cat_codex(_codex_mod(tmp_path), "sid-plain", 10_000)
    assert "[tool: shell]" in text


def test_codex_not_found_is_an_error_while_a_compressed_rollout_is_uninspectable(tmp_path, monkeypatch):
    # Reporting "session not found" while blind to a compressed file is the original defect.
    _force_decoder(monkeypatch, "none")
    _write_zst_rollout(tmp_path / "archived_sessions", "rollout-2026-10-10T12-48-38-other.jsonl.zst")
    with pytest.raises(RuntimeError, match="cannot be reported as not found"):
        vi._cat_codex(_codex_mod(tmp_path), "sid-zst", 10_000)


def test_cat_session_exits_1_with_a_named_error_when_the_decompressor_is_missing(tmp_path, monkeypatch, capsys):
    _force_decoder(monkeypatch, "none")
    _write_zst_rollout(tmp_path / "archived_sessions", "rollout-2026-10-10T12-48-38-sid-zst.jsonl.zst")
    assert vi.cmd_cat(_codex_mod(tmp_path), "codex", "sid-zst", 10_000) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "ERROR:" in captured.err and "no decompressor is available" in captured.err


def test_codex_session_files_ignore_non_rollout_suffixes(tmp_path):
    (tmp_path / "archived_sessions").mkdir()
    (tmp_path / "archived_sessions" / "rollout-2026-10-10T12-48-38-sid-zst.jsonl.bak").write_bytes(b"x")
    assert vi._codex_session_files(_codex_mod(tmp_path), "sid-zst") == []
    assert vi._cat_codex(_codex_mod(tmp_path), "sid-zst", 10_000) is None


def test_codex_cat_omits_harness_injected_context_and_keeps_the_operator_turn(tmp_path):
    # Measured 2026-10-18: the first operator turn sat a median 67,627 chars into a codex render,
    # so a bounded read of 40 of 68 sessions held no operator speech. The injected blocks are
    # named with their size and omitted, so the cap is spent on the conversation.
    day = tmp_path / "sessions" / "2026" / "10" / "18"
    _write_rollout_messages(
        day,
        "rollout-2026-10-18T05-00-00-aaa.jsonl",
        "sid-injected",
        [
            ("developer", "D" * 60_000),
            ("user", "# AGENTS.md instructions for /home/x\n" + "A" * 9_000),
            ("project-doc", "P" * 4_000),
            ("user", '<external_codex_apps_open_page>{"page_id":null}</external_codex_apps_open_page>'),
            ("user", "<environment_context>\n  <cwd>/repo</cwd>\n</environment_context>"),
            ("user", "why does the gate go red on a clean tree?"),
            ("assistant", "the cache key omits the lockfile"),
        ],
    )
    text = vi._cat_codex(_codex_mod(tmp_path), "sid-injected", 2_000)
    assert "why does the gate go red on a clean tree?" in text
    assert "the cache key omits the lockfile" in text
    assert "DDDDDDDD" not in text and "AAAAAAAA" not in text and "PPPPPPPP" not in text
    assert "[omitted harness-injected developer message: 60000 chars]" in text
    assert "[omitted harness-injected project-doc message: 4000 chars]" in text
    assert text.count("[omitted harness-injected user message:") == 3
    assert TRUNCATED not in text  # once the preamble is named rather than rendered, the conversation fits


def test_codex_cat_keeps_an_operator_turn_that_only_quotes_injected_markup(tmp_path):
    # The filter is a prefix test on the message, never a substring test: an operator who
    # mentions AGENTS.md mid-sentence must still be read.
    day = tmp_path / "sessions" / "2026" / "10" / "18"
    _write_rollout_messages(
        day,
        "rollout-2026-10-18T05-00-00-bbb.jsonl",
        "sid-quote",
        [("user", "please read # AGENTS.md instructions for me"), ("assistant", "ok")],
    )
    text = vi._cat_codex(_codex_mod(tmp_path), "sid-quote", 2_000)
    assert "please read # AGENTS.md instructions for me" in text
    assert "[omitted" not in text


def test_codex_cat_cap_clips_the_message_that_crosses_it(tmp_path):
    # --max-chars 1200 once returned 55.8 KB: the whole message was appended before the cap was tested.
    day = tmp_path / "sessions" / "2026" / "10" / "18"
    _write_rollout_messages(day, "rollout-2026-10-18T05-00-00-ccc.jsonl", "sid-big", [("assistant", "x" * 10_000)])
    text = vi._cat_codex(_codex_mod(tmp_path), "sid-big", 500)
    assert text.endswith(TRUNCATED)
    assert len(text) == 500 + len(TRUNCATED)


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
    sessions = vi._index_copilot(_copilot_mod(tmp_path), WINDOW, 10).sessions
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


def _copilot_session(tmp_path: Path, sid: str, events: list[dict]) -> None:
    sdir = tmp_path / "session-state" / sid
    sdir.mkdir(parents=True)
    now = datetime.now(timezone.utc).isoformat()
    (sdir / "workspace.yaml").write_text(f"id: {sid}\ncwd: /w\ncreated_at: '{now}'\nupdated_at: '{now}'\n")
    (sdir / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))


def test_copilot_quota_failure_is_counted_and_rendered(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    _copilot_session(
        tmp_path,
        "sid-quota",
        [
            {"type": "session.start", "timestamp": now, "data": {}},
            {"type": "user.message", "timestamp": now, "data": {"content": "status please"}},
            {"type": "model.model_call_failure", "timestamp": now, "data": {"modelCall": {"status": 402}}},
            {
                "type": "session.error",
                "timestamp": now,
                "data": {
                    "errorType": "quota",
                    "statusCode": 402,
                    "errorCode": "quota_exceeded",
                    "message": "quota (Request ID: SECRET-ID)",
                },
            },
            {"type": "session.shutdown", "timestamp": now, "data": {}},
        ],
    )
    mod = _copilot_mod(tmp_path)
    s = vi._index_copilot(mod, WINDOW, 10).sessions[0]
    assert (s["user_msgs"], s["assistant_msgs"], s["errors"], s["error_codes"]) == (1, 0, 1, ["quota_exceeded"])
    text = vi._cat_copilot(mod, "sid-quota", 10_000)
    assert "status please" in text
    assert "errorType=quota, statusCode=402, errorCode=quota_exceeded" in text
    assert "SECRET-ID" not in text  # free-text message (request ids) is never echoed


def test_copilot_lifecycle_only_session_is_not_reported_missing(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    _copilot_session(
        tmp_path,
        "sid-empty",
        [
            {"type": "session.start", "timestamp": now, "data": {}},
            {"type": "session.mode_changed", "timestamp": now, "data": {}},
            {"type": "session.shutdown", "timestamp": now, "data": {}},
        ],
    )
    text = vi._cat_copilot(_copilot_mod(tmp_path), "sid-empty", 10_000)
    assert text is not None
    assert "lifecycle-only session" in text
    assert "session.mode_changed×1, session.shutdown×1, session.start×1" in text


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
    sessions = vi._index_opencode(mod, WINDOW, 10).sessions
    assert len(sessions) == 1
    s = sessions[0]
    assert (s["user_msgs"], s["assistant_msgs"], s["tool_calls"]) == (1, 1, 1)
    assert s["models"] == ["nemotron-3"]
    text = vi._cat_opencode(mod, "s1", 10_000)
    assert "hello" in text
    assert "[tool: read]" in text


def _make_opencode_v2_db(db_path: Path):
    """v2 schema as measured 2026-10-18: user/synthetic/system keep `text` at the TOP LEVEL of data,
    only assistant rows carry `content` blocks."""
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE session_v2 (id TEXT PRIMARY KEY, directory TEXT, title TEXT, model TEXT, cost REAL, "
        "tokens_input INT, tokens_output INT, time_created INT, time_updated INT)"
    )
    con.execute(
        "CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, seq INT, "
        "time_created INT, time_updated INT, data TEXT)"
    )
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    con.execute("INSERT INTO session_v2 VALUES ('v2s', '/repo', 't', 'm', 0, 1, 1, ?, ?)", (now_ms, now_ms + 1000))
    rows = [
        ("m1", "system", {"text": "S" * 3_000}),
        ("m2", "user", {"text": "why is the gate red on a clean tree?", "agents": [], "files": []}),
        ("m3", "synthetic", {"text": "<system-reminder>\nYou are in Plan mode. " + "R" * 400 + "\n</system-reminder>"}),
        ("m3b", "synthetic", {"text": "The following shell command was executed by the user: git status"}),
        (
            "m4",
            "assistant",
            {
                "content": [
                    {"type": "text", "text": "the cache key omits the lockfile"},
                    {"type": "tool", "name": "read"},
                ]
            },
        ),
    ]
    for seq, (mid, kind, data) in enumerate(rows):
        con.execute(
            "INSERT INTO session_message VALUES (?, 'v2s', ?, ?, ?, ?, ?)",
            (mid, kind, seq, now_ms + seq, now_ms + seq, json.dumps(data)),
        )
    con.commit()
    con.close()


def test_opencode_v2_cat_renders_top_level_user_text_and_omits_injected_system(tmp_path):
    # Measured 2026-10-18: 206 user messages across 59 opencode sessions were never rendered, because the
    # reader walked only data["content"]. Operator turns (where corrections live) were invisible.
    db = tmp_path / "opencode.db"
    _make_opencode_v2_db(db)
    text = vi._cat_opencode(_fake_mod(opencode={"path": db}), "v2s", 10_000)
    assert "--- user ---\nwhy is the gate red on a clean tree?" in text
    assert "--- synthetic ---\nThe following shell command was executed by the user: git status" in text
    assert "the cache key omits the lockfile" in text and "[tool: read]" in text
    assert "SSSSSSSS" not in text
    assert "[omitted harness-injected system message: 3000 chars]" in text
    # a synthetic row that is the harness's own <system-reminder> wrapper is omitted too, while a
    # synthetic row recording a shell command the operator ran (asserted above) stays visible
    assert "RRRRRRRR" not in text
    assert "[omitted harness-injected synthetic message:" in text


def test_opencode_cat_cap_clips_the_message_that_crosses_it(tmp_path):
    db = tmp_path / "opencode.db"
    _make_opencode_db(db)
    con = sqlite3.connect(db)
    con.execute("UPDATE part SET data = ? WHERE id = 'p1'", (json.dumps({"type": "text", "text": "h" * 5_000}),))
    con.commit()
    con.close()
    text = vi._cat_opencode(_fake_mod(opencode={"path": db}), "s1", 300)
    assert text.endswith(TRUNCATED)
    assert len(text) == 300 + len(TRUNCATED)


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
    sessions = vi._index_gemini(mod, WINDOW, 10).sessions
    assert len(sessions) == 1
    s = sessions[0]
    assert s["id"] == "gsid"
    assert s["cwd"] == "/real/cwd"
    assert (s["user_msgs"], s["assistant_msgs"], s["tool_calls"]) == (1, 1, 1)
    assert s["models"] == ["gemini-3.5-flash"]
    text = vi._cat_gemini(mod, "gsid", 10_000)
    assert "question" in text
    assert "[tool: read_file]" in text


def test_gemini_cat_cap_clips_the_message_that_crosses_it(tmp_path):
    _write_gemini_session(tmp_path / "proj-slug", "gsid-big")
    path = tmp_path / "proj-slug" / "chats" / "session-gsid-big.jsonl"
    lines = path.read_text().splitlines()
    big = json.loads(lines[1])
    big["content"] = [{"text": "q" * 5_000}]
    path.write_text("\n".join([lines[0], json.dumps(big), *lines[2:]]))
    text = vi._cat_gemini(_fake_mod(gemini={"path": tmp_path}), "gsid-big", 300)
    assert text.endswith(TRUNCATED)
    assert len(text) == 300 + len(TRUNCATED)


def test_gemini_window_uses_header_time_not_file_mtime(tmp_path):
    # A freshly touched file holding an old conversation must stay out of the window.
    _write_gemini_session(tmp_path / "proj-slug", "gsid-old")
    path = tmp_path / "proj-slug" / "chats" / "session-gsid-old.jsonl"
    lines = path.read_text().splitlines()
    header = json.loads(lines[0])
    header["startTime"] = header["lastUpdated"] = OLD.isoformat()
    path.write_text("\n".join([json.dumps(header), *lines[1:]]))
    result = vi._index_gemini(_fake_mod(gemini={"path": tmp_path}), WINDOW, 10)
    assert result.sessions == []
    assert result.total_in_window == 0


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
    sessions = vi._index_antigravity(mod, WINDOW, 10).sessions
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


def _pb_len(field_no: int, payload: bytes) -> bytes:
    """Encode one length-delimited protobuf field (enough wire format for fixtures)."""

    def varint(n: int) -> bytes:
        out = bytearray()
        while True:
            b = n & 0x7F
            n >>= 7
            out.append(b | (0x80 if n else 0))
            if not n:
                return bytes(out)

    return varint(field_no << 3 | 2) + varint(len(payload)) + payload


def _agy_call(name: str, args: dict) -> bytes:
    # Measured 2026-10-17 shape of a type-132 step: field 5 → 4 (1 id, 2 name, 3 JSON args),
    # plus an unrelated sibling (field 140) that the decoder must ignore.
    header = _pb_len(1, b"call-01") + _pb_len(2, name.encode()) + _pb_len(3, json.dumps(args).encode())
    return b"\x08\x01" + _pb_len(5, _pb_len(4, header)) + _pb_len(140, b"\x0a\x03abc")


def test_antigravity_decodes_type_132_as_tool_calls_not_messages(tmp_path):
    root = tmp_path / "antigravity-cli"
    conv = root / "conversations"
    conv.mkdir(parents=True)
    con = sqlite3.connect(conv / "cid-pb.db")
    con.execute(
        "CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, metadata BLOB)"
    )
    run = _agy_call("run_command", {"CommandLine": "ls", "toolSummary": "List   the\nrepo", "toolAction": "x"})
    say = _agy_call("send_message", {"Message": "all done", "Recipient": "user", "toolSummary": "s"})
    con.execute("INSERT INTO steps VALUES (1, 132, 3, ?, ?)", (run, b""))
    con.execute("INSERT INTO steps VALUES (2, 132, 3, ?, ?)", (say, b""))
    con.execute("INSERT INTO steps VALUES (3, 15, 3, ?, ?)", (b"wrapper", b""))
    con.commit()
    con.close()
    mod = _fake_mod(antigravity={"path": root})
    s = vi._index_antigravity(mod, WINDOW, 10).sessions[0]
    assert (s["assistant_msgs"], s["tool_calls"], s["other_steps"]) == (1, 1, 1)
    text = vi._cat_antigravity(mod, "cid-pb", 10_000)
    assert "[tool: run_command — List the repo]" in text  # summary collapsed to one line
    assert "--- assistant (send_message) ---\nall done" in text
    assert "CommandLine" not in text  # args other than the summary never leak into the excerpt


def test_antigravity_undecodable_blob_reports_shape_not_missing(tmp_path):
    root = tmp_path / "antigravity-cli"
    conv = root / "conversations"
    conv.mkdir(parents=True)
    con = sqlite3.connect(conv / "cid-opaque.db")
    con.execute(
        "CREATE TABLE steps (idx INTEGER PRIMARY KEY, step_type INT, status INT, step_payload BLOB, metadata BLOB)"
    )
    con.execute("INSERT INTO steps VALUES (1, 15, 3, ?, ?)", (b"\xff\xfe", b""))
    con.execute("INSERT INTO steps VALUES (2, 101, 3, ?, ?)", (b"\x00", b""))
    con.commit()
    con.close()
    text = vi._cat_antigravity(_fake_mod(antigravity={"path": root}), "cid-opaque", 10_000)
    assert text is not None
    assert "no decodable messages or tool calls" in text
    assert "15×1, 101×1" in text


def test_pb_fields_rejects_truncated_input():
    with pytest.raises(ValueError):
        list(vi._pb_fields(b"\x2a\x10abc"))  # field 5, claims 16 bytes, has 3


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


# ─── index honesty: population, cap, ordering (R3) ───────────────────


def test_index_result_records_true_population_when_capped(tmp_path):
    root = tmp_path / "roots"
    for i in range(5):
        _write_claude_session(root / f"proj-{i}", f"sess-{i}")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [root])
    result = vi._index_claude(mod, WINDOW, 2)
    assert result.total_in_window == 5
    assert len(result.sessions) == 2


def test_rank_takes_most_recent_n():
    kept, total, capped = vi._rank([(1.0, "old"), (3.0, "new"), (2.0, "mid")], 2)
    assert kept == ["new", "mid"]
    assert total == 3
    assert capped is True


def test_cmd_index_writes_meta_block(tmp_path, monkeypatch):
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path / "out")
    store = tmp_path / "store"
    for i in range(3):
        _write_claude_session(store / f"proj-{i}", f"sess-{i}")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [store])
    assert vi.cmd_index(mod, "claude", 30, 2) == 0
    doc = json.loads((tmp_path / "out" / "claude" / "index.json").read_text())
    meta = doc["meta"]
    assert meta["total_in_window"] == 3
    assert meta["shown"] == 2
    assert meta["capped"] is True
    assert meta["order_key"] == "file mtime"


def test_render_names_the_cap_in_coverage_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path)
    vdir = tmp_path / "antigravity"
    vdir.mkdir()
    index = {
        "vendor": "antigravity",
        "window": {"start": "2026-07-07T00:00:00", "end": "2026-08-06T00:00:00"},
        "meta": {
            "total_in_window": 638,
            "shown": 2,
            "capped": True,
            "order_key": "blob mtime",
            "notes": ["501 of 506 summarized conversations have no local blob store (pruned)"],
        },
        "sessions": [
            {"id": "a", "user_msgs": 1, "assistant_msgs": 1, "tool_calls": 0, "models": []},
            {"id": "b", "user_msgs": 0, "assistant_msgs": 0, "tool_calls": 0, "models": []},
        ],
    }
    (vdir / "index.json").write_text(json.dumps(index))
    (vdir / "narrative.json").write_text(json.dumps({"tldr": "x"}))
    assert vi.cmd_render("antigravity") == 0
    html_text = (vdir / "report.html").read_text()
    assert "2 of 638 in-window sessions indexed" in html_text
    assert "Index cap: 2 of 638" in html_text
    assert "Store note: 501 of 506" in html_text


def test_codex_index_reports_capsule_churn_and_rollout_files(tmp_path):
    day = tmp_path / "sessions" / "2026" / "07" / "26"
    _write_rollout(day, "rollout-2026-07-26T05-00-00-aaa.jsonl", "sid-parent")
    _write_rollout(day, "rollout-2026-07-26T09-00-00-bbb.jsonl", "sid-parent")
    _write_rollout(day, "rollout-2026-07-26T10-00-00-ccc.jsonl", "sid-other")
    result = vi._index_codex(_codex_mod(tmp_path), WINDOW, 10)
    assert result.extra["capsule_churn"] == {
        "files_total": 3,
        "logical_sessions": 2,
        "mean_files_per_session": 1.5,
        "max_files_in_one_session": 2,
    }
    parent = next(s for s in result.sessions if s["id"] == "sid-parent")
    assert parent["rollout_files"] == 2


def test_opencode_window_includes_sessions_updated_in_window(tmp_path):
    # A session CREATED long before the window but still ACTIVE inside it is
    # in-window; the old time_created-only predicate silently dropped it.
    db = tmp_path / "opencode.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE session (id TEXT, directory TEXT, title TEXT, model TEXT, time_created INT, time_updated INT)"
    )
    con.execute("CREATE TABLE message (id TEXT, session_id TEXT, data TEXT, time_created INT)")
    con.execute("CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT, data TEXT, time_created INT)")
    old_ms = int(OLD.timestamp() * 1000)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    con.execute("INSERT INTO session VALUES ('s-old-active', '/r', 't', NULL, ?, ?)", (old_ms, now_ms))
    con.execute("INSERT INTO session VALUES ('s-dead', '/r', 't', NULL, ?, ?)", (old_ms, old_ms))
    con.commit()
    con.close()
    result = vi._index_opencode(_fake_mod(opencode={"path": db}), WINDOW, 10)
    assert [s["id"] for s in result.sessions] == ["s-old-active"]
    assert result.total_in_window == 1


# ─── opencode health-sensor ingest (insight-cross-vendor-ingest) ─────
# The cross-vendor health packet must read the SAME stores vendor-insights does: the frozen
# legacy-share copy alone reports a live lane as silent (sessions_seen=0).

_NOW_MS = int(datetime.now(timezone.utc).timestamp() * 1000)


def _ingest_legacy_store(path: Path, sessions: dict[str, int]):
    """Legacy-schema store: {session_id: cost}."""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE session (id TEXT, directory TEXT, title TEXT, model TEXT, cost REAL, "
        "tokens_input INT, tokens_output INT, time_created INT, time_updated INT)"
    )
    con.execute("CREATE TABLE message (id TEXT, session_id TEXT, data TEXT, time_created INT)")
    con.execute("CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT, data TEXT, time_created INT)")
    for sid, cost in sessions.items():
        con.execute(
            "INSERT INTO session VALUES (?, '/r', 't', 'm-legacy', ?, 5, 5, ?, ?)",
            (sid, cost, _NOW_MS, _NOW_MS + 90_000),
        )
        con.execute("INSERT INTO message VALUES (?, ?, '{}', ?)", (f"lm-{sid}", sid, _NOW_MS))
    con.commit()
    con.close()


def _ingest_v2_store(path: Path, sessions: dict[str, int], error_blocks: int = 0):
    """v2-schema store: {session_id: cost}; error_blocks tool errors are attached to the first session."""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE session_v2 (id TEXT PRIMARY KEY, directory TEXT, title TEXT, model TEXT, cost REAL, "
        "tokens_input INT, tokens_output INT, time_created INT, time_updated INT)"
    )
    con.execute(
        "CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT, type TEXT, seq INT, "
        "time_created INT, time_updated INT, data TEXT)"
    )
    for i, (sid, cost) in enumerate(sessions.items()):
        con.execute(
            "INSERT INTO session_v2 VALUES (?, '/r', 't', 'm-v2', ?, 5, 5, ?, ?)",
            (sid, cost, _NOW_MS, _NOW_MS + 90_000),
        )
        blocks = [{"type": "text", "text": "an error was mentioned in prose only"}]
        if i == 0:
            blocks += [{"type": "tool", "name": "shell", "state": {"status": "error"}}] * error_blocks
            blocks.append({"type": "tool", "name": "read", "state": {"status": "completed"}})
        con.execute(
            "INSERT INTO session_message VALUES (?, ?, 'assistant', 1, ?, ?, ?)",
            (f"m-{sid}", sid, _NOW_MS, _NOW_MS, json.dumps({"content": blocks})),
        )
    con.commit()
    con.close()


def _point_ingest_at(monkeypatch, legacy: Path, live_dir: Path | None = None):
    entry = dict(ingest.VENDOR_REGISTRY["opencode"])
    entry["path"] = legacy
    entry["extra_root_globs"] = [str(live_dir)] if live_dir else []
    monkeypatch.setitem(ingest.VENDOR_REGISTRY, "opencode", entry)


def test_ingest_opencode_v2_counts_tool_errors_not_prose(tmp_path, monkeypatch):
    live = tmp_path / "live"
    live.mkdir()
    _ingest_v2_store(live / "opencode.db", {"s1": 0, "s2": 1.5}, error_blocks=2)
    _point_ingest_at(monkeypatch, tmp_path / "absent.db", live)
    packet = ingest._ingest_opencode(WINDOW)
    signals = {s["signal"]: s["count"] for s in packet["friction_signals"]}
    assert packet["sessions_seen"] == 2
    # 2 tool blocks finished with status=error; the word 'error' in prose must not count
    assert signals["error_parts"] == 2
    assert signals["zero_cost_sessions"] == 1


def test_ingest_opencode_counts_a_session_once_across_legacy_and_live_stores(tmp_path, monkeypatch):
    legacy, live = tmp_path / "legacy.db", tmp_path / "live"
    live.mkdir()
    # s0 exists only in the frozen legacy store, s1 in both (v2 is a superset), s2 only in live
    _ingest_legacy_store(legacy, {"s0": 1.0, "s1": 1.0})
    _ingest_v2_store(live / "opencode.db", {"s1": 1.0, "s2": 1.0})
    _point_ingest_at(monkeypatch, legacy, live)
    packet = ingest._ingest_opencode(WINDOW)
    assert packet["sessions_seen"] == 3


def test_ingest_opencode_legacy_only_host_still_reads(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy.db"
    _ingest_legacy_store(legacy, {"s0": 0})
    _point_ingest_at(monkeypatch, legacy)
    packet = ingest._ingest_opencode(WINDOW)
    assert packet["sessions_seen"] == 1
    assert {s["signal"] for s in packet["friction_signals"]} == {"zero_cost_sessions"}


def test_ingest_opencode_no_store_reports_not_found(tmp_path, monkeypatch):
    _point_ingest_at(monkeypatch, tmp_path / "absent.db")
    packet = ingest._ingest_opencode(WINDOW)
    assert packet["sessions_seen"] == 0
    assert "opencode.db not found" in packet["data_quality_notes"]


def test_oldest_opencode_spans_every_store(tmp_path, monkeypatch):
    legacy, live = tmp_path / "legacy.db", tmp_path / "live"
    live.mkdir()
    _ingest_legacy_store(legacy, {"s0": 1.0})
    _ingest_v2_store(live / "opencode.db", {"s1": 1.0})
    # age the live store's only session so it is the oldest record anywhere
    con = sqlite3.connect(live / "opencode.db")
    old_ms = int(OLD.timestamp() * 1000)
    con.execute("UPDATE session_v2 SET time_created = ?", (old_ms,))
    con.commit()
    con.close()
    _point_ingest_at(monkeypatch, legacy, live)
    assert ingest._oldest_opencode() == ingest._iso(datetime.fromtimestamp(old_ms / 1000, tz=timezone.utc))
    _point_ingest_at(monkeypatch, tmp_path / "absent.db")
    assert ingest._oldest_opencode() is None


# ─── antigravity three-source union (R4) ─────────────────────────────

_AGY_SUMMARIES_DDL = (
    "CREATE TABLE IF NOT EXISTS conversation_summaries ("
    "conversation_id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', preview TEXT NOT NULL DEFAULT '', "
    "step_count INTEGER NOT NULL DEFAULT 0, last_modified_time datetime NOT NULL, "
    "workspace_uris TEXT NOT NULL, status TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '', "
    "project_id TEXT NOT NULL DEFAULT '', agent_name TEXT NOT NULL DEFAULT '', "
    "parent_conversation_id TEXT NOT NULL DEFAULT '', nesting_depth INTEGER NOT NULL DEFAULT 0, "
    "battle_id TEXT NOT NULL DEFAULT '', winning_conversation_id TEXT NOT NULL DEFAULT '', "
    "not_fully_idle numeric NOT NULL DEFAULT false, killed numeric NOT NULL DEFAULT false, "
    "last_user_input_time datetime NOT NULL, last_user_input_step_index INTEGER NOT NULL DEFAULT -1, "
    "app_data_dir TEXT NOT NULL DEFAULT '')"
)


def _add_agy_summary(root: Path, cid: str, ts: str, step_count: int = 7):
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "conversation_summaries.db")
    con.execute(_AGY_SUMMARIES_DDL)
    con.execute(
        "INSERT INTO conversation_summaries (conversation_id, title, preview, step_count, "
        "last_modified_time, workspace_uris, last_user_input_time) VALUES (?,?,?,?,?,?,?)",
        (
            cid,
            "SECRET-TITLE",
            "SECRET-PREVIEW",
            step_count,
            ts,
            json.dumps(["file:///agy/ws"]),
            "0001-01-01 00:00:00+00:00",
        ),
    )
    con.commit()
    con.close()


def test_antigravity_index_unions_summaries_blobs_and_history(tmp_path):
    root = tmp_path / "antigravity-cli"
    _make_agy_estate(root, "cid-both")  # blob + history
    now_iso = datetime.now(timezone.utc).isoformat()
    _add_agy_summary(root, "cid-both", now_iso)
    _add_agy_summary(root, "cid-summary-only", now_iso)
    result = vi._index_antigravity(_fake_mod(antigravity={"path": root}), WINDOW, 10)
    assert {s["id"] for s in result.sessions} == {"cid-both", "cid-summary-only"}
    assert result.total_in_window == 2
    assert result.sources["union"] == 2
    by_id = {s["id"]: s for s in result.sessions}
    assert by_id["cid-both"]["content_depth"] == "blob"
    assert by_id["cid-summary-only"]["content_depth"] == "summary_only"
    assert by_id["cid-summary-only"]["step_count"] == 7
    assert by_id["cid-summary-only"]["cwd"] == "/agy/ws"


def test_antigravity_orders_by_summaries_time_before_mtime(tmp_path):
    # The summaries timestamp outranks a fresh blob mtime: a 9-day-old
    # conversation whose blob file was touched today must NOT displace
    # genuinely recent work under the cap.
    root = tmp_path / "agy"
    _make_agy_estate(root, "cid-blob-old")
    now = datetime.now(timezone.utc)
    _add_agy_summary(root, "cid-blob-old", (now - timedelta(days=9)).isoformat())
    _add_agy_summary(root, "cid-fresh", now.isoformat())
    result = vi._index_antigravity(_fake_mod(antigravity={"path": root}), WINDOW, 1)
    assert [s["id"] for s in result.sessions] == ["cid-fresh"]
    assert result.total_in_window == 2


def test_antigravity_ignores_zero_sentinel_times(tmp_path):
    # The store writes literal year-1 datetimes where it has no value; a
    # sentinel-dated summary with no other source is undateable and must be
    # excluded from a WINDOWED index, not ranked as ancient.
    root = tmp_path / "agy"
    _add_agy_summary(root, "cid-sentinel", "0001-01-01 00:00:00+00:00")
    result = vi._index_antigravity(_fake_mod(antigravity={"path": root}), WINDOW, 10)
    assert result.sessions == []
    assert result.total_in_window == 0


def test_antigravity_summaries_query_reads_no_content_columns():
    # The PII firewall, made mechanical: title/preview are conversation content
    # and must never enter this organ's SQL.
    sql = vi._AGY_SUMMARY_SQL.lower()
    assert "title" not in sql
    assert "preview" not in sql


def test_cat_antigravity_reports_pruned_blob_honestly(tmp_path):
    root = tmp_path / "agy"
    _add_agy_summary(root, "cid-pruned", datetime.now(timezone.utc).isoformat())
    text = vi._cat_antigravity(_fake_mod(antigravity={"path": root}), "cid-pruned", 10_000)
    assert "blob store pruned" in text
    assert "content not locally readable" in text
    assert "step_count=7" in text
    assert "SECRET-TITLE" not in text
    assert "SECRET-PREVIEW" not in text


def test_antigravity_missing_summaries_db_is_not_fatal(tmp_path):
    root = tmp_path / "agy"
    _make_agy_estate(root, "cid-1")  # blob + history, no summaries db
    result = vi._index_antigravity(_fake_mod(antigravity={"path": root}), WINDOW, 10)
    assert [s["id"] for s in result.sessions] == ["cid-1"]
    assert any("absent" in n for n in result.notes)


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


# ─── desktop lanes + cline (Branch B) ────────────────────────────────


def test_every_registry_vendor_is_adapter_or_dormant():
    # "every vendor must appear here; silence is not allowed" cuts both ways:
    # a registered vendor either has a live adapter or is declared dormant.
    for vendor, meta in ingest.VENDOR_REGISTRY.items():
        assert vendor in ingest.ADAPTERS or meta.get("dormant"), f"'{vendor}' has no adapter and is not dormant"


def test_every_indexer_has_a_catter():
    assert set(vi.INDEXERS) == set(vi.CATTERS)


def test_dormant_vendors_emit_packets_even_when_targeted(monkeypatch, capsys):
    # --vendor jules used to emit NOTHING: not in ADAPTERS ("Unknown vendor"),
    # and the trailing dormant loop skipped it because it WAS targeted.
    monkeypatch.setattr(sys, "argv", ["insight-cross-vendor-ingest.py", "--vendor", "jules", "--dry-run"])
    assert ingest.main() == 0
    out = capsys.readouterr().out
    packet = json.loads(out)
    assert packet["vendor"] == "jules"
    assert any("DORMANT" in note for note in packet["data_quality_notes"])


def _claude_desktop_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "Claude"
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    (root / "claude-code-sessions" / "sess-aaa").mkdir(parents=True)
    (root / "claude-code-sessions" / "sess-aaa" / "meta.json").write_text('{"k": 1}')
    (root / "local-agent-mode-sessions" / "sess-bbb").mkdir(parents=True)
    leveldb = root / "Local Storage" / "leveldb"
    leveldb.mkdir(parents=True)
    (leveldb / "000003.log").write_bytes(b"SECRET-CONVERSATION-CONTENT do not surface")
    (root / "plan-usage-history.json").write_text(
        json.dumps(
            {
                "version": 2,
                "samples": [
                    {"org": "o", "t": now_ms - 1000, "u": {"fh": 95, "sd": 40}},
                    {"org": "o", "t": now_ms, "u": {"fh": 10, "sd": 20}},
                    {"org": "o", "t": 1, "u": {"fh": 100, "sd": 100}},  # out of window
                ],
            }
        )
    )
    return root


def test_claude_desktop_never_opens_leveldb(tmp_path, monkeypatch):
    root = _claude_desktop_fixture(tmp_path)
    monkeypatch.setitem(ingest.VENDOR_REGISTRY["claude-desktop"], "path", root)
    mod = _fake_mod(**{"claude-desktop": ingest.VENDOR_REGISTRY["claude-desktop"]})

    res = vi._index_claude_desktop(mod, WINDOW, 10)
    assert {s["id"] for s in res.sessions} == {"sess-aaa", "sess-bbb"}
    assert all(s["user_msgs"] == 0 and s["assistant_msgs"] == 0 for s in res.sessions)
    assert res.extra["plan_usage"]["samples_in_window"] == 2
    assert res.extra["plan_usage"]["saturated_samples"] == 1
    assert res.extra["plan_usage"]["peak_five_hour_pct"] == 95
    assert "SECRET-CONVERSATION-CONTENT" not in json.dumps(res.sessions) + json.dumps(res.extra)

    cat = vi._cat_claude_desktop(mod, "sess-aaa", 10_000)
    assert "meta.json" in cat
    assert "never parses" in cat
    assert "SECRET-CONVERSATION-CONTENT" not in cat

    packet = ingest._ingest_claude_desktop(WINDOW)
    assert packet["sessions_seen"] == 2
    signals = {s["signal"]: s["count"] for s in packet["friction_signals"]}
    assert signals.get("plan_saturation") == 1
    assert "SECRET-CONVERSATION-CONTENT" not in json.dumps(packet)


def test_chatgpt_desktop_never_reads_data_payload(tmp_path, monkeypatch):
    root = tmp_path / "com.openai.chat"
    conv = root / "conversations-v3-acct123"
    conv.mkdir(parents=True)
    payload = b"SECRET-PAYLOAD user said something private"
    (conv / "conv-one.data").write_bytes(payload)
    monkeypatch.setitem(ingest.VENDOR_REGISTRY["chatgpt-desktop"], "path", root)
    mod = _fake_mod(**{"chatgpt-desktop": ingest.VENDOR_REGISTRY["chatgpt-desktop"]})

    res = vi._index_chatgpt_desktop(mod, WINDOW, 10)
    assert [s["id"] for s in res.sessions] == ["conv-one"]
    assert res.sessions[0]["approx_bytes"] == len(payload)
    assert "SECRET-PAYLOAD" not in json.dumps(res.sessions)

    cat = vi._cat_chatgpt_desktop(mod, "conv-one", 10_000)
    assert f"{len(payload)}B" in cat
    assert "never reads" in cat
    assert "SECRET-PAYLOAD" not in cat

    packet = ingest._ingest_chatgpt_desktop(WINDOW)
    assert packet["sessions_seen"] == 1
    assert "SECRET-PAYLOAD" not in json.dumps(packet)


def test_cat_cline_does_not_echo_state_values(tmp_path, monkeypatch):
    root = tmp_path / "cline-data"
    ws = root / "workspaces" / "ws-alpha"
    ws.mkdir(parents=True)
    (ws / "workspaceState.json").write_text('{"apiKey": "SECRET-STATE-VALUE", "taskHistory": "SECRET-TASK"}')
    monkeypatch.setitem(ingest.VENDOR_REGISTRY["cline"], "path", root)
    mod = _fake_mod(cline=ingest.VENDOR_REGISTRY["cline"])

    res = vi._index_cline(mod, WINDOW, 10)
    assert [s["id"] for s in res.sessions] == ["ws-alpha"]
    assert res.sessions[0]["user_msgs"] == 0
    assert any("zero message counts are the finding" in n for n in res.notes)

    cat = vi._cat_cline(mod, "ws-alpha", 10_000)
    assert "workspaceState.json" in cat
    assert "SECRET-STATE-VALUE" not in cat
    assert "SECRET-TASK" not in cat


def _write_vscode_session(ws_root: Path, sid: str, requests: list, patches: int = 0, version: int = 3):
    chat_dir = ws_root / "hash-1" / "chatSessions"
    chat_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "version": version,
        "sessionId": sid,
        "creationDate": int(datetime.now(timezone.utc).timestamp() * 1000),
        "requests": requests,
    }
    lines = [json.dumps({"kind": 0, "v": snapshot})]
    lines += [json.dumps({"kind": 1, "v": {"op": i}}) for i in range(patches)]
    (chat_dir / f"{sid}.jsonl").write_text("\n".join(lines))


def test_vscode_chat_reads_v3_snapshot_and_counts_patches(tmp_path, monkeypatch):
    ws_root = tmp_path / "workspaceStorage"
    _write_vscode_session(
        ws_root,
        "sess-v3",
        [{"message": {"text": "find the bug"}, "response": {"text": "found it"}}],
        patches=2,
    )
    monkeypatch.setitem(ingest.VENDOR_REGISTRY["vscode-copilot-chat"], "path", ws_root)
    mod = _fake_mod(**{"vscode-copilot-chat": ingest.VENDOR_REGISTRY["vscode-copilot-chat"]})

    res = vi._index_vscode_chat_stable(mod, WINDOW, 10)
    assert len(res.sessions) == 1
    s = res.sessions[0]
    assert s["id"] == "sess-v3"
    assert s["user_msgs"] == 1
    assert s["assistant_msgs"] == 1
    assert s["patch_lines"] == 2

    cat = vi._cat_vscode_chat_stable(mod, "sess-v3", 10_000)
    assert "find the bug" in cat
    assert "found it" in cat
    assert "not replayed" in cat

    packet = ingest._ingest_vscode_chat_stable(WINDOW)
    assert packet["sessions_seen"] == 1
    patterns = set(packet["notable_patterns"])
    assert "v3_snapshot_headers: 1" in patterns
    assert "patch_lines_total: 2" in patterns


def test_vscode_chat_non_v3_degrades_to_counts_only(tmp_path, monkeypatch):
    ws_root = tmp_path / "workspaceStorage"
    _write_vscode_session(ws_root, "sess-v9", [{"message": {"text": "secret future format"}}], version=9)
    monkeypatch.setitem(ingest.VENDOR_REGISTRY["vscode-copilot-chat"], "path", ws_root)
    mod = _fake_mod(**{"vscode-copilot-chat": ingest.VENDOR_REGISTRY["vscode-copilot-chat"]})

    res = vi._index_vscode_chat_stable(mod, WINDOW, 10)
    assert len(res.sessions) == 1
    assert res.sessions[0]["snapshot"] == "unreadable"
    assert res.sessions[0]["user_msgs"] == 0
    assert any("not v3-snapshot-readable" in n for n in res.notes)

    cat = vi._cat_vscode_chat_stable(mod, "sess-v9", 10_000)
    assert "not v3-readable" in cat
    assert "secret future format" not in cat


def test_aggregate_facets_tolerates_non_numeric_counts():
    # A model-written facet crashed the render with prose in goal_categories
    # (2026-08-06) — non-numeric truthy values now count as 'present'.
    facets = [
        {
            "outcome": "achieved",
            "goal_categories": {"coding": True, "other": "fleet dispatch admission", "research": False},
            "friction_counts": {"errors": "2"},
            "user_satisfaction_counts": {"neutral": 1},
        }
    ]
    agg = vi._aggregate_facets(facets)
    assert agg["goal_categories"] == {"coding": 1, "other": 1, "research": 0}
    assert agg["friction_counts"] == {"errors": 2}
    assert agg["satisfaction_counts"] == {"neutral": 1}
