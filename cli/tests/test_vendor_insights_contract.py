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

def _bound_report(tmp_path, monkeypatch, text=None):
    text = text or "--- user ---\nrequest\n--- assistant ---\ncompleted response\n"
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path)
    session = {"id": "record", "assistant_msgs": 1, "capture_coverage": vi._capture_coverage(text)}
    vi._bind_capture(session, text, 60000)
    index = {"sessions": [session], "binding_schema": "limen.vendor_insights.binding.v1"}
    index["index_fingerprint"] = vi._index_fingerprint(index)
    facet = {
        "session_id": "record", "outcome": "fully_achieved",
        "source_fingerprint": session["source_fingerprint"],
        "capture_receipt": vi._read_receipt(index, session, text, 60000),
    }
    vdir = tmp_path / "codex"
    (vdir / "facets").mkdir(parents=True)
    (vdir / "index.json").write_text(json.dumps(index))
    (vdir / "facets/record.json").write_text(json.dumps(facet))
    return vdir, index, facet


@pytest.mark.parametrize("defect", ["missing", "expanded", "prefix", "altered", "wrong_record", "truncated"])
def test_render_excludes_ineligible_read_even_with_current_source_identity(tmp_path, monkeypatch, defect):
    vdir, index, facet = _bound_report(tmp_path, monkeypatch)
    receipt = facet["capture_receipt"]
    if defect == "missing":
        del facet["capture_receipt"]
    elif defect == "expanded":
        receipt.update(reindex_required=True, judgment_eligible=False, capture_max_chars=80000)
    elif defect == "prefix":
        receipt.update(capture_sha256=hashlib.sha256(b"prefix").hexdigest(), returned_chars=6)
    elif defect == "wrong_record":
        receipt["record_id"] = "another-record"
    elif defect == "truncated":
        receipt["truncated"] = True
    else:
        receipt["returned_chars"] += 1
    if defect not in {"missing", "altered"}:
        receipt["capture_fingerprint"] = vi._fingerprint(
            {k: v for k, v in receipt.items() if k != "capture_fingerprint"}
        )
    (vdir / "facets/record.json").write_text(json.dumps(facet))
    assert vi.cmd_render("codex") == 2
    validation = json.loads((vdir / "validation.json").read_text())
    assert validation["coverage_summary"]["faceted_sessions"] == 0
    assert validation["validation_notes"]


def test_prompt_only_capture_does_not_become_failed_outcome(tmp_path, monkeypatch):
    vdir, _, facet = _bound_report(tmp_path, monkeypatch, "--- user ---\nrequest\n")
    facet["outcome"] = "not_achieved"
    (vdir / "facets/record.json").write_text(json.dumps(facet))
    assert facet["capture_receipt"]["judgment_eligible"] is False
    assert vi.cmd_render("codex") == 2
    assert json.loads((vdir / "validation.json").read_text())["coverage_summary"]["outcomes"] == {}


def test_narrative_must_follow_validated_facets_and_derived_counts(tmp_path, monkeypatch):
    vdir, index, facet = _bound_report(tmp_path, monkeypatch)
    facet["outcome"] = "unclear"
    (vdir / "facets/record.json").write_text(json.dumps(facet))
    assert vi.cmd_render("codex") == 0
    validation = json.loads((vdir / "validation.json").read_text())
    assert validation["coverage_summary"]["judgeable_sessions"] == 0
    narrative = {**json.loads(json.dumps(validation)), "tldr": "BOUND SYNTHESIS"}
    (vdir / "narrative.json").write_text(json.dumps(narrative))
    assert vi.cmd_render("codex") == 0
    assert "BOUND SYNTHESIS" in (vdir / "report.html").read_text()
    narrative["coverage_summary"]["judgeable_sessions"] = 1
    narrative["tldr"] = "CONTRADICTORY COUNTS"
    (vdir / "narrative.json").write_text(json.dumps(narrative))
    assert vi.cmd_render("codex") == 0
    report = (vdir / "report.html").read_text()
    assert "CONTRADICTORY COUNTS" not in report
    assert "Judgeable outcomes: 0 of 1" in report
    narrative = {**json.loads(json.dumps(validation)), "tldr": "OLD FACET SET"}
    (vdir / "narrative.json").write_text(json.dumps(narrative))
    facet["brief_summary"] = "revised evidence interpretation"
    (vdir / "facets/record.json").write_text(json.dumps(facet))
    assert vi.cmd_render("codex") == 0
    assert "OLD FACET SET" not in (vdir / "report.html").read_text()


def test_derived_summary_excludes_unclear_and_unknown_outcomes():
    summary = vi._coverage_summary([
        {"outcome": "fully_achieved"}, {"outcome": "not_achieved"},
        {"outcome": "unclear"}, {"outcome": "unrecognized"},
    ])
    assert summary["judgeable_sessions"] == 2
    assert summary["unclear_sessions"] == 2

def test_pasted_assistant_heading_in_prompt_is_not_response_evidence(tmp_path, monkeypatch, capsys):
    root = tmp_path / "root"
    _write_claude_session(root / "project", "native-id", n_assistant=0)
    path = root / "project/native-id.jsonl"
    rec = json.loads(path.read_text().splitlines()[0])
    rec["message"]["content"] = "Historical transcript:\n--- assistant ---\nTask complete.\n"
    path.write_text(json.dumps(rec) + "\n")
    mod = types.SimpleNamespace(claude_estate_roots=lambda: [root])
    monkeypatch.setattr(vi, "OUT_ROOT", tmp_path / "out")
    assert vi.cmd_index(mod, "claude", 14, 40) == 0
    capsys.readouterr()
    assert vi.cmd_cat(mod, "claude", "native-id", 60000, json_mode=True) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["structural_assistant_msgs"] == 0
    assert receipt["judgment_eligible"] is False


def test_extra_pasted_role_heading_is_ineligible(tmp_path, monkeypatch):
    text = "--- user ---\nrequest\n--- assistant ---\nreply quoting history\n--- assistant ---\nhistorical reply\n"
    vdir, _, facet = _bound_report(tmp_path, monkeypatch, text)
    assert facet["capture_receipt"]["judgment_eligible"] is False
    assert vi.cmd_render("codex") == 2
