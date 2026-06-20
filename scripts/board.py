#!/usr/bin/env python3
"""board.py — live terminal dashboard for the conductor. READ-ONLY (never writes
tasks.yaml, so it never races the daemon). Run once, or `--watch [secs]` to refresh.

  python3 scripts/board.py            # one snapshot
  python3 scripts/board.py --watch    # live, refresh every 5s
  python3 scripts/board.py --watch 2  # every 2s
"""
import datetime
import json
import os
import re
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
C = {
    "r": "\033[31m", "g": "\033[32m", "y": "\033[33m", "b": "\033[34m",
    "m": "\033[35m", "c": "\033[36m", "w": "\033[37m", "gray": "\033[90m",
    "bold": "\033[1m", "x": "\033[0m",
}
LANE_ORDER = ["jules", "codex", "opencode", "agy", "claude", "gemini"]
BLOCKS = " ▁▂▃▄▅▆▇█"


def bar(pct, width=22):
    fill = int(round(pct / 100 * width))
    col = C["r"] if pct >= 90 else C["y"] if pct >= 60 else C["g"]
    return col + "█" * fill + C["gray"] + "░" * (width - fill) + C["x"]


def spark(values, width=40):
    if not values:
        return ""
    vals = values[-width:]
    hi = max(vals) or 1
    return "".join(BLOCKS[min(8, int(v / hi * 8))] for v in vals)


def load():
    d = yaml.safe_load((ROOT / "tasks.yaml").read_text()) or {}
    ticks = []
    tp = ROOT / "logs" / "ticks.jsonl"
    if tp.exists():
        for ln in tp.read_text().strip().split("\n")[-60:]:
            try:
                ticks.append(json.loads(ln))
            except Exception:
                pass
    usage = {}
    up = ROOT / "logs" / "usage.json"
    if up.exists():
        try:
            usage = json.loads(up.read_text())
        except Exception:
            pass
    return d, ticks, usage


def fmt_n(n):
    return f"{n/1e6:.1f}M" if n >= 1e6 else f"{n/1e3:.0f}k" if n >= 1000 else str(n)


# the polyrhythm: voice → (subdivision, phase-of-cadence)
_VOICES = [
    ("dispatch", 1, "BUILD"), ("tick", 1, "—"), ("balance", 2, "PLAN"),
    ("feed", 3, "EXPLORE"), ("drain", 3, "VERIFY"), ("web", 4, "LEARN"),
    ("heal", 6, "HEAL"), ("hygiene", 8, "—"), ("backup", 48, "RELAY"),
]


def read_pulse():
    """current beat #, tempo, and recent events from the daemon log."""
    log = ROOT / "logs" / "heartbeat.out.log"
    beat, tempo, events, alive = 0, "?", [], False
    try:
        lines = log.read_text(errors="ignore").splitlines()[-400:]
        for ln in lines:
            m = re.search(r"beat (\d+)", ln)
            if m:
                beat = int(m.group(1))
            m2 = re.search(r"tempo:.*?(\d+)s", ln)
            if m2:
                tempo = m2.group(1) + "s"
            if re.search(r"→ PR|PARALLEL done|dispatched:|RATE-LIMIT|reopened|rebalanced|mined|harvest", ln):
                events.append(ln.strip()[:72])
    except Exception:
        pass
    return beat, tempo, events[-6:]


def read_integrity():
    """dispatch-verification snapshot (silent-failure detector). Empty if never run."""
    p = ROOT / "logs" / "dispatch-verify.json"
    try:
        return json.loads(p.read_text()).get("counts", {})
    except Exception:
        return {}


