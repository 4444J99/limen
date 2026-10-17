"""Source identity and bounded capture regressions; synthetic stores only."""

import hashlib
import json
import os
import types
from datetime import UTC, datetime, timedelta

import pytest
from test_vendor_insights import _write_claude_session, ingest, vi


def test_fresh_claude_file_survives_old_parent_directory(tmp_path):
    root = tmp_path / "root"
    project = root / "project"
    _write_claude_session(project, "native-id")
    old = (datetime.now(UTC) - timedelta(days=90)).timestamp()
    os.utime(project, (old, old))
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [root])
    result = vi._index_claude(mod, datetime.now(UTC) - timedelta(days=14), 40)
    assert result.total_in_window == 1


def test_ingest_fresh_claude_file_survives_old_parent(tmp_path, monkeypatch):
    root = tmp_path / "root"
    project = root / "project"
    _write_claude_session(project, "native-id")
    old = (datetime.now(UTC) - timedelta(days=90)).timestamp()
    os.utime(project, (old, old))
    monkeypatch.setattr(ingest, "claude_estate_roots", lambda: [root])
    result = ingest._ingest_claude(datetime.now(UTC) - timedelta(days=14))
    assert result["sessions_seen"] == 1


def test_same_native_id_has_distinct_source_records(tmp_path):
    roots = [tmp_path / "a", tmp_path / "b"]
    for root in roots:
        _write_claude_session(root / "project", "native-id")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: roots)
    result = vi._index_claude(mod, datetime.now(UTC) - timedelta(days=14), 40)
    assert len({s["record_id"] for s in result.sessions}) == 2
    assert {s["id"] for s in result.sessions} == {"native-id"}
    assert vi._cat_claude(mod, "native-id", 128) is None


def test_claude_capture_bound_includes_headers_and_marker(tmp_path):
    root = tmp_path / "root"
    project = root / "project"
    _write_claude_session(project, "native-id", n_assistant=0)
    path = project / "native-id.jsonl"
    rec = json.loads(path.read_text().splitlines()[0])
    rec["message"]["content"] = "\u2603" * 4096
    path.write_text(json.dumps(rec) + "\n")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [root])
    text = vi._cat_claude(mod, "native-id", 128)
    assert len(text) <= 128
    assert "truncated" in text


def test_record_read_resolves_the_indexed_source(tmp_path, monkeypatch, capsys):
    roots = [tmp_path / "a", tmp_path / "b"]
    for n, root in enumerate(roots):
        _write_claude_session(root / "project", "native-id", n_user=n + 1)
    mod = types.SimpleNamespace(claude_estate_roots=lambda: roots)
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path / "out")
    assert vi.cmd_index(mod, "claude", 14, 40) == 0
    capsys.readouterr()
    index = json.loads((vi.OUT_ROOT / "claude/index.json").read_text())
    second = next(s for s in index["sessions"] if s["user_msgs"] == 2)
    assert vi.cmd_cat(mod, "claude", None, 60000, record_id=second["record_id"], json_mode=True) == 0
    capture = json.loads(capsys.readouterr().out)
    assert capture["text"].count("hi there") == 2
    assert capture["record_id"] == second["record_id"]
    assert capture["capture_sha256"] == hashlib.sha256(capture["text"].encode()).hexdigest()


def test_index_names_selection_and_count_basis(tmp_path, monkeypatch):
    root = tmp_path / "root"
    _write_claude_session(root / "project", "native-id")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [root])
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path / "out")
    vi.cmd_index(mod, "claude", 14, 40)
    doc = json.loads((vi.OUT_ROOT / "claude/index.json").read_text())
    assert doc["meta"]["population_unit"] == "source_records"
    assert doc["meta"]["message_count_basis"] == "selected_session_lifetime"
    assert doc["meta"]["selection_basis"] == "file mtime"


def test_antigravity_history_only_is_readable(tmp_path):
    now = int(datetime.now(UTC).timestamp() * 1000)
    (tmp_path / "history.jsonl").write_text(
        json.dumps(
            {
                "conversationId": "history-only",
                "display": "synthetic request",
                "timestamp": now,
            }
        )
        + "\n"
    )
    mod = types.SimpleNamespace(VENDOR_REGISTRY={"antigravity": {"path": tmp_path}})
    assert "synthetic request" in vi._cat_antigravity(mod, "history-only", 1000)


@pytest.mark.parametrize("limit", [0, 1, 8, 32, 128])
def test_bound_writer_never_exceeds_requested_limit(limit):
    text = vi._bounded_text("\u2603" * 1000, limit)
    assert len(text) <= limit


def test_expanded_read_receipt_hashes_actual_returned_text(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    project = root / "project"
    _write_claude_session(project, "native-id", n_assistant=0)
    path = project / "native-id.jsonl"
    rec = json.loads(path.read_text().splitlines()[0])
    rec["message"]["content"] = "x" * 70000
    path.write_text(json.dumps(rec) + "\n")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [root])
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path / "out")
    vi.cmd_index(mod, "claude", 14, 40)
    capsys.readouterr()
    assert vi.cmd_cat(mod, "claude", "native-id", 80000, json_mode=True) == 0
    capture = json.loads(capsys.readouterr().out)
    assert len(capture["text"]) > 60000
    assert capture["capture_max_chars"] == 80000
    assert capture["capture_sha256"] == hashlib.sha256(capture["text"].encode()).hexdigest()
    assert capture["reindex_required"] is True
    assert capture["judgment_eligible"] is False


def test_missing_capture_is_classified_without_inventing_failure(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    _write_claude_session(root / "project", "native-id", n_assistant=0)
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [root])
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path / "out")
    vi.cmd_index(mod, "claude", 14, 40)
    capsys.readouterr()
    vi.cmd_cat(mod, "claude", "native-id", 60000, json_mode=True)
    capture = json.loads(capsys.readouterr().out)
    assert capture["availability"] == "prompt_only"
    assert capture["readable_assistant_turns"] == 0
    assert capture["tool_result_coverage"] == "not_exposed_by_adapter"


def test_registered_root_alias_is_one_source_record(tmp_path):
    root = tmp_path / "root"
    _write_claude_session(root / "project", "native-id")
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [root, alias])
    result = vi._index_claude(mod, datetime.now(UTC) - timedelta(days=14), 40)
    assert result.total_in_window == 1


def test_source_reference_cannot_read_unregistered_file(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    _write_claude_session(root / "project", "native-id")
    _write_claude_session(outside / "project", "native-id")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [root])
    assert (
        vi._cat_claude(
            mod,
            "native-id",
            128,
            source_ref={
                "kind": "claude_jsonl",
                "path": str(outside / "project/native-id.jsonl"),
            },
        )
        is None
    )


def test_ambiguous_session_json_reports_ambiguity(tmp_path, monkeypatch, capsys):
    roots = [tmp_path / "a", tmp_path / "b"]
    for root in roots:
        _write_claude_session(root / "project", "native-id")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: roots)
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path / "out")
    vi.cmd_index(mod, "claude", 14, 40)
    capsys.readouterr()
    assert vi.cmd_cat(mod, "claude", "native-id", 128, json_mode=True) == 2
    assert json.loads(capsys.readouterr().out)["availability"] == "ambiguous_identity"
