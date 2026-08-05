"""media-atomize: his personal DOCS → first-class Shot atoms (strand D slice 1).

Mirrors test_corpus_converge.py: load the script as a module with LIMEN_ROOT pointed at the
real repo (so `import limen.*` resolves) and every store/source/state redirected to tmp.
Covers the safety contract — dry-run writes nothing, --apply is idempotent, missing source
fails open — plus the engine reuse (offline converge) and corpus-converge absorption.
"""

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "media-atomize.py"
CORPUS = Path(__file__).resolve().parents[2] / "scripts" / "corpus-converge.py"
REPO = Path(__file__).resolve().parents[2]


def _load(monkeypatch, script: Path, name: str):
    monkeypatch.setenv("LIMEN_ROOT", str(REPO))
    spec = importlib.util.spec_from_file_location(name, script)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _docs(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (root / name).write_text(body)
    return root


# ─── unit: chunk + atomize ───────────────────────────────────────────


def test_chunk_splits_on_markdown_headings(monkeypatch):
    m = _load(monkeypatch, SCRIPT, "media_uut_chunk")
    text = "# Title\n\nintro para that is reasonably long " * 6 + "\n\n## Section Two\n\n" + "body " * 60
    chunks = m._chunk(text)
    assert len(chunks) >= 2
    assert any("Section Two" in c for c in chunks)


def test_chunk_empty_is_no_atoms(monkeypatch):
    m = _load(monkeypatch, SCRIPT, "media_uut_empty")
    assert m._chunk("   \n\n  ") == []


def test_atomize_doc_builds_addressed_atoms(tmp_path, monkeypatch):
    m = _load(monkeypatch, SCRIPT, "media_uut_atomize")
    p = tmp_path / "note.md"
    p.write_text("# Note\n\n" + ("alpha beta gamma delta " * 40) + "\n\n## More\n\n" + ("epsilon " * 60))
    atoms = m.atomize_doc(p)
    assert atoms and all({"id", "text", "source", "doc", "section", "kind"} <= set(a) for a in atoms)
    assert all(a["source"] == str(p) and a["kind"] == "doc" for a in atoms)
    # content-addressed: ids are stable for the same content
    assert [a["id"] for a in atoms] == [a["id"] for a in m.atomize_doc(p)]


# ─── subprocess: the safety contract ─────────────────────────────────


def _env(tmp_path, src: Path) -> dict:
    return dict(
        os.environ,
        LIMEN_ROOT=str(REPO),
        LIMEN_MEDIA_SRC=str(src),
        LIMEN_MEDIA_ATOMS=str(tmp_path / "atoms"),
        LIMEN_MEDIA_STATE=str(tmp_path / "state.json"),
        LIMEN_MEDIA_LOG=str(tmp_path / "log.jsonl"),
        LIMEN_CORPUS_ROOT=str(tmp_path / "kc"),
    )


def _photos_env(tmp_path, db: Path) -> dict:
    env = _env(tmp_path, tmp_path / "unused-doc-src")
    env["LIMEN_PHOTOS_DB"] = str(db)
    return env


def _photos_db(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE ZASSET (
          Z_PK INTEGER PRIMARY KEY,
          ZUUID VARCHAR,
          ZFILENAME VARCHAR,
          ZDATECREATED TIMESTAMP,
          ZADDEDDATE TIMESTAMP,
          ZKIND INTEGER,
          ZUNIFORMTYPEIDENTIFIER VARCHAR,
          ZWIDTH INTEGER,
          ZHEIGHT INTEGER,
          ZDURATION FLOAT,
          ZLATITUDE FLOAT,
          ZLONGITUDE FLOAT,
          ZISDETECTEDSCREENSHOT INTEGER,
          ZFAVORITE INTEGER,
          ZHIDDEN INTEGER
        );
        CREATE TABLE ZINTERNALRESOURCE (
          Z_PK INTEGER PRIMARY KEY,
          ZASSET INTEGER,
          ZDATALENGTH INTEGER
        );
        INSERT INTO ZASSET VALUES
          (1, 'photo-1', 'IMG_0001.HEIC', 804000001, 804000002, 0, 'public.heic',
           4032, 3024, 0, 40.7, -73.9, 0, 1, 0),
          (2, 'shot-1', 'Screenshot 2026-06-29 at 9.00.00 PM.png', 804000101, 804000102, 0,
           'public.png', 1440, 900, 0, -180, -180, 1, 0, 0);
        INSERT INTO ZINTERNALRESOURCE VALUES
          (10, 1, 100),
          (11, 1, 150),
          (12, 2, 200);
        """
    )
    conn.commit()
    conn.close()
    return path


def test_preview_writes_nothing(tmp_path):
    src = _docs(tmp_path / "src", {"a.md": "# A\n\n" + "word " * 80})
    r = subprocess.run([sys.executable, str(SCRIPT)], env=_env(tmp_path, src), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "atoms").exists()
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "log.jsonl").exists()
    assert "preview" in r.stdout


def test_apply_stores_atoms_then_idempotent(tmp_path):
    src = _docs(
        tmp_path / "src",
        {
            "a.md": "# A\n\n" + ("alpha " * 80) + "\n\n## A2\n\n" + ("beta " * 80),
            "b.txt": "gamma " * 120,
        },
    )
    env = _env(tmp_path, src)
    r1 = subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)
    assert r1.returncode == 0, r1.stderr
    atoms_dir = tmp_path / "atoms"
    first = list(atoms_dir.glob("*.json"))
    assert first, "atoms should be written on --apply"
    assert (tmp_path / "state.json").exists()
    # every atom is valid json with the expected shape
    a0 = json.loads(first[0].read_text())
    assert {"id", "text", "source"} <= set(a0)
    # second run over unchanged sources adds NOTHING new (idempotent via state + content-address)
    r2 = subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert "0 new atoms" in r2.stdout
    assert len(list(atoms_dir.glob("*.json"))) == len(first)


def test_changed_source_reatomizes(tmp_path):
    src = _docs(tmp_path / "src", {"a.md": "# A\n\n" + ("alpha " * 80)})
    env = _env(tmp_path, src)
    subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)
    before = len(list((tmp_path / "atoms").glob("*.json")))
    # rewrite with new content (mtime/size change) → re-atomized, new atoms appear
    (src / "a.md").write_text("# A\n\n" + ("omega " * 120) + "\n\n## New\n\n" + ("psi " * 90))
    r = subprocess.run([sys.executable, str(SCRIPT), "--apply"], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert len(list((tmp_path / "atoms").glob("*.json"))) > before


def test_missing_source_fails_open(tmp_path):
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--apply"], env=_env(tmp_path, tmp_path / "nope"), capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    assert "not present" in r.stdout
    assert not (tmp_path / "atoms").exists()


def test_malformed_numeric_env_falls_back(tmp_path):
    src = _docs(tmp_path / "src", {"a.md": "# A\n\n" + "word " * 80})
    env = _env(tmp_path, src)
    env.update(
        {
            "LIMEN_MEDIA_MAX_CHARS": "bad",
            "LIMEN_MEDIA_MIN_CHARS": "bad",
            "LIMEN_MEDIA_PDF_TIMEOUT": "bad",
            "LIMEN_MEDIA_LIMIT": "bad",
        }
    )
    r = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True)

    assert r.returncode == 0, r.stderr
    assert "preview" in r.stdout
    assert not (tmp_path / "atoms").exists()


def test_photos_metadata_preview_writes_nothing(tmp_path):
    db = _photos_db(tmp_path / "Photos Library.photoslibrary" / "database" / "Photos.sqlite")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--photos-metadata", "--limit", "2"],
        env=_photos_env(tmp_path, db),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "Photos assets" in r.stdout
    assert "preview" in r.stdout
    assert not (tmp_path / "atoms").exists()
    assert not (tmp_path / "state.json").exists()
    assert not (tmp_path / "log.jsonl").exists()


def test_photos_metadata_apply_is_idempotent_and_extracts_flags(tmp_path):
    db = _photos_db(tmp_path / "Photos Library.photoslibrary" / "database" / "Photos.sqlite")
    env = _photos_env(tmp_path, db)
    r1 = subprocess.run(
        [sys.executable, str(SCRIPT), "--photos-metadata", "--apply", "--limit", "5"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r1.returncode == 0, r1.stderr
    atoms = sorted((tmp_path / "atoms").glob("*.json"))
    assert len(atoms) == 2
    rows = [json.loads(p.read_text()) for p in atoms]
    screenshot = next(a for a in rows if a["photos_uuid"] == "shot-1")
    photo = next(a for a in rows if a["photos_uuid"] == "photo-1")
    assert screenshot["kind"] == "photo_metadata"
    assert screenshot["is_screenshot"] is True
    assert "screenshot: yes" in screenshot["text"]
    assert screenshot["local_resource_count"] == 1
    assert photo["local_resource_count"] == 2
    assert photo["local_resource_bytes"] == 250
    assert photo["has_location"] is True
    assert (tmp_path / "state.json").exists()

    r2 = subprocess.run(
        [sys.executable, str(SCRIPT), "--photos-metadata", "--apply", "--limit", "5"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r2.returncode == 0, r2.stderr
    assert "0 new atoms" in r2.stdout
    assert len(list((tmp_path / "atoms").glob("*.json"))) == len(atoms)


def test_photos_metadata_missing_db_fails_open(tmp_path):
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--photos-metadata", "--apply"],
        env=_photos_env(tmp_path, tmp_path / "missing.sqlite"),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "not present" in r.stdout
    assert not (tmp_path / "atoms").exists()


def test_photos_metadata_partial_db_fails_open(tmp_path):
    db = tmp_path / "partial.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE ZASSET (Z_PK INTEGER PRIMARY KEY, ZFILENAME VARCHAR)")
    conn.commit()
    conn.close()
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--photos-metadata", "--apply"],
        env=_photos_env(tmp_path, db),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "missing ZASSET identity columns" in r.stdout
    assert not (tmp_path / "atoms").exists()


def test_converge_proof_offline(tmp_path):
    src = _docs(
        tmp_path / "src",
        {
            "a.md": "# Trip\n\nwe drove to the mountains and hiked all day " * 8,
            "b.md": "# Trip notes\n\nthe mountains were cold and the hike was long " * 8,
        },
    )
    env = _env(tmp_path, src)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--apply", "--converge", "the mountain trip"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "media converge (offline proof)" in r.stdout
    assert "score:" in r.stdout


# ─── integration: corpus-converge absorbs the media atoms ────────────


def test_corpus_converge_absorbs_media_atoms(tmp_path, monkeypatch):
    # atomize a doc into a shared media-atoms store...
    monkeypatch.setenv("LIMEN_MEDIA_ATOMS", str(tmp_path / "atoms"))
    monkeypatch.setenv("LIMEN_CORPUS_ROOT", str(tmp_path / "kc"))
    monkeypatch.setenv("LIMEN_SESSION_META", str(tmp_path / "nope-sm"))  # only media surfaces
    mm = _load(monkeypatch, SCRIPT, "media_uut_absorb")
    doc = tmp_path / "journal.md"
    doc.write_text("# Journal\n\n" + ("a remembered day by the sea with the family " * 12))
    wrote = sum(1 for a in mm.atomize_doc(doc) if mm._store_atom(a, apply=True))
    assert wrote >= 1

    # ...and corpus-converge's gather sees them as new shots (state count would rise on absorb).
    cc = _load(monkeypatch, CORPUS, "corpus_uut_absorb")
    items = cc.gather_new_material(2, with_graph=False, absorbed=set())
    assert items, "corpus-converge should absorb media atoms from the store"
    assert any(it["source"] == str(doc) for it in items)
    # absorbed-set dedup holds: re-gather with those ids marked absorbed yields none of them
    seen = {it["id"] for it in items}
    again = cc.gather_new_material(2, with_graph=False, absorbed=seen)
    assert not any(it["id"] in seen for it in again)
