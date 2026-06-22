#!/usr/bin/env python3
"""studium-analysis.py — the PRACTICE-AS-DATA face ("packaging as data analysis").

His ask: "we create systems of interaction for studying and learning and trial and packaging as data
analysis." Every interaction the Studium generates is data; this face packages it. It reads three real
on-disk sources and fails OPEN on each:

  1. the authored MUSIC corpus (studium/music/*/book-*.yaml)  → force distribution across the canon
  2. the SYNTHESIS spine (studium/synthesis/concepts.yaml)    → concept reach + counter-system count
  3. his solo LEDGER (studium/ledger/*.md + logs/studium-state.json) → practice cadence, force-per-day,
     KEEP/REPLACE tally
  4. (staged) the interaction EVENT log (logs/studium-events.jsonl, per analysis/events-schema.yaml)
     → rubric trends, concept heat, claim survival — empty until events flow (community scale, his gate)

Renders a self-contained web/app/out/analysis.html (meta-refresh, pure string templating — NO network,
cannot time out), mirrored to web/app/public/. Read-only on the curriculum; writes only its own outputs.

Usage:  python3 scripts/studium-analysis.py
"""
import json
import os
import tempfile
from collections import Counter
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


def _load_json(path: Path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _load_jsonl(path: Path):
    out = []
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _forces():
    return (_load_yaml(STUDIUM / "dominant-force.yaml", {}) or {}).get("forces", {})


# ── data sources (each fails open) ────────────────────────────────────────────────
def corpus_force_distribution():
    """Count every track force across ALL authored arcs — how the canon encodes force, as built."""
    counts, arcs, works = Counter(), 0, set()
    for f in sorted((STUDIUM / "music").glob("*/book-*.yaml")):
        doc = _load_yaml(f, None)
        if not doc:
            continue
        arcs += 1
        works.add(f.parent.name)
        for t in doc.get("tracks", []) or []:
            fc = (t.get("force") or "").strip()
            if fc:
                counts[fc] += 1
    return counts, arcs, len(works)


def concept_reach():
    data = _load_yaml(STUDIUM / "synthesis" / "concepts.yaml", {})
    rows = []
    for name, spec in (data.get("concepts", {}) or {}).items():
        rows.append({"name": name, "force": (spec.get("force") or "").strip(),
                     "works": len(spec.get("works") or [])})
    rows.sort(key=lambda r: -r["works"])
    return rows, len(data.get("counter_systems") or [])


def parse_ledger():
    """Extract {date, text, force, keep_replace} from each ledger daily-page (his hand's data)."""
    days = []
    for f in sorted((STUDIUM / "ledger").glob("studium-*.md")):
        rec = {"date": "", "text": "", "force": "", "keep_replace": ""}
        try:
            for ln in f.read_text().splitlines():
                if ":" not in ln:
                    continue
                k, _, v = ln.partition(":")
                k = k.strip().upper()
                v = v.strip()
                if k == "DATE":
                    rec["date"] = v
                elif k == "TEXT":
                    rec["text"] = v
                elif k == "DOMINANT FORCE":
                    rec["force"] = v
                elif k.startswith("KEEP / REPLACE") or k.startswith("KEEP/REPLACE"):
                    rec["keep_replace"] = v
        except OSError:
            continue
        days.append(rec)
    return days


def build_view():
    counts, arcs, works = corpus_force_distribution()
    forces = _forces()
    max_c = max(counts.values()) if counts else 1
    dist = [{"force": fc, "n": n, "pct": round(100 * n / max_c),
             "color": (forces.get(fc, {}) or {}).get("color", "#8a93a6")}
            for fc, n in counts.most_common()]

    concepts, counters = concept_reach()
    for c in concepts:
        c["color"] = (forces.get(c["force"], {}) or {}).get("color", "#8a93a6")

    days = parse_ledger()
    state = _load_json(LOGS / "studium-state.json", {})
    kr = Counter(d["keep_replace"].split()[0].lower() for d in days if d["keep_replace"])

    events = _load_jsonl(LOGS / "studium-events.jsonl")
    ev_types = Counter(e.get("type", "?") for e in events)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "today": str(date.today()),
        "dist": dist, "arcs": arcs, "works": works,
        "concepts": concepts, "counters": counters,
        "days": days, "streak": state.get("streak", 0),
        "kr": dict(kr),
        "events": len(events), "ev_types": dict(ev_types),
    }


