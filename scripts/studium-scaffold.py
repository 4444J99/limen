#!/usr/bin/env python3
"""studium-scaffold.py — generate the whole Studium edifice from canon.yaml.

Lays out the full structure with a PLAN.md manifest in EVERY location and a master STUDIUM-PLAN.md
tracker — the "plan of every item, full structure, a plan file in every location." Idempotent and
self-updating: statuses reflect which content files are actually authored, so re-running refreshes the
tracker. NO empty per-division stubs — manifests enumerate the items; content (book-NN.yaml, <lang>.md,
<work>.md) appears as authored.

Layers per work:  reading orientation · music arc(s) · essay(s) · script lesson (per language).

Usage:  python3 scripts/studium-scaffold.py        # (re)generate manifests + tracker
"""
import os
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
STUDIUM = ROOT / "studium"

try:
    import yaml
except ImportError:
    yaml = None


def _w(path: Path, text: str):
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
    return (yaml.safe_load((STUDIUM / "canon.yaml").read_text()) or {}) if yaml else {}


def _music_count(wid):
    d = STUDIUM / "music" / wid
    return len(list(d.glob("book-*.yaml"))) if d.exists() else 0


def _film_done(wid):
    return (STUDIUM / "film" / f"{wid}.yaml").exists()


def reading_done(wid):
    return (STUDIUM / "reading" / f"{wid}.md").exists()


def script_done(lang):
    return (STUDIUM / "scripts" / f"{lang}.md").exists()


def write_work_music_plan(wid, w):
    divs = w.get("divisions", {}) or {}
    n = divs.get("count") or 0
    label = divs.get("label", "Section")
    done = _music_count(wid)
    rows = []
    for i in range(1, int(n) + 1):
        f = STUDIUM / "music" / wid / f"book-{i:02d}.yaml"
        rows.append(f"| {i} | (author) | {'✓' if f.exists() else '☐'} |")
    cantiche = divs.get("cantiche")
    rail = (w.get("source_rails") or ["—"])[0]
    body = f"""# Music arcs — {w.get('title')} (`{wid}`)

> **Manifest.** Author one `book-NN.yaml` per {label.lower()} in the gold-standard format
> (template: [`../iliad/book-01.yaml`](../iliad/book-01.yaml); prose seed: `../../_seed/iliad-book-01-playlist.md`).
> Each arc = scene → track → decision + per-track *why*, with a `force_arc` from
> [`../../dominant-force.yaml`](../../dominant-force.yaml). The publishable essay mirrors to
> `../../essays/{wid}/book-NN.md`. Status ✓ = the file exists.

- **Main question:** {w.get('main_question')}
- **Tradition / script:** {w.get('tradition')} / {w.get('script')} · **language lesson:** [`../../scripts/{w.get('language')}.md`](../../scripts/{w.get('language')}.md)
- **Corpus:** `{w.get('corpus_path')}` ({w.get('original_file') or 'translations only'})
- **Source rail:** {rail}
- **Divisions:** {n} × {label}{(' · cantiche: ' + ', '.join(cantiche)) if cantiche else ''}
- **Progress:** {done}/{n} arcs authored

| {label} | dominant force | status |
| --: | --- | :--: |
{chr(10).join(rows) if rows else '| — | — | — |'}
"""
    _w(STUDIUM / "music" / wid / "PLAN.md", body)
    (STUDIUM / "essays" / wid).mkdir(parents=True, exist_ok=True)


