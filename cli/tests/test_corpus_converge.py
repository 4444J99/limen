"""corpus-converge: the CONVERGE engine pointed at Anthony's WORDS (not code PRs).

Faces are idea-clusters; new session-meta/prompt/graph shots get assigned to the nearest face and
distilled into it. Offline (dry-run kit) — no network. Write-back is gated on --live so the concat
fallback can never bloat the real corpus.
"""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "corpus-converge.py"
REPO = Path(__file__).resolve().parents[2]


def _load(monkeypatch):
    # LIMEN_ROOT must point at the real repo so `import limen.*` resolves; corpus/state/log/tasks
    # are redirected to tmp by each test via env.
    monkeypatch.setenv("LIMEN_ROOT", str(REPO))
    spec = importlib.util.spec_from_file_location("corpus_converge_uut", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _make_corpus(root: Path, faces: dict[str, str]) -> Path:
    (root / "reduced").mkdir(parents=True)
    for name, body in faces.items():
        (root / "reduced" / f"{name}.md").write_text(body)
    return root


def test_load_faces_reads_title_and_text(tmp_path, monkeypatch):
    m = _load(monkeypatch)
    corpus = _make_corpus(tmp_path / "kc", {
        "the-prompt-hand": "# The Prompt Hand\n\nRaw prompts atomized.",
        "carrier-wave": "# Carrier Wave\n\nCivilization attention substrate.",
    })
    faces = m.load_faces(corpus)
    assert {f["name"] for f in faces} == {"the-prompt-hand", "carrier-wave"}
    titles = {f["title"] for f in faces}
    assert "The Prompt Hand" in titles and "Carrier Wave" in titles


def test_assign_routes_each_item_to_nearest_face(tmp_path, monkeypatch):
    m = _load(monkeypatch)
    faces = [
        {"name": "prompts", "title": "Prompts", "text": "prompt atom hand keystroke typed",
         "path": tmp_path / "p.md"},
        {"name": "revenue", "title": "Revenue", "text": "money dollar revenue product ship sell",
         "path": tmp_path / "r.md"},
    ]
    items = [
        {"id": "a", "text": "a new prompt atom typed by the hand", "source": "x"},
        {"id": "b", "text": "ship the product and sell it for money", "source": "y"},
    ]
    buckets = m.assign_to_faces(faces, items)
    assert [it["id"] for it in buckets["prompts"]] == ["a"]
    assert [it["id"] for it in buckets["revenue"]] == ["b"]


def test_managed_text_preserves_title_strips_doubled_h1_adds_provenance(tmp_path, monkeypatch):
    m = _load(monkeypatch)
    out = m._managed_text("The One Face", "# The One Face\n\nThe distilled body.",
                          absorbed_n=3, losers_n=1, kind="shots")
    # exactly one H1, the synthesizer's doubled H1 stripped, provenance present, body kept
    assert out.count("# The One Face") == 1
    assert "Converged" in out and "absorbed 3 new shots" in out
    assert "The distilled body." in out
    assert "[[distillation-not-reduction]]" in out


def test_converge_face_and_write_back_offline(tmp_path, monkeypatch):
    m = _load(monkeypatch)
    from limen.converge import _build_dry_run_kit
    face = {"name": "f", "title": "Face F", "text": "# Face F\n\nalpha beta gamma",
            "path": tmp_path / "f.md"}
    face["path"].write_text(face["text"])
    items = [{"id": "i1", "text": "alpha beta gamma delta", "source": "s1"}]
    r = m.converge_face(face, items, _build_dry_run_kit(), threshold=0.0)
    assert r.better_version.strip()
    m.write_face(face, r, len(items))
    written = face["path"].read_text()
    assert written.startswith("# Face F")
    assert "Converged" in written and "absorbed 1 new shots" in written


def test_emit_gaps_bounded_idempotent(tmp_path, monkeypatch):
    m = _load(monkeypatch)
    (tmp_path / "tasks.yaml").write_text(yaml.safe_dump({"tasks": []}))
    monkeypatch.setenv("LIMEN_TASKS", str(tmp_path / "tasks.yaml"))
    added = m.emit_gaps(["explore: governance", "explore: governance"], "some-face", apply=True)
    assert added == 1  # duplicate collapsed
    out = yaml.safe_load((tmp_path / "tasks.yaml").read_text())
    corp = [t for t in out["tasks"] if t["id"].startswith("CORP-")]
    assert len(corp) == 1 and corp[0]["type"] == "corpus-gap"
    # second run with the same gap adds nothing (id derived from text)
    assert m.emit_gaps(["explore: governance"], "some-face", apply=True) == 0


def test_gather_new_material_fail_open_on_missing_dirs(tmp_path, monkeypatch):
    m = _load(monkeypatch)
    monkeypatch.setenv("LIMEN_SESSION_META", str(tmp_path / "nope"))
    monkeypatch.setenv("LIMEN_CORPUS_ROOT", str(tmp_path / "alsonope"))
    # no sources exist → empty list, no crash (never-NO)
    assert m.gather_new_material(2, with_graph=False, absorbed=set()) == []


def test_main_offline_preview_writes_nothing(tmp_path, monkeypatch):
    corpus = _make_corpus(tmp_path / "kc", {
        "prompts": "# Prompts\n\nprompt atom hand keystroke typed idea",
    })
    sm = tmp_path / "sm"
    sm.mkdir()
    (sm / "dialogue.md").write_text("a fresh prompt atom typed by the hand about an idea")
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(yaml.safe_dump({"tasks": []}))
    env = dict(os.environ, LIMEN_ROOT=str(REPO), LIMEN_CORPUS_ROOT=str(corpus),
               LIMEN_SESSION_META=str(sm), LIMEN_TASKS=str(tasks),
               LIMEN_CORPUS_STATE=str(tmp_path / "state.json"),
               LIMEN_CORPUS_LOG=str(tmp_path / "log.jsonl"))
    # offline, no --apply: pure preview
    r = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "log.jsonl").exists()
    # face untouched, no gap tasks written
    assert (corpus / "reduced" / "prompts.md").read_text().startswith("# Prompts")
    assert yaml.safe_load(tasks.read_text())["tasks"] == []


def test_main_offline_apply_emits_gaps_but_never_writes_faces(tmp_path, monkeypatch):
    # offline --apply: gaps + log allowed, but faces must NOT be written (concat would bloat) and
    # nothing absorbed (we didn't really fold it).
    corpus = _make_corpus(tmp_path / "kc", {
        "prompts": "# Prompts\n\nprompt atom hand",  # missing tokens vs idea → gap finder fires
    })
    sm = tmp_path / "sm"
    sm.mkdir()
    (sm / "d.md").write_text("prompt atom hand keystroke")
    tasks = tmp_path / "tasks.yaml"
    tasks.write_text(yaml.safe_dump({"tasks": []}))
    env = dict(os.environ, LIMEN_ROOT=str(REPO), LIMEN_CORPUS_ROOT=str(corpus),
               LIMEN_SESSION_META=str(sm), LIMEN_TASKS=str(tasks),
               LIMEN_CORPUS_STATE=str(tmp_path / "state.json"),
               LIMEN_CORPUS_LOG=str(tmp_path / "log.jsonl"),
               LIMEN_CORPUS_CONVERGE_LIVE="0")
    before = (corpus / "reduced" / "prompts.md").read_text()
    r = subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # face is byte-for-byte unchanged (no write-back without --live)
    assert (corpus / "reduced" / "prompts.md").read_text() == before
    # nothing absorbed (state stays empty / unwritten since changed_any is False)
    assert not (tmp_path / "state.json").exists()
