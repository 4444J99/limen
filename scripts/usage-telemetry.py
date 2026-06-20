#!/usr/bin/env python3
"""usage-telemetry.py — emit REAL per-vendor usage (not fictional run-counts).

Each vendor exposes a different truth (see BACKLOG.md vendor table); this reads the best
available real signal and writes logs/usage.json for board.py + the portal:
  codex   — sum total_tokens from ~/.codex/sessions/*.jsonl in the 5h rolling window
  claude  — sum usage tokens from ~/.claude/projects/**/*.jsonl in the 5h window
  jules   — dispatch count today vs 100 (the one true proxy; rolling 24h)
  gemini  — dispatch count today vs RPD-ish cap + last rate-limit event
  opencode/agy — dispatch count today + last rate-limit event (no readable meter)

READ-ONLY w.r.t. tasks.yaml (writes ONLY logs/usage.json) → never races the daemon.
"""
import datetime
import json
import os
import re
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # launchd/cron may resolve a Python without PyYAML
    yaml = None

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
HOME = Path.home()
NOW = datetime.datetime.now(datetime.timezone.utc)
W5H = NOW - datetime.timedelta(hours=5)
TODAY = NOW.date().isoformat()
_IN = re.compile(r'"input_tokens"\s*:\s*(\d+)')
_OUT = re.compile(r'"output_tokens"\s*:\s*(\d+)')
_CLAUDE_RATE_LIMIT_TEXT = re.compile(
    r"monthly spend limit|rate[_ -]?limit|too many requests|\b429\b|usage limit|"
    r"insufficient_quota|out of (?:tokens|credits)",
    re.IGNORECASE,
)

# tunable per-vendor LIMITS (the "amount possible") — defaults are honest estimates;
# calibrate to your real plan (codex/claude: see each CLI's /status). Override via
# logs/usage-limits.json or env LIMEN_<VENDOR>_LIMIT.
_DEFAULT_LIMITS = {
    "jules":    {"limit": 100,        "unit": "runs",   "window": "24h",        "source": "known hard cap"},
    "codex":    {"limit": 100_000_000, "unit": "tokens", "window": "5h rolling", "source": "ESTIMATE — tune to plan (/status)"},
    "claude":   {"limit": 100_000_000, "unit": "tokens", "window": "5h rolling", "source": "ESTIMATE — tune to plan (/status)"},
    "gemini":   {"limit": 1000,       "unit": "runs",   "window": "24h",        "source": "ESTIMATE — free-tier RPD"},
    "opencode": {"limit": 200,        "unit": "runs",   "window": "today",      "source": "ESTIMATE — set $/run budget"},
    "agy":      {"limit": 200,        "unit": "runs",   "window": "today",      "source": "ESTIMATE — credit budget"},
}


# Hold back this % of every cap so a live lane is paced-OUT before it hits 0 — the
# "never run out" reserve. Override via env LIMEN_RESERVE_PCT or a top-level
# "reserve_pct" key in logs/usage-limits.json.
_DEFAULT_RESERVE_PCT = 15.0


def load_limits():
    path = ROOT / "logs" / "usage-limits.json"
    limits = {k: dict(v) for k, v in _DEFAULT_LIMITS.items()}
    if path.exists():
        try:
            for k, v in json.loads(path.read_text()).items():
                if not isinstance(v, dict):  # e.g. top-level "reserve_pct": 15 → not a vendor
                    continue
                limits.setdefault(k, {}).update(v)
        except Exception:
            pass
    else:
        try:
            path.parent.mkdir(exist_ok=True)
            path.write_text(json.dumps(_DEFAULT_LIMITS, indent=2))
        except Exception:
            pass
    for k in limits:  # env override wins
        env = os.environ.get(f"LIMEN_{k.upper()}_LIMIT")
        if env and env.isdigit():
            limits[k]["limit"] = int(env)
    return limits


def load_reserve_pct():
    """The fraction of every cap to hold in reserve. env LIMEN_RESERVE_PCT wins, then a
    top-level "reserve_pct" in logs/usage-limits.json, else the default."""
    env = os.environ.get("LIMEN_RESERVE_PCT")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    path = ROOT / "logs" / "usage-limits.json"
    if path.exists():
        try:
            v = json.loads(path.read_text()).get("reserve_pct")
            if v is not None:
                return float(v)
        except Exception:
            pass
    return _DEFAULT_RESERVE_PCT


def _window_hours(window: str) -> float:
    """Refresh-window length in hours, parsed from the human label telemetry already carries:
    "5h"/"5h rolling" → 5, "24h"/"rolling 24h" → 24, "today" → hours left in the UTC day."""
    if window:
        m = re.search(r"(\d+)\s*h", window)
        if m:
            return float(m.group(1))
        if "today" in window:
            return max(1.0, 24 - NOW.hour - NOW.minute / 60)
    return 24.0


def load_tasks_data():
    path = ROOT / "tasks.yaml"
    try:
        text = path.read_text()
    except OSError:
        return {}
    if yaml is not None:
        return yaml.safe_load(text) or {}
    # Fail open for telemetry instead of crashing the heartbeat. Without PyYAML we lose
    # dispatch-count/budget-derived signals, but transcript/token health still works.
    return {}


def _recent(p: Path) -> bool:
    try:
        return datetime.datetime.fromtimestamp(p.stat().st_mtime, datetime.timezone.utc) >= W5H
    except Exception:
        return False


