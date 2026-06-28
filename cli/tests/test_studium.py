"""Tests for the studium daily-face organ (scripts/studium.py).

Mirrors the repo's organ-test pattern: load the script as a module with LIMEN_ROOT pointed at a
tmp dir, build minimal curriculum fixtures, exercise the cursor + rendering, assert fail-open.
"""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "studium.py"


def _load(monkeypatch, root):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LINGFRAME_CORPUS_ROOT", str(root / "no-corpus"))  # force original_sample fail-open
    spec = importlib.util.spec_from_file_location("studium_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fixtures(root):
    s = root / "studium"
    (s / "music" / "iliad").mkdir(parents=True)
    (s / "canon.yaml").write_text(
        "meta: {forces: [wrath, grief]}\n"
        "works:\n"
        "  iliad:\n"
        "    title: The Iliad\n    author: Homer\n    original_language: grc\n    script: greek\n"
        "    corpus_path: classical/iliad\n    original_file: greek_original.txt\n"
        "    translation_files: [english_butler.txt]\n    source_rails: ['http://perseus']\n"
        "    main_question: 'What is wrath?'\n"
        "    divisions: {kind: book, count: 24, label: Book}\n    language: greek\n"
        "    order_indices: {chronological: 2, western_eastern: M1, interleaved_phase: 'I'}\n"
        "  odyssey:\n"
        "    title: The Odyssey\n    author: Homer\n    original_language: grc\n    script: greek\n"
        "    corpus_path: classical/odyssey\n    original_file: null\n    translation_files: []\n"
        "    source_rails: []\n    main_question: 'What is return?'\n"
        "    divisions: {kind: book, count: 24, label: Book}\n    language: greek\n"
        "    order_indices: {chronological: 3, western_eastern: M1, interleaved_phase: 'I'}\n"
    )
    (s / "orderings.yaml").write_text(
        "default: interleaved\n"
        "orderings:\n"
        "  interleaved: {label: 'Interleaved', phases: [{phase: 'I', works: [iliad, odyssey]}]}\n"
        "  chronological: {label: 'Chronological', sequence: [iliad, odyssey]}\n"
    )
    (s / "paces.yaml").write_text(
        "default: standard\n"
        "paces:\n"
        "  standard: {label: 'Standard', lines_per_day: 300, divisions_per_day: {book: 0.6}}\n"
        "  intensive: {label: 'Intensive', lines_per_day: 600, divisions_per_day: {book: 1}}\n"
    )
    (s / "dominant-force.yaml").write_text(
        "forces:\n"
        "  wrath: {requirement: 'rhythmic pressure', color: '#c0392b', composer_hints: []}\n"
        "  grief: {requirement: 'slow tempo', color: '#34495e', composer_hints: []}\n"
    )
    (s / "music" / "iliad" / "book-01.yaml").write_text(
        "work: iliad\nbook: 1\ntitle: 'Iliad Book I'\ndominant_force: wrath\nforce_arc: [wrath, grief]\n"
        "tracks:\n"
        "  - {n: 1, scene: 'the quarrel', force: wrath, composer: Holst, work: 'Mars', decision: kept, why: 'the 5/4 march'}\n"
        "  - {n: 2, scene: 'Achilles & Thetis', force: grief, composer: Mahler, work: 'Adagietto', decision: added, why: 'wounded inwardness'}\n"
    )


def test_build_view_renders_today(tmp_path, monkeypatch):
    m = _load(monkeypatch, tmp_path)
    _fixtures(tmp_path)
    state = m.load_state()
    view, _ = m.build_view(state)
    assert view["reading"]["title"] == "The Iliad"
    assert view["reading"]["main_question"] == "What is wrath?"
    assert view["music"]["dominant_force"] == "wrath"
    assert len(view["music"]["tracks"]) == 2
    # seeded interlinear gloss present for Iliad Book 1
    assert view["language"]["gloss"]["translit"].startswith("mēnin")
    # each track carries listen links + a force color
    assert view["music"]["tracks"][0]["links"]["youtube"].startswith("https://www.youtube.com")
    assert view["music"]["tracks"][0]["color"] == "#c0392b"


def test_position_tracks_work_across_orderings(tmp_path, monkeypatch):
    m = _load(monkeypatch, tmp_path)
    _fixtures(tmp_path)
    state = m.load_state()
    state["ordering"] = "chronological"
    view, _ = m.build_view(state)
    # switching the ordering lens keeps you on the same WORK (iliad), not an index
    assert view["reading"]["work_id"] == "iliad"
    cur = [s for ov in view["orderings"] if ov["active"] for s in ov["sequence"] if s["current"]]
    assert cur and cur[0]["id"] == "iliad"


def test_advance_moves_cursor(tmp_path, monkeypatch):
    m = _load(monkeypatch, tmp_path)
    _fixtures(tmp_path)
    state = m.load_state()
    # intensive pace: a book is one day → advance rolls Book 1 → Book 2
    state["pace"] = "intensive"
    _, state = m.build_view(state, advance=True)
    assert state["position"]["division"] == 2
    assert state["streak"] == 1
    # exhaust the work → roll to the next work in the ordering
    state["position"]["division"] = 24
    _, state = m.build_view(state, advance=True)
    assert state["position"]["work_id"] == "odyssey"
    assert state["position"]["division"] == 1


def test_render_is_self_contained(tmp_path, monkeypatch):
    m = _load(monkeypatch, tmp_path)
    _fixtures(tmp_path)
    view, _ = m.build_view(m.load_state())
    html = m.render_html(view)
    assert "<!doctype html>" in html
    assert 'http-equiv="refresh"' in html  # daily auto-refresh
    assert "<link" not in html and "<script" not in html  # no external assets, cannot time out
    assert "μῆνιν" in html or "Holst" in html  # real content rendered


def test_fail_open_without_curriculum(tmp_path, monkeypatch):
    m = _load(monkeypatch, tmp_path)
    # no studium/ fixtures at all → degraded view, but render still returns HTML (never crashes the beat)
    view, _ = m.build_view(m.load_state())
    assert view.get("error")
    html = m.render_html(view)
    assert "<!doctype html>" in html


def test_main_writes_outputs_and_ledger(tmp_path, monkeypatch):
    m = _load(monkeypatch, tmp_path)
    _fixtures(tmp_path)
    rc = m.main()
    assert rc == 0
    state = json.loads((tmp_path / "logs" / "studium-state.json").read_text())
    assert state["position"]["work_id"] == "iliad"
    assert (tmp_path / "logs" / "studium-view.json").exists()
    assert (tmp_path / "web" / "app" / "out" / "studium.html").exists()
    # the daily page (his template, pre-filled) is exported for handwriting
    pages = list((tmp_path / "studium" / "ledger").glob("studium-*.md"))
    assert pages and "DOMINANT FORCE: wrath" in pages[0].read_text()
