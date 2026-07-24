#!/usr/bin/env python3
"""usage-telemetry.py — emit REAL per-vendor usage (not fictional run-counts).

Each vendor exposes a different truth (see BACKLOG.md vendor table); this reads the best
available real signal and writes logs/usage.json for board.py + the portal:
  codex   — sum total_tokens from ~/.codex/sessions/*.jsonl in the 5h rolling window
  claude  — sum usage tokens from ~/.claude/projects/**/*.jsonl in the 5h window
  jules   — dispatch count today vs 100 (the one true proxy; rolling 24h)
  gemini  — dispatch count today vs RPD-ish cap + last rate-limit event
  opencode — opencode-clock token meter when present, else dispatch count today
  agy      — dispatch count today + last rate-limit event (no readable meter)

READ-ONLY w.r.t. tasks.yaml (writes ONLY logs/usage.json) → never races the daemon.
"""

import argparse
import datetime
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
CLI_SRC = ROOT / "cli" / "src"
if CLI_SRC.is_dir() and str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

try:
    import yaml
except ModuleNotFoundError:  # launchd/cron may resolve a Python without PyYAML
    yaml = None

try:  # the metered vendor rows DERIVE from the census register (the single vendor umbrella)
    from limen import census as _census  # launchd may resolve a Python without the package
except Exception:  # pragma: no cover - import-fallback exercised only off the installed fleet
    _census = None

try:
    from limen.provider_health import (
        load_provider_outcomes as _load_provider_outcomes,
        project_provider_health as _project_provider_health,
        provider_health_policy as _provider_health_policy,
        provider_outcome_ledger_path as _provider_outcome_ledger_path,
    )
except Exception:  # pragma: no cover - installed fleet may briefly precede this module
    _load_provider_outcomes = None
    _project_provider_health = None
    _provider_health_policy = None
    _provider_outcome_ledger_path = None

HOME = Path.home()
NOW = datetime.datetime.now(datetime.timezone.utc)
W5H = NOW - datetime.timedelta(hours=5)
TODAY = NOW.date().isoformat()
_IN = re.compile(r'"input_tokens"\s*:\s*(\d+)')
_OUT = re.compile(r'"output_tokens"\s*:\s*(\d+)')


def _number_or_default(value, default=0):
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed) or parsed < 0:
        return default
    return int(parsed) if parsed.is_integer() else parsed


def _percent_or_default(value, default):
    parsed = _number_or_default(value, default)
    if parsed > 100:
        return default
    return parsed


# A rate-limit gate must come from a REAL, RECENT 429 — never from text that merely MENTIONS
# rate limits (a planning session discussing "rate limit" / "429" must not bench a lane). And it
# must auto-expire: a lane is only "rate-limited" while a real event sits inside this cooldown,
# then it heals on its own. Override via env LIMEN_RL_COOLDOWN_MIN. ([[no-never-happens-again]])
COOLDOWN_MIN = _number_or_default(os.environ.get("LIMEN_RL_COOLDOWN_MIN", "30"), 30)
RL_COOLDOWN = NOW - datetime.timedelta(minutes=COOLDOWN_MIN)


def _parse_ts(value) -> "datetime.datetime | None":
    """Parse an ISO-ish timestamp into an aware UTC datetime; None if unparseable."""
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except (ValueError, TypeError):
        return None


# tunable per-vendor LIMITS (the "amount possible"). The metered-lane rows DERIVE from the census
# register (cli/src/limen/census.py — the single vendor umbrella) rather than being re-typed here:
# each vendor's Budget is the "means" half of the census. The filter is principled — a lane with a
# real metering window (Budget.window != "none") is exactly the dispatchable metered set
# (codex/claude/opencode/agy/gemini/jules); the unmetered floor (ollama), issue-assignment
# (copilot), paid-service (warp/oz) and CI (github_actions) carry window="none" and are not
# usage-metered. Calibrate a real cap to your plan (codex/claude: see each CLI's /status) via
# logs/usage-limits.json or env LIMEN_<VENDOR>_LIMIT.
#
# `trust` is MACHINE-READABLE so a controller can read an untrusted cap PESSIMISTICALLY
# instead of optimistically (an estimate cap the size of 100M tokens otherwise looks like
# infinite headroom → a lane never sheds early → the pre-condition of a usage-window
# blowout). measured = a real known cap; estimate = a placeholder to tune to the plan;
# unmodeled = we don't have the number yet. `pool` links lanes that draw on ONE
# subscription window (the claude-cli lane, the Claude app, and interactive Claude Code all
# spend the SAME Claude plan; codex-cli + the ChatGPT app spend the SAME OpenAI plan) — a
# pool's real cap belongs on `pool_cap` once discovered. Extra keys here are ignored by the
# existing consumers (all use .get()); scripts/verify-budget-gauge.py audits them.


