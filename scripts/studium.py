#!/usr/bin/env python3
"""studium.py — the daily transmission-curriculum face.

Each day this renders today's passage through the studium protocol — reading + original-script
handwriting drill + glossed translation + a force-matched classical composition — and writes a
self-contained web/app/out/studium.html (meta-refresh, pure string templating — NO Next.js, NO
network, so it CANNOT time out), mirrored to web/app/public/ for the remote/phone face. It also
exports today's daily-page (his template, pre-filled) to studium/ledger/ for handwriting.

ALL avenues are surfaced as his living choices (his "why reduce? always all avenues"): every reading
ORDERING, PACE, and LANGUAGE DEPTH is visualized and switchable from logs/studium-state.json — never
pre-decided down to one.

Anti-waste + never-"NO": every section fails OPEN — a missing canon/music/corpus file yields an empty
or degraded section, never a crash. Read-only on the corpus + curriculum; writes only its own outputs.

Usage:
  python3 scripts/studium.py            # render today's face
  python3 scripts/studium.py --advance  # advance the reading cursor one day, then render
"""
import json
import os
import sys
import tempfile
import urllib.parse
from datetime import date, datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
STUDIUM = ROOT / "studium"
LOGS = ROOT / "logs"
LEDGER = STUDIUM / "ledger"
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]

CORPUS_ROOT = Path(os.environ.get(
    "LINGFRAME_CORPUS_ROOT",
    os.path.expanduser("~/Workspace/organvm/linguistic-atomization-framework/corpus"),
))

try:
    import yaml
except ImportError:  # fail-open: the face still renders, just without YAML-backed data
    yaml = None

DEFAULT_STATE = {
    "ordering": "interleaved",      # interleaved | western_eastern | chronological
    "pace": "standard",             # gentle | standard | intensive
    "language_depth": "glossed",    # calligraphy | glossed | grammar
    # position tracks the WORK (not an ordering-relative index), so switching the canon lens keeps
    # you on the same book. Default: where he is now — the Iliad, Book I.
    "position": {"work_id": "iliad", "division": 1, "day_in_division": 1},
    "streak": 0,
    "last_advanced": None,
    "history": [],
}

# Seeded interlinear gloss for the very first passage so day-one looks complete; the real gloss
# module (Pillar C, extending LingFrame TranslationAnalysis) supersedes this per-passage.
SEED_GLOSS = {
    ("iliad", 1): {
        "original": "μῆνιν ἄειδε θεὰ Πηληϊάδεω Ἀχιλῆος",
        "translit": "mēnin aeide thea Pēlēiadeō Achilēos",
        "gloss": [["μῆνιν", "wrath (acc.)"], ["ἄειδε", "sing (impv.)"], ["θεά", "goddess (voc.)"],
                  ["Πηληϊάδεω", "of Peleus' son"], ["Ἀχιλῆος", "of Achilles"]],
        "literal": "The wrath sing, goddess, of Peleus' son Achilles",
        "literary": "Rage — sing, goddess, the rage of Achilles, son of Peleus",
    },
}


# ── io helpers (self-contained; never corrupt on crash) ─────────────────────────
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


def _load_yaml(path: Path, default):
    if yaml is None:
        return default
    try:
        return yaml.safe_load(Path(path).read_text()) or default
    except (OSError, ValueError, yaml.YAMLError):
        return default


def _load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ── state ───────────────────────────────────────────────────────────────────────
def load_state():
    st = _load_json(LOGS / "studium-state.json", {})
    merged = json.loads(json.dumps(DEFAULT_STATE))  # deep copy
    merged.update({k: v for k, v in st.items() if k in merged})
    pos = dict(DEFAULT_STATE["position"])
    pos.update(st.get("position", {}) if isinstance(st.get("position"), dict) else {})
    merged["position"] = pos
    return merged


