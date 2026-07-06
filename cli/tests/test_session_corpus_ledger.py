from __future__ import annotations

import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "session-corpus-ledger.py"


def _load(name: str = "session_corpus_ledger_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_external_roots_are_file_capped(monkeypatch, tmp_path: Path):
    archive = tmp_path / "archive"
    archive.mkdir()
    for idx in range(5):
        (archive / f"chat-{idx}.md").write_text(f"chat {idx}\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_ROOTS", str(archive))
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_MAX_FILES_PER_ROOT", "2")
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_MAX_DIRS_PER_ROOT", "50")
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_MAX_DEPTH", "5")

    ledger = _load("session_corpus_ledger_file_cap")
    ledger.LOCAL_SOURCES = []
    rows, limits = ledger.scan_local_files(None)

    assert len(rows) == 2
    assert limits[0]["source"] == "external-session:archive"
    assert limits[0]["truncated"] is True
    assert limits[0]["reason"] == "file-cap"
    assert limits[0]["accepted_files"] == 2


def test_external_depth_limit_bounds_recursive_scan(monkeypatch, tmp_path: Path):
    archive = tmp_path / "archive"
    level1 = archive / "level1"
    level2 = level1 / "level2"
    level2.mkdir(parents=True)
    (archive / "root.md").write_text("root\n", encoding="utf-8")
    (level1 / "level1.md").write_text("level1\n", encoding="utf-8")
    (level2 / "too-deep.md").write_text("too deep\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_ROOTS", str(archive))
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_MAX_FILES_PER_ROOT", "50")
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_MAX_DIRS_PER_ROOT", "50")
    monkeypatch.setenv("LIMEN_EXTERNAL_SESSION_MAX_DEPTH", "1")

    ledger = _load("session_corpus_ledger_depth")
    ledger.LOCAL_SOURCES = []
    rows, limits = ledger.scan_local_files(None)
    names = {Path(row["path"]).name for row in rows}

    assert names == {"root.md", "level1.md"}
    assert limits[0]["truncated"] is False


def test_external_roots_accept_multiple_paths(monkeypatch, tmp_path: Path):
    archive = tmp_path / "archive"
    recovery = tmp_path / "recovery"
    archive.mkdir()
    recovery.mkdir()
    (archive / "chat.jsonl").write_text("{}\n", encoding="utf-8")
    (recovery / "notes.md").write_text("notes\n", encoding="utf-8")
    monkeypatch.setenv(
        "LIMEN_EXTERNAL_SESSION_ROOTS",
        os.pathsep.join([str(archive), str(recovery)]),
    )

    ledger = _load("session_corpus_ledger_multi_root")
    ledger.LOCAL_SOURCES = []
    rows, limits = ledger.scan_local_files(None)

    assert {row["source"] for row in rows} == {
        "external-session:archive",
        "external-session:recovery",
    }
    assert {item["source"] for item in limits} == {
        "external-session:archive",
        "external-session:recovery",
    }


def test_limen_root_symlink_is_resolved(monkeypatch, tmp_path: Path):
    real_root = tmp_path / "real-limen"
    link_root = tmp_path / "link-limen"
    real_root.mkdir()
    link_root.symlink_to(real_root, target_is_directory=True)
    monkeypatch.setenv("LIMEN_ROOT", str(link_root))

    ledger = _load("session_corpus_ledger_symlink")

    assert ledger.ROOT == real_root.resolve()
    assert ledger.WORKSPACE == real_root.parent.resolve()