def _budget_row(b) -> dict:
    """Project a census Budget dataclass onto the historical usage-limits row shape. `pool` is
    omitted when None so a derived row is byte-for-byte the hand-typed one it replaces."""
    row = {"limit": b.limit, "unit": b.unit, "window": b.window, "source": b.source, "trust": b.trust}
    if getattr(b, "pool", None) is not None:
        row["pool"] = b.pool
    return row


def _census_vendor_limits():
    """The metered vendor rows, DERIVED from the census register. None when `limen` isn't importable
    (launchd may resolve a Python without the package) → the drift-guarded fallback is used."""
    if _census is None:
        return None
    try:
        return {name: _budget_row(b) for name, b in _census.budgets().items() if b.window != "none"}
    except Exception:  # pragma: no cover - defensive; census is pure-stdlib
        return None


# Drift-guarded FALLBACK for the metered vendor rows — used ONLY when `limen` isn't importable.
# Kept byte-for-byte in lockstep with census.budgets() (window != "none") by
# test_census::test_usage_telemetry_limits_derive_from_census, so it can never silently diverge
# from the umbrella (the same pattern that guards dispatch._LANE_CASCADE).
_FALLBACK_VENDOR_LIMITS = {
    "codex": {
        "limit": 100_000_000,
        "unit": "tokens",
        "window": "5h rolling",
        "source": "ESTIMATE - tune to plan (/status)",
        "trust": "estimate",
        "pool": "openai-plan",
    },
    "claude": {
        "limit": 100_000_000,
        "unit": "tokens",
        "window": "5h rolling",
        "source": "ESTIMATE - tune to plan (/status)",
        "trust": "estimate",
        "pool": "claude-plan",
    },
    "opencode": {
        "limit": 100,
        "unit": "runs",
        "window": "today",
        "source": "operator board cap until live vendor meter",
        "trust": "calibrated",
    },
    "agy": {
        "limit": 100,
        "unit": "runs",
        "window": "today",
        "source": "operator board cap until live vendor meter",
        "trust": "calibrated",
    },
    "gemini": {
        "limit": 10,
        "unit": "runs",
        "window": "24h",
        "source": "operator board cap until live vendor meter",
        "trust": "calibrated",
    },
    "jules": {"limit": 100, "unit": "runs", "window": "24h", "source": "known hard cap", "trust": "measured"},
}

# App-plane allotments share the same paid subscriptions as the CLI pools, but they are not
# dispatchable lanes (no Vendor record). Model the plane explicitly so budget audits do not
# pretend it is absent.
_APP_PLANE_LIMITS = {
    "chatgpt-app": {
        "plane": "app",
        "unit": "app-runs",
        "window": "168h",
        "source": "modeled app-plane; cap unavailable locally",
        "trust": "modeled",
        "pool": "openai-plan",
    },
    "claude-app": {
        "plane": "app",
        "unit": "app-runs",
        "window": "168h",
        "source": "modeled app-plane; cap unavailable locally",
        "trust": "modeled",
        "pool": "claude-plan",
    },
}

_DEFAULT_LIMITS = {**(_census_vendor_limits() or _FALLBACK_VENDOR_LIMITS), **_APP_PLANE_LIMITS}


# Hold back this % of every cap so a live lane is paced-OUT before it hits 0 — the
# "never run out" reserve. Override via env LIMEN_RESERVE_PCT or a top-level
# "reserve_pct" key in logs/usage-limits.json.
_DEFAULT_RESERVE_PCT = 15.0