def main():
    if not yaml:
        print("studium-scaffold: pyyaml unavailable; cannot read canon")
        return 0
    canon = _canon()
    works = canon.get("works", {})
    if not works:
        print("studium-scaffold: no works in canon.yaml")
        return 0

    # order works by the chronological index for a stable presentation
    order = sorted(works.items(), key=lambda kv: kv[1].get("order_indices", {}).get("chronological", 999))
    languages = []
    for wid, w in order:
        write_work_music_plan(wid, w)
        lang = w.get("language")
        if lang and lang not in languages:
            languages.append(lang)

    # staged Tier-2 works (his "after the first pass") are enumerated + located but kept out of the
    # first-pass coverage counts and out of orderings.yaml — they grow on his gate, not the daily face.
    active = [(wid, w) for wid, w in order if not w.get("staged")]
    staged = [(wid, w) for wid, w in order if w.get("staged")]

    # ── per-layer manifests ──────────────────────────────────────────────
    _w(STUDIUM / "music" / "PLAN.md",
       "# Music layer — force-matched classical arcs\n\n"
       "> Each work has its own `<work>/PLAN.md` enumerating every division. Method: tag each passage "
       "with a dominant force (`../dominant-force.yaml`) → choose a piece whose affect meets that "
       "force's musical requirement; justify every track the way Book I does. Gold standard: "
       "`iliad/book-01.yaml`. Iliad is complete (24/24).\n\n"
       "## Works (first pass)\n" + "\n".join(
           f"- [`{wid}`]({wid}/PLAN.md) — {w.get('title')} · {_music_count(wid)}/{(w.get('divisions') or {}).get('count','?')} arcs"
           for wid, w in active)
       + ("\n\n## Tier 2 — staged (after the first pass)\n" + "\n".join(
           f"- [`{wid}`]({wid}/PLAN.md) — {w.get('title')} · {_music_count(wid)}/{(w.get('divisions') or {}).get('count','?')} arcs · staged"
           for wid, w in staged) if staged else "") + "\n")

    _w(STUDIUM / "essays" / "PLAN.md",
       "# Essays layer — publishable per-arc prose\n\n"
       "> One `essays/<work>/book-NN.md` per music arc: a short framing of the division, the track "
       "table, per-track reasoning (scene → why the piece fits the force), and the dominant arc. These "
       "are the build-in-public artifacts (`../publish/_drafts/` are generated from them + the arcs by "
       "`scripts/studium-publish.py`). They mirror the music arcs 1:1.\n")

    _w(STUDIUM / "reading" / "PLAN.md",
       "# Reading layer — per-work orientations\n\n"
       "> One `reading/<work>.md` per work: how to read it (structure, the main question, what to watch "
       "for, how to portion it daily, which translation to compare). Surfaced in the daily face beside "
       "the passage. Template: keep it to one page; lead with the work's main question from "
       "`../canon.yaml`.\n\n## Works (first pass)\n" + "\n".join(
           f"- `{wid}.md` — {w.get('title')} — *{w.get('main_question')}* — {'✓' if reading_done(wid) else '☐'}"
           for wid, w in active)
       + ("\n\n## Tier 2 — staged (after the first pass)\n" + "\n".join(
           f"- `{wid}.md` — {w.get('title')} — *{w.get('main_question')}* — {'✓' if reading_done(wid) else '☐ staged'}"
           for wid, w in staged) if staged else "") + "\n")

    _w(STUDIUM / "scripts" / "PLAN.md",
       "# Script / language layer\n\n"
       "> One `<language>.md` per script, three layers each (calligraphy/paleography · glossed reading · "
       "grammar), per his order *script → grammar → translation*. Template: `greek.md` (done). "
       "The interlinear gloss tool `scripts/studium-gloss.py` operates over the corpus per work.\n\n"
       "## Languages (derived from canon.yaml)\n" + "\n".join(
           f"- `{lang}.md` — {'✓' if script_done(lang) else '☐'}" for lang in languages) + "\n")

    # ── master tracker ───────────────────────────────────────────────────
    rows, r_done, s_done, arcs_total, divs_total, film_done = [], 0, 0, 0, 0, 0
    for wid, w in active:
        n = (w.get("divisions") or {}).get("count") or 0
        mc = _music_count(wid)
        rdone = reading_done(wid)
        fdone = _film_done(wid)
        lang = w.get("language")
        sdone = script_done(lang)
        r_done += 1 if rdone else 0
        film_done += 1 if fdone else 0
        arcs_total += mc
        divs_total += int(n)
        rows.append(f"| {w.get('title')} | {w.get('tradition')} | {'✓' if rdone else '☐'} "
                    f"| {mc}/{n} | {'✓' if fdone else '☐'} | {lang} {'✓' if sdone else '☐'} |")
    s_done = sum(1 for l in languages if script_done(l))
    staged_rows = [
        f"| {w.get('title')} | {w.get('tradition')} | {(w.get('divisions') or {}).get('count','?')} × "
        f"{(w.get('divisions') or {}).get('label','—')} | {_music_count(wid)} arcs | "
        f"{'✓' if _film_done(wid) else '☐'} | {w.get('language')} |"
        for wid, w in staged]
    staged_section = ("" if not staged else
        "\n## Tier 2 — staged (after the first pass, his spec §57)\n"
        "Enumerated + located; kept out of `orderings.yaml` so the daily face does not route to them "
        "until his gate. Reading + arcs + film deferred to `expansion-backlog.yaml`.\n\n"
        "| Work | Tradition | Divisions | Music | Film | Script |\n| --- | --- | :--: | :--: | :--: | --- |\n"
        + "\n".join(staged_rows) + "\n")
    tracker = f"""# THE STUDIUM — master plan & tracker

> Generated by `scripts/studium-scaffold.py` from `canon.yaml`. **Re-run to refresh statuses.**
> The whole edifice: every work × {{ reading · music · script }}, every division located. A `PLAN.md`
> manifest lives in every directory; content files appear as authored (no empty stubs).

## The ~100 things — coverage matrix
| Work | Tradition | Reading | Music (arcs/divs) | Film | Script |
| --- | --- | :--: | :--: | :--: | --- |
{chr(10).join(rows)}

**Totals:** reading {r_done}/{len(active)} · scripts {s_done}/{len(languages)} · film companions {film_done}/{len(active)} · music {arcs_total} arcs authored of {divs_total} divisions across the first-pass canon.
{staged_section}
## Method
Read → copy the original script → translate a unit → compare translations → one note → one fitting
composition (its **dominant force** drives the choice) → log. The music is a second commentary system,
the handwriting a third, translation the encounter. Gold standard for arcs: `music/iliad/`.

## Fill strategies (all enabled by this scaffold — his "all of your options")
- **Breadth-first** — one arc + reading orientation per work + the script lessons (all ~100 at first-pass depth).
- **One-work-deep** — a work to its full division count, Iliad-style (Iliad = done, 24/24).
- **By-layer** — all scripts, or all reading orientations, across the canon.
Deepening is gap-driven: each `music/<work>/PLAN.md` lists the unfilled divisions → fleet across all lanes.

## A plan file in every location
- `music/PLAN.md`, `essays/PLAN.md`, `reading/PLAN.md`, `scripts/PLAN.md` (the layers)
- `music/<work>/PLAN.md` (every work — its full division list + status)
- this file (the master index)

## Gate (`release-gate-hold`)
Staged on `feat/studium-transmission-curriculum`; non-destructive. His levers: live-daemon deploy
(`LIMEN_STUDIUM=1`), the edu-organism mirror, all publishing, opening the deepening backlog to the fleet.
"""
    _w(STUDIUM / "STUDIUM-PLAN.md", tracker)

    print(f"studium-scaffold: {len(active)} first-pass + {len(staged)} staged works · {len(languages)} languages · "
          f"reading {r_done}/{len(active)} · scripts {s_done}/{len(languages)} · film {film_done}/{len(active)} · {arcs_total} arcs · "
          f"manifests in music/<work>/ + 4 layers + master tracker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
