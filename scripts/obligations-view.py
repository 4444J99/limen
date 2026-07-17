#!/usr/bin/env python3
"""obligations-view.py — the ONE mail-obligation feed, pervasive faces.

The north star ("known, owned, pervasive — then I tend the handful that matters"): this
renders obligations-ledger.json (built keylessly by universal-mail--automation's
obligations_build.py from the inbox-sweep receipts) into a self-contained
web/app/out/obligations.html (meta-refresh, pure string templating — NO Next.js, NO
network, so it CANNOT time out), mirrored to web/app/public/ for the phone face, plus
logs/obligations-view.json for the notify-events push diff.

Every buried obligation across all accounts, owned (yours), each with its protocol-derived
next step, sorted by consequence — the fires you'd otherwise never see surface here and
stay visible until you decide they matter. No nagging.

Anti-waste + never-"NO": every section fails OPEN — a missing/torn ledger yields an empty
state, never a crash. Read-only on the ledger; writes only its own output files.
"""
import json
import os
from datetime import date, datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]
LEDGER = Path(os.environ.get("LIMEN_OBLIGATIONS_LEDGER", ROOT / "obligations-ledger.json"))
# His-hand atoms hang HERE, in git — a separate file from the ledger ON PURPOSE: the mail
# builder regenerates obligations-ledger.json every sweep, so any lever placed there is wiped.
# These are unioned in below and survive regen. A his-hand task never hangs on him or in memory.
HIS_HAND = Path(os.environ.get("LIMEN_HIS_HAND_LEVERS", ROOT / "his-hand-levers.json"))


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _union_levers(ledger):
    """His-hand levers (git, durable) first, then the mail ledger's levers; dedup by id.
    Fail-open: a missing/torn his-hand file just yields the ledger levers, never a crash."""
    if not isinstance(ledger, dict):
        ledger = {}
    his_hand = _load_json(HIS_HAND, {})
    his = his_hand.get("levers", []) if isinstance(his_hand, dict) else []
    out, seen = [], set()
    ledger_levers = ledger.get("levers", [])
    if not isinstance(ledger_levers, list):
        ledger_levers = []
    for lev in list(his) + list(ledger_levers):
        if not isinstance(lev, dict):
            continue
        if lev.get("discharged"):
            continue
        lid = lev.get("id")
        if lid in seen:
            continue
        seen.add(lid)
        out.append(lev)
    return out


def build_view():
    ledger = _load_json(LEDGER, {})
    if not isinstance(ledger, dict):
        ledger = {}
    obligations = ledger.get("obligations", [])
    if not isinstance(obligations, list):
        obligations = []
    obligations = [o for o in obligations if isinstance(o, dict)]
    verify_first = [o for o in obligations if isinstance(o, dict) and o.get("verify_first")]
    accounts = ledger.get("accounts", [])
    if not isinstance(accounts, list):
        accounts = []
    accounts = [a for a in accounts if isinstance(a, dict)]
    totals = ledger.get("totals", {})
    if not isinstance(totals, dict):
        totals = {}
    noise_killers = ledger.get("noise_killers", [])
    if not isinstance(noise_killers, list):
        noise_killers = []
    noise_killers = [n for n in noise_killers if isinstance(n, dict)]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "built_at": ledger.get("generated_at", ""),
        "spine": ledger.get("spine", ""),
        "accounts": accounts,
        "totals": totals,
        "obligations": obligations,
        "verify_first": verify_first,
        "noise_killers": noise_killers,
        "levers": _union_levers(ledger),
    }


# priority → urgency color band (by consequence, not brand)
def _band(pri):
    if pri >= 85:
        return "#e74c3c"      # red — security/money/legal critical
    if pri >= 70:
        return "#e67e22"      # orange — real action
    if pri >= 45:
        return "#f1c40f"      # yellow — reply/decide
    return "#8a93a6"          # grey — low / self


_RUNG_BADGE = {"protocol": ("protocol", "#2ecc71"),
               "precedent": ("precedent", "#4a86e8"),
               "exploration": ("review", "#8a93a6")}

