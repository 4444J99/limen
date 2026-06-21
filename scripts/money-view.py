#!/usr/bin/env python3
"""money-view.py — the ONE revenue feed, three faces.

Each beat this distills the curated revenue-ladder.json + the live fleet feeds (ticks.jsonl
done-trend, merge-drain.log ships, usage.json fleet health) into a single logs/money-view.json, and
renders a self-contained web/app/out/money.html (meta-refresh, pure string templating — NO Next.js,
NO network, so it CANNOT time out the way the old dashboard build does). Both are mirrored to
web/app/public/ for the remote/phone face.

This is the answer to "when you're not working it looks like nothing is happening": a glance that
shows motion TOWARD THE FIRST DOLLAR — which product is how close, what shipped since you last
looked, and which gate is yours to pull.

Anti-waste + never-"NO": every section fails OPEN — a missing or torn feed yields an empty section,
never a crash. Read-only on the fleet's data; writes only its own output files.
"""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]

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
    """Merged PRs in the last 24h, parsed from merge-drain.log (local timestamps). Returns
    (total, per_repo, recent_refs)."""
    try:
        lines = (LOGS / "merge-drain.log").read_text().splitlines()
    except OSError:
        return 0, {}, []
    cutoff = datetime.now() - timedelta(hours=24)
    per_repo, refs = {}, []
    for ln in lines:
        m = _TS_RE.search(ln)
        if not m:
            continue
        try:
            when = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if when < cutoff:
            continue
        for ref in _PR_RE.findall(ln):
            repo = ref.split("#")[0]
            per_repo[repo] = per_repo.get(repo, 0) + 1
            refs.append(ref)
    return len(refs), per_repo, refs[-12:]


def build_view():
    ladder = _load_json(ROOT / "revenue-ladder.json", {})
    ticks = _ticks()
    last = ticks[-1] if ticks else {}
    ships_total, ships_by_repo, recent_refs = _ships_last_24h()
    usage = _load_json(LOGS / "usage.json", {}).get("vendors", {})

    products = []
    for p in ladder.get("products", []):
        prod = dict(p)
        prod["shipped_24h"] = ships_by_repo.get(p.get("repo", ""), 0)
        products.append(prod)
    products.sort(key=lambda x: x.get("rank", 99))

    your_gates = [p for p in products
                  if p.get("whose_hand") == "yours" and p.get("stage") in ("deploy-ready", "live")]

    fleet = {name: {"health": info.get("health"), "remaining": info.get("remaining")}
             for name, info in usage.items() if isinstance(info, dict)}

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "spine": ladder.get("spine", ""),
        "products": products,
        "your_gates": your_gates,
        "your_levers": ladder.get("your_levers", []),
        "pulse": {
            "done": last.get("done"),
            "total": last.get("total"),
            "open": last.get("open"),
            "dispatched": last.get("dispatched"),
            "daily_spent": last.get("daily_spent"),
            "daily_cap": last.get("daily_cap"),
            "done_spark": _sparkline([t.get("done", 0) for t in ticks]),
            "open_spark": _sparkline([t.get("open", 0) for t in ticks]),
        },
        "ships_24h": {"total": ships_total, "by_repo": ships_by_repo, "recent": recent_refs},
        "fleet": fleet,
    }


_STAGE_COLOR = {"building": "#8a93a6", "deploy-ready": "#2ecc71",
                "live": "#27ae60", "monetized": "#f1c40f"}
