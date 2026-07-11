from __future__ import annotations

import importlib.util
import json
import os
import argparse
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


def test_missing_local_sources_distinguish_absent_and_empty(tmp_path: Path):
    ledger = _load("session_corpus_ledger_missing_sources")
    missing = tmp_path / "missing"
    empty = tmp_path / "empty"
    empty.mkdir()
    present = tmp_path / "present"
    present.mkdir()
    (present / "chat.json").write_text("{}\n", encoding="utf-8")
    ledger.LOCAL_SOURCES = [
        ("missing-app", missing, ("*.json",)),
        ("empty-app", empty, ("*.json",)),
        ("present-app", present, ("*.json",)),
    ]

    rows, _limits = ledger.scan_local_files(None)
    gaps = {item["source"]: item["reason"] for item in ledger.missing_local_sources(rows)}

    assert gaps == {"empty-app": "no-matching-files", "missing-app": "missing-root"}


def test_current_desktop_app_sources_cover_real_store_roots():
    ledger = _load("session_corpus_ledger_current_app_sources")
    sources = {source: (root, patterns) for source, root, patterns in ledger.LOCAL_SOURCES}

    chatgpt_root, chatgpt_patterns = sources["chatgpt-desktop-app-support"]
    assert chatgpt_root.parts[-1] == "com.openai.chat"
    assert "*.data" in chatgpt_patterns
    assert sources["chatgpt-atlas-app-support"][0].parts[-2:] == ("OpenAI", "ChatGPT Atlas")
    assert sources["gemini-desktop-stores"][0].parts[-1] == "com.google.GeminiMacOS"
    assert "*.store" in sources["gemini-desktop-stores"][1]
    assert "*.store-*" in sources["gemini-desktop-stores"][1]
    assert sources["perplexity-desktop-stores"][0].parts[-1] == "ai.perplexity.macv3"
    assert "*.plist" in sources["perplexity-desktop-stores"][1]
    assert "*.data" in ledger.EXTERNAL_PATTERNS


def test_limen_root_symlink_is_resolved(monkeypatch, tmp_path: Path):
    real_root = tmp_path / "real-limen"
    link_root = tmp_path / "link-limen"
    real_root.mkdir()
    link_root.symlink_to(real_root, target_is_directory=True)
    monkeypatch.setenv("LIMEN_ROOT", str(link_root))

    ledger = _load("session_corpus_ledger_symlink")

    assert ledger.ROOT == real_root.resolve()
    assert ledger.WORKSPACE == real_root.parent.resolve()


def test_quicken_snapshot_uses_latest_summary_event(tmp_path: Path):
    ledger = _load("session_corpus_ledger_quicken_summary")
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "session-lifecycle.jsonl"
    events = [
        {"ts": 1000, "sessions": 2, "stalled": ["old"], "alive": [], "done": [], "reaped": []},
        {
            "ts": 2000,
            "sessions": 3,
            "stalled": ["a"],
            "alive": ["b"],
            "done": [],
            "reaped": [],
        },
        {"ts": 3000, "breathed": "a", "ok": True},
    ]
    log_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    ledger.ROOT = tmp_path

    snapshot = ledger.quicken_snapshot()

    assert snapshot["sessions"] == 3
    assert snapshot["stalled"] == 1
    assert snapshot["alive"] == 1
    assert snapshot["closed"] == 1
    assert snapshot["reaped"] == 0


def test_tracked_receipts_render_when_atom_ledger_is_not_bootstrapped(tmp_path: Path):
    ledger = _load("session_corpus_ledger_receipt_render")
    ledger.ROOT = tmp_path
    docs = tmp_path / "docs"
    docs.mkdir()
    for name in (
        "prompt-priority-map.md",
        "prompt-batch-review-ledger.md",
        "prompt-packet-ledger.md",
        "prompt-packet-resolution-receipts.json",
        "capability-substrate-ledger.md",
    ):
        (docs / name).write_text("receipt\n", encoding="utf-8")

    snapshot = {
        "organs": [],
        "session_meta": {
            "manifest": {"present": False, "lines": 0},
            "atoms": {"present": False, "lines": 0},
        },
        "knowledge_corpus": {"reduced_faces": 0, "the_one_present": False},
        "quicken": {"present": False},
        "codex_quicken": {"present": False},
        "private_screenshots": {"files": 0},
        "object_store": {"object_count": 0},
        "scan_limits": [],
    }
    rendered = ledger.render_markdown(
        snapshot,
        [],
        argparse.Namespace(days=7),
        None,
    )

    assert "Prompt priority map" in rendered
    assert "Prompt batch review ledger" in rendered
    assert "Prompt packet ledger" in rendered
    assert "Prompt packet resolution receipts" in rendered
    assert "Capability substrate ledger" in rendered