# The reserve is only useful EARLY in a window (don't bottom out mid-cycle); near a reset it is pure
# waste — the budget refills to full anyway, so headroom held back just EXPIRES. So the EFFECTIVE
# reserve decays from the full reserve early in the window down to this hard floor near the reset:
# we recover the otherwise-wasted headroom while still never cutting a task off at zero. Logic, not a
# pinned cap. Override via env LIMEN_RESERVE_FLOOR_PCT.
_DEFAULT_RESERVE_FLOOR_PCT = 5.0


def load_reserve_floor_pct():
    env = os.environ.get("LIMEN_RESERVE_FLOOR_PCT")
    if env:
        return _percent_or_default(env, _DEFAULT_RESERVE_FLOOR_PCT)
    path = ROOT / "logs" / "usage-limits.json"
    if path.exists():
        try:
            v = json.loads(path.read_text()).get("reserve_floor_pct")
            if v is not None:
                return _percent_or_default(v, _DEFAULT_RESERVE_FLOOR_PCT)
        except Exception:
            pass
    return _DEFAULT_RESERVE_FLOOR_PCT


def _time_left_frac(agent: str, reset_map: dict, window_hours: float) -> float:
    """Fraction of the agent's budget window still remaining, from the dispatcher's per-agent reset
    timestamp (track.per_agent_reset). 1.0 = just reset, 0.0 = at the cliff. Unknown → 1.0 (treat as
    fresh, keep the full reserve — never under-reserve on missing data)."""
    last_iso = reset_map.get(agent)
    if not last_iso or not window_hours:
        return 1.0
    last = _parse_ts(last_iso)
    if last is None:
        return 1.0
    elapsed_h = max(0.0, (NOW - last).total_seconds() / 3600.0)
    return max(0.0, min(1.0, (window_hours - elapsed_h) / window_hours))


def _effective_reserve(reserve_pct: float, floor_pct: float, time_left_frac: float) -> float:
    """Linear decay of the reserve across the window: full reserve at the start, floor near the
    cliff. floor is clamped to ≤ reserve so a tiny reserve never INFLATES near a reset."""
    floor = min(floor_pct, reserve_pct)
    return round(floor + (reserve_pct - floor) * time_left_frac, 2)


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
        return _percent_or_default(env, _DEFAULT_RESERVE_PCT)
    path = ROOT / "logs" / "usage-limits.json"
    if path.exists():
        try:
            v = json.loads(path.read_text()).get("reserve_pct")
            if v is not None:
                return _percent_or_default(v, _DEFAULT_RESERVE_PCT)
        except Exception:
            pass
    return _DEFAULT_RESERVE_PCT


def _window_hours(window: str) -> float:
    """Refresh-window length in hours, parsed from the human label telemetry already carries:
    "5h"/"5h rolling" → 5, "24h"/"rolling 24h" → 24, "today" → hours left in the UTC day."""
    window = str(window or "")
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
    gated = False
    try:
        if base.exists():
            with os.scandir(base):  # explicit probe — TCC/permission denial raises HERE
                pass  # (rglob silently skips unreadable dirs, so it can't detect it)
            for f in base.rglob("*.jsonl"):
                if not _recent(f):
                    continue
                sessions += 1
                try:
                    txt = f.read_text(errors="ignore")
                    mi = max([int(x) for x in _IN.findall(txt)] or [0])  # cumulative → max ≈ session total
                    mo = max([int(x) for x in _OUT.findall(txt)] or [0])
                    total += mi + mo  # billable (input+output), excludes cached
                except (PermissionError, OSError):
                    gated = True  # macOS TCC denied this app-data file — skip, don't crash
                except Exception:
                    pass
    except (PermissionError, OSError):
        # macOS TCC ("access data from other apps") denied the whole ~/.codex scan. Treat usage as
        # UNKNOWN, not zero — and unknown ⇒ HEALTHY (real headroom), never bench. ([[meter-lie-and-dead-daemon-incident]])
        gated = True
    if gated:
        return {
            "signal": "tokens",
            "window": "5h rolling",
            "consumed": total,
            "unit": "tokens",
            "sessions": sessions,
            "health": "ok",
            "tcc_gated": True,
            "note": "codex usage source TCC-gated — assuming healthy; grant FDA to read ~/.codex",
        }
    return {
        "signal": "tokens",
        "window": "5h rolling",
        "consumed": total,
        "unit": "tokens",
        "sessions": sessions,
        "health": "ok",
        "note": "billable codex tokens (input+output, 5h)",
    }