# ── canon / orderings / pace resolution ─────────────────────────────────────────
def work_sequence(canon, orderings, ordering_key):
    """Return the ordered list of work ids for the active ordering (derived from orderings.yaml)."""
    spec = (orderings.get("orderings", {}) or {}).get(ordering_key, {})
    seq = []
    if "sequence" in spec:
        seq = list(spec["sequence"])
    elif "phases" in spec:
        for ph in spec["phases"]:
            seq.extend(ph.get("works", []))
    elif "movements" in spec:
        for mv in spec["movements"]:
            seq.extend(mv.get("works", []))
    works = canon.get("works", {})
    return [w for w in seq if w in works]


def resolve_today(canon, orderings, paces, state):
    works = canon.get("works", {})
    seq = work_sequence(canon, orderings, state["ordering"]) or list(works.keys())
    if not seq:
        return None
    pos = state["position"]
    work_id = pos.get("work_id") or seq[0]
    if work_id not in works:
        work_id = seq[0]
    wi = seq.index(work_id) if work_id in seq else 0
    w = works.get(work_id, {})
    div = pos.get("division", 1)
    divs = w.get("divisions", {}) or {}
    pace = (paces.get("paces", {}) or {}).get(state["pace"], {})
    lines_per_day = pace.get("lines_per_day", 300)
    return {
        "work_id": work_id, "work": w, "division": div,
        "division_label": divs.get("label", "Section"),
        "division_count": divs.get("count"),
        "division_kind": divs.get("kind", "section"),
        "day_in_division": pos.get("day_in_division", 1),
        "lines_per_day": lines_per_day,
        "sequence": seq, "work_index": wi,
    }


def advance_cursor(state, today):
    """Move one day forward: step within a division by lines_per_day; roll to next division/work."""
    pos = state["position"]
    w = today["work"]
    divs = w.get("divisions", {}) or {}
    kind = today["division_kind"]
    per_day = (today.get("pace_divs") or {}).get(kind)
    # Simple, honest model: each division takes ~ (typical lines / lines_per_day) days; we don't parse
    # every corpus file each run, so advance one division per day at intensive, else track day_in_division.
    day = pos.get("day_in_division", 1)
    # Heuristic days-per-division by kind (line-based works longer at gentler paces).
    big = kind in ("book", "tablet", "parva", "kanda", "cycle", "tale", "chapter")
    span = {"gentle": 3, "standard": 2, "intensive": 1}.get(state["pace"], 2) if big else 1
    if day >= span:
        pos["day_in_division"] = 1
        nxt = pos.get("division", 1) + 1
        count = divs.get("count")
        if count and nxt > count:
            pos["division"] = 1
            seq = today["sequence"]
            idx = min(today["work_index"] + 1, len(seq) - 1)
            pos["work_id"] = seq[idx]
        else:
            pos["division"] = nxt
        state["streak"] = state.get("streak", 0) + 1
    else:
        pos["day_in_division"] = day + 1
        state["streak"] = state.get("streak", 0) + 1
    state["last_advanced"] = str(date.today())
    return state


# ── music ────────────────────────────────────────────────────────────────────────
def load_curated_music(work_id, division):
    p = STUDIUM / "music" / work_id / f"book-{int(division):02d}.yaml"
    return _load_yaml(p, None)


def _listen_links(composer, work):
    q = urllib.parse.quote_plus(f"{composer} {work}")
    return {
        "youtube": f"https://www.youtube.com/results?search_query={q}",
        "spotify": f"https://open.spotify.com/search/{q}",
    }


# ── film (the fourth commentary system) ───────────────────────────────────────────
def load_film(work_id):
    """Load studium/film/<work>.yaml (a per-work force-tagged companion). None if absent (fail-open)."""
    return _load_yaml(STUDIUM / "film" / f"{work_id}.yaml", None)