_HEALTH_DOT = {"ok": "#2ecc71", "throttle": "#f1c40f", "low": "#e67e22",
               "rate-limited": "#e67e22", "exhausted": "#7f8c8d"}


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_html(v):
    rows = []
    for p in v["products"]:
        color = _STAGE_COLOR.get(p.get("stage"), "#8a93a6")
        hand = p.get("whose_hand", "")
        hand_badge = ('<span class="hand you">YOUR GATE</span>' if hand == "yours"
                      else '<span class="hand me">fleet</span>')
        ships = p.get("shipped_24h", 0)
        ships_s = f'<span class="ship">+{ships} today</span>' if ships else ""
        rows.append(f"""
        <tr>
          <td class="rank">{_esc(p.get('rank',''))}</td>
          <td><b>{_esc(p.get('product',''))}</b><div class="repo">{_esc(p.get('repo',''))}</div></td>
          <td><span class="stage" style="background:{color}">{_esc(p.get('stage',''))}</span> {hand_badge}</td>
          <td class="next">{_esc(p.get('next_action',''))} {ships_s}</td>
        </tr>""")

    gates = ""
    if v["your_gates"]:
        items = "".join(f"<li><b>{_esc(g.get('product'))}</b> is "
                        f"<span class='stage' style='background:{_STAGE_COLOR.get(g.get('stage'),'#888')}'>"
                        f"{_esc(g.get('stage'))}</span> &rarr; {_esc(g.get('next_action'))}</li>"
                        for g in v["your_gates"])
        gates = f'<div class="card gate"><h2>⟶ YOUR MOVE = FIRST DOLLAR</h2><ul>{items}</ul></div>'

    pulse = v["pulse"]
    done, total = pulse.get("done") or 0, pulse.get("total") or 0
    pct = f"{(done/total*100):.0f}%" if total else "—"

    fleet_dots = "".join(
        f'<span class="vd"><span class="dot" style="background:{_HEALTH_DOT.get(i.get("health"),"#555")}"></span>'
        f'{_esc(n)}</span>'
        for n, i in v["fleet"].items())

    levers = "".join(f"<li>{_esc(x)}</li>" for x in v["your_levers"])
    ships = v["ships_24h"]
    recent = " · ".join(_esc(r) for r in ships.get("recent", [])) or "—"

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>LIMEN — money view</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:880px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .gate{{border-color:#2ecc71;background:#10231a}} .gate h2{{color:#2ecc71;margin:0 0 8px;font-size:15px}}
 table{{width:100%;border-collapse:collapse}} td{{padding:9px 6px;border-top:1px solid #21262d;vertical-align:top}}
 .rank{{color:#8a93a6;width:22px}} .repo{{color:#8a93a6;font-size:12px}}
 .stage{{color:#06140c;font-weight:700;border-radius:5px;padding:1px 7px;font-size:12px}}
 .hand{{font-size:11px;border-radius:5px;padding:1px 6px;margin-left:4px}}
 .hand.you{{background:#2ecc71;color:#06140c;font-weight:700}} .hand.me{{background:#21262d;color:#8a93a6}}
 .next{{color:#c9d1d9;font-size:13px}} .ship{{color:#2ecc71;font-weight:700}}
 .big{{font-size:28px;font-weight:700}} .spark{{font-size:18px;letter-spacing:1px;color:#2ecc71}}
 .vd{{display:inline-block;margin-right:12px;font-size:13px}} .dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:4px;vertical-align:middle}}
 ul{{margin:6px 0;padding-left:18px}} li{{margin:3px 0}}
 .row{{display:flex;gap:24px;flex-wrap:wrap}} .stat .k{{color:#8a93a6;font-size:12px}}
</style></head><body><div class="wrap">
 <h1>LIMEN — money view</h1>
 <div class="sub">updated {_esc(v['generated_at'])} · auto-refresh 30s · spine: {_esc(v['spine'])}</div>
 {gates}
 <div class="card">
   <table><tbody>{''.join(rows)}</tbody></table>
 </div>
 <div class="card row">
   <div class="stat"><div class="k">shipped (24h)</div><div class="big">{ships.get('total',0)}</div></div>
   <div class="stat"><div class="k">done</div><div class="big">{done}/{total} <span style="font-size:15px;color:#8a93a6">{pct}</span></div><div class="spark">{_esc(pulse.get('done_spark',''))}</div></div>
   <div class="stat"><div class="k">open · dispatched</div><div class="big">{pulse.get('open','—')} · {pulse.get('dispatched','—')}</div><div class="spark">{_esc(pulse.get('open_spark',''))}</div></div>
   <div class="stat"><div class="k">spend today</div><div class="big">{pulse.get('daily_spent','—')}<span style="font-size:15px;color:#8a93a6">/{pulse.get('daily_cap','—')}</span></div></div>
 </div>
 <div class="card"><div class="k" style="color:#8a93a6;font-size:12px">fleet</div><div style="margin-top:6px">{fleet_dots or '—'}</div>
   <div style="color:#8a93a6;font-size:12px;margin-top:10px">recent ships: {recent}</div></div>
 <div class="card"><div class="k" style="color:#8a93a6;font-size:12px">YOUR LEVERS (the 10-week path)</div><ul>{levers}</ul></div>
</div></body></html>"""


def main():
    view = build_view()
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "money-view.json").write_text(json.dumps(view, indent=2))
    html = render_html(view)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "money.html").write_text(html)
            (d / "money-view.json").write_text(json.dumps(view, indent=2))
            wrote.append(str(d / "money.html"))
        except OSError:
            continue
    print(f"money-view: {len(view['products'])} products, "
          f"{view['ships_24h']['total']} ships/24h, done {view['pulse'].get('done')}/"
          f"{view['pulse'].get('total')} -> {', '.join(wrote) or 'logs/money-view.json only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
