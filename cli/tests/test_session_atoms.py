from __future__ import annotations

import json
from pathlib import Path

import pytest
from limen import session_atoms


def _owner_module(root: Path, body: str) -> None:
    ingest = root / "ingest"
    ingest.mkdir(parents=True, exist_ok=True)
    (ingest / "atoms_store.py").write_text(body, encoding="utf-8")


def _v2_marker(root: Path, generation: str = "sha256-" + "a" * 64) -> Path:
    store = root / "ingest" / "atoms-store"
    (store / "generations" / generation).mkdir(parents=True)
    (store / "CURRENT").write_text(generation + "\n", encoding="utf-8")
    return store


def _configure(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setenv("LIMEN_SESSION_META", str(root))
    monkeypatch.delenv("ATOMS_STORE_ROOT", raising=False)
    monkeypatch.delenv("LIMEN_EXPORT_ATOMS", raising=False)
    session_atoms._load_owner_module.cache_clear()


def test_v2_stream_is_preferred_over_explicit_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "session-meta"
    _configure(monkeypatch, root)
    _v2_marker(root)
    _owner_module(
        root,
        "def iter_collection(root):\n    yield {'text': 'v2', 'source': 'codex', 'ts': '2026-07-23T00:00:00Z'}\n",
    )
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(json.dumps({"text": "legacy"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_EXPORT_ATOMS", str(legacy))

    assert [row["text"] for row in session_atoms.iter_atoms()] == ["v2"]
    summary = session_atoms.atoms_summary()
    assert summary["format"] == "session-meta.atoms-store.v2"
    assert summary["lines"] == 1


def test_malformed_v2_fails_closed_without_legacy_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "session-meta"
    _configure(monkeypatch, root)
    _v2_marker(root)
    _owner_module(
        root,
        "def iter_collection(root):\n    raise RuntimeError('corrupt shard')\n    yield\n",
    )
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(json.dumps({"text": "must-not-fallback"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_EXPORT_ATOMS", str(legacy))

    with pytest.raises(session_atoms.AtomStreamError, match="corrupt shard"):
        list(session_atoms.iter_atoms())


def test_explicit_legacy_stream_is_one_release_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "session-meta"
    _configure(monkeypatch, root)
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(
        "".join(json.dumps({"text": f"row-{index}"}) + "\n" for index in range(3)),
        encoding="utf-8",
    )
    monkeypatch.setenv("LIMEN_EXPORT_ATOMS", str(legacy))

    assert [row["text"] for row in session_atoms.iter_atoms()] == ["row-0", "row-1", "row-2"]
    assert session_atoms.atoms_summary()["format"] == "legacy-jsonl-v1"


def test_implicit_atoms_jsonl_is_not_a_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "session-meta"
    _configure(monkeypatch, root)
    (root / "ingest").mkdir(parents=True)
    (root / "ingest" / "atoms.jsonl").write_text(
        json.dumps({"text": "implicit legacy"}) + "\n",
        encoding="utf-8",
    )

    assert list(session_atoms.iter_atoms()) == []
    assert session_atoms.atoms_summary()["present"] is False


def test_incomplete_v2_marker_fails_instead_of_using_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "session-meta"
    _configure(monkeypatch, root)
    store = root / "ingest" / "atoms-store"
    (store / "generations").mkdir(parents=True)
    _owner_module(
        root,
        "def iter_collection(root):\n    raise RuntimeError('CURRENT missing')\n    yield\n",
    )
    legacy = tmp_path / "legacy.jsonl"
    legacy.write_text(json.dumps({"text": "legacy"}) + "\n", encoding="utf-8")
    monkeypatch.setenv("LIMEN_EXPORT_ATOMS", str(legacy))

    with pytest.raises(session_atoms.AtomStreamError, match="CURRENT missing"):
        list(session_atoms.iter_atoms())
