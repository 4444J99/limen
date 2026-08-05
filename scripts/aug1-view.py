#!/usr/bin/env python3
"""aug1-view.py — the GATE board: $10k/wk + in the EV + life progress, by 2026-08-01.

The single computation behind both faces of the goal. It loads the committed truth
(state/aug1/*.json + his-hand-levers.json) and the PRIVATE, never-committed life file, evaluates
the five-leg triad gate, writes logs/aug1-view.json (which scripts/aug1-gate.sh reads for its exit
code), and renders a self-contained web/app/{out,public}/aug1.html (meta-refresh, pure string
templating — no Next.js, no network, cannot time out).

This board has exactly one job and it is merciless about it: show whether the gate is TRUE, and name
the one un-automatable human act that moves it. It counts RECEIVED DOLLARS and BOOKED CALLS — never
lines of code shipped. It is the mirror pointed at the cliff (memory: close-is-the-cliff).

Anti-waste + never-"NO": every input fails toward FALSE — a missing or torn file is an unmet leg,
never a crash, never a fake pass. Read-only on all state; writes only its own output files.
"""
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
STATE = ROOT / "state" / "aug1"
LEVERS_FILE = ROOT / "his-hand-levers.json"
LIFE_FILE = Path(os.environ.get(
    "AUG1_LIFE_FILE", Path.home() / "Workspace" / "_health-private" / "aug1-life.json"))
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]

DEADLINE = date(2026, 8, 1)
WEEK_TARGET_CENTS = 1_000_000          # $10,000.00 / week
LIFE_STALE_DAYS = 7                    # the life leg must be logged recently to count
REVENUE_LEVER_IDS = ("L-REVENUE-ACCT", "L-PAYRAIL-INDIVIDUAL")

# PRIVACY BOUNDARY: this file is public. It reads ONLY booleans the private life file self-attests
# (ev_in_progress, on_track) — never a streak count, never a date. No live recovery number or
# derivable recovery date ever lands in public source or in any rendered output. The story is
# published deliberately (docs/AUG1-10K-GATE.md); the live numbers stay in the private file.


def _load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _dict_rows(value):
    return [row for row in _list(value) if isinstance(row, dict)]


