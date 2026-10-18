"""Tests for scripts/lesson-harvest.py — the deterministic half of /lesson-harvest.

The non-Claude lanes are enumerated from the per-vendor index scripts/vendor-insights.py builds
(logs/vendor-insights/<vendor>/index.json), not from the raw stores. These tests pin the contract
that matters for a backlog predicate: a missing or corrupt index EXCLUDES the lane (backlog unknown,
never zero), the index's rolling window is stated on every verb, project labels carry no username,
and the timestamp shapes observed live (trailing 'Z', missing started_at) all parse. Everything runs
against synthetic trees in tmp_path, never the live estate."""

import importlib.util
import json
import types
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"

_spec = importlib.util.spec_from_file_location("lesson_harvest_for_tests", _SCRIPTS / "lesson-harvest.py")
lh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lh)

HOME_DIR = "/Users/someone"


def _write_index(root: Path, vendor: str, sessions: list[dict], *, days: int = 14) -> None:
    vendor_dir = root / vendor
    vendor_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "vendor": vendor,
        "generated_at": "2026-10-18T00:10:12+00:00",
        "window": {"start": "2026-10-04T00:10:11+00:00", "end": "2026-10-18T00:10:12+00:00", "days": days},
        "sessions": sessions,
    }
    (vendor_dir / "index.json").write_text(json.dumps(doc), encoding="utf-8")


def _record(sid: str, **over) -> dict:
    rec = {
        "id": sid,
        "started_at": "2026-10-17T18:24:43+00:00",
        "ended_at": "2026-10-17T23:03:21+00:00",
        "cwd": "/Users/someone/Workspace/limen",
        "approx_bytes": 1234,
    }
    rec.update(over)
    return rec


@pytest.fixture
def env(tmp_path, monkeypatch):
    """An isolated estate: index root, cursor, a stubbed ingest module, and a fake home."""
    index_root = tmp_path / "vendor-insights"
    index_root.mkdir()
    cursor = tmp_path / "lesson-harvest.jsonl"
    claude_root = tmp_path / "claude-projects"
    claude_root.mkdir()
    home = tmp_path / "home"
    home.mkdir()

    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(index_root))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(lh, "CURSOR", cursor)

    registry = {name: {} for name in ("claude", "codex", "gemini", "jules")}
    monkeypatch.setattr(
        lh,
        "_load_ingest_module",
        lambda: types.SimpleNamespace(VENDOR_REGISTRY=registry, claude_estate_roots=lambda: [claude_root]),
    )
    return types.SimpleNamespace(index_root=index_root, cursor=cursor, claude_root=claude_root, home=home)


def _enumerate(vendor: str):
    return lh.ENUMERATORS[vendor](None)


def test_indexed_vendors_have_enumerators():
    assert set(lh.INDEXED_VENDORS) == {"antigravity", "codex", "copilot", "gemini", "opencode"}
    for vendor in lh.INDEXED_VENDORS:
        assert vendor in lh.ENUMERATORS
    assert "claude" in lh.ENUMERATORS


def test_record_shape_maps_to_a_session(env):
    _write_index(env.index_root, "codex", [_record("sid-1", approx_bytes=392870)])
    (session,) = _enumerate("codex")
    assert session["sid"] == "sid-1"
    assert session["vendor"] == "codex"
    assert session["project"] == "limen"
    assert session["bytes"] == 392870
    assert session["mtime"] == pytest.approx(1792278201.0)  # 2026-10-17T23:03:21Z


def test_missing_index_is_excluded_not_zero(env):
    assert _enumerate("codex") is None
    sessions, excluded = lh._scope(lh._load_ingest_module(), None)
    assert "codex" in excluded
    assert not [s for s in sessions if s["vendor"] == "codex"]
    assert "codex" not in lh.COVERAGE


@pytest.mark.parametrize(
    "payload",
    ["{not json", json.dumps({"vendor": "codex"}), json.dumps({"sessions": "nope"}), json.dumps([1, 2])],
    ids=["invalid-json", "no-sessions-key", "sessions-not-a-list", "document-not-an-object"],
)
def test_corrupt_index_is_excluded_not_zero(env, payload):
    (env.index_root / "codex").mkdir()
    (env.index_root / "codex" / "index.json").write_text(payload, encoding="utf-8")
    assert _enumerate("codex") is None


def test_empty_but_readable_index_is_zero_not_excluded(env):
    _write_index(env.index_root, "gemini", [], days=30)
    assert _enumerate("gemini") == []
    _, excluded = lh._scope(lh._load_ingest_module(), None)
    assert "gemini" not in excluded


def test_records_without_an_id_are_skipped_and_bad_bytes_become_zero(env):
    _write_index(
        env.index_root,
        "codex",
        [
            _record(""),
            _record("   "),
            {"started_at": "2026-10-17T18:00:00+00:00"},
            "stray",
            _record("ok", approx_bytes="x"),
        ],
    )
    sessions = _enumerate("codex")
    assert [s["sid"] for s in sessions] == ["ok"]
    assert sessions[0]["bytes"] == 0


def test_started_at_is_the_fallback_when_there_is_no_ended_at(env):
    # antigravity writes ended_at only for most records; some carry neither.
    _write_index(
        env.index_root,
        "codex",
        [_record("only-start", ended_at=None), _record("neither", ended_at=None, started_at=None)],
    )
    by_sid = {s["sid"]: s for s in _enumerate("codex")}
    assert by_sid["only-start"]["mtime"] == pytest.approx(1792261483.0)  # 2026-10-17T18:24:43Z
    assert by_sid["neither"]["mtime"] == 0.0