def codex_live_rate_limits() -> dict:
    """Read Codex's vendor-reported rate-limit gauge from the newest session stream."""
    base = HOME / ".codex" / "sessions"
    try:
        files = [p for p in base.rglob("rollout-*.jsonl") if p.is_file()]
    except OSError:
        return {}
    if not files:
        return {}
    newest = max(files, key=lambda p: p.stat().st_mtime)
    last: dict = {}
    try:
        for line in newest.read_text(encoding="utf-8", errors="ignore").splitlines():
            if '"rate_limits"' not in line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
            rate_limits = info.get("rate_limits") or payload.get("rate_limits")
            if isinstance(rate_limits, dict):
                last = rate_limits
    except OSError:
        return {}
    return last


def codex_vendor_gauge() -> dict | None:
    """Return a percent-based Codex gauge when the vendor exposes one; otherwise None."""
    rate_limits = codex_live_rate_limits()
    primary = rate_limits.get("primary") if isinstance(rate_limits.get("primary"), dict) else {}
    used = primary.get("used_percent")
    if used is None:
        return None
    try:
        used_pct = float(used)
    except (TypeError, ValueError):
        return None
    window_minutes = primary.get("window_minutes")
    try:
        window_hours = max(1.0, float(window_minutes) / 60.0) if window_minutes else 5.0
    except (TypeError, ValueError):
        window_hours = 5.0
    secondary = rate_limits.get("secondary") if isinstance(rate_limits.get("secondary"), dict) else {}
    return {
        "signal": "vendor-rate-limit",
        "window": f"{window_hours:g}h rolling",
        "consumed": used_pct,
        "unit": "percent",
        "health": "ok",
        "note": "vendor-reported Codex rate-limit gauge",
        "plan_type": rate_limits.get("plan_type"),
        "resets_at": primary.get("resets_at"),
        "weekly_used_percent": secondary.get("used_percent"),
        "weekly_resets_at": secondary.get("resets_at"),
    }


