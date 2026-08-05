from __future__ import annotations

import gzip
import importlib.util
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "opencode-db-corpus-intake.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE session (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          parent_id TEXT,
          slug TEXT NOT NULL,
          directory TEXT NOT NULL,
          title TEXT NOT NULL,
          version TEXT NOT NULL,
          share_url TEXT,
          summary_additions INTEGER,
          summary_deletions INTEGER,
          summary_files INTEGER,
          summary_diffs TEXT,
          revert TEXT,
          permission TEXT,
          time_created INTEGER NOT NULL,
          time_updated INTEGER NOT NULL,
          time_compacting INTEGER,
          time_archived INTEGER,
          workspace_id TEXT,
          path TEXT,
          agent TEXT,
          model TEXT,
          cost REAL NOT NULL DEFAULT 0,
          tokens_input INTEGER NOT NULL DEFAULT 0,
          tokens_output INTEGER NOT NULL DEFAULT 0,
          tokens_reasoning INTEGER NOT NULL DEFAULT 0,
          tokens_cache_read INTEGER NOT NULL DEFAULT 0,
          tokens_cache_write INTEGER NOT NULL DEFAULT 0,
          metadata TEXT
        );
        CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, data TEXT NOT NULL);
        CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT NOT NULL, session_id TEXT NOT NULL, time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, data TEXT NOT NULL);
        CREATE TABLE session_message (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, type TEXT NOT NULL, time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, data TEXT NOT NULL, seq INTEGER NOT NULL);
        CREATE TABLE session_input (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, prompt TEXT NOT NULL, delivery TEXT NOT NULL, admitted_seq INTEGER NOT NULL, promoted_seq INTEGER, time_created INTEGER NOT NULL);
        CREATE TABLE event (id TEXT PRIMARY KEY, aggregate_id TEXT NOT NULL, seq INTEGER NOT NULL, type TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT NOT NULL, vcs TEXT, name TEXT, icon_url TEXT, icon_color TEXT, time_created INTEGER NOT NULL, time_updated INTEGER NOT NULL, time_initialized INTEGER, sandboxes TEXT NOT NULL, commands TEXT, icon_url_override TEXT);
        CREATE TABLE workspace (id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', branch TEXT, directory TEXT, extra TEXT, project_id TEXT NOT NULL, time_used INTEGER NOT NULL DEFAULT 0);
        """
    )
    conn.execute(
        """
        INSERT INTO session (
          id, project_id, slug, directory, title, version, time_created, time_updated,
          path, agent, model, cost, tokens_input, tokens_output, tokens_reasoning,
          tokens_cache_read, tokens_cache_write
        ) VALUES (
          's1', 'p1', 'secret-slug', '/private/work', 'Private Session Title', '1',
          1000, 2000, '/private/work/file.py', 'opencode', 'model-a', 1.25,
          10, 20, 30, 40, 50
        )
        """
    )
    conn.execute("INSERT INTO message VALUES ('m1','s1',1000,1001,'SECRET RAW MESSAGE')")
    conn.execute("INSERT INTO part VALUES ('p1','m1','s1',1000,1001,'SECRET RAW PART')")
    conn.execute("INSERT INTO session_message VALUES ('sm1','s1','assistant',1000,1001,'SECRET RAW SESSION MESSAGE',1)")
    conn.execute("INSERT INTO event VALUES ('e1','s1',1,'message','SECRET RAW EVENT')")
    conn.commit()
    conn.close()


def test_snapshot_writes_private_index_and_counts_only_doc(monkeypatch, tmp_path):
    mod = _load("opencode_db_intake_doc_uut")
    db = tmp_path / "opencode.db"
    _make_db(db)
    root = tmp_path / "limen"
    private = root / ".limen-private" / "session-corpus"
    monkeypatch.setattr(mod, "HOME", tmp_path)
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "DB_PATH", db)
    monkeypatch.setattr(mod, "PRIVATE_ROOT", private)
    monkeypatch.setattr(mod, "PRIVATE_BASE", private / "lifecycle" / "opencode-db-intake")
    monkeypatch.setattr(mod, "ARCHIVE_BASE", tmp_path / "archive")
    monkeypatch.setattr(mod, "DOC_PATH", root / "docs" / "opencode-db-corpus-intake.md")
    monkeypatch.setattr(mod, "LOG_PATH", root / "logs" / "opencode-db-corpus-intake.jsonl")

    snapshot = mod.build_snapshot(archive=False, hash_archive=False, run_id="run")
    mod.write_outputs(snapshot)

    doc = mod.DOC_PATH.read_text(encoding="utf-8")
    assert "SECRET RAW MESSAGE" not in doc
    assert "SECRET RAW PART" not in doc
    assert "| `session` | `1` |" in doc
    assert "local database was not deleted" in doc
    index_path = private / "lifecycle" / "opencode-db-intake" / "run" / "session-index.jsonl.gz"
    with gzip.open(index_path, "rt", encoding="utf-8") as fh:
        row = json.loads(fh.readline())
    assert row["id"] == "s1"
    assert row["message_count"] == 1
    assert row["part_count"] == 1
    assert db.exists()


def test_archive_backup_is_verified(monkeypatch, tmp_path):
    mod = _load("opencode_db_intake_archive_uut")
    db = tmp_path / "opencode.db"
    _make_db(db)
    root = tmp_path / "limen"
    archive = tmp_path / "archive"
    private = root / ".limen-private" / "session-corpus"
    monkeypatch.setattr(mod, "HOME", tmp_path)
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "DB_PATH", db)
    monkeypatch.setattr(mod, "PRIVATE_ROOT", private)
    monkeypatch.setattr(mod, "PRIVATE_BASE", private / "lifecycle" / "opencode-db-intake")
    monkeypatch.setattr(mod, "ARCHIVE_BASE", archive)

    snapshot = mod.build_snapshot(archive=True, hash_archive=False, run_id="run")

    assert snapshot["status"] == "archived_private_intake"
    assert snapshot["archive_status"] == "verified"
    archived = archive / "run" / "opencode.db"
    assert archived.exists()
    assert snapshot["archive"]["integrity_check"] == "ok"
