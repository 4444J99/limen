#!/usr/bin/env python3
"""organ-health.py — PROPRIOCEPTION: the organism feels whether its own organs are firing.

The self-* ladder is asserted from code ("all rungs wired and live") but, until now, nothing
SHOWED whether each rung actually fires on cadence. A liveness belief that the logs can quietly
contradict is not autonomic — it's faith. This organ closes that gap: for every rung
(SUSTAIN · ROUTE · FEED · MERGE · HEAL · IMPROVE · PRESERVE · CONVERGE · MAIL · HEALTH) it derives
the LAST time the organ fired and marks it green / stale / down / gated against its OWN cadence.

Two signal sources, in priority order:
  1. logs/.voice/<voice>   — a stamp the heartbeat writes the instant a voice plays (ground truth).
  2. an artifact the organ produces (mtime or embedded timestamp) — works TODAY, before stamping
     lands in the live loop.

Derive, never pin: cadences (C_*) and the adaptive tempo (LOOP_MIN/MAX) are PARSED out of
heartbeat-loop.sh, so if he retunes a voice the health window follows automatically. Gate flags are
read from ~/.limen.env so a gated-OFF organ reads "gated" (intentional), never a false "down".

Anti-waste + never-"NO": read-only on the fleet's data; writes only its own logs/organ-health.json
and the self-contained organ-health.html face. Every probe fails OPEN — a missing artifact yields
"unknown", never a crash, and never blocks the beat.
"""
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
VOICED = LOGS / ".voice"
LOOP_SH = ROOT / "scripts" / "heartbeat-loop.sh"
ENV_FILE = Path(os.environ.get("LIMEN_ENV_FILE", Path.home() / ".limen.env"))
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]

_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")


# ── derive cadences + tempo from the loop itself (never pin) ──────────────────────────────────
def _loop_text():
    try:
        return LOOP_SH.read_text()
    except OSError:
        return ""


def _parse_cadences(text):
    """C_NAME="${LIMEN_BEAT_NAME:-N}"  →  {"NAME": N}.  Env overrides the parsed default."""
    out = {}
    for name, default in re.findall(r'C_([A-Z_]+)="\$\{LIMEN_BEAT_[A-Z_]+:-(\d+)\}"', text):
        try:
            out[name] = int(os.environ.get(f"LIMEN_BEAT_{name}", default))
        except ValueError:
            continue
    return out


def _parse_tempo(text):
    def grab(var, fallback):
        m = re.search(rf'{var}:-(\d+)', text)
        val = m.group(1) if m else str(fallback)
        try:
            return int(os.environ.get(var, val))
        except ValueError:
            return fallback
    return grab("LIMEN_LOOP_MIN", 120), grab("LIMEN_LOOP_MAX", 1800)