def _watch_links(title, year=None, slug=None):
    """Legal rails only — Letterboxd (his rail) + JustWatch (where-to-stream) + a search. NEVER a pirated source."""
    q = urllib.parse.quote_plus(f"{title} {year}".strip())
    lb = (f"https://letterboxd.com/film/{slug}/" if slug
          else f"https://letterboxd.com/search/{urllib.parse.quote_plus(str(title))}/")
    return {
        "letterboxd": lb,
        "justwatch": f"https://www.justwatch.com/us/search?q={urllib.parse.quote_plus(str(title))}",
        "search": f"https://duckduckgo.com/?q={q}+film",
    }


def load_letterboxd_history():
    """logs/letterboxd-history.json (from studium-letterboxd.py) → {slug: record}. Empty if absent (fail-open)."""
    data = _load_json(LOGS / "letterboxd-history.json", {})
    films = data.get("films") if isinstance(data, dict) else data
    by_slug = {}
    for r in (films or []):
        s = (r.get("slug") or "").strip()
        if s:
            by_slug[s] = r
    return by_slug


# ── original-script sample (real Greek/Latin/… from the corpus head) ─────────────
def original_sample(work, division, n=6):
    of = work.get("original_file")
    cp = work.get("corpus_path")
    if not of or not cp:
        return None
    path = CORPUS_ROOT / cp / of
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    # Only the head is a faithful Book-1 sample; deeper divisions need the gloss module's offsets.
    head = [ln for ln in lines[:200] if ln.strip()][:n]
    return "\n".join(head) if head else None


