#!/usr/bin/env python3
"""media-atomize.py — strand D slice 1: his personal DOCS become first-class Shot atoms.

The system already has the atom abstraction (`limen.converge.Shot`) and the engine
(`converge()` → ONE); it just never fed personal media into them. This organ does the
cheapest, highest-signal slice: turn his documents into `Shot` atoms in the SAME store
the converge engine reads, so `corpus-converge` remixes his media with his words and
`capture.sh` pushes them off-disk into the universal context. (Design:
`docs/atomic-units-personal-media.md`; reuses `cli/src/limen/converge.py` — no new infra.)

THE PIPELINE (slice 1 = stages 1–3; remix/reclaim are later slices):

  INGEST   walk a docs source — DEFAULT the DURABLE Archive4T copy of CloudDocs
           (`/Volumes/Archive4T/personal-cloud-docs`), so we atomize from the offsite
           copy and NEVER re-download iCloud (the vicious re-materialize cycle strand C
           just fixed). text/md/txt now; PDF when `pdftotext` (poppler) is present.
  ATOMIZE  extract text, chunk into section-level shots:
           ``Shot(id=hash, text=section, source=path)`` — the bytes stay put, only text.
  STORE    (--apply) write each atom content-addressed under the media-atoms store the
           converge engine reads (dedup by id; idempotent via a per-source signature so
           re-runs only atomize new/changed docs).
  PROVE    (--converge IDEA) run converge() over the stored atoms with the OFFLINE kit to
           show his media flows through the SAME engine that distills his words.

SAFE (mirrors library-preserve): dry-run by DEFAULT (--apply to write); READ-ONLY on
sources (never move/delete/evict — reclaim is a later byproduct); fail-open per file and
never crashes the heartbeat; bounded per run (--limit). Reversible only.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
sys.path.insert(0, str(ROOT / "cli" / "src"))

# Section boundaries: markdown headings; falls back to paragraph blocks when there are none.
HEAD_RE = re.compile(r"^#{1,3}[ \t]+\S.*$", re.MULTILINE)
PARA_RE = re.compile(r"\n[ \t]*\n")
DOC_EXTS = {".md", ".markdown", ".txt", ".text", ".rst", ".org", ".pdf"}
MAX_CHARS = int(os.environ.get("LIMEN_MEDIA_MAX_CHARS", "4000"))
MIN_CHARS = int(os.environ.get("LIMEN_MEDIA_MIN_CHARS", "200"))
PDF_TIMEOUT = int(os.environ.get("LIMEN_MEDIA_PDF_TIMEOUT", "60"))


# ─── locations (derive at runtime, never pin — [[derive-never-pin-hardcodes]]) ───

def _corpus_root() -> Path:
    return Path(os.environ.get("LIMEN_CORPUS_ROOT", Path.home() / "Workspace" / "knowledge-corpus"))


def _src_root() -> Path:
    # Atomize from the DURABLE Archive4T copy (strand C already copied CloudDocs there),
    # so this never touches/redownloads the live iCloud cache.
    return Path(os.environ.get("LIMEN_MEDIA_SRC", "/Volumes/Archive4T/personal-cloud-docs"))


def _atoms_root() -> Path:
    # The canonical media-atoms store the converge engine reads (content-addressed).
    return Path(os.environ.get("LIMEN_MEDIA_ATOMS", _corpus_root() / "02-media-atoms"))


def _state_path() -> Path:
    return Path(os.environ.get("LIMEN_MEDIA_STATE", ROOT / "logs" / "media-atomize-state.json"))


def _log_path() -> Path:
    return Path(os.environ.get("LIMEN_MEDIA_LOG", ROOT / "logs" / "media-atomize-log.jsonl"))


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _hash(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(p.encode("utf-8", "replace"))
    return h.hexdigest()[:16]


def _sig(p: Path) -> str:
    """A cheap change signature so re-runs skip unchanged sources (idempotent)."""
    try:
        st = p.stat()
        return f"{int(st.st_mtime)}:{st.st_size}"
    except Exception:
        return ""


# ─── ingest + atomize ────────────────────────────────────────────────

def _iter_docs(src: Path, limit: int):
    """Yield up to ``limit`` document paths under ``src`` (bounded, deterministic, fail-open).

    Uses os.walk with sorted dirs/files and an early stop so a huge tree is never fully
    materialised; skips dotfiles/dot-dirs (system/cache cruft)."""
    if not src.is_dir():
        return
    n = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith("."):
                continue
            p = Path(root) / name
            if p.suffix.lower() not in DOC_EXTS:
                continue
            yield p
            n += 1
            if n >= limit:
                return


def _pdf_text(path: Path) -> str:
    """Extract PDF text via poppler's pdftotext if present; fail-open to '' otherwise.

    Slice 1 has no hard PDF dependency: if poppler isn't installed the PDF is simply
    skipped this slice (counted), never a crash. text/md/txt still atomize."""
    exe = shutil.which("pdftotext")
    if not exe:
        return ""
    try:
        proc = subprocess.run(
            [exe, "-q", "-enc", "UTF-8", str(path), "-"],
            capture_output=True, text=True, timeout=PDF_TIMEOUT, check=False,
        )
        return proc.stdout or ""
    except Exception:
        return ""


def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf_text(path)
    try:
        return path.read_text(errors="replace")
    except Exception:
        return ""


def _chunk(text: str) -> list[str]:
    """Split text into section-level chunks: markdown headings first, else paragraph blocks;
    oversize sections are hard-wrapped and tiny adjacent ones coalesced toward MIN_CHARS."""
    text = text.strip()
    if not text:
        return []
    positions = [m.start() for m in HEAD_RE.finditer(text)]
    if positions:
        sections = []
        if positions[0] > 0:
            sections.append(text[: positions[0]])
        bounds = positions + [len(text)]
        for i in range(len(positions)):
            sections.append(text[positions[i]: bounds[i + 1]])
    else:
        sections = PARA_RE.split(text)

    sized: list[str] = []
    for s in sections:
        s = s.strip()
        if not s:
            continue
        if len(s) <= MAX_CHARS:
            sized.append(s)
            continue
        for para in PARA_RE.split(s):
            para = para.strip()
            while len(para) > MAX_CHARS:
                sized.append(para[:MAX_CHARS])
                para = para[MAX_CHARS:]
            if para:
                sized.append(para)

    merged: list[str] = []
    for s in sized:
        if merged and len(merged[-1]) < MIN_CHARS:
            merged[-1] = merged[-1] + "\n\n" + s
        else:
            merged.append(s)
    return merged


def atomize_doc(path: Path) -> list[dict]:
    """One document → its section-level atoms (dicts). Bytes never inlined beyond the text."""
    chunks = _chunk(_extract_text(path))
    atoms = []
    for i, c in enumerate(chunks):
        atoms.append({
            "id": _hash(str(path), str(i), c[:120]),
            "text": c,
            "source": str(path),
            "doc": path.name,
            "section": i,
            "kind": "doc",
        })
    return atoms


# ─── store (content-addressed, dedup, idempotent) ────────────────────

def _store_atom(atom: dict, apply: bool) -> bool:
    """Write ONE atom content-addressed; dedup by id. Returns True if it was new."""
    dst = _atoms_root() / f"{atom['id']}.json"
    if dst.exists():
        return False
    if apply:
        from limen.io import atomic_write_text
        _atoms_root().mkdir(parents=True, exist_ok=True)
        atomic_write_text(dst, json.dumps(atom, ensure_ascii=False, indent=2))
    return True


def _load_atoms(limit: int) -> list[dict]:
    """Load up to ``limit`` stored atoms (for the --converge proof). Fail-open."""
    root = _atoms_root()
    out: list[dict] = []
    if not root.is_dir():
        return out
    for p in sorted(root.glob("*.json"))[:limit]:
        try:
            out.append(json.loads(p.read_text()))
        except Exception:
            continue
    return out


def _load_state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except Exception:
        return {"absorbed": {}}


def _save_state(state: dict) -> None:
    from limen.io import atomic_write_text
    _state_path().parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(_state_path(), json.dumps(state, indent=2))


# ─── prove the engine reuse (offline) ────────────────────────────────

def _prove_converge(idea: str, limit: int = 50) -> None:
    """Distill the stored atoms at ``idea`` with the OFFLINE kit — proof the media atoms
    flow through the SAME engine that distills his words. No network, no write-back."""
    from limen.converge import Shot, _build_dry_run_kit, converge
    atoms = _load_atoms(limit)
    if not atoms:
        print("[media-atomize] no stored atoms yet — nothing to converge")
        return
    shots = [Shot(id=a["id"], text=a.get("text", ""), source=a.get("source", "")) for a in atoms]
    r = converge(idea, shots, **_build_dry_run_kit())
    head = r.better_version.strip().splitlines()[:6]
    print("── media converge (offline proof) ──")
    print(f"  idea: {idea}")
    print(f"  atoms: {len(shots)}  score: {r.score:.3f}  promoted: {r.promoted}  "
          f"cited: {len(r.cited_losers)}  next_shots: {len(r.next_shots)}")
    if head:
        print("  better_version (head): " + " ".join(head)[:300])


# ─── main ────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="media-atomize — his docs → first-class Shot atoms (strand D slice 1)")
    ap.add_argument("--apply", action="store_true", help="write atoms/state/log (else preview)")
    ap.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_MEDIA_LIMIT", "50")),
                    help="max source documents atomized per run (bounded)")
    ap.add_argument("--src", default=None, help="docs source dir (default: Archive4T CloudDocs copy)")
    ap.add_argument("--converge", metavar="IDEA", default=None,
                    help="after atomizing, distill the stored atoms at IDEA (offline proof)")
    args = ap.parse_args(argv)

    src = Path(args.src).expanduser() if args.src else _src_root()
    state = _load_state()
    absorbed: dict = state.get("absorbed", {})

    docs = atoms_new = skipped_pdf = 0
    done: list[tuple[str, str]] = []
    if not src.is_dir():
        print(f"[media-atomize] source {src} not present — nothing to ingest (fail-open)")
    else:
        for p in _iter_docs(src, args.limit):
            sig = _sig(p)
            if sig and absorbed.get(str(p)) == sig:
                continue  # unchanged since last absorb → idempotent skip
            try:
                shots = atomize_doc(p)
            except Exception as exc:  # never crash the heartbeat
                print(f"[media-atomize] {p.name}: atomize failed ({exc}); skipping")
                continue
            if not shots:
                if p.suffix.lower() == ".pdf":
                    skipped_pdf += 1
                continue
            wrote = sum(1 for a in shots if _store_atom(a, args.apply))
            docs += 1
            atoms_new += wrote
            done.append((str(p), sig))
            print(f"[media-atomize] {p.name}: {len(shots)} sections → {wrote} new atoms"
                  f"{'' if args.apply else ' (preview)'}")

    if args.apply and done:
        for sp, sg in done:
            absorbed[sp] = sg
        state["absorbed"] = absorbed
        _save_state(state)
        try:
            _log_path().parent.mkdir(parents=True, exist_ok=True)
            with _log_path().open("a") as fh:
                fh.write(json.dumps({"ts": _now().isoformat(), "docs": docs,
                                     "atoms_new": atoms_new, "skipped_pdf": skipped_pdf}) + "\n")
        except Exception:
            pass

    pdf_note = f", {skipped_pdf} pdf skipped (no pdftotext)" if skipped_pdf else ""
    mode = "apply" if args.apply else "preview"
    print(f"[media-atomize] {docs} docs → {atoms_new} new atoms{pdf_note} "
          f"[{mode}] store={_atoms_root()}")

    if args.converge:
        _prove_converge(args.converge)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
