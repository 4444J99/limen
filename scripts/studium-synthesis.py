#!/usr/bin/env python3
"""studium-synthesis.py — the cross-canon SYNTHESIS face.

His thesis (studium/thesis.md) is that the canon is one conversation the species has been having with
itself: each work is one tradition's answer to a handful of encodings — violence, law, memory, fate,
sacrifice, speech, revelation, empire, desire, death, return, transformation, salvation, comedy. The
daily face (studium.py) reads ACROSS a work; this face reads DOWN a concept — one encoding answered by
many traditions at once, with the Eastern works set as COUNTER-SYSTEMS to the Western line.

Renders studium/synthesis/concepts.yaml into a self-contained web/app/out/synthesis.html (meta-refresh,
pure string templating — NO network, cannot time out), mirrored to web/app/public/. Concept colors are
borrowed from each concept's nearest dominant FORCE in dominant-force.yaml (derived, never pinned). A
concept links to its prose essay synthesis/<concept>.md when authored.

Anti-waste + never-"NO": every section fails OPEN — a missing concepts.yaml/canon/essay yields a degraded
section, never a crash. Read-only on the curriculum; writes only its own outputs.

Usage:  python3 scripts/studium-synthesis.py
"""
import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
STUDIUM = ROOT / "studium"
LOGS = ROOT / "logs"
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]

try:
    import yaml
except ImportError:  # fail-open: the face still renders, just without YAML-backed data
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


def _load_yaml(path: Path, default):
    if yaml is None:
        return default
    try:
        return yaml.safe_load(Path(path).read_text()) or default
    except (OSError, ValueError, yaml.YAMLError):
        return default


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_view():
    data = _load_yaml(STUDIUM / "synthesis" / "concepts.yaml", {})
    canon = _load_yaml(STUDIUM / "canon.yaml", {})
    forces = (_load_yaml(STUDIUM / "dominant-force.yaml", {}) or {}).get("forces", {})
    works = canon.get("works", {})

    def title_of(wid):
        return works.get(wid, {}).get("title", wid)

    concepts = []
    for name, spec in (data.get("concepts", {}) or {}).items():
        force = (spec.get("force") or "").strip()
        color = (forces.get(force, {}) or {}).get("color", "#8a93a6")
        essay = STUDIUM / "synthesis" / f"{name}.md"
        concepts.append({
            "name": name,
            "gloss": spec.get("gloss", ""),
            "force": force,
            "color": color,
            "essay": essay.exists(),
            "works": [{"id": w.get("id"), "title": title_of(w.get("id")),
                       "how": w.get("how", ""),
                       "staged": works.get(w.get("id"), {}).get("staged", False)}
                      for w in (spec.get("works") or [])],
        })

    counters = []
    for c in (data.get("counter_systems") or []):
        counters.append({
            "concept": c.get("concept", ""),
            "west": title_of(c.get("west")), "east": title_of(c.get("east")),
            "on": c.get("on", ""),
        })

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": str(date.today()),
        "concepts": concepts,
        "counters": counters,
        "have_data": bool(concepts),
    }


