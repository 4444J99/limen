from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "corpus-feed.py"


def load_corpus_feed(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_SESSION_META", str(tmp_path / "missing-session-meta"))
    spec = importlib.util.spec_from_file_location("corpus_feed_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_source_census_is_counts_only(tmp_path: Path, monkeypatch) -> None:
    module = load_corpus_feed(tmp_path, monkeypatch)
    chatgpt = tmp_path / "chatgpt"
    chatgpt.mkdir()
    (chatgpt / "conversation.data").write_text("private prompt body\n")
    (chatgpt / "nested").mkdir()
    (chatgpt / "nested" / "other.data").write_text("more private prompt body\n")
    module.PROVIDER_ROOTS = {"chatgpt-desktop": chatgpt}

    census = module._source_census()

    assert census["chatgpt-desktop"]["present"] is True
    assert census["chatgpt-desktop"]["files"] == 2
    assert census["chatgpt-desktop"]["bytes"] > 0
    encoded = json.dumps(census)
    assert "conversation.data" not in encoded
    assert "private prompt body" not in encoded
    assert str(tmp_path) not in encoded


def test_missing_session_meta_is_fail_open(tmp_path: Path, monkeypatch) -> None:
    module = load_corpus_feed(tmp_path, monkeypatch)

    result = module._run_refresh()

    assert result["status"] == "missing_session_meta"
    assert result["session_meta_present"] is False


def test_fallback_atomizer_writes_v2_store_not_implicit_jsonl(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_corpus_feed(tmp_path, monkeypatch)
    session_meta = tmp_path / "session-meta"
    ingest = session_meta / "ingest"
    ingest.mkdir(parents=True)
    (ingest / "manifest.py").write_text("# fixture\n", encoding="utf-8")
    (ingest / "atomize.py").write_text("# fixture\n", encoding="utf-8")
    module.SESSION_META = session_meta
    calls: list[list[str]] = []

    def fake_run(command: list[str], *, cwd: Path):
        assert cwd == session_meta
        calls.append(command)
        return {"status": "pass"}

    monkeypatch.setattr(module, "_run_command", fake_run)
    monkeypatch.setattr(
        module,
        "atoms_summary",
        lambda: {
            "present": True,
            "format": "session-meta.atoms-store.v2",
            "lines": 3,
        },
    )

    result = module._run_refresh()

    assert result["status"] == "pass"
    atomize = calls[1]
    assert "--store-root" in atomize
    assert "ingest/atoms.jsonl" not in atomize
    assert result["atoms_store"]["lines"] == 3


def test_successful_refresh_without_published_store_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = load_corpus_feed(tmp_path, monkeypatch)
    session_meta = tmp_path / "session-meta"
    refresh = session_meta / "ingest" / "refresh-atoms.sh"
    refresh.parent.mkdir(parents=True)
    refresh.write_text("# fixture\n", encoding="utf-8")
    module.SESSION_META = session_meta
    monkeypatch.setattr(module, "_run_command", lambda *_args, **_kwargs: {"status": "pass"})
    monkeypatch.setattr(
        module,
        "atoms_summary",
        lambda: {"present": False, "format": None, "lines": 0},
    )

    result = module._run_refresh()

    assert result["status"] == "store_missing"
