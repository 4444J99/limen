#!/usr/bin/env python3
"""omni-view.py — THE ONE SURFACE. Everything, on one screen, past · present · future.

Six faces already exist (money/corpus/internal/qa/client/public), each reading its own slice; none
unify, none show time. This renders a single self-contained web/app/out/omni.html (meta-refresh, pure
string templating — NO Next.js, NO network, so it CANNOT time out) that consolidates every live feed:

  VALUE (top)  the ledger verdict — is the fleet earning its keep, or sinking money? (logs/ledger.json)
  PRESENT      board status mix + governor gate + dispatch integrity (tasks.yaml, autonomy-policy.json,
               dispatch-verify.json) + live fleet headroom (usage.json)
  PAST         done/open trend sparkline + 24h ships (ticks.jsonl, merge-drain.log)
  FUTURE       per-vendor runway + the revenue ladder + YOUR LEVERS + corpus/ingestion coverage
  EVERYTHING   a navigable index of the rest of the estate (memories, plans, organs, the other faces)

So you glance once and walk away, instead of battling me for a status. Every section FAILS OPEN — a
missing/torn feed yields an empty section, never a crash. Read-only on the fleet's data; writes only its
own output files. ([[no-never-happens-again]])
"""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]
# the rest of the estate — where "everything" lives (env-overridable so tests can inject)
MEMORY_DIR = Path(os.environ.get("LIMEN_MEMORY_DIR",
                                 Path.home() / ".claude" / "projects" /
                                 "-Users-4jp-Workspace-limen" / "memory"))
PLANS_DIR = Path(os.environ.get("LIMEN_PLANS_DIR", Path.home() / ".claude" / "plans"))