def test_epoch_normalises_z_suffix_and_naive_stamps():
    aware = lh._epoch("2026-10-17T23:03:21+00:00")
    assert lh._epoch("2026-10-17T23:03:21Z") == aware
    assert lh._epoch("2026-10-17T23:03:21") == aware  # naive is UTC, never the host's local zone
    assert lh._epoch("2026-10-17T19:03:21-04:00") == aware
    assert lh._epoch("garbage") is None
    assert lh._epoch(None) is None


def test_cwd_label_is_username_free(env):
    assert lh._cwd_label(str(env.home)) == "home"
    assert lh._cwd_label("/Users/someone/Workspace/limen") == "limen"
    assert lh._cwd_label("/Users/someone/Workspace/limen/.claude/worktrees/lh-20261018") == "lh-20261018"
    assert lh._cwd_label("") == "unknown"
    assert lh._cwd_label(None) == "unknown"
    assert lh._cwd_label("/") == "unknown"


def test_labels_never_contain_a_path_separator(env):
    _write_index(env.index_root, "codex", [_record("a", cwd=str(env.home)), _record("b", cwd="/x/y/z/")])
    for session in _enumerate("codex"):
        assert "/" not in session["project"]


def test_scope_unions_claude_and_indexed_lanes_and_excludes_the_rest(env):
    project = env.claude_root / "-Users-someone-Workspace-limen"
    project.mkdir()
    (project / "claude-sid.jsonl").write_text("{}\n", encoding="utf-8")
    _write_index(env.index_root, "codex", [_record("codex-sid")])
    sessions, excluded = lh._scope(lh._load_ingest_module(), None)
    assert {(s["vendor"], s["sid"]) for s in sessions} == {("claude", "claude-sid"), ("codex", "codex-sid")}
    assert sorted(excluded) == ["gemini", "jules"]  # gemini: no index here; jules: no enumerator


def test_coverage_is_per_pass_so_a_vanished_index_leaves_no_stale_note(env):
    _write_index(env.index_root, "codex", [_record("a")])
    lh._scope(lh._load_ingest_module(), None)
    assert "codex" in lh.COVERAGE
    (env.index_root / "codex" / "index.json").unlink()
    _, excluded = lh._scope(lh._load_ingest_module(), None)
    assert "codex" in excluded
    assert "codex" not in lh.COVERAGE


def test_coverage_note_states_window_generation_and_the_age_limit(env):
    _write_index(env.index_root, "gemini", [_record("g")], days=30)
    lh._scope(lh._load_ingest_module(), "gemini")
    note = lh.COVERAGE["gemini"]
    assert "1 session(s)" in note
    assert "window 30d 2026-10-04..2026-10-18" in note
    assert "generated 2026-10-18T00:10" in note
    assert "older than the window are not enumerated" in note


def test_check_counts_the_backlog_and_prints_coverage(env, capsys):
    _write_index(env.index_root, "codex", [_record("a"), _record("b")])
    assert lh.cmd_check() == 1
    out = capsys.readouterr().out
    assert "codex: 2 unprocessed / 0 processed" in out
    assert "coverage: codex: 2 session(s)" in out
    assert "excluded (no enumerator or no readable index — backlog unknown, NOT zero): jules" in out
    assert "TOTAL unprocessed in scope: 2" in out


def test_check_is_green_only_when_every_indexed_session_is_marked(env, capsys):
    _write_index(env.index_root, "codex", [_record("a"), _record("b")])
    assert lh.cmd_mark("a", "codex", None, True) == 0
    assert lh.cmd_check() == 1
    assert lh.cmd_mark("b", "codex", json.dumps([{"owner_kind": "existing", "owner_ref": "PREC-x"}]), False) == 0
    capsys.readouterr()
    assert lh.cmd_check() == 0
    out = capsys.readouterr().out
    assert "codex: 0 unprocessed / 2 processed" in out
    assert "TOTAL unprocessed in scope: 0" in out


def test_queue_is_newest_first_across_vendors_and_pii_clean(env, capsys):
    _write_index(
        env.index_root,
        "codex",
        [
            _record("old", ended_at="2026-10-10T00:00:00Z"),
            _record("new", ended_at="2026-10-17T23:00:00Z", cwd=str(env.home)),
        ],
    )
    assert lh.cmd_queue("codex", 10) == 0
    captured = capsys.readouterr()
    rows = [line.split("\t") for line in captured.out.splitlines()]
    assert [r[1] for r in rows] == ["new", "old"]
    assert rows[0][2] == "home" and rows[0][3] == "2026-10-17"
    assert "/Users" not in captured.out
    assert "# coverage: codex:" in captured.err


def test_queue_skips_marked_sessions_and_notes_the_overflow(env, capsys):
    _write_index(env.index_root, "codex", [_record("a"), _record("b"), _record("c")])
    assert lh.cmd_mark("a", "codex", None, True) == 0
    capsys.readouterr()
    assert lh.cmd_queue("codex", 1) == 0
    captured = capsys.readouterr()
    assert len(captured.out.splitlines()) == 1
    assert "# +1 more unprocessed" in captured.err


def test_the_same_sid_in_two_lanes_is_tracked_independently(env, capsys):
    _write_index(env.index_root, "codex", [_record("shared")])
    _write_index(env.index_root, "gemini", [_record("shared")], days=30)
    assert lh.cmd_mark("shared", "codex", None, True) == 0
    capsys.readouterr()
    assert lh.cmd_check() == 1
    out = capsys.readouterr().out
    assert "codex: 0 unprocessed / 1 processed" in out
    assert "gemini: 1 unprocessed / 0 processed" in out