# ── view ──────────────────────────────────────────────────────────────────────────
def build_view(state, advance=False):
    canon = _load_yaml(STUDIUM / "canon.yaml", {})
    orderings = _load_yaml(STUDIUM / "orderings.yaml", {})
    paces = _load_yaml(STUDIUM / "paces.yaml", {})
    forces = (_load_yaml(STUDIUM / "dominant-force.yaml", {}) or {}).get("forces", {})

    today = resolve_today(canon, orderings, paces, state)
    if today is None:
        return {"error": "no canon loaded", "generated_at": datetime.now().isoformat(timespec="seconds")}, state

    if advance:
        today["pace_divs"] = (paces.get("paces", {}) or {}).get(state["pace"], {}).get("divisions_per_day", {})
        state = advance_cursor(state, today)
        today = resolve_today(canon, orderings, paces, state)

    w = today["work"]
    work_id = today["work_id"]
    div = today["division"]
    music = load_curated_music(work_id, div)
    gloss = SEED_GLOSS.get((work_id, div))
    sample = original_sample(w, div)

    # music tracks with listen links + force colors
    tracks = []
    if music:
        for t in music.get("tracks", []):
            f = (t.get("force") or "").strip()
            tracks.append({
                **t,
                "color": (forces.get(f, {}) or {}).get("color", "#8a93a6"),
                "links": _listen_links(t.get("composer", ""), t.get("work", "")),
            })

    dom = (music or {}).get("dominant_force") or (w.get("force_arc") or [None])[0]
    dom_color = (forces.get(dom, {}) or {}).get("color", "#8a93a6")
    dom_req = (forces.get(dom, {}) or {}).get("requirement", "")

    # film (fourth commentary system): the work's companion, with the day's-force films highlighted.
    film_doc = load_film(work_id)
    seen_by_slug = load_letterboxd_history()        # his Letterboxd "watched" (empty until ingested)
    films = []
    if film_doc:
        for fm in film_doc.get("films", []):
            ff = (fm.get("force") or "").strip()
            slug = (fm.get("letterboxd") or "").strip()
            films.append({
                **fm,
                "color": (forces.get(ff, {}) or {}).get("color", "#8a93a6"),
                "match": ff == dom,           # surfaces on a day whose dominant force this film encodes
                "in_div": div in (fm.get("divisions") or []),
                "seen": bool(slug and slug in seen_by_slug),
                "links": _watch_links(fm.get("title", ""), fm.get("year"), slug or None),
            })
        # day's-force films first, then the rest (the weekly companion still shows in full)
        films.sort(key=lambda x: (not x["match"]))

    # Film of the Day: promote ONE pick best-fitting TODAY — his "a movie for today, fitting and not
    # obvious." Division match first, then the day's force; the literal adaptation is never promoted (it
    # lives in film_doc['adaptations'], deliberately set aside). This is the object lesson of the day.
    film_of_day = None
    if films:
        def _score(fm):
            return (2 if fm.get("match") else 0) + (1 if fm.get("in_div") else 0)
        top = sorted(films, key=lambda fm: (-_score(fm), not fm.get("match")))[0]
        if _score(top) > 0:                          # only promote a genuine fit for today
            reason = ("today’s force, in this very book" if top.get("match") and top.get("in_div")
                      else "this very book" if top.get("in_div") else "today’s force")
            film_of_day = {**top, "reason": reason,
                           "force_req": (forces.get((top.get("force") or "").strip(), {}) or {}).get("requirement", "")}

    # all orderings, for the canon map
    ord_views = []
    for key, spec in (orderings.get("orderings", {}) or {}).items():
        seq = work_sequence(canon, orderings, key)
        ord_views.append({
            "key": key, "label": spec.get("label", key),
            "active": key == state["ordering"],
            "sequence": [{"id": wid, "title": canon["works"].get(wid, {}).get("title", wid),
                          "current": (key == state["ordering"] and wid == work_id)} for wid in seq],
        })

    depth_labels = {"calligraphy": "Calligraphy / paleography",
                    "glossed": "Script + glossed reading", "grammar": "Serious grammar track"}
    pace_label = (paces.get("paces", {}) or {}).get(state["pace"], {}).get("label", state["pace"])

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": str(date.today()),
        "ordering": state["ordering"],
        "pace": state["pace"], "pace_label": pace_label,
        "depth": state["language_depth"], "depth_label": depth_labels.get(state["language_depth"], state["language_depth"]),
        "streak": state.get("streak", 0),
        "reading": {
            "work_id": work_id, "title": w.get("title"), "author": w.get("author"),
            "division_label": today["division_label"], "division": div,
            "division_count": today["division_count"],
            "day_in_division": today["day_in_division"],
            "main_question": w.get("main_question"), "period": w.get("period"),
            "lines_per_day": today["lines_per_day"],
            "source_rails": w.get("source_rails", []),
            "translations": w.get("translation_files", []),
        },
        "language": {
            "script": w.get("script"), "name": w.get("language"),
            "sample": sample, "gloss": gloss,
        },
        "music": {"title": (music or {}).get("title"), "dominant_force": dom,
                  "dom_color": dom_color, "dom_req": dom_req,
                  "force_arc": (music or {}).get("force_arc", []),
                  "tracks": tracks, "have_curated": bool(music)},
        "film": {"title": (film_doc or {}).get("title"), "have_companion": bool(film_doc),
                 "dom_color": dom_color, "films": films, "of_day": film_of_day,
                 "have_history": bool(seen_by_slug)},
        "orderings": ord_views,
        "all_paces": [(k, v.get("label", k)) for k, v in (paces.get("paces", {}) or {}).items()],
        "all_depths": list(depth_labels.items()),
    }, state


