#!/usr/bin/env python3
"""pillars-view.py — make the "platform of pillars" VISIBLE on the face you already look at.

The pillars (ingest, distillation, federation, config, memory, portal, views) were built many
times across local and remote dirs; the recurring ask is to CONVERGE and SEE them, not rebuild.
This renders pillars.yaml — the convergence registry — into a self-contained web/app/out/pillars.html
(meta-refresh, pure string templating, NO Next.js, NO network, can't time out) plus
logs/pillars-view.json, mirrored to web/app/public for the phone face.

STATUS IS DERIVED, never pinned: each pillar's live state comes from whether its `path` exists and
whether its `health_signal` (a logs/*.json) is fresh — so a pillar that goes stale shows stale, and
a hardcoded "done" can't lie ([[derive-never-pin-hardcodes]], [[pillars-platform-convergence]]).

Anti-waste + never-"NO": every pillar fails OPEN — a missing registry / torn signal yields an
ABSENT/UNKNOWN badge, never a crash. Read-only on every pillar; writes only its own output files.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]
PILLARS_YAML = Path(os.environ.get("LIMEN_PILLARS", ROOT / "pillars.yaml"))
STALE_DAYS = float(os.environ.get("LIMEN_PILLARS_STALE_DAYS", "2"))


def _now():
    return datetime.now(timezone.utc)


def _load_yaml(path):
    try:
        import yaml
        return yaml.safe_load(Path(path).read_text()) or {}
    except Exception:
        return {}


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _parse_ts(v):
    """Best-effort ISO8601 → aware datetime, else None."""
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)   # naive stamps → assume UTC


def _signal_freshness(signal_path):
    """Return (age_days|None, stamp_str|None) for a logs/*.json health signal — from an embedded
    timestamp field if present, else the file mtime. None age = no signal on disk."""
    p = Path(signal_path)
    if not p.is_file():
        return None, None
    data = _load_json(p, {})
    ts = None
    for k in ("generated", "generated_at", "timestamp", "last_run", "updated"):
        ts = _parse_ts(data.get(k)) if isinstance(data, dict) else None
        if ts:
            break
    if ts is None:
        try:
            ts = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
        except OSError:
            return None, None
    age = (_now() - ts).total_seconds() / 86400.0
    return age, ts.isoformat(timespec="seconds")


def _headline(pillar_id, signal_path):
    """A one-line headline metric for pillars whose signal shape we know; else ''."""
    data = _load_json(signal_path, {})
    if not isinstance(data, dict):
        return ""
    if pillar_id == "ingest":
        by = data.get("by_source") or {}
        nonzero = sorted((k for k, v in by.items() if v), key=lambda k: -by[k])[:4]
        srcs = (" · " + ", ".join(nonzero)) if nonzero else ""
        return (f"{data.get('atoms', '?')} atoms · {len([k for k,v in by.items() if v]) or data.get('sources','?')} "
                f"live sources · {data.get('coverage_pct', '?')}% coverage{srcs}")
    if pillar_id == "distillation":
        return (f"{data.get('face_count', '?')} faces · {data.get('absorbed_total', 0)} absorbed · "
                f"last run {data.get('last_run') or 'never'}")
    if pillar_id == "views":
        return "omni surface live"
    return ""


def build_view():
    reg = _load_yaml(PILLARS_YAML)
    program = reg.get("program", []) if isinstance(reg, dict) else []
    pillars_in = reg.get("pillars", []) if isinstance(reg, dict) else []

    pillars = []
    for p in pillars_in:
        path = p.get("path")
        exists = bool(path) and Path(os.path.expanduser(path)).exists()
        signal_rel = p.get("health_signal")
        age = stamp = None
        headline = ""
        if signal_rel:
            signal_path = ROOT / signal_rel
            age, stamp = _signal_freshness(signal_path)
            headline = _headline(p.get("id", ""), signal_path)
        # derive status — never pinned
        if path and not exists:
            status = "absent"
        elif age is not None and age > STALE_DAYS:
            status = "stale"
        elif signal_rel and age is None:
            status = "unknown"     # has a signal slot but none on disk yet
        else:
            status = "live"
        pillars.append({
            "id": p.get("id"), "name": p.get("name"), "role": p.get("role"),
            "owner": p.get("owner"), "path": path, "producer": p.get("producer"),
            "status": status, "headline": headline,
            "signal_age_days": round(age, 2) if age is not None else None,
            "signal_stamp": stamp,
        })

    counts = {}
    for p in pillars:
        counts[p["status"]] = counts.get(p["status"], 0) + 1

    return {
        "generated": _now().isoformat(timespec="seconds"),
        "program": program,
        "pillars": pillars,
        "pillar_count": len(pillars),
        "status_counts": counts,
    }


# ─── render ──────────────────────────────────────────────────────────

def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_BADGE = {
    "live": ("LIVE", "ok"), "armed": ("ARMED", "warn"), "stale": ("STALE", "warn"),
    "absent": ("ABSENT", "bad"), "unknown": ("UNKNOWN", "dim"),
}


def _badge(status):
    label, cls = _BADGE.get(status, (str(status).upper(), "dim"))
    return f"<span class='badge {cls}'>{label}</span>"


def render_html(v):
    prog_rows = "".join(
        f"<tr><td class='pid'>{_esc(p.get('id'))}</td>"
        f"<td><b>{_esc(p.get('title'))}</b><div class='sub2'>{_esc(p.get('note') or '')}</div></td>"
        f"<td>{_badge(p.get('status'))}</td></tr>"
        for p in v["program"])

    pill_rows = []
    for p in v["pillars"]:
        meta = p.get("headline") or _esc(p.get("role") or "")
        if p.get("headline"):
            meta = _esc(p["headline"])
        age = (f" · signal {p['signal_age_days']}d old" if p.get("signal_age_days") is not None else "")
        producer = f" · <span class='mono'>{_esc(p['producer'])}</span>" if p.get("producer") else ""
        pill_rows.append(
            f"<tr><td><b>{_esc(p.get('name'))}</b>"
            f"<div class='sub2'>{_esc(p.get('owner') or '')}{producer}</div></td>"
            f"<td>{_badge(p.get('status'))}</td>"
            f"<td>{meta}<div class='sub2'>{_esc(p.get('role') or '') if p.get('headline') else ''}{age}</div></td></tr>")

    counts = v["status_counts"]
    pulse = " · ".join(f"{n} {s}" for s, n in sorted(counts.items()))

    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="60"><title>LIMEN — the pillars</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:880px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:14px 16px;margin:12px 0}}
 .k{{color:#8a93a6;font-size:12px;text-transform:uppercase;letter-spacing:.5px}}
 table{{width:100%;border-collapse:collapse}} td{{padding:8px 6px;border-top:1px solid #21262d;vertical-align:top}}
 .sub2{{color:#8a93a6;font-size:12px;margin-top:2px}} .pid{{color:#7c6cff;font-weight:700;width:48px}}
 .mono{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}}
 .badge{{font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;white-space:nowrap}}
 .ok{{color:#0d1117;background:#2ecc71}} .warn{{color:#0d1117;background:#e3b341}}
 .bad{{color:#fff;background:#da3633}} .dim{{color:#8a93a6;background:#21262d}}
</style></head><body><div class="wrap">
 <h1>LIMEN — the platform of pillars</h1>
 <div class="sub">updated {_esc(v['generated'])} · auto-refresh 60s · {_esc(pulse)} · status DERIVED, not pinned</div>
 <div class="card"><div class="k">CONVERGENCE PROGRAM</div>
   <table><tbody>{prog_rows or '<tr><td class=sub2>no program</td></tr>'}</tbody></table></div>
 <div class="card"><div class="k">THE PILLARS</div>
   <table><tbody>{''.join(pill_rows) or '<tr><td class=sub2>no pillars registered</td></tr>'}</tbody></table></div>
</div></body></html>"""


def main():
    view = build_view()
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "pillars-view.json").write_text(json.dumps(view, indent=2))
    html = render_html(view)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "pillars.html").write_text(html)
            (d / "pillars-view.json").write_text(json.dumps(view, indent=2))
            wrote.append(str(d / "pillars.html"))
        except OSError:
            continue
    c = view["status_counts"]
    print(f"pillars-view: {view['pillar_count']} pillars ({', '.join(f'{n} {s}' for s, n in sorted(c.items()))}) "
          f"-> {', '.join(wrote) or 'logs/pillars-view.json only'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