def render_html(v):
    if not v["have_data"]:
        return ("<!doctype html><meta charset=utf-8><body style='background:#0d1117;color:#e6edf3;"
                "font-family:sans-serif;padding:2rem'><h1>studium — synthesis</h1>"
                "<p>concepts.yaml not loaded — the synthesis spine resolves once it is present.</p></body>")

    # counter-systems marquee
    crows = ""
    for c in v["counters"]:
        crows += (f'<tr><td class="cc">{_esc(c["concept"])}</td>'
                  f'<td class="cw">{_esc(c["west"])}</td><td class="ar">↔</td>'
                  f'<td class="ce">{_esc(c["east"])}</td>'
                  f'<td class="con">{_esc(c["on"])}</td></tr>')
    counter_card = f"""
     <div class="card">
       <h2>⇄ Counter-systems <span class="muted">(the Eastern answer beside the Western statement)</span></h2>
       <table class="counters"><tbody>{crows}</tbody></table>
     </div>""" if crows else ""

    cards = ""
    for c in v["concepts"]:
        wrows = ""
        for w in c["works"]:
            tag = ' <span class="st">staged</span>' if w["staged"] else ""
            wrows += (f'<tr><td class="wt">{_esc(w["title"])}{tag}</td>'
                      f'<td class="wh">{_esc(w["how"])}</td></tr>')
        essay_link = (f'<a class="read" href="{_esc(c["name"])}.md">read the essay →</a>'
                      if c["essay"] else '<span class="muted">essay pending</span>')
        cards += f"""
     <div class="card concept">
       <div class="chead">
         <span class="cname" style="color:{_esc(c['color'])}">{_esc(c['name'])}</span>
         <span class="force" style="background:{_esc(c['color'])}">{_esc(c['force'])}</span>
       </div>
       <div class="gloss">{_esc(c['gloss'])}</div>
       <table class="works"><tbody>{wrows}</tbody></table>
       <div class="cfoot">{essay_link}</div>
     </div>"""

    n = len(v["concepts"])
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600"><title>LIMEN — studium · synthesis</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:920px;margin:0 auto;padding:18px}}
 h1{{font-size:21px;margin:0 0 2px}} h2{{font-size:16px;margin:0 0 8px}}
 .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .thesis{{font-style:italic;color:#c9d1d9;margin:8px 0 16px;font-size:15px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .muted{{color:#8a93a6;font-size:13px;font-style:normal}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(390px,1fr));gap:12px}}
 .concept{{margin:0}}
 .chead{{display:flex;align-items:center;justify-content:space-between;margin-bottom:4px}}
 .cname{{font-size:18px;font-weight:700;text-transform:capitalize}}
 .force{{color:#06140c;font-weight:700;border-radius:5px;padding:1px 8px;font-size:11px;text-transform:lowercase}}
 .gloss{{color:#c9d1d9;font-size:13px;margin:2px 0 8px}}
 table.works{{width:100%;border-collapse:collapse}}
 table.works td{{padding:4px 6px;border-top:1px solid #21262d;vertical-align:top;font-size:13px}}
 .wt{{width:38%;color:#e6edf3}} .wh{{color:#8a93a6}}
 .st{{font-size:10px;color:#8a93a6;background:#21262d;border-radius:4px;padding:0 5px}}
 .cfoot{{margin-top:8px}} .read{{color:#58a6ff;font-size:13px;text-decoration:none}}
 table.counters{{width:100%;border-collapse:collapse}}
 table.counters td{{padding:5px 8px;border-top:1px solid #21262d;font-size:13px;vertical-align:top}}
 .cc{{color:#8a93a6;text-transform:capitalize;width:14%}} .cw{{color:#e6edf3;width:20%}}
 .ar{{color:#2ecc71;text-align:center;width:18px}} .ce{{color:#e6edf3;width:20%}} .con{{color:#8a93a6}}
 a{{color:#58a6ff}}
</style></head><body><div class="wrap">
 <h1>LIMEN — studium · synthesis</h1>
 <div class="sub">{_esc(v['today'])} · {n} encodings across the canon · the vertical axis (the daily face reads horizontally)</div>
 <div class="thesis">Not just reading great books — studying how civilizations <b>encode</b> the same handful of things,
   so that read together, across cultures and in their own scripts, they become a single conversation the species
   has been having with itself.</div>
 {counter_card}
 <div class="grid">{cards}</div>
 <div class="card muted">
   Read DOWN a concept to see one encoding answered by many traditions; read ACROSS a work (in the daily
   face) to see one book answering many encodings. Concept color = its nearest dominant force
   (<code>dominant-force.yaml</code>). Essays live in <code>studium/synthesis/&lt;concept&gt;.md</code>.
 </div>
</div></body></html>"""


def main():
    v = build_view()
    html = render_html(v)
    LOGS.mkdir(parents=True, exist_ok=True)
    _atomic_write(LOGS / "studium-synthesis-view.json", json.dumps(v, indent=2))
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            _atomic_write(d / "synthesis.html", html)
            wrote.append(str(d / "synthesis.html"))
        except OSError:
            continue
    print(f"studium-synthesis: {len(v['concepts'])} concepts · {len(v['counters'])} counter-systems "
          f"-> {', '.join(wrote) or 'logs only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
