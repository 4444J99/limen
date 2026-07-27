"""Bounded-memory prompt-authority contracts for the overnight producer."""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "overnight-watch.py"


def _load_module(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_PRIVATE_SESSION_CORPUS", str(tmp_path / "private"))
    (tmp_path / "logs" / "async-runs").mkdir(parents=True)
    (tmp_path / "tasks.yaml").write_text('{"version":1,"tasks":[]}\n', encoding="utf-8")
    spec = importlib.util.spec_from_file_location("overnight_prompt_streaming_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _signature(path: Path) -> dict[str, int]:
    metadata = path.stat()
    return {"size": metadata.st_size, "mtime_ns": metadata.st_mtime_ns}


def _write_authority(module, captured_at: dt.datetime, material: bytes, operator_count: int):
    source = module.PROMPT_ATOM_SNAPSHOT
    source.parent.mkdir(parents=True)
    paths = module._prompt_paths(source)
    paths["events"].write_bytes(material)
    paths["outcomes"].write_text("", encoding="utf-8")
    cursor = {
        "version": 2,
        "scanner_version": 2,
        "scope": "all",
        "target_scope": "all",
        "all_baseline_complete": True,
        "pending_files": 0,
        "source_errors": [],
        "unsupported_source_count": 0,
        "unresolved_unit_count": 0,
        "adapter_gaps": [],
        "source_families": {
            "fixture": {
                "discovered": 1,
                "converged": 1,
                "pending": 0,
                "errors": 0,
                "unsupported": 0,
            }
        },
        "files": {},
        "last_scan_at": captured_at.isoformat(timespec="seconds"),
    }
    paths["cursor"].write_text(json.dumps(cursor, sort_keys=True), encoding="utf-8")
    snapshot = {
        "version": 1,
        "source_cursor_digest": module._cursor_digest(cursor),
        "source_scope": module._cursor_semantic(cursor),
        "coverage": {"operator_occurrences": operator_count},
        "validation": {"ok": True, "errors": []},
        "journal_signatures": {
            "events": _signature(paths["events"]),
            "outcomes": _signature(paths["outcomes"]),
            "cursor": _signature(paths["cursor"]),
        },
    }
    source.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")
    return paths


def _row(occurrence_id: str, authority: str, **extra) -> bytes:
    value = {
        "occurrence": {
            "occurrence_id": occurrence_id,
            "authority": authority,
        },
        "atoms": [],
        **extra,
    }
    return json.dumps(value, sort_keys=True).encode("utf-8") + b"\n"


def test_prompt_authority_streams_large_event_journal_without_whole_file_read(tmp_path, monkeypatch):
    module = _load_module(tmp_path, monkeypatch)
    captured_at = dt.datetime(2026, 7, 27, tzinfo=dt.timezone.utc)
    material = b"".join(
        [
            _row("operator-1", "operator"),
            _row("agent-1", "agent", payload="x" * (2 * 1024 * 1024)),
        ]
    )
    paths = _write_authority(module, captured_at, material, operator_count=1)
    original_read = module._read_trusted_regular_file

    def reject_whole_event_read(path, *, label):
        if path == paths["events"]:
            raise AssertionError("prompt event journal must not be materialized")
        return original_read(path, label=label)

    monkeypatch.setattr(module, "_read_trusted_regular_file", reject_whole_event_read)

    snapshot = module.prompt_authority_snapshot(captured_at)

    assert snapshot["present"] is True
    assert snapshot["validation_ok"] is True
    assert snapshot["exact_all"] is True
    assert snapshot["operator_occurrences"] == 1
    assert snapshot["source_custody"]["events"] == {
        "present": True,
        "size": len(material),
        "digest": hashlib.sha256(material).hexdigest(),
    }


def test_streamed_revision_count_and_prefix_custody_match_byte_semantics(tmp_path, monkeypatch):
    module = _load_module(tmp_path, monkeypatch)
    events = tmp_path / "prompt-events.jsonl"
    material = b"".join(
        [
            _row("operator-1", "operator"),
            _row("operator-1", "agent", revision_of="operator-1"),
        ]
    )
    events.write_bytes(material)

    expected_count, expected_errors = module._operator_count_from_event_bytes(material)
    count, errors, custody, file_errors = module._operator_event_file_snapshot(events)

    assert file_errors == []
    assert (count, errors) == (expected_count, expected_errors) == (0, 0)
    events.write_bytes(material + _row("operator-2", "operator"))
    assert module._prefix_matches(events, custody) is True
    assert module._operator_count_at_custody(events, custody) == (0, 0)