def _env_flag(name, default=""):
    """Read a gate flag from the live env, falling back to ~/.limen.env, then default. Read-only."""
    if name in os.environ:
        return os.environ[name]
    try:
        for ln in ENV_FILE.read_text().splitlines():
            ln = ln.strip()
            if ln.startswith(f"{name}=") or ln.startswith(f"export {name}="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return default


# ── signal probes ─────────────────────────────────────────────────────────────────────────────
def _mtime(path):
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def _voice_stamp(voice):
    """Ground-truth last-fire from logs/.voice/<voice> (mtime; content is the ISO ts but mtime
    is enough and avoids parse cost)."""
    return _mtime(VOICED / voice)


def _last_log_ts(path):
    """Newest 'YYYY-MM-DD HH:MM:SS' found in a log file → epoch (local). Fail-open to None."""
    try:
        text = Path(path).read_text()
    except OSError:
        return None
    best = None
    for m in _TS_RE.findall(text):
        try:
            when = datetime.strptime(m.replace("T", " "), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        if best is None or when > best:
            best = when
    return best


def _json_field_ts(path, *fields):
    """Epoch from the first present ISO/'%Y-%m-%d %H:%M:%S' field in a json file."""
    try:
        obj = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    for f in fields:
        v = obj.get(f)
        if not isinstance(v, str):
            continue
        m = _TS_RE.search(v)
        if not m:
            continue
        try:
            return datetime.strptime(m.group(1).replace("T", " "), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
    return None


# ── the organ registry ──────────────────────────────────────────────────────────────────────
# Each organ: rung label, the heartbeat VOICE that fires it (→ voice-stamp + cadence key), the
# fallback artifact probe (used until stamping is live), an optional gate, and a one-line "what".
# cadence is a beats key into the parsed C_* map; IMPROVE runs on a wall-clock producer cadence,
# expressed in seconds directly.
def _registry():
    return [
        dict(key="sustain", rung="SUSTAIN", voice="tick", cadence_beats=1,
             what="heartbeat daemon — the base tempo every voice rides on",
             probe=lambda: _mtime(LOGS / "ticks.jsonl")),
        dict(key="route", rung="ROUTE", voice="balance", cadence_key="BALANCE",
             what="capacity-aware routing across the lanes",
             probe=lambda: _mtime(LOGS / "route-health.json")),  # route.py stamps this every balance beat
        dict(key="feed", rung="FEED", voice="feed", cadence_key="FEED",
             what="mine + generate backlog (revenue-first)",
             probe=lambda: _mtime(LOGS / "feed-health.json")),  # generate-backlog.py stamps this every feed beat
        dict(key="merge", rung="MERGE", voice="merge", cadence_beats=1, gate_note="merges gated on permission",
             what="merge-ready assessment; CLEAN PRs ship",
             probe=lambda: _last_log_ts(LOGS / "merge-drain.log")),
        dict(key="heal", rung="HEAL", voice="heal", cadence_key="HEAL",
             what="repair CI-red/conflict PRs; reconcile phantom dispatches",
             probe=lambda: _mtime(LOGS / "dispatch-verify.json")),
        dict(key="improve", rung="IMPROVE", voice="improve", interval_s=10 * 3600,
             what="learn lane productivity → routing weights (producer)",
             probe=lambda: _json_field_ts(LOGS / "self-improve-proposal.json", "generated_at", "timestamp")
                           or _mtime(LOGS / "self-improve-proposal.json")),
        dict(key="preserve", rung="PRESERVE", voice="backup", cadence_key="BACKUP",
             what="copy irreplaceable → Archive4T; reclaim regenerable caches",
             probe=lambda: _mtime(LOGS / "library-levers.json") or _mtime(LOGS / "capture-log.jsonl")),
        dict(key="converge", rung="CONVERGE", voice="corpus", cadence_key="CORPUS",
             gate="LIMEN_CORPUS_CONVERGE", gate_default="0",
             what="distill his words toward THE ONE (the 'back again')",
             probe=lambda: _mtime(LOGS / "corpus-converge-state.json")),
        dict(key="mail", rung="MAIL", voice="mail", cadence_key="MAIL",
             gate="GMAIL_OAUTH_OP_REF", gate_default="", gate_truthy_nonempty=True,
             what="sweep inbound (flag/archive) + rebuild obligations ledger",
             probe=lambda: _mtime(LOGS / "obligations-view.json")),
        dict(key="nomenclator", rung="NOMENCLATOR", voice="nomenclator", cadence_key="NOMENCLATOR",
             gate="LIMEN_NOMENCLATOR", gate_default="0",
             what="INDEX·NOMINVM — hold the roll of names to the canon (nota)",
             probe=lambda: _mtime(LOGS / "nomenclator.json")),
        dict(key="health", rung="HEALTH", voice="health", cadence_key="HEALTH",
             what="personal health office — chase open clinical loops + prep visits (PII local)",
             probe=lambda: _mtime(LOGS / "health-organ-state.json")),
    ]


def build():
    text = _loop_text()
    cadences = _parse_cadences(text)
    loop_min, loop_max = _parse_tempo(text)

    organs = []
    for o in _registry():
        # cadence → expected seconds between fires, worst-case (idle beats run at LOOP_MAX).
        if "interval_s" in o:
            expected = o["interval_s"]
            cadence_desc = f"~{o['interval_s'] // 3600}h"
        else:
            beats = o.get("cadence_beats") or cadences.get(o.get("cadence_key", ""), 0) or 1
            expected = beats * loop_max
            cadence_desc = "every beat" if beats == 1 else f"every {beats} beats"

        # gate state
        gated = False
        if o.get("gate"):
            val = _env_flag(o["gate"], o.get("gate_default", ""))
            if o.get("gate_truthy_nonempty"):
                gated = (val == "")
            else:
                gated = (val != "1")

        # best signal: voice-stamp (ground truth) else artifact probe
        src = "voice-stamp"
        ts = _voice_stamp(o["voice"])
        if ts is None:
            ts = o["probe"]()
            src = "artifact"
        if ts is None:
            src = "none"

        now = time.time()
        age = (now - ts) if ts else None

        if gated:
            status = "gated"
        elif age is None:
            status = "unknown"
        elif age <= expected * 1.5:
            status = "green"
        elif age <= expected * 4:
            status = "stale"
        else:
            status = "down"

        organs.append({
            "key": o["key"], "rung": o["rung"], "what": o["what"],
            "voice": o["voice"], "cadence": cadence_desc,
            "status": status, "source": src,
            "last_fired": datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None,
            "age_h": round(age / 3600, 1) if age is not None else None,
            "expected_h": round(expected / 3600, 1),
            "note": o.get("gate_note", ""),
        })

    counts = {}
    for o in organs:
        counts[o["status"]] = counts.get(o["status"], 0) + 1
    rungs_live = sum(1 for o in organs if o["status"] in ("green", "gated"))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tempo": {"min_s": loop_min, "max_s": loop_max},
        "summary": {"total": len(organs), "live": rungs_live, **counts},
        "organs": organs,
    }


_DOT = {"green": "#2ecc71", "stale": "#f1c40f", "down": "#e74c3c",
        "gated": "#8a93a6", "unknown": "#6e7681"}
_LABEL = {"green": "live", "stale": "stale", "down": "DOWN",
          "gated": "gated (intentional)", "unknown": "no signal yet"}


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(v):
    rows = []
    for o in v["organs"]:
        color = _DOT.get(o["status"], "#555")
        age = f"{o['age_h']}h ago" if o["age_h"] is not None else "—"
        last = o["last_fired"] or "never observed"
        src = "" if o["source"] == "voice-stamp" else f' <span class="src">({o["source"]})</span>'
        note = f' · <span class="note">{_esc(o["note"])}</span>' if o["note"] else ""
        rows.append(f"""
        <tr>
          <td><span class="dot" style="background:{color}"></span><b>{_esc(o['rung'])}</b>
              <div class="what">{_esc(o['what'])}</div></td>
          <td class="cad">{_esc(o['cadence'])}{note}</td>
          <td class="age">{_esc(age)}<div class="last">{_esc(last)}{src}</div></td>
          <td><span class="badge" style="background:{color}">{_esc(_LABEL.get(o['status'], o['status']))}</span></td>
        </tr>""")

    s = v["summary"]
    headline = f"{s.get('live', 0)}/{s.get('total', 0)} rungs live"
    sub_bits = [f"{n}: {s[n]}" for n in ("green", "gated", "stale", "down", "unknown") if s.get(n)]
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>LIMEN — organ health</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:820px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:6px 16px;margin:12px 0}}
 .big{{font-size:26px;font-weight:700;margin:6px 0}}
 table{{width:100%;border-collapse:collapse}} td{{padding:11px 6px;border-top:1px solid #21262d;vertical-align:top}}
 tr:first-child td{{border-top:none}}
 .dot{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:7px;vertical-align:middle}}
 .what{{color:#8a93a6;font-size:12px;margin:2px 0 0 18px}}
 .cad{{color:#c9d1d9;font-size:13px}} .note{{color:#8a93a6;font-size:12px}}
 .age{{font-size:13px}} .last{{color:#6e7681;font-size:11px}} .src{{color:#8a93a6}}
 .badge{{color:#06140c;font-weight:700;border-radius:5px;padding:2px 8px;font-size:12px}}
</style></head><body><div class="wrap">
 <h1>LIMEN — organ health</h1>
 <div class="sub">proprioception · does each self-* rung actually fire? · updated {_esc(v['generated_at'])} · auto-refresh 30s</div>
 <div class="card"><div class="big">{_esc(headline)}</div>
   <div class="sub" style="margin:0 0 8px">{_esc(' · '.join(sub_bits))}</div></div>
 <div class="card"><table><tbody>{''.join(rows)}</tbody></table></div>
 <div class="sub">green/stale/down derived per-organ against its OWN cadence (worst-case beat = {v['tempo']['max_s']}s).
   Ground-truth source is logs/.voice/&lt;voice&gt; once heartbeat voice-stamping is live; until then,
   organs fall back to their output artifact's freshness (shown as "(artifact)").</div>
</div></body></html>"""


def main():
    view = build()
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "organ-health.json").write_text(json.dumps(view, indent=2))
    html = render_html(view)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "organ-health.html").write_text(html)
            (d / "organ-health.json").write_text(json.dumps(view, indent=2))
            wrote.append(str(d / "organ-health.html"))
        except OSError:
            continue
    s = view["summary"]
    detail = " ".join(f"{o['rung']}:{o['status']}" for o in view["organs"])
    print(f"organ-health: {s.get('live', 0)}/{s.get('total', 0)} live -> "
          f"{', '.join(wrote) or 'logs/organ-health.json only'}\n  {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