_SPARK = "▁▂▃▄▅▆▇█"
_PR_RE = re.compile(r"[\w.\-]+/[\w.\-]+#\d+")
_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _ticks(n=40):
    try:
        lines = (LOGS / "ticks.jsonl").read_text().splitlines()
    except OSError:
        return []
    out = []
    for ln in lines[-n:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def _sparkline(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return _SPARK[0] * len(vals)
    return "".join(_SPARK[int((v - lo) / (hi - lo) * (len(_SPARK) - 1))] for v in vals)


def _ships_last_24h():
    try:
        lines = (LOGS / "merge-drain.log").read_text().splitlines()
    except OSError:
        return 0, []
    cutoff = datetime.now() - timedelta(hours=24)
    refs = []
    for ln in lines:
        m = _TS_RE.search(ln)
        if not m:
            continue
        try:
            when = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if when >= cutoff:
            refs += _PR_RE.findall(ln)
    return len(refs), refs[-10:]


def _board_status():
    """Status mix straight from the live board (the present). Fail-open to {}."""
    try:
        import yaml
        data = yaml.safe_load((ROOT / "tasks.yaml").read_text()) or {}
        tasks = data.get("tasks", []) if isinstance(data, dict) else (data or [])
        mix = {}
        for t in tasks:
            if isinstance(t, dict):
                mix[t.get("status", "?")] = mix.get(t.get("status", "?"), 0) + 1
        return mix
    except Exception:
        return {}


def _count(path: Path, pat: str) -> int:
    try:
        return sum(1 for _ in path.glob(pat))
    except OSError:
        return 0


def build_view():
    ledger = _load_json(LOGS / "ledger.json", {})
    governor = _load_json(LOGS / "autonomy-policy.json", {})
    integrity = _load_json(LOGS / "dispatch-verify.json", {})
    usage = _load_json(LOGS / "usage.json", {}).get("vendors", {})
    ladder = _load_json(ROOT / "revenue-ladder.json", {})
    corpus = _load_json(LOGS / "corpus-view.json", {})
    ingest = _load_json(LOGS / "ingest-coverage.json", {})  # Strand 3 writes this; fail-open
    ticks = _ticks()
    ships_total, recent_refs = _ships_last_24h()

    fleet = {n: {"health": i.get("health"), "headroom_pct": i.get("headroom_pct"),
                 "runway_h": i.get("runway_h")}
             for n, i in usage.items() if isinstance(i, dict)}

    # FRONT-LOAD: the reset-window accelerator's job, made visible — which lanes will lose budget at
    # their reset if pacing stays even (will_expire from usage.json), worst first. Empty when nothing
    # is at a cliff. accel_on reflects LIMEN_ACCEL (the daemon's env at write-time isn't known here, so
    # default-on matches the dispatcher default).
    expiring = sorted(
        ({"lane": n, "expire": i.get("will_expire"), "unit": i.get("unit"),
          "h_left": round((i.get("time_left_frac") or 0) * (i.get("window_hours") or 0), 1),
          "headroom_pct": i.get("headroom_pct")}
         for n, i in usage.items()
         if isinstance(i, dict) and i.get("will_expire")),
        key=lambda d: -(d["expire"] or 0))
    front_load = {"accel": os.environ.get("LIMEN_ACCEL", "1") == "1", "expiring": expiring[:8]}

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "spine": ladder.get("spine", ""),
        "value": {
            "verdict": ledger.get("verdict"),
            "net": ledger.get("net"),
            "lane_rank": ledger.get("lane_rank", []),
            "lanes": ledger.get("lanes", {}),
            "worst_sink": ledger.get("worst_sink"),
            "attribution": ledger.get("revenue_attribution", []),
        },
        "present": {
            "board": _board_status(),
            "governor": {"mode": governor.get("mode"),
                         "reserve_pct": (governor.get("bounds") or {}).get("reserve_pct"),
                         "cap": (governor.get("bounds") or {}).get("daily_dispatch_cap")},
            "integrity": integrity.get("counts", {}),
            "fleet": fleet,
        },
        "past": {
            "done_spark": _sparkline([t.get("done", 0) for t in ticks]),
            "open_spark": _sparkline([t.get("open", 0) for t in ticks]),
            "ships_24h": ships_total,
            "recent_ships": recent_refs,
        },
        "future": {
            "front_load": front_load,
            "your_levers": ladder.get("your_levers", []),
            "products": sorted(ladder.get("products", []), key=lambda p: p.get("rank", 99)),
            "corpus": {"faces": corpus.get("face_count"), "absorbed": corpus.get("absorbed_total"),
                       "one": corpus.get("one_sentence")},
            "ingestion": {"atoms": ingest.get("atoms"), "sources": ingest.get("sources"),
                          "coverage_pct": ingest.get("coverage_pct"), "last_run": ingest.get("last_run")},
        },
        "everything": {
            "memories": _count(MEMORY_DIR, "*.md"),
            "plans": _count(PLANS_DIR, "*.md"),
            "organs": _count(ROOT / "scripts", "*.py") + _count(ROOT / "scripts", "*.sh"),
            "faces": ["omni.html", "money.html", "corpus.html", "internal", "qa", "client", "public"],
        },
    }


_HEALTH_DOT = {"ok": "#2ecc71", "throttle": "#f1c40f", "low": "#e67e22",
               "rate-limited": "#e67e22", "exhausted": "#7f8c8d"}
_NET_COLOR = {"WORTH IT": "#2ecc71", "EVEN": "#f1c40f", "WASTE": "#e74c3c"}


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(v):
    val = v["value"]
    net = val.get("net") or "—"
    net_color = _NET_COLOR.get(net, "#8a93a6")
    lane_rows = ""
    for lane in val.get("lane_rank", []):
        d = val["lanes"].get(lane, {})
        sr = int((d.get("success_rate", 0) or 0) * 100)
        cps = d.get("cost_per_shipped")
        bar = "#2ecc71" if sr >= 60 else ("#f1c40f" if sr >= 30 else "#e74c3c")
        lane_rows += (f"<tr><td><b>{_esc(lane)}</b></td><td>{d.get('tasks',0)}</td>"
                      f"<td><span style='color:{bar};font-weight:700'>{sr}%</span></td>"
                      f"<td>{d.get('sunk',0)}</td><td>{cps if cps is not None else '—'}</td></tr>")
    # lane steering: which lanes are being shed from which work-classes (the ledger→routing loop)
    steer = []
    for lane, d in val.get("lanes", {}).items():
        wc = d.get("waste_classes") or []
        if wc:
            steer.append(f"{_esc(lane)} ⤼ {_esc(', '.join(wc[:4]))}")
    steer_html = (f'<div class="mut" style="margin-top:8px">steering away: {" · ".join(steer)}</div>'
                  if steer else "")

    pres = v["present"]
    board = " · ".join(f"{k} {n}" for k, n in sorted(pres["board"].items(), key=lambda x: -x[1]))
    gov = pres["governor"]
    integ = pres["integrity"]
    integ_s = " · ".join(f"{k.lower()} {n}" for k, n in integ.items() if n) or "clean"
    fleet_dots = "".join(
        f'<span class="vd"><span class="dot" style="background:{_HEALTH_DOT.get(i.get("health"),"#555")}">'
        f'</span>{_esc(n)} <span class="mut">{i.get("headroom_pct","?")}%</span></span>'
        for n, i in pres["fleet"].items())

    past = v["past"]
    fut = v["future"]
    fl = fut.get("front_load") or {}
    fl_items = "".join(
        f"<span class='vd'><b>{_esc(d['lane'])}</b> "
        f"<span class='mut'>~{d['expire']}{_esc(d.get('unit') or '')} expiring · {d['h_left']}h left "
        f"· {d.get('headroom_pct','?')}% idle</span></span>"
        for d in fl.get("expiring", []))
    fl_html = (f"<div class='card'><div class='lab'>future · front-load "
               f"<span class='{'you' if fl.get('accel') else 'mut'}'>"
               f"[accelerator {'ON' if fl.get('accel') else 'OFF'}]</span></div>"
               f"<div>{fl_items or '<span class=mut>no lane near a reset cliff — nothing expiring</span>'}</div>"
               f"<div class='mut' style='margin-top:6px'>budget that would expire unused at the next "
               f"reset if pacing stayed even — the accelerator burns it into win-class work first.</div></div>"
               if fl_items or fl else "")
    levers = "".join(f"<li>{_esc(x)}</li>" for x in fut["your_levers"])
    prod_rows = "".join(
        f"<tr><td class='mut'>{_esc(p.get('rank',''))}</td><td><b>{_esc(p.get('product',''))}</b>"
        f"<div class='mut'>{_esc(p.get('repo',''))}</div></td>"
        f"<td>{_esc(p.get('stage',''))}</td>"
        f"<td class='{'you' if p.get('whose_hand')=='yours' else 'mut'}'>"
        f"{'YOUR GATE' if p.get('whose_hand')=='yours' else 'fleet'}</td></tr>"
        for p in fut["products"])
    attr = "".join(f"<li>{_esc(a['product'])}: spent {a['spent']} → {a['shipped']} shipped, "
                   f"{a['wasted']} wasted</li>" for a in val.get("attribution", []))
    corp = fut["corpus"]
    ing = fut["ingestion"]
    ing_s = (f"{ing['atoms']:,} atoms · {ing['sources']} sources · {ing['coverage_pct']}% "
             f"(last {ing['last_run']})" if ing.get("atoms") else
             f"{corp.get('faces','?')} corpus faces · {corp.get('absorbed','?')} absorbed")
    ev = v["everything"]

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>LIMEN — the one surface</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:900px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .verdict{{border-color:{net_color};background:#10231a}}
 .verdict h2{{margin:0 0 6px;font-size:15px;color:{net_color}}} .verdict .big{{font-size:18px;font-weight:700}}
 .lab{{color:#8a93a6;font-size:11px;letter-spacing:.06em;text-transform:uppercase;margin-bottom:6px}}
 table{{width:100%;border-collapse:collapse}} td,th{{padding:6px 6px;border-top:1px solid #21262d;text-align:left;font-size:13px}}
 th{{color:#8a93a6;font-weight:600;border:0}}
 .mut{{color:#8a93a6;font-size:12px}} .you{{color:#2ecc71;font-weight:700;font-size:12px}}
 .spark{{font-size:18px;letter-spacing:1px;color:#2ecc71}}
 .row{{display:flex;gap:22px;flex-wrap:wrap}} .vd{{display:inline-block;margin-right:12px;font-size:13px}}
 .dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px;vertical-align:middle}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} @media(max-width:680px){{.grid{{grid-template-columns:1fr}}}}
 ul{{margin:6px 0;padding-left:18px}} li{{margin:3px 0}} a{{color:#58a6ff;text-decoration:none}}
 .big{{font-size:26px;font-weight:700}}
</style></head><body><div class="wrap">
 <h1>LIMEN — the one surface</h1>
 <div class="sub">updated {_esc(v['generated_at'])} · auto-refresh 30s · spine: {_esc(v['spine'])}</div>

 <div class="card verdict">
   <h2>⚖ IS IT EARNING ITS KEEP?</h2>
   <div class="big">net <span style="color:{net_color}">{_esc(net)}</span></div>
   <div class="mut">{_esc(val.get('verdict') or 'no ledger yet — runs each heal beat')}</div>
   <table><thead><tr><th>lane</th><th>tasks</th><th>worth-it</th><th>sunk</th><th>cost/ship</th></tr></thead>
   <tbody>{lane_rows or '<tr><td class=mut colspan=5>scoring…</td></tr>'}</tbody></table>
   {steer_html}
 </div>

 <div class="grid">
  <div class="card"><div class="lab">present · board</div><div>{_esc(board) or '—'}</div>
    <div class="mut" style="margin-top:8px">governor: <b>{_esc(gov.get('mode') or '?')}</b>
      · reserve {_esc(gov.get('reserve_pct'))}% · cap {_esc(gov.get('cap'))}</div>
    <div class="mut" style="margin-top:4px">integrity: {_esc(integ_s)}</div></div>
  <div class="card"><div class="lab">present · fleet</div><div>{fleet_dots or '—'}</div></div>
  <div class="card"><div class="lab">past · trend</div>
    <div>done <span class="spark">{_esc(past.get('done_spark'))}</span></div>
    <div>open <span class="spark">{_esc(past.get('open_spark'))}</span></div>
    <div class="mut" style="margin-top:6px">ships 24h: <b>{past.get('ships_24h',0)}</b>
      · {_esc(' '.join(past.get('recent_ships') or []) or '—')}</div></div>
  <div class="card"><div class="lab">future · knowledge</div><div>{_esc(ing_s)}</div>
    <div class="mut" style="margin-top:6px">{_esc((corp.get('one') or '')[:160])}</div></div>
 </div>

 {fl_html}

 <div class="card"><div class="lab">future · revenue ladder</div>
   <table><tbody>{prod_rows}</tbody></table>
   {f'<div class="lab" style="margin-top:10px">spend → ships</div><ul>{attr}</ul>' if attr else ''}</div>

 <div class="card verdict" style="background:#10231a">
   <div class="lab" style="color:#2ecc71">YOUR LEVERS — the moves only you can make</div>
   <ul>{levers or '<li>—</li>'}</ul></div>

 <div class="card"><div class="lab">everything · the rest of the estate</div>
   <div class="row"><span>{ev['memories']} memories</span><span>{ev['plans']} plans</span>
     <span>{ev['organs']} organs</span></div>
   <div class="mut" style="margin-top:8px">faces:
     {' · '.join(f'<a href="/{f}">{_esc(f)}</a>' if f.endswith('.html') else _esc(f) for f in ev['faces'])}</div></div>
</div></body></html>"""


def main():
    view = build_view()
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "omni-view.json").write_text(json.dumps(view, indent=2))
    html = render_html(view)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "omni.html").write_text(html)
            wrote.append(str(d / "omni.html"))
        except OSError:
            continue
    print(f"omni-view: net {view['value'].get('net')} · "
          f"board {sum(view['present']['board'].values())} tasks · "
          f"ships24h {view['past']['ships_24h']} -> {', '.join(wrote) or 'logs only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
