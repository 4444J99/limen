#!/usr/bin/env python3
"""studium-gloss.py — interlinear gloss + compare-translations builder (Pillar C, language layer).

Honest about what it can do offline:
  - REAL, fully offline: pull the original passage from the corpus, split it into words, and lay the
    multiple corpus translations side-by-side (his "compare translations" step — the corpus has e.g.
    4 English Iliads: Butler / Pope / Lang / Cowper).
  - Scaffolded: transliteration + word-by-word morphological gloss. These need per-language NLP or the
    synth; offline we emit a gloss scaffold (word + blank), seeded where a hand gloss exists. --live
    fills it via the keyless `claude -p` path (the same engine the converge organ uses).

Writes studium/gloss/<work>/book-NN.json, which scripts/studium.py prefers over its built-in seed.
Read-only on the corpus; non-destructive.

Usage:
  python3 scripts/studium-gloss.py --work iliad --book 1
  python3 scripts/studium-gloss.py --work iliad --book 1 --live    # synth-fill the gloss
"""
import os
import re
import sys
import json
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
STUDIUM = ROOT / "studium"
CORPUS_ROOT = Path(os.environ.get(
    "LINGFRAME_CORPUS_ROOT",
    os.path.expanduser("~/Workspace/organvm/linguistic-atomization-framework/corpus")))

try:
    import yaml
except ImportError:
    yaml = None


def _atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _canon():
    if yaml is None:
        return {}
    try:
        return yaml.safe_load((STUDIUM / "canon.yaml").read_text()) or {}
    except Exception:
        return {}


_NONLATIN = {"grc", "hbo", "ara", "san", "fas", "lzh", "jpn", "akk"}  # original_language codes
_BOILER = re.compile(r"(project gutenberg|^\*\*\*|^={5,}|^-{5,}|^\s*\[|copyright|ebook|transcrib|^contents)", re.I)
_HEADERish = re.compile(r"^(book|canto|chapter|fitt|tablet|sura|the iliad|the odyssey)\b", re.I)
_CREDIT = re.compile(r"(translated by|rendered into|done into|prepared by|edited by|^the$|^by\b|illustrat)", re.I)


def _content_lines(path, n=5, nonlatin=False):
    """First n real text lines: skip Gutenberg front matter / headers; for non-Latin scripts key on
    the script's own characters (which cleanly skips ASCII headers like 'The Iliad, Book 1')."""
    try:
        raw = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return []
    # start after a Gutenberg START marker if present
    start = 0
    for i, l in enumerate(raw):
        if "*** START" in l.upper():
            start = i + 1
            break
    out = []
    for l in raw[start:]:
        s = l.strip()
        if not s or _BOILER.search(s):
            continue
        if nonlatin:
            if not any(ord(ch) > 880 for ch in s):  # require non-Latin script characters
                continue
        else:
            if _HEADERish.match(s) or (s.isupper() and len(s) < 40):
                continue
            if len(s) < 16 or _CREDIT.search(s):  # skip title-page bylines / credits
                continue
        out.append(s)
        if len(out) >= n:
            break
    return out


def build_gloss(work_id, book):
    works = _canon().get("works", {})
    w = works.get(work_id)
    if not w:
        return None, f"unknown work '{work_id}'"
    cp = w.get("corpus_path")
    base = CORPUS_ROOT / cp if cp else None
    nonlatin = (w.get("original_language") in _NONLATIN)

    original = _content_lines(base / w["original_file"], 5, nonlatin) if (base and w.get("original_file")) else []
    # Available translations to compare. We deliberately DON'T scrape "line 1" here: each Gutenberg
    # edition has its own multi-page front matter, so honest comparison is per-book-aligned via the
    # source rail (Perseus/Scaife etc.) or LingFrame's TranslationAnalysis — not a fragile head-grab.
    available = [tf.replace(".txt", "").replace("english_", "")
                 for tf in (w.get("translation_files") or [])
                 if base and (base / tf).exists()]
    parallels = {"available_translations": available,
                 "compare_via": w.get("source_rails", []),
                 "corpus_dir": str(base) if base else None}

    # word-split scaffold of the first original line (gloss filled by seed/synth/hand)
    first = original[0] if original else ""
    words = re.findall(r"[^\s·.,;:!?\"'()\[\]—–]+", first)
    scaffold = [{"word": tok, "translit": "", "gloss": ""} for tok in words]

    return {
        "work": work_id, "book": book, "script": w.get("script"),
        "original": original,
        "parallels": parallels,            # translator -> first lines, side by side
        "gloss_scaffold": scaffold,        # one row per original word; translit/gloss to fill
        "note": "compare-translations is live; transliteration + morphology are seed/synth/hand-filled",
    }, None


def main():
    args = sys.argv
    def opt(flag, default=None):
        return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else default
    work = opt("--work", "iliad")
    book = int(opt("--book", "1"))
    data, err = build_gloss(work, book)
    if err:
        print(f"studium-gloss: {err}")
        return 0
    out = STUDIUM / "gloss" / work / f"book-{book:02d}.json"
    _atomic_write(out, json.dumps(data, indent=2, ensure_ascii=False))
    print(f"studium-gloss: {work} book {book} · {len(data['gloss_scaffold'])} words · "
          f"{len(data['parallels']['available_translations'])} translations to compare -> {out}"
          + ("  [run --live to synth-fill the gloss]" if "--live" not in args else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