def codex_5h():
    base = HOME / ".codex" / "sessions"
    total = sessions = 0
    if base.exists():
        for f in base.rglob("*.jsonl"):
            if not _recent(f):
                continue
            sessions += 1
            try:
                txt = f.read_text(errors="ignore")
                mi = max([int(x) for x in _IN.findall(txt)] or [0])   # cumulative → max ≈ session total
                mo = max([int(x) for x in _OUT.findall(txt)] or [0])
                total += mi + mo  # billable (input+output), excludes cached
            except Exception:
                pass
    return {"signal": "tokens", "window": "5h rolling", "consumed": total,
            "unit": "tokens", "sessions": sessions,
            "health": "ok", "note": "billable codex tokens (input+output, 5h)"}


def claude_5h():
    base = HOME / ".claude" / "projects"
    total = msgs = rate_limit_events = 0
    if base.exists():
        for f in base.rglob("*.jsonl"):
            if not _recent(f):
                continue
            try:
                for ln in f.read_text(errors="ignore").splitlines():
                    try:
                        row = json.loads(ln)
                    except Exception:
                        continue
                    blob = json.dumps(row, ensure_ascii=False)
                    if row.get("error") == "rate_limit" or _CLAUDE_RATE_LIMIT_TEXT.search(blob):
                        rate_limit_events += 1
                    u = (row.get("message", {}) or {}).get("usage")
                    if not u:
                        continue
                    total += (u.get("input_tokens", 0) + u.get("output_tokens", 0)
                              + u.get("cache_creation_input_tokens", 0))  # billable; exclude cheap cache_read
                    msgs += 1
            except Exception:
                pass
    return {"signal": "tokens", "window": "5h rolling", "consumed": total,
            "unit": "tokens", "messages": msgs,
            "health": "rate-limited" if rate_limit_events else "ok",
            "rate_limit_events": rate_limit_events,
            "note": "billable claude tokens (in+out+cache-create, excl cache-read, 5h)"}


def dispatch_counts(tasks):
    """today's dispatch_log dispatched-events per agent."""
    by = {}
    for t in tasks:
        for e in t.get("dispatch_log", []) or []:
            ts = str(e.get("timestamp", ""))
            if ts[:10] == TODAY and e.get("status") == "dispatched":
                a = e.get("agent")
                by[a] = by.get(a, 0) + 1
    return by


def last_ratelimit():
    log = ROOT / "logs" / "heartbeat.out.log"
    out = {}
    if log.exists():
        for ln in log.read_text(errors="ignore").splitlines():
            m = re.search(r"RATE-LIMIT (\w+)", ln)
            if m:
                out[m.group(1)] = "seen"
    return out


def main():
    data = load_tasks_data()
    tasks = data.get("tasks", [])
    budget = (data.get("portal") or {}).get("budget") or {}
    caps = budget.get("per_agent", {}) or {}
    track = (budget.get("track") or {}).get("per_agent", {}) or {}
    dc = dispatch_counts(tasks)
    rl = last_ratelimit()
    limits = load_limits()

    vendors = {
        "codex": codex_5h(),
        "claude": claude_5h(),
        "jules": {"signal": "count", "window": "rolling 24h", "consumed": track.get("jules", 0),
                  "unit": "runs", "note": "count vs cap — the one true proxy"},
    }
    for v in ("gemini", "opencode", "agy"):
        vendors[v] = {"signal": "dispatch-count", "window": "today",
                      "consumed": dc.get(v, 0), "unit": "runs",
                      "note": "no readable meter — dispatch count + rate-limit watch"}

    # attach the "amount POSSIBLE" → headroom + the refresh-window PACING math for every vendor.
    # The split decision: never run a live lane to 0. Burning faster than safe_rate_per_h
    # (cap / window) will exhaust the window; staying at-or-below it self-refreshes forever.
    reserve_pct = load_reserve_pct()
    for name, v in vendors.items():
        lim = limits.get(name, {})
        possible = lim.get("limit")
        v["possible"] = possible
        v["limit_source"] = lim.get("source", "")
        if possible:
            remaining = max(0, possible - v["consumed"])
            v["remaining"] = remaining
            v["headroom_pct"] = round(remaining / possible * 100)
            wh = _window_hours(lim.get("window") or v.get("window", ""))
            burn = round(v["consumed"] / wh) if wh else 0       # consumed-per-hour, in-window
            safe = round(possible / wh) if wh else 0            # cap-per-hour = steady-state ceiling
            v["window_hours"] = round(wh, 2)
            v["reserve_pct"] = reserve_pct
            v["burn_rate_per_h"] = burn
            v["safe_rate_per_h"] = safe
            v["runway_h"] = round(remaining / burn, 1) if burn > 0 else None  # hrs to 0 at this pace
            pre_health = v.get("health")
            if rl.get(name) or pre_health == "rate-limited":
                v["health"] = "rate-limited"
            elif remaining <= 0:
                v["health"] = "exhausted"
            elif v["headroom_pct"] <= reserve_pct:
                v["health"] = "low"        # at/below reserve → stop with fuel still in the tank
            elif v["headroom_pct"] <= 2 * reserve_pct or burn > safe:
                v["health"] = "throttle"   # still has runway, but pace down / steer work away
            else:
                v["health"] = "ok"
        else:
            v.setdefault("health", "rate-limited" if rl.get(name) else "ok")

    out = {"generated": NOW.isoformat(timespec="seconds"), "vendors": vendors}
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "usage.json").write_text(json.dumps(out, indent=2))
    print(f"usage-telemetry: codex {vendors['codex']['consumed']}tok/5h · "
          f"claude {vendors['claude']['consumed']}tok/5h · jules {vendors['jules']['consumed']}/100 · "
          f"gemini {vendors['gemini']['consumed']} · opencode {vendors['opencode']['consumed']} · agy {vendors['agy']['consumed']}")


if __name__ == "__main__":
    main()
