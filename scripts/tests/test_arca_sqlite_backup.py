"""Online SQLite custody capture must include WAL data and fail without overwrite."""

from __future__ import annotations

import importlib.util
import sqlite3
import stat
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "arca-sqlite-backup.py"
SPEC = importlib.util.spec_from_file_location("arca_sqlite_backup", SCRIPT)
assert SPEC and SPEC.loader
backup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = backup
SPEC.loader.exec_module(backup)


def test_online_backup_includes_uncheckpointed_wal_and_never_overwrites(tmp_path: Path) -> None:
    source = tmp_path / "live.sqlite"
    writer = sqlite3.connect(source)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE event (value TEXT)")
    writer.execute("INSERT INTO event VALUES ('preserved')")
    writer.commit()
    destination = tmp_path / "private" / "snapshot.sqlite"
    receipt = backup.capture(source, destination)
    assert receipt["state"] == "captured-needs-encrypted-remote-custody"
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    assert sorted(path.name for path in destination.parent.iterdir()) == ["snapshot.sqlite"]
    with sqlite3.connect(destination) as restored:
        assert restored.execute("SELECT value FROM event").fetchall() == [("preserved",)]
        assert restored.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    with pytest.raises(backup.CaptureError, match="already exists"):
        backup.capture(source, destination)
    writer.close()


def test_partial_or_symlink_source_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "live.sqlite"
    with sqlite3.connect(source) as writer:
        writer.execute("CREATE TABLE event (value TEXT)")
    destination = tmp_path / "private" / "snapshot.sqlite"
    destination.parent.mkdir(mode=0o700)
    partial = destination.with_name(f".{destination.name}.partial")
    partial.write_bytes(b"interrupted")
    with pytest.raises(backup.CaptureError, match="prior partial"):
        backup.capture(source, destination)
    partial.unlink()
    alias = tmp_path / "alias.sqlite"
    alias.symlink_to(source)
    with pytest.raises(backup.CaptureError, match="not a regular file"):
        backup.capture(alias, destination)
    assert not destination.exists()


def test_deadline_retains_partial_without_publishing(tmp_path: Path) -> None:
    source = tmp_path / "live.sqlite"
    with sqlite3.connect(source) as writer:
        writer.execute("CREATE TABLE event (value TEXT)")
        writer.executemany("INSERT INTO event VALUES (?)", [(str(index),) for index in range(1000)])
    destination = tmp_path / "private" / "snapshot.sqlite"
    with pytest.raises(backup.CaptureError, match="deadline exceeded"):
        backup.capture(source, destination, deadline_seconds=0.000001)
    assert not destination.exists()
    assert destination.with_name(f".{destination.name}.partial").exists()