# ── render ──────────────────────────────────────────────────────────────────────
def render_daily_page(v):
    r, lang, mus = v["reading"], v["language"], v["music"]
    g = lang.get("gloss") or {}
    gl = "\n".join(f"  {o} = {m}" for o, m in g.get("gloss", [])) if g else ""
    track = ""
    if mus["tracks"]:
        t = mus["tracks"][0]
        track = f"{t.get('composer')} — {t.get('work')}"
    fod = (v.get("film") or {}).get("of_day")
    film_line = ""
    if fod:
        seen = " · ✓ in your Letterboxd" if fod.get("seen") else ""
        film_line = f"{fod.get('title')} ({fod.get('director')}, {fod.get('year')}){seen}"
        obj = ", ".join(fod.get("objects") or [])
        ol = " ".join((fod.get("object_lesson") or "").split())
        film_line += (f"\nObject: {obj or '—'}\nObject lesson: {ol}") if (obj or ol) else ""
    return f"""DATE: {v['today']}
TEXT: {r['title']}
BOOK / CHAPTER / LINES: {r['division_label']} {r['division']} (~{r['lines_per_day']} lines)

SCENE:
DOMINANT FORCE: {mus.get('dominant_force') or ''}

ORIGINAL SCRIPT:
{lang.get('sample') or '[hand-copied separately]'}

TRANSLITERATION:
{g.get('translit', '')}

WORD-BY-WORD GLOSS:
{gl}

LITERAL TRANSLATION:
{g.get('literal', '')}

LITERARY TRANSLATION:
{g.get('literary', '')}

ONE FORMAL OBSERVATION:

ONE INTERTEXT:

TODAY'S COMPOSITION: {track}
Why this composition fits:

FILM / OBJECT LESSON (weekly): {film_line}
What the film made visible that the page did not:

KEEP / REPLACE:
"""