def _cents(row):
    if not isinstance(row, dict):
        return 0
    try:
        return int(row.get("cents", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _parse_day(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def build_view():
    today = date.today()
    received = _dict_rows(_dict(_load(STATE / "revenue-received.json", {})).get("received"))
    engagements = _dict_rows(_dict(_load(STATE / "engagements.json", {})).get("engagements"))
    open_levers = _list(_dict(_load(LEVERS_FILE, {})).get("levers"))
    life = _load(LIFE_FILE, None)

    total_cents = sum(_cents(r) for r in received)
    wk_cutoff = today - timedelta(days=7)
    trailing7 = sum(_cents(r) for r in received
                    if isinstance(r, dict) and (_parse_day(r.get("at")) or date.min) >= wk_cutoff)
    signed = [e for e in engagements
              if isinstance(e, dict) and e.get("status") == "signed" and e.get("deposit_cleared") is True]
    open_lever_ids = {lev.get("id") for lev in open_levers if isinstance(lev, dict)}
    blocking_levers = sorted(open_lever_ids & set(REVENUE_LEVER_IDS))

    # life leg: PRIVATE file, booleans only. Fails toward FALSE if absent/stale/incomplete.
    # We read self-attested booleans (ev_in_progress, on_track) — never a count, never a date —
    # so no live recovery number can leak into rendered output. The raw streak, if kept at all,
    # lives in the private file and is never read here.
    life_ok, life_detail = False, "life leg unverified — self-attest in ~/…/_health-private/aug1-life.json"
    if isinstance(life, dict):
        ev = life.get("ev_in_progress") is True
        on_track = life.get("on_track") is True
        logged = _parse_day(life.get("updated") or life.get("at"))
        fresh = logged is not None and (today - logged).days <= LIFE_STALE_DAYS
        life_ok = ev and on_track and fresh
        life_detail = (f"EV {'in progress' if ev else 'not yet'} · "
                       f"{'on track' if on_track else 'not yet'}"
                       f"{'' if fresh or logged is None else ' · STALE — re-log'}")

    legs = [
        {"key": "rail", "label": "A rail has received a real dollar",
         "ok": total_cents > 0,
         "detail": f"${total_cents/100:,.0f} received to date" if total_cents else "$0 — no rail has collected yet",
         "act": "Rails are LIVE (Ko-fi 4444j99 · MONETA BTC mint since 2026-07-12 · PromptScope USDC) — the gap is a payer, not a rail. Put a paid ask in front of one human today; Lemon Squeezy KYC (L-REVENUE-ACCT) only if card checkout is the blocker."},
        {"key": "signed", "label": "≥1 signed engagement, deposit cleared",
         "ok": len(signed) > 0,
         "detail": f"{len(signed)} signed+cleared" if signed else "0 signed — no client closed yet",
         "act": "Send Offer A to ONE warm human and ask for the call. The one-pager + message are staged."},
        {"key": "runrate", "label": "Trailing-7d run-rate ≥ $10k/wk",
         "ok": trailing7 >= WEEK_TARGET_CENTS,
         "detail": f"${trailing7/100:,.0f} / $10,000 this week",
         "act": "Stack signed engagements toward $10k/wk. Close, don't build."},
        {"key": "levers", "label": "Revenue / pay-rail levers closed",
         "ok": not blocking_levers,
         "detail": ("open: " + ", ".join(blocking_levers)) if blocking_levers else "all closed",
         "act": "Close L-REVENUE-ACCT — claim the account/handle that receives the money."},
        {"key": "life", "label": "In the EV · clean streak · life progress",
         "ok": life_ok, "detail": life_detail,
         "act": "Self-log the EV + clean-streak leg (private file). This one is yours to live, not to code."},
    ]
    gate_pass = all(leg["ok"] for leg in legs)
    next_act = next((leg["act"] for leg in legs if not leg["ok"]), None)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "deadline": DEADLINE.isoformat(),
        "days_left": (DEADLINE - today).days,
        "gate": {"pass": gate_pass, "legs": legs},
        "next_act": next_act,
        "ledger": {
            "received_total_cents": total_cents,
            "trailing7_cents": trailing7,
            "received_count": len(received),
            "engagements": len(engagements),
            "signed": len(signed),
        },
    }


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(v):
    g = v["gate"]
    is_true = g["pass"]
    hero_color = "#2ecc71" if is_true else "#e74c3c"
    hero_word = "TRUE" if is_true else "FALSE"
    leg_rows = "".join(
        f'<tr><td class="m">{"✓" if leg["ok"] else "✗"}</td>'
        f'<td><b style="color:{"#2ecc71" if leg["ok"] else "#e6edf3"}">{_esc(leg["label"])}</b>'
        f'<div class="d">{_esc(leg["detail"])}</div></td></tr>'
        for leg in g["legs"])
    act = v.get("next_act")
    act_card = (f'<div class="card act"><div class="lab">the one move that matters today</div>'
                f'<div class="big">{_esc(act)}</div>'
                f'<div class="d" style="margin-top:8px">Not another commit. The fleet absorbs all the '
                f'code. Your hours go only to the two acts no machine can do: open a rail, talk to a '
                f'buyer.</div></div>') if act and not is_true else ""
    led = v["ledger"]
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>LIMEN — Aug-1 gate</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:760px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .gate{{border-color:{hero_color};background:{'#10231a' if is_true else '#23100f'}}}
 .gate .lab{{color:{hero_color}}} .gate .huge{{font-size:40px;font-weight:800;color:{hero_color};letter-spacing:1px}}
 .act{{border-color:#f1c40f;background:#1c1a0d}} .act .lab{{color:#f1c40f}}
 .lab{{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#8a93a6;margin-bottom:6px}}
 .big{{font-size:17px;font-weight:700;line-height:1.4}}
 table{{width:100%;border-collapse:collapse}} td{{padding:9px 6px;border-top:1px solid #21262d;vertical-align:top}}
 td.m{{width:22px;font-size:18px;font-weight:800;color:#8a93a6}}
 .d{{color:#8a93a6;font-size:12px;margin-top:2px}}
 .row{{display:flex;gap:26px;flex-wrap:wrap}} .stat .k{{color:#8a93a6;font-size:12px}} .stat .n{{font-size:24px;font-weight:700}}
 .foot{{color:#6b7280;font-size:11px;margin-top:14px;text-align:center}}
</style></head><body><div class="wrap">
 <h1>LIMEN — the Aug-1 gate</h1>
 <div class="sub">updated {_esc(v['generated_at'])} · {v['days_left']} days to {_esc(v['deadline'])} · auto-refresh 30s · the predicate decides, not the craving</div>
 <div class="card gate"><div class="lab">$10k/wk · in the EV · life progress</div>
   <div class="huge">GATE: {hero_word}</div></div>
 {act_card}
 <div class="card"><div class="lab">the five legs</div>
   <table><tbody>{leg_rows}</tbody></table></div>
 <div class="card row">
   <div class="stat"><div class="k">received to date</div><div class="n">${led['received_total_cents']/100:,.0f}</div></div>
   <div class="stat"><div class="k">this week</div><div class="n">${led['trailing7_cents']/100:,.0f}<span style="font-size:13px;color:#8a93a6">/10k</span></div></div>
   <div class="stat"><div class="k">signed · engagements</div><div class="n">{led['signed']} · {led['engagements']}</div></div>
 </div>
 <div class="foot">this board counts received dollars + booked calls — never lines shipped · plan: docs/AUG1-10K-GATE.md</div>
</div></body></html>"""


def main():
    view = build_view()
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "aug1-view.json").write_text(json.dumps(view, indent=2))
    html = render_html(view)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "aug1.html").write_text(html)
            (d / "aug1-view.json").write_text(json.dumps(view, indent=2))
            wrote.append(str(d / "aug1.html"))
        except OSError:
            continue
    g = view["gate"]
    met = sum(1 for leg in g["legs"] if leg["ok"])
    print(f"aug1-view: gate {'TRUE' if g['pass'] else 'FALSE'} ({met}/{len(g['legs'])} legs), "
          f"${view['ledger']['received_total_cents']/100:,.0f} received, "
          f"{view['days_left']}d left -> {', '.join(wrote) or 'logs/aug1-view.json only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