# Warm inbound leads get a first-class badge on the face (the limen-side of the opportunity lane):
# a recruiter/client/LinkedIn reach-out the UMA inbound-lead protocols classified. Just the door,
# never a name — the row already carries the PII-clean provenance below it.
_INBOUND_DOORS = {"inbound-lead-hire": "hire", "inbound-lead-deploy": "deploy",
                  "inbound-linkedin": "linkedin"}


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _deadline_badge(lever, today=None):
    """The face's own clock: a lever past (or near) its `deadline` auto-flags so it can never
    silently rot on the surface. Pure + derived — no hand-maintained status field. Fails open:
    a missing or malformed deadline yields no badge, never a crash."""
    raw = lever.get("deadline")
    if not raw:
        return ""
    try:
        due = datetime.strptime(str(raw), "%Y-%m-%d").date()
    except ValueError:
        return ""
    delta = (due - (today or date.today())).days
    if delta < 0:
        return f'<span class="due overdue">OVERDUE {-delta}d</span>'
    if delta == 0:
        return '<span class="due overdue">DUE TODAY</span>'
    if delta <= 3:
        return f'<span class="due soon">due in {delta}d</span>'
    return f'<span class="due">due {_esc(raw)}</span>'


def render_html(v):
    verify = ""
    if v["verify_first"]:
        items = "".join(
            f"<li><b>{_esc(o.get('title'))}</b> &middot; {_esc(o.get('next_step'))}</li>"
            for o in v["verify_first"])
        verify = (f'<div class="card alert"><h2>⚠ VERIFY FIRST '
                  f'({len(v["verify_first"])})</h2><div class="hint">spoof-prone notices — '
                  f'confirm the sender is real before acting; never click their links</div>'
                  f'<ul>{items}</ul></div>')

    rows = []
    for o in v["obligations"]:
        color = _band(o.get("priority", 0))
        rung_label, rung_color = _RUNG_BADGE.get(o.get("rung"), ("?", "#555"))
        occ = o.get("occurrences", 1)
        occ_s = f'<span class="occ">×{occ}</span>' if occ > 1 else ""
        reply = '<span class="tag reply">reply</span>' if o.get("requires_reply") else ""
        door = _INBOUND_DOORS.get(o.get("cls"))
        warm = f'<span class="tag warm">🎯 warm lead · {door}</span>' if door else ""
        accts = ", ".join(a.split("@")[-1] for a in o.get("accounts", []))
        samples = o.get("sample_subjects", [])
        sample_s = (f'<div class="samples">{_esc(" · ".join(samples[:3]))}</div>'
                    if samples else "")
        draft = ""
        if o.get("draft_text"):
            saved = ' · saved to Drafts' if o.get("draft_saved") else ' · not yet saved'
            draft = (f'<details class="draft"><summary>ready draft → {_esc(o.get("draft_to",""))}'
                     f'{saved} (never sent)</summary><pre>{_esc(o["draft_text"])}</pre></details>')
        rows.append(f"""
        <tr>
          <td class="pri" style="color:{color}">{_esc(o.get('priority',''))}</td>
          <td>
            <b>{_esc(o.get('title',''))}</b> {occ_s}
            <span class="rung" style="background:{rung_color}">{rung_label}</span> {reply} {warm}
            <div class="next">{_esc(o.get('next_step',''))}</div>
            {sample_s}
            {draft}
            <div class="prov">{_esc(accts)}</div>
          </td>
        </tr>""")

    noise = ""
    if v["noise_killers"]:
        nrows = "".join(
            f'<tr><td class="occ">×{n.get("count",1)}</td>'
            f'<td><b>{_esc(n.get("name",""))}</b> <span class="prov">{_esc(n.get("domain",""))}</span>'
            f'<div class="next">{_esc(n.get("action",""))}</div></td></tr>'
            for n in v["noise_killers"][:25])
        noise = (f'<div class="card"><div class="k">NOISE KILLERS — recurring senders to '
                 f'unsubscribe/filter at source ({len(v["noise_killers"])}, gated on a write '
                 f'door; proposed so nothing refills silently)</div>'
                 f'<table><tbody>{nrows}</tbody></table></div>')

    totals = v["totals"]
    by_rung = totals.get("by_rung", {})
    rung_s = " · ".join(f"{k}:{val}" for k, val in by_rung.items()) or "—"

    acct_s = "".join(
        f'<span class="vd">{_esc(a.get("account","").split("@")[-1])} '
        f'<b>{a.get("fires",0)}</b> fires / {a.get("total",0)}</span>'
        for a in v["accounts"]) or "—"

    levers = "".join(
        f'<li><b>{_esc(lev.get("id"))}</b> — {_esc(lev.get("label"))} '
        f'<span class="cost">({_esc(lev.get("cost",""))})</span>'
        f'{_deadline_badge(lev)}'
        f'{(" &rarr; <b>" + _esc(lev.get("unlocks")) + "</b>") if lev.get("unlocks") else ""}</li>'
        for lev in v["levers"])

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>LIMEN — obligations</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:880px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .alert{{border-color:#e74c3c;background:#21100f}} .alert h2{{color:#e74c3c;margin:0 0 4px;font-size:15px}}
 .hint{{color:#8a93a6;font-size:12px;margin-bottom:6px}}
 table{{width:100%;border-collapse:collapse}} td{{padding:10px 6px;border-top:1px solid #21262d;vertical-align:top}}
 .pri{{width:30px;font-weight:700;font-size:16px;text-align:center}}
 .rung{{color:#06140c;font-weight:700;border-radius:5px;padding:1px 7px;font-size:11px}}
 .occ{{color:#e67e22;font-weight:700;font-size:13px;margin-left:2px}}
 .tag{{font-size:11px;border-radius:5px;padding:1px 6px;margin-left:3px}}
 .tag.reply{{background:#4a86e8;color:#fff}}
 .tag.warm{{background:#e67e22;color:#fff}}
 .next{{color:#c9d1d9;font-size:13px;margin-top:3px}}
 .samples{{color:#6e7681;font-size:11.5px;margin-top:3px;font-style:italic}}
 .prov{{color:#6e7681;font-size:11px;margin-top:2px}}
 .draft{{margin-top:5px}} .draft summary{{cursor:pointer;color:#4a86e8;font-size:12px}}
 .draft pre{{white-space:pre-wrap;background:#0d1117;border:1px solid #21262d;border-radius:6px;padding:8px;font-size:12px;color:#c9d1d9;margin:6px 0 0}}
 .vd{{display:inline-block;margin-right:14px;font-size:13px;color:#c9d1d9}}
 ul{{margin:6px 0;padding-left:18px}} li{{margin:4px 0}}
 .cost{{color:#8a93a6;font-size:11px}}
 .due{{font-size:11px;border-radius:5px;padding:1px 6px;margin-left:5px;background:#21262d;color:#8a93a6}}
 .due.overdue{{background:#e74c3c;color:#fff;font-weight:700}}
 .due.soon{{background:#f1c40f;color:#06140c;font-weight:700}}
 .big{{font-size:28px;font-weight:700}} .k{{color:#8a93a6;font-size:12px}}
 .row{{display:flex;gap:24px;flex-wrap:wrap}}
</style></head><body><div class="wrap">
 <h1>LIMEN — obligations</h1>
 <div class="sub">updated {_esc(v['generated_at'])} · ledger built {_esc(v['built_at'])} · auto-refresh 30s<br>{_esc(v['spine'])}</div>
 {verify}
 <div class="card row">
   <div><div class="k">obligations</div><div class="big">{totals.get('obligations','—')}</div></div>
   <div><div class="k">from fires</div><div class="big">{totals.get('fires','—')}</div></div>
   <div><div class="k">verify-first</div><div class="big" style="color:#e74c3c">{totals.get('verify_first','—')}</div></div>
   <div><div class="k">by rung</div><div style="margin-top:8px;font-size:13px">{_esc(rung_s)}</div></div>
 </div>
 <div class="card"><table><tbody>{''.join(rows) or '<tr><td>— no obligations (clean) —</td></tr>'}</tbody></table></div>
 {noise}
 <div class="card"><div class="k">accounts swept</div><div style="margin-top:6px">{acct_s}</div></div>
 <div class="card"><div class="k">YOUR LEVERS (raise the ceiling — known &amp; owned, never forced)</div><ul>{levers or '<li>—</li>'}</ul></div>
</div></body></html>"""


def main():
    view = build_view()
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "obligations-view.json").write_text(json.dumps(view, indent=2))
    html = render_html(view)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "obligations.html").write_text(html)
            (d / "obligations-view.json").write_text(json.dumps(view, indent=2))
            wrote.append(str(d / "obligations.html"))
        except OSError:
            continue
    t = view["totals"]
    print(f"obligations-view: {t.get('obligations', 0)} obligations "
          f"({t.get('verify_first', 0)} verify-first) -> "
          f"{', '.join(wrote) or 'logs/obligations-view.json only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