def render_html(v):
    if v.get("error"):
        return f"<!doctype html><meta charset=utf-8><body style='background:#0d1117;color:#e6edf3;font-family:sans-serif;padding:2rem'><h1>Studium</h1><p>{_esc(v['error'])}</p></body>"
    r, lang, mus = v["reading"], v["language"], v["music"]
    music_title = mus.get("title") or "Today's composition"

    rails = " · ".join(f'<a href="{_esc(u)}" target="_blank">source</a>' for u in r["source_rails"]) or "—"
    trans = ", ".join(_esc(t.replace('.txt', '').replace('english_', '')) for t in r["translations"]) or "—"

    # script + gloss
    sample_html = f'<pre class="orig">{_esc(lang["sample"])}</pre>' if lang.get("sample") else \
        '<div class="muted">original-script sample for this division resolves once the gloss module indexes it (Book I shows live)</div>'
    gloss_html = ""
    g = lang.get("gloss")
    if g:
        rows = "".join(f'<tr><td class="gk">{_esc(o)}</td><td class="gm">{_esc(m)}</td></tr>' for o, m in g.get("gloss", []))
        gloss_html = f"""
        <div class="translit">{_esc(g.get('translit',''))}</div>
        <table class="gloss">{rows}</table>
        <div class="lit"><b>literal:</b> {_esc(g.get('literal',''))}</div>
        <div class="lit"><b>literary:</b> {_esc(g.get('literary',''))}</div>"""

    # music arc
    arc = " → ".join(_esc(f) for f in mus.get("force_arc", [])) or ""
    track_rows = ""
    for t in mus["tracks"]:
        links = t.get("links", {})
        track_rows += f"""
        <tr>
          <td class="tn">{_esc(t.get('n',''))}</td>
          <td><span class="force" style="background:{_esc(t.get('color'))}">{_esc(t.get('force',''))}</span></td>
          <td class="scene">{_esc(t.get('scene',''))}</td>
          <td><b>{_esc(t.get('composer',''))}</b> — {_esc(t.get('work',''))}
              <div class="why">{_esc(t.get('why',''))}</div></td>
          <td class="lk"><a href="{_esc(links.get('youtube','#'))}" target="_blank">▶ YT</a>
              <a href="{_esc(links.get('spotify','#'))}" target="_blank">♫ Sp</a></td>
        </tr>"""
    music_card = ""
    if mus["have_curated"]:
        music_card = f"""
     <div class="card">
       <h2 style="color:{_esc(mus['dom_color'])}">🎵 {_esc(music_title)}</h2>
       <div class="muted">dominant arc: {arc}</div>
       <table class="tracks"><tbody>{track_rows}</tbody></table>
     </div>"""
    else:
        music_card = f"""
     <div class="card">
       <h2 style="color:{_esc(mus['dom_color'])}">🎵 Today's composition</h2>
       <div class="muted">dominant force: <b style="color:{_esc(mus['dom_color'])}">{_esc(mus.get('dominant_force') or '—')}</b> — {_esc(mus.get('dom_req'))}</div>
       <div class="muted">curated arc pending for this division — the synthesizer pairs it on demand (gap-driven expansion).</div>
     </div>"""

    # film card (the fourth commentary system) — day's-force films highlighted
    fl = v["film"]
    if fl["have_companion"]:
        film_rows = ""
        for fm in fl["films"]:
            links = fm.get("links", {})
            badge = '<span class="todayf">today’s force</span>' if fm.get("match") else ""
            seenm = '<span class="seen">✓ seen</span>' if fm.get("seen") else ""
            objs = "".join(f'<span class="objchip">⬡ {_esc(o)}</span>' for o in (fm.get("objects") or []))
            cn = f'<div class="cnote">{_esc(fm.get("content_note",""))}</div>' if fm.get("content_note") else ""
            film_rows += f"""
        <tr class="{'match' if fm.get('match') else ''}">
          <td><span class="force" style="background:{_esc(fm.get('color'))}">{_esc(fm.get('force',''))}</span></td>
          <td><b>{_esc(fm.get('title',''))}</b> <span class="muted">— {_esc(fm.get('director',''))}, {_esc(fm.get('year',''))}</span>{badge}{seenm}{objs}
              <div class="scene">{_esc(fm.get('scene_or_theme',''))}</div>
              <div class="why">{_esc(fm.get('why',''))}</div>{cn}</td>
          <td class="lk"><a href="{_esc(links.get('letterboxd','#'))}" target="_blank">▤ LB</a>
              <a href="{_esc(links.get('justwatch','#'))}" target="_blank">▷ where</a>
              <a href="{_esc(links.get('search','#'))}" target="_blank">🔎</a></td>
        </tr>"""
        film_card = f"""
     <div class="card">
       <h2 style="color:{_esc(fl['dom_color'])}">🎬 Film resonance <span class="muted">— the fourth commentary system (weekly)</span></h2>
       <div class="muted">{_esc(fl.get('title') or '')} · the day’s-force films are highlighted; the community Watch-Along screens one a week</div>
       <table class="tracks"><tbody>{film_rows}</tbody></table>
     </div>"""
    else:
        film_card = f"""
     <div class="card">
       <h2 style="color:{_esc(fl['dom_color'])}">🎬 Film resonance</h2>
       <div class="muted">film companion pending for this work — staged in <code>expansion-backlog.yaml</code> (film pillar). Gold standard: <code>studium/film/iliad.yaml</code>.</div>
     </div>"""

    # Film of the Day — the headline object lesson, promoted above the weekly companion
    fod = fl.get("of_day")
    today_film_card = ""
    if fod:
        flinks = fod.get("links", {})
        objs = "".join(f'<span class="objchip">⬡ {_esc(o)}</span>' for o in (fod.get("objects") or []))
        seen = '<span class="seen">✓ in your Letterboxd</span>' if fod.get("seen") else ""
        cn = f'<div class="cnote">{_esc(fod.get("content_note",""))}</div>' if fod.get("content_note") else ""
        today_film_card = f"""
     <div class="card todayfilm" style="border-color:{_esc(fl['dom_color'])}">
       <h2 style="color:{_esc(fl['dom_color'])}">🎬 Today's film — an object lesson in {_esc(fod.get('force',''))}</h2>
       <div class="filmtitle"><b>{_esc(fod.get('title',''))}</b> <span class="muted">— {_esc(fod.get('director',''))}, {_esc(fod.get('year',''))}</span> {objs} {seen}</div>
       <div class="muted">fits {_esc(fod.get('reason',''))} · {_esc(fod.get('scene_or_theme',''))}</div>
       <div class="objlesson">{_esc(' '.join((fod.get('object_lesson') or '').split()))}</div>
       <div class="why">{_esc(' '.join((fod.get('why') or '').split()))}</div>{cn}
       <div class="lk"><a href="{_esc(flinks.get('letterboxd','#'))}" target="_blank">▤ Letterboxd</a>
           <a href="{_esc(flinks.get('justwatch','#'))}" target="_blank">▷ where to watch</a>
           <a href="{_esc(flinks.get('search','#'))}" target="_blank">🔎</a></div>
       <div class="muted" style="margin-top:6px">the obvious screen-adaptation is set aside — this is the non-obvious one; it feeds <a href="https://objectlessons.film" target="_blank">objectlessons.film</a></div>
     </div>"""

    # canon map (all orderings)
    maps = ""
    for ov in v["orderings"]:
        chips = "".join(
            f'<span class="chip{" cur" if s["current"] else ""}">{_esc(s["title"])}</span>'
            for s in ov["sequence"])
        maps += f"""
        <div class="ord{' active' if ov['active'] else ''}">
          <div class="ordlbl">{'● ' if ov['active'] else '○ '}{_esc(ov['label'])}</div>
          <div class="chips">{chips}</div>
        </div>"""

    paces = " · ".join(f'<span class="opt{" on" if k==v["pace"] else ""}">{_esc(lbl)}</span>' for k, lbl in v["all_paces"])
    depths = " · ".join(f'<span class="opt{" on" if k==v["depth"] else ""}">{_esc(lbl)}</span>' for k, lbl in v["all_depths"])

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600"><title>LIMEN — studium</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:900px;margin:0 auto;padding:18px}}
 h1{{font-size:21px;margin:0 0 2px}} h2{{font-size:16px;margin:0 0 8px}}
 .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .muted{{color:#8a93a6;font-size:13px;margin:4px 0}}
 .q{{font-size:17px;color:#e6edf3;font-style:italic;margin:6px 0}}
 .orig{{font-size:20px;line-height:1.7;background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:10px 12px;white-space:pre-wrap;margin:8px 0}}
 .translit{{color:#9bb4d4;font-style:italic;margin:6px 0}}
 table.gloss{{border-collapse:collapse;margin:8px 0}} table.gloss td{{padding:2px 12px 2px 0}}
 .gk{{font-size:17px}} .gm{{color:#8a93a6}}
 .lit{{margin:3px 0}}
 table.tracks{{width:100%;border-collapse:collapse}} table.tracks td{{padding:8px 6px;border-top:1px solid #21262d;vertical-align:top}}
 .tn{{color:#8a93a6;width:18px}} .scene{{color:#c9d1d9;font-size:13px;width:150px}}
 .why{{color:#8a93a6;font-size:12px;margin-top:3px}}
 .cnote{{color:#6e7681;font-size:11px;margin-top:3px;font-style:italic}}
 tr.match td{{background:#11281a}} tr.match{{box-shadow:inset 3px 0 0 #2ecc71}}
 .todayf{{font-size:10px;color:#06140c;background:#2ecc71;border-radius:4px;padding:0 5px;margin-left:6px;font-weight:700}}
 .todayfilm{{border-width:1px;border-style:solid;background:#12171f}}
 .filmtitle{{font-size:16px;margin:4px 0 6px}}
 .objchip{{font-size:11px;background:#1f2a38;color:#9bb4d4;border-radius:5px;padding:1px 7px;margin-left:4px}}
 .seen{{font-size:11px;color:#06140c;background:#e2a44a;border-radius:5px;padding:1px 7px;margin-left:4px;font-weight:700}}
 .objlesson{{color:#e6edf3;font-size:14px;line-height:1.5;margin:8px 0;padding-left:10px;border-left:2px solid #2b3340}}
 .force{{color:#06140c;font-weight:700;border-radius:5px;padding:1px 7px;font-size:11px;text-transform:lowercase}}
 .lk a{{color:#58a6ff;font-size:12px;margin-right:6px;text-decoration:none;white-space:nowrap}}
 .ord{{margin:8px 0}} .ord.active .ordlbl{{color:#2ecc71}} .ordlbl{{font-size:13px;margin-bottom:4px}}
 .chips{{display:flex;flex-wrap:wrap;gap:4px}}
 .chip{{font-size:11px;background:#21262d;color:#8a93a6;border-radius:5px;padding:2px 7px}}
 .chip.cur{{background:#2ecc71;color:#06140c;font-weight:700}}
 .opt{{font-size:12px;color:#8a93a6}} .opt.on{{color:#2ecc71;font-weight:700}}
 a{{color:#58a6ff}}
</style></head><body><div class="wrap">
 <h1>LIMEN — studium</h1>
 <div class="sub">{_esc(v['today'])} · streak {v['streak']} · ordering: <b>{_esc(v['ordering'])}</b> · pace: {_esc(v['pace_label'])} · depth: {_esc(v['depth_label'])}</div>

 <div class="card">
   <h2>📖 Today's reading</h2>
   <div><b>{_esc(r['title'])}</b> — {_esc(r['author'])} · {_esc(r['division_label'])} {_esc(r['division'])}{(' / '+str(r['division_count'])) if r['division_count'] else ''} · day {_esc(r['day_in_division'])} · ~{_esc(r['lines_per_day'])} lines</div>
   <div class="q">{_esc(r['main_question'])}</div>
   <div class="muted">compare translations: {trans} · {rails}</div>
 </div>

 <div class="card">
   <h2>✍︎ Script &amp; translation <span class="muted">({_esc(v['depth_label'])})</span></h2>
   <div class="muted">script: <b>{_esc(lang.get('script') or '—')}</b> — handwrite, then translate the unit</div>
   {sample_html}
   {gloss_html}
 </div>

 {music_card}

 {today_film_card}

 {film_card}

 <div class="card">
   <h2>🗺 The canon — all paths (choice is the fruit of life)</h2>
   {maps}
   <div class="muted" style="margin-top:10px">pace: {paces}</div>
   <div class="muted">depth: {depths}</div>
   <div class="muted" style="margin-top:6px">switch any avenue by editing <code>logs/studium-state.json</code> (ordering · pace · language_depth)</div>
 </div>

 <div class="card muted">
   protocol: read → copy the script → translate a unit → compare translations → one note → one composition → log the resonance.
   today's page exported to <code>studium/ledger/studium-{_esc(v['today'])}.md</code>
 </div>
</div></body></html>"""


def main():
    state = load_state()
    advance = "--advance" in sys.argv
    # --daily (the heartbeat cadence): advance the cursor once when the date rolls, else just refresh.
    if "--daily" in sys.argv and not advance:
        advance = state.get("last_advanced") != str(date.today())
    view, state = build_view(state, advance=advance)
    LOGS.mkdir(parents=True, exist_ok=True)

    _atomic_write(LOGS / "studium-state.json", json.dumps(state, indent=2))
    _atomic_write(LOGS / "studium-view.json", json.dumps(view, indent=2))

    html = render_html(view)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            _atomic_write(d / "studium.html", html)
            _atomic_write(d / "studium-view.json", json.dumps(view, indent=2))
            wrote.append(str(d / "studium.html"))
        except OSError:
            continue

    if not view.get("error"):
        _atomic_write(LEDGER / f"studium-{view['today']}.md", render_daily_page(view))
        r = view["reading"]
        m = view["music"]
        print(f"studium: {r['title']} {r['division_label']} {r['division']} · force={m.get('dominant_force')} · "
              f"{len(m.get('tracks',[]))} tracks · ordering={view['ordering']} -> {', '.join(wrote) or 'logs only'}")
    else:
        print(f"studium: {view['error']} (rendered degraded face)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
