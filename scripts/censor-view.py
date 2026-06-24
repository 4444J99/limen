#!/usr/bin/env python3
"""censor-view.py — make THE CENSOR visible on the face you already look at.

Renders the Censor's insights→actions ledger into a self-contained censor.html
(meta-refresh, pure string templating, NO Next.js, NO network, can't time out) plus
logs/censor-view.json, mirrored to web/app/public for the phone face.

It shows the constitution at work: each recent decision tagged by the BRANCH that
reached it (protocol / precedent / exploration) and its DISPOSITION (auto-applied /
proposed / surfaced-to-you / exploring), plus the cadence clock (when each tier last
ran and when it is next due). Status is DERIVED from the ledger, never pinned
([[derive-never-pin-hardcodes]], [[pillars-platform-convergence]]). Read-only + fail-open.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
CENSOR_DIR = ROOT / "censor"
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]
TIER_SECONDS = {"hourly": 3600, "daily": 86400, "weekly": 604800}
MAX_DECISIONS = int(os.environ.get("LIMEN_CENSOR_VIEW_ROWS", "40"))


def _now():
    return datetime.now(timezone.utc)


def _parse_ts(v):
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _tail_jsonl(path, n):
    try:
        lines = [ln for ln in Path(path).read_text().splitlines() if ln.strip()]
    except OSError:
        return []
    out = []
    for ln in lines[-n:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def build_view():
    state = _load_json(LOGS / "censor-state.json", {"last_run": {}})
    last = _load_json(LOGS / "censor-last.json", {})
    # the live picture is the latest run (fresh every beat, dry or armed); fall back to
    # the durable ledger tail when no run summary exists yet.
    decisions = last.get("decisions") or _tail_jsonl(LOGS / "censor-decisions.jsonl", MAX_DECISIONS)
    decisions = decisions[-MAX_DECISIONS:]
    now = _now()

    cadence = []
    for tier, span in TIER_SECONDS.items():
        prev = _parse_ts(state.get("last_run", {}).get(tier))
        if prev is None:
            cadence.append({"tier": tier, "last": None, "due": True, "in_h": 0})
        else:
            elapsed = (now - prev).total_seconds()
            cadence.append({"tier": tier, "last": prev.isoformat(timespec="seconds"),
                            "due": elapsed >= span,
                            "in_h": round(max(0, span - elapsed) / 3600.0, 1)})

    counts = {}
    branches = {}
    for d in decisions:
        disp = (d.get("verdict") or {}).get("disposition", "?")
        br = (d.get("verdict") or {}).get("branch", "?")
        counts[disp] = counts.get(disp, 0) + 1
        branches[br] = branches.get(br, 0) + 1

    return {
        "generated": now.isoformat(timespec="seconds"),
        "last_run_applied": last.get("applied"),
        "last_tiers": last.get("tiers_run", []),
        "cadence": cadence,
        "disposition_counts": counts,
        "branch_counts": branches,
        "decisions": list(reversed(decisions)),   # newest first
        "decision_count": len(decisions),
    }


# ─── render ──────────────────────────────────────────────────────────

def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_DISP = {
    "auto": ("AUTO-APPLIED", "ok"), "propose": ("PROPOSED", "warn"),
    "surface": ("FOR YOU", "info"), "explore": ("EXPLORING", "dim"),
}
_BRANCH = {"protocol": "⚖ protocol", "precedent": "§ precedent",
           "exploration": "🔭 exploration", "ideal-form": "✶ ideal-form"}


def _disp_badge(disp):
    label, cls = _DISP.get(disp, (str(disp).upper(), "dim"))
    return f"<span class='badge {cls}'>{label}</span>"


def render_html(v):
    cad = " · ".join(
        f"{c['tier']}: {'DUE now' if c['due'] else str(c['in_h']) + 'h'}"
        for c in v["cadence"]) or "no cadence yet"

    rows = []
    for d in v["decisions"]:
        s = d.get("signal", {})
        ver = d.get("verdict", {})
        branch = _BRANCH.get(ver.get("branch"), _esc(ver.get("branch", "?")))
        rows.append(
            f"<tr><td class='mono'>{_esc(d.get('tier'))}</td>"
            f"<td><b>{_esc(s.get('type'))}</b> · {_esc(s.get('subject'))}"
            f"<div class='sub2'>{branch} — {_esc(ver.get('rationale') or ver.get('action') or '')}</div></td>"
            f"<td>{_disp_badge(ver.get('disposition'))}"
            f"<div class='sub2'>{_esc(d.get('outcome') or '')}</div></td></tr>")

    dc = v["disposition_counts"]
    pulse = " · ".join(f"{n} {k}" for k, n in sorted(dc.items())) or "no decisions yet"

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60"><title>LIMEN — the Censor</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:900px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .k{{color:#8a93a6;font-size:12px;text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px}}
 table{{width:100%;border-collapse:collapse}} td{{padding:8px 6px;border-top:1px solid #21262d;vertical-align:top}}
 .sub2{{color:#8a93a6;font-size:12px;margin-top:2px}}
 .mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:#7c6cff}}
 .badge{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;white-space:nowrap}}
 .ok{{color:#0d1117;background:#2ecc71}} .warn{{color:#0d1117;background:#e3b341}}
 .info{{color:#0d1117;background:#58a6ff}} .dim{{color:#8a93a6;background:#21262d}}
</style></head><body><div class="wrap">
 <h1>LIMEN — the Censor</h1>
 <div class="sub">insights → actions, on cadence · updated {_esc(v['generated'])} · auto-refresh 60s · {_esc(pulse)}</div>
 <div class="card"><div class="k">the lustrum — cadence clock</div>{_esc(cad)}</div>
 <div class="card"><div class="k">decisions (newest first) — branch reached · disposition</div>
   <table><tbody>{''.join(rows) or '<tr><td class=sub2>no decisions yet — run censor.py</td></tr>'}</tbody></table></div>
 <div class="sub">separation of powers: protocol dictates → else precedent → else exploration → until ideal-form. Autonomy is derived from reversibility, never set.</div>
</div></body></html>"""


def main():
    v = build_view()
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "censor-view.json").write_text(json.dumps(v, indent=2))
    html = render_html(v)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "censor.html").write_text(html)
            (d / "censor-view.json").write_text(json.dumps(v, indent=2))
            wrote.append(str(d / "censor.html"))
        except OSError:
            continue
    print(f"censor-view: {v['decision_count']} decisions -> {', '.join(wrote) or 'logs/censor-view.json only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