def render(d, ticks, usage=None):
    tasks = d.get("tasks", [])
    b = (d.get("portal") or {}).get("budget") or {}
    caps = b.get("per_agent", {}) or {}
    track = b.get("track", {}) or {}
    tp = track.get("per_agent", {}) or {}
    daily, dspent = b.get("daily", 300), track.get("spent", 0)
    by_status = {}
    by_lane_open = {}
    for t in tasks:
        by_status[t.get("status")] = by_status.get(t.get("status"), 0) + 1
        if t.get("status") == "open":
            a = t.get("target_agent")
            by_lane_open[a] = by_lane_open.get(a, 0) + 1

    out = []
    p = out.append
    now = datetime.datetime.now().strftime("%F %T")
    p(f"{C['bold']}{C['c']}╔══ LIMEN CONDUCTOR ─ {now} ══════════════════════════╗{C['x']}")
    p(f"{C['bold']}VENDOR CAPACITY{C['x']}  {C['gray']}(used/cap · refresh on UTC date-roll){C['x']}")
    for a in [x for x in LANE_ORDER if x in caps] + [x for x in caps if x not in LANE_ORDER]:
        cap = caps.get(a, 0)
        sp = tp.get(a, 0)
        rem = max(0, min(daily - dspent, cap - sp))
        pct = round(sp / cap * 100) if cap else 0
        kind = C["m"] + "cloud" if a == "jules" else C["g"] + "local"
        p(f"  {a:9} {bar(pct)} {sp:>3}/{cap:<3} {C['gray']}{rem:>3} left · {by_lane_open.get(a,0):>2} queued{C['x']}  {kind}{C['x']}")
    dpct = round(dspent / daily * 100) if daily else 0
    p(f"  {C['bold']}{'daily':9}{C['x']} {bar(dpct)} {dspent:>3}/{daily:<3}")

    p("")
    p(f"{C['bold']}FUNNEL{C['x']}")
    funnel = [("done", "g"), ("dispatched", "y"), ("in_progress", "c"),
              ("failed", "r"), ("cancelled", "gray"), ("open", "b")]
    tot = len(tasks) or 1
    for k, col in funnel:
        n = by_status.get(k, 0)
        if not n and k in ("in_progress", "cancelled"):
            continue
        w = int(n / tot * 30)
        p(f"  {k:11} {C[col]}{'■'*w}{C['x']} {n}")
    p(f"  {C['gray']}total {len(tasks)}{C['x']}")

    integ = read_integrity()
    if integ:
        p("")
        p(f"{C['bold']}INTEGRITY{C['x']}  {C['gray']}(babysit every dispatch · ⚠ = silent failure){C['x']}")
        healthy = [("PR_OPEN", "g"), ("JULES_ASYNC", "c"), ("DISPATCHED_RUNNING", "b")]
        bad = [("PR_MERGED", "y"), ("PR_CLOSED", "y"), ("PR_MISSING", "r"), ("DISPATCHED_NO_PR", "r")]
        names = {"PR_OPEN": "open-pr", "JULES_ASYNC": "jules", "DISPATCHED_RUNNING": "running"}
        line = "  "
        for k, col in healthy:
            line += f"{C[col]}{names.get(k,k.lower())}:{integ.get(k,0)}{C['x']}  "
        p(line)
        actionable = sum(integ.get(k, 0) for k, _ in bad)
        if actionable:
            bl = "  "
            for k, col in bad:
                n = integ.get(k, 0)
                if n:
                    bl += f"{C[col]}⚠ {k.lower()}:{n}{C['x']}  "
            p(bl)
            p(f"  {C['gray']}{actionable} need heal (merged→done · closed/no-pr→reopen) — heal-dispatch.py{C['x']}")
        else:
            p(f"  {C['g']}✓ no silent failures{C['x']}")
        nch = integ.get("CHRONIC", 0)
        if nch:
            p(f"  {C['m']}⚑ chronic:{nch}{C['x']} {C['gray']}(reopened ≥3× · never a PR · failing all lanes → escalate, not re-loop){C['x']}")

    if ticks:
        p("")
        p(f"{C['bold']}HEARTBEAT{C['x']}  {C['gray']}({len(ticks)} ticks){C['x']}")
        p(f"  dispatched {C['c']}{spark([t.get('dispatched',0) for t in ticks])}{C['x']}")
        p(f"  open       {C['b']}{spark([t.get('open',0) for t in ticks])}{C['x']}")
        last = ticks[-1]
        p(f"  {C['gray']}last {last.get('ts','?')} · spent {last.get('daily_spent',0)}/{last.get('daily_cap',0)}{C['x']}")

    if usage and usage.get("vendors"):
        p("")
        p(f"{C['bold']}REAL USAGE & HEADROOM{C['x']}  {C['gray']}(used / possible · true signal){C['x']}")
        for a, v in usage["vendors"].items():
            h = v.get("health", "")
            hcol = C["r"] if h in ("exhausted", "rate-limited") else C["y"] if h == "low" else C["g"]
            cons = fmt_n(v.get("consumed", 0))
            poss = v.get("possible")
            if poss:
                hp = v.get("headroom_pct", 0)
                used_pct = 100 - hp
                p(f"  {a:9} {bar(used_pct)} {C['w']}{cons}/{fmt_n(poss)}{C['x']} {v.get('unit','')[:3]:3} {C['gray']}{hp}% left{C['x']} {hcol}{h}{C['x']}")
            else:
                p(f"  {a:9} {C['gray']}{'░'*22}{C['x']} {C['w']}{cons}{C['x']} {v.get('unit','')[:3]:3} {C['gray']}no cap{C['x']} {hcol}{h}{C['x']}")

    beat, tempo, events = read_pulse()
    p("")
    p(f"{C['bold']}CADENCE — POLYRHYTHM{C['x']}  {C['gray']}beat {beat} · tempo {tempo} · ● fires this window{C['x']}")
    for name, sub, phase in _VOICES:
        cells = ""
        for k in range(beat + 1, beat + 17):
            if k % sub == 0:
                cells += C["c"] + "●" + C["x"]
            else:
                cells += C["gray"] + "·" + C["x"]
        nextin = sub - (beat % sub) if (beat % sub) else 0
        p(f"  {name:8} {cells} {C['gray']}/{sub} {phase}{C['x']}")
    if events:
        p("")
        p(f"{C['bold']}LIVE EVENTS{C['x']}")
        for e in events:
            ec = C["g"] if ("PR" in e or "dispatched" in e) else C["y"] if ("RATE" in e or "reopened" in e) else C["gray"]
            p(f"  {ec}{e}{C['x']}")

    p(f"{C['bold']}{C['c']}╚════════════════════════════════════════════════════════╝{C['x']}")
    return "\n".join(out)


def main():
    watch = "--watch" in sys.argv
    secs = 5
    for a in sys.argv[1:]:
        if a.isdigit():
            secs = int(a)
    if not watch:
        print(render(*load()))
        return
    try:
        while True:
            print("\033[2J\033[H", end="")  # clear
            print(render(*load()))
            print(f"{C['gray']}  ↻ every {secs}s · Ctrl-C to exit{C['x']}")
            time.sleep(secs)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