def claude_5h():
    base = HOME / ".claude" / "projects"
    total = msgs = rate_limit_events = 0
    recent_rl = False
    gated = False
    try:
        if base.exists():
            with os.scandir(base):  # explicit probe — TCC/permission denial raises HERE
                pass  # (rglob silently skips unreadable dirs, so it can't detect it)
            _it = base.rglob("*.jsonl")
        else:
            _it = []
    except (PermissionError, OSError):
        _it, gated = [], True  # TCC denied the ~/.claude scan — unknown ⇒ healthy, never bench
    if not gated:
        for f in _it:
            if not _recent(f):
                continue
            try:
                for ln in f.read_text(errors="ignore").splitlines():
                    try:
                        row = json.loads(ln)
                    except Exception:
                        continue
                    # ONLY a structured API rate_limit error counts — never free-text that merely
                    # mentions "rate limit"/"429" (a transcript discussing limits is not a 429).
                    ts = _parse_ts(row.get("timestamp"))
                    if row.get("error") == "rate_limit" or (
                        isinstance(row.get("error"), dict) and row["error"].get("type") == "rate_limit_error"
                    ):
                        rate_limit_events += 1
                        if ts is None or ts >= RL_COOLDOWN:  # recent (or undated → treat as recent)
                            recent_rl = True
                    u = (row.get("message", {}) or {}).get("usage")
                    if not u:
                        continue
                    if ts is not None and ts < W5H:
                        continue
                    total += (
                        u.get("input_tokens", 0) + u.get("output_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                    )  # billable; exclude cheap cache_read
                    msgs += 1
            except (PermissionError, OSError):
                gated = True  # macOS TCC denied this app-data file — skip, don't crash
            except Exception:
                pass
    if gated:
        return {
            "signal": "tokens",
            "window": "5h rolling",
            "consumed": total,
            "unit": "tokens",
            "messages": msgs,
            "health": "ok",
            "tcc_gated": True,
            "rate_limit_events": rate_limit_events,
            "recent_rate_limit": recent_rl,
            "note": "claude usage source TCC-gated — assuming healthy; grant FDA to read ~/.claude",
        }
    return {
        "signal": "tokens",
        "window": "5h rolling",
        "consumed": total,
        "unit": "tokens",
        "messages": msgs,
        "health": "rate-limited" if recent_rl else "ok",
        "rate_limit_events": rate_limit_events,
        "recent_rate_limit": recent_rl,
        "note": "billable claude tokens (in+out+cache-create, excl cache-read, 5h)",
    }


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
    """Lanes with a RECENT rate-limit marker in the heartbeat log. Time-boxed: a one-time
    historical 'RATE-LIMIT <lane>' must NOT bench a lane forever. We bound recency by the log
    TAIL (the last few beats' worth of lines) so the gate auto-expires as the log advances —
    a lane with full headroom and no fresh marker is never gated. ([[no-never-happens-again]])"""
    log = ROOT / "logs" / "heartbeat.out.log"
    out = {}
    if log.exists():
        try:
            tail_lines = int(os.environ.get("LIMEN_RL_TAIL_LINES", "400"))
            lines = log.read_text(errors="ignore").splitlines()[-tail_lines:]
            for ln in lines:
                m = re.search(r"RATE-LIMIT (\w+)", ln)
                if m:
                    out[m.group(1)] = "recent"
        except Exception:
            pass
    return out


def _read_opencode_clock() -> dict | None:
    """Read opencode's internal clock state if available."""
    path = HOME / ".local/share/opencode/clock.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return None
    return None


def _provider_outcome_projection() -> dict:
    if not all(
        (
            _load_provider_outcomes,
            _project_provider_health,
            _provider_health_policy,
            _provider_outcome_ledger_path,
        )
    ):
        return {}
    try:
        snapshot = _project_provider_health(
            _load_provider_outcomes(_provider_outcome_ledger_path()),
            _provider_health_policy(),
            now=NOW,
        )
    except Exception:
        return {}
    entries = [*snapshot.providers.values(), *snapshot.models.values()]
    last_success = max((entry.last_success for entry in entries if entry.last_success), default=None)
    last_failure = max(
        (entry.last_terminal_failure for entry in entries if entry.last_terminal_failure),
        default=None,
    )
    cooldown_expiry = max((entry.cooldown_until for entry in entries if entry.cooldown_until), default=None)
    blocked = [entry for entry in entries if entry.blocked(NOW)]
    return {
        "provider_outcome_health": "degraded" if blocked else "ok",
        "provider_cooldown_count": len(blocked),
        "provider_last_success": last_success.isoformat() if last_success else None,
        "provider_last_terminal_failure": last_failure.isoformat() if last_failure else None,
        "provider_cooldown_expiry": cooldown_expiry.isoformat() if cooldown_expiry else None,
        "provider_health_snapshot_hash": snapshot.snapshot_hash(),
    }


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Emit real per-vendor usage telemetry to logs/usage.json.")
    return parser.parse_args(argv)


def main(argv=None):
    # Parse before touching runtime state so informational CLI actions such as --help are
    # side-effect free. A no-argument invocation retains the historical write behavior.
    _parse_args(argv)
    data = load_tasks_data()
    tasks = data.get("tasks", [])
    budget = (data.get("portal") or {}).get("budget") or {}
    reset_map = (budget.get("track") or {}).get("per_agent_reset", {}) or {}
    dc = dispatch_counts(tasks)
    rl = last_ratelimit()
    limits = load_limits()

    vendors = {
        "codex": codex_5h(),
        "claude": claude_5h(),
        # consumed from the LIVE dispatch-log count (today), like gemini/agy — never the persisted
        # per_agent accumulator, whose stale value deadlocked the lane (a full counter + a reset that
        # only persists on a beat that dispatches → jules gated to remaining=0 forever). [[no-never-happens-again]]
        "jules": {
            "signal": "dispatch-count",
            "window": "rolling 24h",
            "consumed": dc.get("jules", 0),
            "unit": "runs",
            "note": "live dispatch count today vs cap — no stale accumulator",
        },
    }
    codex_vendor = codex_vendor_gauge()
    if codex_vendor is not None:
        vendors["codex"].update(codex_vendor)
    for v in ("gemini", "agy"):
        vendors[v] = {
            "signal": "dispatch-count",
            "window": "today",
            "consumed": dc.get(v, 0),
            "unit": "runs",
            "note": "no readable meter — dispatch count + rate-limit watch",
        }

    # opencode: prefer its internal DB meter (clock.json) over dispatch counting.
    # The SQLite DB tracks real token consumption per session, giving us a live
    # token-level clock instead of a blind run count.
    oc_clock = _read_opencode_clock()
    if oc_clock is not None:
        consumed = _number_or_default(oc_clock.get("heavy_used"), 0) + _number_or_default(
            oc_clock.get("cache_read_used"), 0
        )
        cap = _number_or_default(oc_clock.get("cap_tokens"), 0)
        note = "real token usage from opencode internal clock (SQLite DB)"
        vendors["opencode"] = {
            "signal": "db-meter",
            "window": "today",
            "consumed": consumed,
            "unit": "tokens",
            "possible": cap,
            "note": note,
            "health": oc_clock.get("health", "ok"),
            "clock_used_pct": _number_or_default(oc_clock.get("used_pct"), 0),
        }
    else:
        vendors["opencode"] = {
            "signal": "dispatch-count",
            "window": "today",
            "consumed": dc.get("opencode", 0),
            "unit": "runs",
            "note": "no readable meter — dispatch count + rate-limit watch",
        }
    vendors["opencode"].update(_provider_outcome_projection())

    # attach the "amount POSSIBLE" → headroom + the refresh-window PACING math for every vendor.
    # The split decision: never run a live lane to 0. Burning faster than safe_rate_per_h
    # (cap / window) will exhaust the window; staying at-or-below it self-refreshes forever.
    reserve_pct = load_reserve_pct()
    reserve_floor = load_reserve_floor_pct()
    for name, v in vendors.items():
        lim = limits.get(name, {})
        # db-meter vendors (opencode) report real token consumption; use token_limit as possible.
        if v.get("signal") == "db-meter":
            possible = lim.get("token_limit") or v.get("possible")
        elif v.get("signal") == "vendor-rate-limit":
            possible = 100
        else:
            possible = lim.get("limit")
        possible = _number_or_default(possible, 0)
        v["consumed"] = _number_or_default(v.get("consumed"), 0)
        v["possible"] = possible
        v["limit_source"] = "vendor rate_limits" if v.get("signal") == "vendor-rate-limit" else lim.get("source", "")
        if possible:
            remaining = max(0, possible - v["consumed"])
            v["remaining"] = remaining
            v["headroom_pct"] = round(remaining / possible * 100)
            window_label = (
                v.get("window", "")
                if v.get("signal") == "vendor-rate-limit"
                else lim.get("window") or v.get("window", "")
            )
            wh = _window_hours(window_label)
            burn = round(v["consumed"] / wh) if wh else 0  # consumed-per-hour, in-window
            safe = round(possible / wh) if wh else 0  # cap-per-hour = steady-state ceiling
            v["window_hours"] = round(wh, 2)
            # the EFFECTIVE reserve decays toward the floor as this lane nears its reset, so headroom
            # that would just expire is spent instead — while a task in flight is never cut off at 0.
            tlf = _time_left_frac(name, reset_map, wh)
            eff_reserve = _effective_reserve(reserve_pct, reserve_floor, tlf)
            v["reserve_pct"] = reserve_pct
            v["time_left_frac"] = round(tlf, 3)
            v["effective_reserve_pct"] = eff_reserve
            v["burn_rate_per_h"] = burn
            v["safe_rate_per_h"] = safe
            v["runway_h"] = round(remaining / burn, 1) if burn > 0 else None  # hrs to 0 at this pace
            # FRONT-LOAD signal: budget that will EXPIRE unused if the lane keeps pacing evenly =
            # how far its unspent fraction outruns its time-left fraction, in raw units. >0 ⇒ the
            # accelerator should burn this before the reset wipes it. (headroom held for the floor
            # is excluded — that part is meant to survive to the reset.)
            headroom_frac = v["headroom_pct"] / 100.0
            v["required_rate_per_h"] = round(remaining / (wh * tlf), 1) if (wh and tlf > 0) else None
            v["will_expire"] = round(max(0.0, (headroom_frac - tlf - eff_reserve / 100.0)) * possible)
            pre_health = v.get("health")
            # A lane is hard-DOWN only on a real, recent 429 (rl marker is now tail-bounded; the
            # claude structured-error check is cooldown-bounded). Everything else is paced, not
            # benched. THE INVARIANT: real headroom + no recent 429 ⇒ never gated. ([[no-never-happens-again]])
            recent_rl = bool(rl.get(name)) or v.get("recent_rate_limit") or pre_health == "rate-limited"
            healthy_headroom = v["headroom_pct"] > 2 * eff_reserve
            if recent_rl:
                v["health"] = "rate-limited"
            elif healthy_headroom:
                v["health"] = "ok"  # INVARIANT: cannot bench a lane that has real headroom
            elif v.get("signal") == "tokens":
                # token "consumed" is LOCAL transcript spend (incl. the interactive session), NOT the
                # vendor's true remaining budget — it can never PROVE a lane is down. Pace-down hint
                # only; hard-down needs a real 429. So a bad/low cap can't falsely exhaust the lane.
                v["health"] = "throttle" if (v["headroom_pct"] <= 0 or burn > safe) else "ok"
            elif remaining <= 0:
                v["health"] = "exhausted"  # count lanes: real dispatch count hit the real cap
            elif v["headroom_pct"] <= eff_reserve:
                v["health"] = "low"  # at/below the (decaying) reserve → stop, fuel still in tank
            else:
                v["health"] = "throttle"  # in (reserve, 2*reserve] or burn>safe → pace down, still up
        else:
            recent_rl = bool(rl.get(name)) or v.get("recent_rate_limit")
            v.setdefault("health", "rate-limited" if recent_rl else "ok")

    out = {"generated": NOW.isoformat(timespec="seconds"), "vendors": vendors}
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "usage.json").write_text(json.dumps(out, indent=2))
    codex_suffix = "%" if vendors["codex"].get("unit") == "percent" else "tok"
    print(
        f"usage-telemetry: codex {vendors['codex']['consumed']}{codex_suffix}/5h · "
        f"claude {vendors['claude']['consumed']}tok/5h · jules {vendors['jules']['consumed']}/100 · "
        f"gemini {vendors['gemini']['consumed']} · opencode {vendors['opencode']['consumed']} · agy {vendors['agy']['consumed']}"
    )
    gated = [n for n, v in vendors.items() if v.get("tcc_gated")]
    if gated:
        print(
            f"  usage: {','.join(gated)} source TCC-gated (assuming healthy) — "
            f"grant Full Disk Access to the daemon python to silence the macOS prompt"
        )
    # front-load visibility: which lanes will lose budget at their reset if pacing stays even, so the
    # accelerator's job is visible on screen (and on omni.html) instead of inferred.
    accel_on = os.environ.get("LIMEN_ACCEL", "1") == "1"
    expiring = sorted(
        ((n, v) for n, v in vendors.items() if v.get("will_expire")), key=lambda kv: -kv[1]["will_expire"]
    )
    if expiring:
        parts = [
            f"{n} ~{v['will_expire']}{('tok' if v.get('unit') == 'tokens' else '')}"
            f"@{round((v.get('time_left_frac') or 0) * (v.get('window_hours') or 0), 1)}h"
            for n, v in expiring[:6]
        ]
        print(f"  front-load [{'ON' if accel_on else 'OFF'}]: would-expire {' · '.join(parts)}")


if __name__ == "__main__":
    main()
