#!/usr/bin/env python3
"""studium-validate.py — deterministic invariant checker + reconciler for the music arcs.

The dominant-force engine has hard invariants the face depends on (force-colored music). This validates
every `studium/music/<work>/book-NN.yaml` against them and can mechanically reconcile the one purely-
bookkeeping invariant (force_arc) so heal agents never have to transcribe a 13-element array by hand:

  1. every track `force` is a VALID force (keys of dominant-force.yaml)
  2. `dominant_force` is a VALID force
  3. `force_arc` length == number of tracks
  4. `force_arc[i] == tracks[i].force`  (the gold-standard invariant; see music/iliad/book-10.yaml)

Forces are DERIVED from dominant-force.yaml (never pinned) per derive-never-pin-hardcodes.

Usage:
  python3 scripts/studium-validate.py              # report violations, exit 1 if any
  python3 scripts/studium-validate.py --reconcile  # rewrite force_arc = ordered track forces, then report
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
STUDIUM = ROOT / "studium"

# Hand-seeded arcs whose force_arc intentionally encodes the SCENE arc (distinct from the music's
# per-track force) — Anthony's verbatim Iliad Book I playlist. force_arc renders as its own strip in
# the face (studium.py), independent of per-track colors, so divergence here is by design, not a bug.
# These are exempt from the force_arc==track-forces equality (still checked for valid forces + length).
SCENE_ARC_EXEMPT = {"music/iliad/book-01.yaml"}

try:
    import yaml
except ImportError:
    yaml = None


def valid_forces():
    data = yaml.safe_load((STUDIUM / "dominant-force.yaml").read_text()) or {}
    return set((data.get("forces") or {}).keys())


def valid_objects():
    """The Object Lessons taxonomy (studium/film/object-taxonomy.yaml). Empty if absent → checks skipped
    (fail-open; objects are an optional bridge to objectlessons.film)."""
    try:
        data = yaml.safe_load((STUDIUM / "film" / "object-taxonomy.yaml").read_text()) or {}
    except OSError:
        return set()
    return {(o.get("slug") or "").strip() for o in (data.get("objects") or []) if o.get("slug")}


def arc_files():
    return sorted((STUDIUM / "music").glob("*/book-*.yaml"))


def film_files():
    # per-work companions only — object-taxonomy.yaml is the tracked-object dictionary, not a companion
    return sorted(f for f in (STUDIUM / "film").glob("*.yaml") if f.name != "object-taxonomy.yaml")


def validate_film(valid, objs):
    """The fourth commentary system: every film `force` (and adaptation scene force) ∈ force taxonomy, and
    every `objects[]` ∈ the Object Lessons taxonomy (when that taxonomy is present). Non-breaking + fail-open
    — a missing film/ dir simply yields no checks; an absent object-taxonomy.yaml skips the object checks."""
    viol = []
    for f in film_files():
        try:
            doc = yaml.safe_load(f.read_text()) or {}
        except Exception as e:  # noqa: BLE001
            viol.append((f.relative_to(STUDIUM), f"YAML parse error: {e}"))
            continue
        rel = f.relative_to(STUDIUM)
        for i, fm in enumerate(doc.get("films") or [], 1):
            fc = (fm.get("force") or "").strip()
            if fc not in valid:
                viol.append((rel, f"film {i} ({fm.get('title','?')}): invalid force {fc!r}"))
            if objs:
                for ob in fm.get("objects") or []:
                    if (ob or "").strip() not in objs:
                        viol.append((rel, f"film {i} ({fm.get('title','?')}): unknown object {ob!r} (not in object-taxonomy.yaml)"))
        for ad in doc.get("adaptations") or []:
            for sc in ad.get("scenes") or []:
                fc = (sc.get("force") or "").strip()
                if fc and fc not in valid:
                    viol.append((rel, f"adaptation {ad.get('title','?')}: invalid scene force {fc!r}"))
    return viol


def reconcile_file(path: Path, track_forces):
    """Rewrite the force_arc flow-list to equal the ordered track forces. Preserves comments/format."""
    text = path.read_text()
    new_line = "force_arc: [" + ", ".join(track_forces) + "]"
    # match `force_arc:` then EITHER a flow list [...] OR a block list (\n  - item ...), so the
    # reconciler is robust to both styles the authoring agents emitted.
    pat = re.compile(r"force_arc:[ \t]*(?:\[.*?\]|(?:\n[ \t]+-[ \t]*\S+)+)", re.DOTALL)
    if not pat.search(text):
        return False
    new_text = pat.sub(new_line, text, count=1)
    if new_text == text:
        return False
    path.write_text(new_text)
    return True


def main():
    if not yaml:
        print("studium-validate: pyyaml unavailable")
        return 2
    do_reconcile = "--reconcile" in sys.argv
    VALID = valid_forces()
    files = arc_files()
    reconciled, violations = [], []

    for f in files:
        try:
            doc = yaml.safe_load(f.read_text()) or {}
        except Exception as e:  # noqa: BLE001
            violations.append((f, f"YAML parse error: {e}"))
            continue
        tracks = doc.get("tracks") or []
        tforces = [t.get("force") for t in tracks]
        rel = f.relative_to(STUDIUM)
        relkey = rel.as_posix()
        exempt = relkey in SCENE_ARC_EXEMPT

        # 1/2 valid forces
        for i, fc in enumerate(tforces, 1):
            if fc not in VALID:
                violations.append((rel, f"track {i}: invalid force {fc!r}"))
        df = doc.get("dominant_force")
        if df is not None and df not in VALID:
            violations.append((rel, f"dominant_force: invalid {df!r}"))

        # reconcile force_arc (bookkeeping) — only if track forces are themselves valid, and never
        # for a hand-seeded scene-arc (its force_arc is intentionally distinct from the music force)
        if do_reconcile and not exempt and tforces and all(fc in VALID for fc in tforces):
            arc = doc.get("force_arc") or []
            if list(arc) != tforces and reconcile_file(f, tforces):
                reconciled.append(rel)
                continue  # file rewritten; it now satisfies 3/4 by construction

        # 3/4 force_arc invariants
        arc = doc.get("force_arc") or []
        if len(arc) != len(tforces):
            violations.append((rel, f"force_arc length {len(arc)} != {len(tforces)} tracks"))
        elif not exempt and list(arc) != tforces:
            bad = [i + 1 for i, (a, b) in enumerate(zip(arc, tforces)) if a != b]
            violations.append((rel, f"force_arc != track forces at positions {bad}"))

    # film layer (the fourth commentary system) — additive, non-breaking
    films = film_files()
    violations.extend(validate_film(VALID, valid_objects()))

    if reconciled:
        print(f"reconciled force_arc in {len(reconciled)} file(s):")
        for r in reconciled:
            print(f"  ~ {r}")
    if violations:
        print(f"\n{len(violations)} violation(s):")
        for rel, msg in violations:
            print(f"  ✗ {rel}: {msg}")
        return 1
    print(f"\n✓ all {len(files)} arcs valid (forces ∈ taxonomy; force_arc == track forces)"
          f" · {len(films)} film companion(s) valid (forces ∈ taxonomy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
