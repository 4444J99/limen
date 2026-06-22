#!/usr/bin/env python3
"""studium-objectlessons.py — the bridge between the Studium and Anthony's OBJECT LESSONS project.

His direction: the day's film "feeds into object lessons." objectlessons.film (repo organvm/object-lessons)
is his editorial product — a 253-film database (films.yaml) tracking recurring OBJECTS (milk/mirror/clock/…)
across cinema, every film keyed by `letterboxd_url`. This script joins three sources, READ-ONLY, by Letterboxd
slug, and writes a crosswalk the analysis face renders:

  1. his 253-film DB        (object-lessons/src/data/films.yaml)         → objects per film
  2. the Studium film picks (studium/film/<work>.yaml)                   → force + object_lesson per film
  3. his watch history      (logs/letterboxd-history.json)               → what he has SEEN

The unifying model: film ↔ { force (Studium) · object (Object Lessons) · watched (Letterboxd) }. This is the
SAFE side of the bridge — it never edits the live object-lessons repo (that is a his-gate branch). Fail-open:
a missing DB or history simply degrades the crosswalk; it never errors.

Output: logs/objectlessons-crosswalk.json.

Usage:  python3 scripts/studium-objectlessons.py
"""
import json
import os
import re
import tempfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
STUDIUM = ROOT / "studium"
LOGS = ROOT / "logs"
OL_FILMS = Path(os.path.expanduser(os.environ.get(
    "LIMEN_OBJECTLESSONS_FILMS",
    "~/Workspace/organvm/object-lessons/src/data/films.yaml")))
OUT = LOGS / "objectlessons-crosswalk.json"

try:
    import yaml
except ImportError:
    yaml = None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _slug_from_uri(uri):
    m = re.search(r"/film/([^/]+)/?", str(uri or ""))
    return m.group(1) if m else ""


def load_ol_db():
    """{slug: {title, year, objects:[...]}} from his films.yaml. Empty if absent (fail-open)."""
    if yaml is None or not OL_FILMS.exists():
        return {}, False
    try:
        films = yaml.safe_load(OL_FILMS.read_text()) or []
    except (OSError, yaml.YAMLError):
        return {}, False
    db = {}
    for f in films:
        if not isinstance(f, dict):
            continue
        slug = _slug_from_uri(f.get("letterboxd_url")) or str(f.get("id") or "")
        objs = sorted({(o.get("object") or "").strip() for o in (f.get("objects") or []) if o.get("object")})
        db[slug] = {"title": f.get("title"), "year": f.get("year"), "objects": objs,
                    "density": f.get("density_score")}
    return db, True


def load_studium_picks():
    """Every Studium film pick across all film companions: {slug, title, year, force, work, objects[]}."""
    picks = []
    for p in sorted((STUDIUM / "film").glob("*.yaml")):
        if p.name == "object-taxonomy.yaml":
            continue
        doc = (yaml.safe_load(p.read_text()) or {}) if yaml else {}
        for fm in doc.get("films") or []:
            picks.append({
                "title": fm.get("title"), "year": fm.get("year"),
                "slug": (fm.get("letterboxd") or "").strip(),
                "force": (fm.get("force") or "").strip(),
                "objects": fm.get("objects") or [],
                "work": doc.get("work") or p.stem,
            })
    return picks


def load_seen():
    try:
        data = json.loads((LOGS / "letterboxd-history.json").read_text())
    except (OSError, ValueError):
        return set()
    films = data.get("films") if isinstance(data, dict) else data
    return {(r.get("slug") or "").strip() for r in (films or []) if r.get("slug")}


def main():
    db, present = load_ol_db()
    seen = load_seen()
    picks = load_studium_picks()

    # join each Studium pick onto his DB (by slug) + his watch history
    rows = []
    in_db = 0
    for pk in picks:
        slug = pk["slug"]
        ol = db.get(slug)
        if ol:
            in_db += 1
        rows.append({
            **pk,
            "in_db": bool(ol),
            "ol_objects": (ol or {}).get("objects", []),
            "seen": slug in seen,
        })

    # object coverage across his DB (what his catalogue is "about")
    obj_counts = Counter()
    for v in db.values():
        for o in v["objects"]:
            obj_counts[o] += 1

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": str(date.today()),
        "ol_db": {"path": str(OL_FILMS), "present": present, "films": len(db),
                  "objects": dict(obj_counts.most_common())},
        "letterboxd": {"seen_total": len(seen),
                       "seen_in_db": len([s for s in seen if s in db])},
        "studium": {"picks": len(picks), "in_db": in_db, "rows": rows},
    }
    _atomic_write(OUT, json.dumps(payload, indent=2))
    print(f"studium-objectlessons: DB {'present' if present else 'ABSENT'} ({len(db)} films) · "
          f"{len(picks)} studium picks ({in_db} in DB) · {len(seen)} watched ({payload['letterboxd']['seen_in_db']} in DB) -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