def render_html(v):
    # corpus force distribution (bars)
    bars = ""
    for d in v["dist"]:
        bars += (f'<div class="bar"><span class="bl">{_esc(d["force"])}</span>'
                 f'<span class="bt" style="width:{d["pct"]}%;background:{_esc(d["color"])}"></span>'
                 f'<span class="bn">{d["n"]}</span></div>')
    dist_card = f"""
     <div class="card">
       <h2>⚖ Force distribution across the canon <span class="muted">— {v['arcs']} arcs · {v['works']} works, as authored</span></h2>
       <div class="muted">how often each force is the encoding of a scene — the curriculum's own center of gravity</div>
       {bars or '<div class="muted">no arcs authored yet</div>'}
     </div>"""

    # concept reach
    crows = ""
    for c in v["concepts"]:
        crows += (f'<tr><td class="cn" style="color:{_esc(c["color"])}">{_esc(c["name"])}</td>'
                  f'<td class="cf">{_esc(c["force"])}</td><td class="cw">{c["works"]} works</td></tr>')
    concept_card = f"""
     <div class="card">
       <h2>🕸 Concept reach <span class="muted">— {len(v['concepts'])} encodings · {v['counters']} counter-systems</span></h2>
       <div class="muted">how many traditions each encoding spans (the vertical axis; see the synthesis face)</div>
       <table class="ct"><tbody>{crows}</tbody></table>
     </div>""" if v["concepts"] else ""

    # practice cadence (his ledger)
    drows = ""
    for d in v["days"][-14:]:
        drows += (f'<tr><td class="dd">{_esc(d["date"])}</td><td>{_esc(d["text"])}</td>'
                  f'<td class="df">{_esc(d["force"])}</td>'
                  f'<td class="dk">{_esc(d["keep_replace"]) or "—"}</td></tr>')
    kr = v["kr"]
    kr_line = (f'KEEP {kr.get("keep",0)} · REPLACE {kr.get("replace",0)}' if kr else "no verdicts logged yet")
    practice_card = f"""
     <div class="card">
       <h2>📓 Practice cadence <span class="muted">— streak {v['streak']} · {len(v['days'])} day(s) logged · {_esc(kr_line)}</span></h2>
       <div class="muted">his own ledger — the solo data stream (the only live stream; community is consent-gated)</div>
       <table class="dt"><tbody>{drows or '<tr><td class="muted">no ledger pages yet — studium.py exports one per studied day</td></tr>'}</tbody></table>
     </div>"""

    # events (staged)
    ev_card = ""
    if v["events"]:
        ev_rows = "".join(f'<tr><td>{_esc(t)}</td><td>{n}</td></tr>' for t, n in v["ev_types"].items())
        ev_card = f"""
     <div class="card">
       <h2>🔬 Interaction events <span class="muted">— {v['events']} logged</span></h2>
       <table class="dt"><tbody>{ev_rows}</tbody></table>
     </div>"""
    else:
        ev_card = """
     <div class="card muted">
       <h2 style="color:#8a93a6">🔬 Interaction events</h2>
       No community events yet — the schema (<code>studium/analysis/events-schema.yaml</code>) is ready and
       <code>studium-analysis.py</code> ingests <code>logs/studium-events.jsonl</code> the moment it exists.
       Rubric trends, concept heat, and claim-survival populate here once trials run. Community collection is
       <b>consent-gated</b> (his lever); the solo streams above are live now.
     </div>"""

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="3600"><title>LIMEN — studium · analysis</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:920px;margin:0 auto;padding:18px}}
 h1{{font-size:21px;margin:0 0 2px}} h2{{font-size:16px;margin:0 0 8px}}
 .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .muted{{color:#8a93a6;font-size:13px;font-weight:normal}}
 .bar{{display:flex;align-items:center;gap:8px;margin:3px 0}}
 .bl{{width:130px;font-size:12px;color:#c9d1d9;text-align:right}}
 .bt{{height:13px;border-radius:3px;min-width:2px}} .bn{{font-size:12px;color:#8a93a6}}
 table{{width:100%;border-collapse:collapse}} td{{padding:4px 8px;border-top:1px solid #21262d;font-size:13px;vertical-align:top}}
 .cn{{font-weight:700;text-transform:capitalize;width:30%}} .cf{{color:#8a93a6;width:30%}} .cw{{color:#8a93a6}}
 .dd{{color:#8a93a6;width:96px}} .df{{color:#c9d1d9;width:110px}} .dk{{color:#8a93a6}}
 code{{background:#21262d;border-radius:4px;padding:0 4px}}
 a{{color:#58a6ff}}
</style></head><body><div class="wrap">
 <h1>LIMEN — studium · analysis</h1>
 <div class="sub">{_esc(v['today'])} · packaging the practice as data — the conductor's notebook for the "TBR book"</div>
 {dist_card}
 {concept_card}
 {practice_card}
 {ev_card}
 <div class="card muted">
   Three live streams (the authored corpus · the synthesis spine · his ledger) + one staged stream
   (interaction events, consent-gated). Schema: <code>studium/analysis/events-schema.yaml</code> ·
   posture: <code>studium/analysis/PLAN.md</code>. The daily face reads ACROSS a work; the synthesis face
   reads DOWN a concept; this face reads the practice itself.
 </div>
</div></body></html>"""


def main():
    v = build_view()
    html = render_html(v)
    LOGS.mkdir(parents=True, exist_ok=True)
    _atomic_write(LOGS / "studium-analysis-view.json", json.dumps(v, indent=2))
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            _atomic_write(d / "analysis.html", html)
            wrote.append(str(d / "analysis.html"))
        except OSError:
            continue
    print(f"studium-analysis: {v['arcs']} arcs · {len(v['concepts'])} concepts · {len(v['days'])} ledger day(s) · "
          f"{v['events']} events -> {', '.join(wrote) or 'logs only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
