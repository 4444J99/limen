#!/usr/bin/env python3
"""claude-usage.py — resolve Claude's live usage gauge from a CASCADE of avenues.

Claude (unlike Codex) writes no usage percent to disk, and its OAuth token is a race-prone
self-healing Keychain credential the fleet deliberately does NOT hold (the "login flap").
So no single source is reliable — any one silently rots into a forgettable hole (a dead
proxy, a parked token, a stale log) and the gauge reads "all clear" right before a blowout.

The fix is the cascade ruleset: try MULTIPLE avenues, ranked best-first, each fail-open, each
carrying a freshness stamp so a stale avenue is visibly SKIPPED rather than silently trusted.
The resolver returns the first fresh, usable reading AND the full audit trail of every avenue
it tried — so a silently-failing source shows up as `ok=false, note="stale 3h"`, never a hole.
If ALL avenues fail, it returns trust="unknown" with no percent → the controller must then read
Claude PESSIMISTICALLY (shed early), never optimistically.

Avenues, best → worst:
  1. proxy      logs/anthropic-ratelimit.json — anthropic-ratelimit-* headers captured from the
                claude calls the fleet ALREADY makes (a fail-open logging proxy). Truest, zero new auth.
  2. poll       one authed usage call — ONLY when a sanctioned ENV token is present and LIMEN_CLAUDE_POLL=1
                (daemon-set). Never reads the Keychain; off by default so it can't worsen the login-flap race.
  3. ondisk     CALIBRATED windowed cost — weighted token sum from the transcripts the fleet already
                writes (~/.claude/projects), over the real 5h/7d windows, ÷ a cap DERIVED from a one-time
                /status calibration. Zero auth, live numerator; dark until calibrated, expires if stale.
  4. counts     the transcript token sum usage-telemetry already maintains (logs/usage.json) vs a weekly
                cap (env LIMEN_CLAUDE_WEEKLY_TOKENS, else plan-tier default). Zero auth, always available.
  5. reactive   a recent real 429 in logs/usage.json health → treat as exhausted (100%). Last-resort hard stop.

READ-ONLY w.r.t. tasks.yaml; writes ONLY logs/claude-usage.json. Never prints a token.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
NOW = time.time()

# Freshness ceiling: an avenue older than this is SKIPPED (the anti-"forgettable-hole" guard).
FRESH_CEIL_S = float(os.environ.get("LIMEN_CLAUDE_GAUGE_FRESH_S", "1800"))  # 30 min

# ── on-disk calibrated gauge (avenue 2) ───────────────────────────────────────
# Window sizes for the two Claude rate limits (parity with codex primary/secondary).
_SESSION_WIN_S = 5 * 3600
_WEEKLY_WIN_S = 7 * 86400
# Weighted token cost. NOT the exact vendor meter (unknowable) — only needs to be MONOTONE with real
# usage so a one-time /status calibration can absorb the constant factor. Cache reads are cheap, output
# dear; these mirror the published price ratios closely enough to preserve ordering as the mix shifts.
_W_INPUT, _W_OUTPUT, _W_CACHE_READ, _W_CACHE_CREATION = 1.0, 5.0, 0.1, 1.25
# Calibration ageing: a cap derived from a /status reading is trusted while fresh, then decays, then
# EXPIRES — so a stale denominator can never silently read "all clear" (the whole point of the rebuild).
CAL_FRESH_DAYS = 7.0
CAL_STALE_DAYS = 30.0


def _transcripts_dir() -> Path:
    return Path(os.environ.get("LIMEN_CLAUDE_TRANSCRIPTS_DIR", str(Path.home() / ".claude" / "projects")))


def _cal_path() -> Path:
    return ROOT / "logs" / "claude-usage-calibration.json"


def _iso_ts(s: str) -> float | None:
    try:
        from datetime import datetime

        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _weighted_cost_windows() -> dict | None:
    """Sum weighted token cost from the Claude Code transcripts the fleet already writes, into the
    5h (session) and 7d (weekly) windows. Bounded by file mtime so the per-beat scan stays cheap.
    Fail-open: returns {'session','weekly','files'} or None on any error."""
    import glob

    root = _transcripts_dir()
    if not root.exists():
        return None
    session = weekly = 0.0
    files = 0
    try:
        for f in glob.glob(str(root / "**" / "*.jsonl"), recursive=True):
            try:
                if NOW - os.path.getmtime(f) > _WEEKLY_WIN_S:
                    continue
            except OSError:
                continue
            files += 1
            for line in open(f, errors="ignore"):
                if '"usage"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                ts = _iso_ts(o.get("timestamp", "")) if o.get("timestamp") else None
                if ts is None:
                    continue
                age = NOW - ts
                if age > _WEEKLY_WIN_S:
                    continue
                u = (o.get("message") or {}).get("usage") or o.get("usage")
                if not isinstance(u, dict):
                    continue
                w = (
                    _W_INPUT * (u.get("input_tokens", 0) or 0)
                    + _W_OUTPUT * (u.get("output_tokens", 0) or 0)
                    + _W_CACHE_READ * (u.get("cache_read_input_tokens", 0) or 0)
                    + _W_CACHE_CREATION * (u.get("cache_creation_input_tokens", 0) or 0)
                )
                weekly += w
                if age <= _SESSION_WIN_S:
                    session += w
        return {"session": session, "weekly": weekly, "files": files}
    except Exception:
        return None


def _read_calibration() -> dict | None:
    p = _cal_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _fresh(ts: float | None) -> float | None:
    """Seconds since ts (a POSIX time); None if unknown."""
    if ts is None:
        return None
    return max(0.0, NOW - float(ts))


def _reading(avenue, used_percent, window, trust, fresh_s, note=""):
    return {"avenue": avenue, "used_percent": used_percent, "window": window,
            "trust": trust, "fresh_s": fresh_s, "note": note}


# ── avenue 1: proxy header capture ────────────────────────────────────────────
def av_proxy() -> dict:
    p = ROOT / "logs" / "anthropic-ratelimit.json"
    if not p.exists():
        return _reading("proxy", None, None, None, None, "no capture file yet")
    try:
        d = json.loads(p.read_text())
    except Exception as e:
        return _reading("proxy", None, None, None, None, f"unreadable: {type(e).__name__}")
    fresh = _fresh(d.get("captured_at") or p.stat().st_mtime)
    if fresh is not None and fresh > FRESH_CEIL_S:
        return _reading("proxy", None, None, None, fresh, f"STALE ({int(fresh)}s) — skipped")
    # accept a normalized {weekly:{used_percent}} or raw unified headers
    wk = (d.get("weekly") or {}).get("used_percent")
    if wk is None:
        wk = d.get("unified_weekly_used_percent")
    if wk is None:
        return _reading("proxy", None, None, None, fresh, "captured but no weekly field")
    return _reading("proxy", float(wk), "weekly", "measured", fresh, "vendor headers")


# ── avenue 2: calibrated on-disk windowed cost (zero auth, live numerator) ─────
def av_ondisk() -> dict:
    """Claude writes no rate_limits to disk, but it DOES write per-call token counts to every
    transcript. Sum a weighted cost over the real 5h/7d windows and divide by a cap DERIVED from a
    one-time /status calibration (cap = cost_at_obs / pct_at_obs). The numerator is recomputed live
    each beat; only the cap ages. Dark until calibrated — never a fabricated denominator."""
    cal = _read_calibration()
    if not cal:
        return _reading("ondisk", None, None, None, None, "no calibration yet (seed via --calibrate from /status)")
    obs = cal.get("observed_at")
    cal_age = _fresh(obs) if obs else None
    cal_age_days = (cal_age / 86400) if cal_age is not None else None
    if cal_age_days is not None and cal_age_days > CAL_STALE_DAYS:
        return _reading("ondisk", None, None, None, cal_age, f"calibration {cal_age_days:.0f}d old — EXPIRED, re-observe /status")
    win = _weighted_cost_windows()
    if not win:
        return _reading("ondisk", None, None, None, None, "no transcripts to measure")
    binding_pct = None
    binding_win = None
    detail = []
    for key, label in (("session", "session"), ("weekly", "weekly")):
        c = cal.get(key) or {}
        cost0, pct0 = c.get("cost"), c.get("pct")
        if not (isinstance(cost0, (int, float)) and isinstance(pct0, (int, float)) and pct0 > 0 and cost0 > 0):
            continue
        cap = cost0 / (pct0 / 100.0)
        pct = round(100 * win.get(key, 0.0) / cap, 1)
        detail.append(f"{label} {pct:g}%")
        if binding_pct is None or pct > binding_pct:  # the tighter window is the one that bites
            binding_pct, binding_win = pct, label
    if binding_pct is None:
        return _reading("ondisk", None, None, None, cal_age, "calibration present but no usable window")
    trust = "calibrated" if (cal_age_days is None or cal_age_days <= CAL_FRESH_DAYS) else "estimate"
    age_note = f" (cal {cal_age_days:.1f}d old)" if cal_age_days is not None else ""
    return _reading("ondisk", binding_pct, binding_win, trust, cal_age, ", ".join(detail) + age_note)


# ── avenue 3: active poll (guarded; never Keychain, off by default) ───────────
def av_poll() -> dict:
    if os.environ.get("LIMEN_CLAUDE_POLL") != "1":
        return _reading("poll", None, None, None, None, "disabled (LIMEN_CLAUDE_POLL!=1)")
    tok = next((os.environ[k] for k in (
        "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_AUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN",
        "LIMEN_CLAUDE_AUTH_TOKEN") if os.environ.get(k)), None)
    if not tok:
        return _reading("poll", None, None, None, None, "no sanctioned env token")
    try:
        import urllib.request
        body = json.dumps({"model": "claude-haiku-4-5-20251001", "max_tokens": 1,
                           "messages": [{"role": "user", "content": "."}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST")
        req.add_header("authorization", f"Bearer {tok}")
        req.add_header("anthropic-version", "2023-06-01")
        req.add_header("anthropic-beta", "oauth-2025-04-20")
        req.add_header("content-type", "application/json")
        import urllib.error
        try:
            resp = urllib.request.urlopen(req, timeout=20)
            hdrs = dict(resp.headers)
        except urllib.error.HTTPError as e:
            hdrs = dict(e.headers or {})
        wk = None
        for k, v in hdrs.items():
            kl = k.lower()
            if "ratelimit" in kl and ("week" in kl or "7d" in kl or "seven" in kl) and "remaining" in kl:
                # remaining → used_percent needs the limit; best-effort if a paired limit exists
                lim = hdrs.get(k.replace("remaining", "limit")) or hdrs.get(k.replace("remaining", "Limit"))
                try:
                    if lim and float(lim) > 0:
                        wk = round(100 * (1 - float(v) / float(lim)), 1)
                except Exception:
                    pass
        if wk is None:
            return _reading("poll", None, None, None, 0.0, "call ok but no weekly header parsed")
        return _reading("poll", wk, "weekly", "measured", 0.0, "live authed headers")
    except Exception as e:  # fail-open, never crash the beat
        return _reading("poll", None, None, None, None, f"poll failed: {type(e).__name__}")


# ── avenue 4: transcript token counts vs cap (zero auth, always available) ─────
def av_counts() -> dict:
    p = ROOT / "logs" / "usage.json"
    if not p.exists():
        return _reading("counts", None, None, None, None, "no usage.json")
    try:
        d = json.loads(p.read_text())
    except Exception as e:
        return _reading("counts", None, None, None, None, f"unreadable: {type(e).__name__}")
    entry = None
    if isinstance(d, dict):
        entry = d.get("claude") or (d.get("vendors") or {}).get("claude")
    if not isinstance(entry, dict):
        return _reading("counts", None, None, None, None, "no claude entry")
    fresh = _fresh(d.get("updated_at_ts") or p.stat().st_mtime)
    if fresh is not None and fresh > FRESH_CEIL_S:
        return _reading("counts", None, None, None, fresh, f"STALE ({int(fresh)}s) — skipped")
    used = next((entry[k] for k in ("consumed", "billable", "spent", "used_tokens", "tokens")
                 if isinstance(entry.get(k), (int, float))), None)
    if used is None:
        return _reading("counts", None, None, None, fresh, "no token count field")
    # Cap precedence: an explicit human cap (real) → the fleet's own `possible` (don't mint a NEW
    # number). trust reflects the cap's provenance, never fabricated here.
    cap_env = os.environ.get("LIMEN_CLAUDE_WEEKLY_TOKENS")
    if cap_env and cap_env.isdigit():
        cap, trust, src = int(cap_env), "proxy", "env cap"  # real numerator + human-set cap
    else:
        cap = next((entry[k] for k in ("possible", "limit") if isinstance(entry.get(k), (int, float))), None)
        est = "estimate" in str(entry.get("limit_source", "")).lower()
        trust, src = ("estimate" if est else "measured"), f"usage.json {'ESTIMATE' if est else ''} cap"
    if not cap:
        return _reading("counts", None, None, None, fresh, f"{int(used):,} tok but no cap to divide by")
    pct = round(100 * used / cap, 1)
    return _reading("counts", pct, str(entry.get("window", "5h")), trust, fresh, f"{int(used):,}/{int(cap):,} ({src})")


# ── avenue 5: reactive 429 (last-resort hard stop) ────────────────────────────
def av_reactive() -> dict:
    p = ROOT / "logs" / "usage.json"
    if not p.exists():
        return _reading("reactive", None, None, None, None, "no usage.json")
    try:
        d = json.loads(p.read_text())
        entry = d.get("claude") or (d.get("vendors") or {}).get("claude") or {}
    except Exception:
        return _reading("reactive", None, None, None, None, "unreadable")
    health = str(entry.get("health", "")).lower()
    if health in ("rate-limited", "exhausted"):
        return _reading("reactive", 100.0, "now", "measured", 0.0, f"health={health}")
    return _reading("reactive", None, None, None, None, f"health={health or 'unknown'} (no 429)")


AVENUES = [av_proxy, av_poll, av_ondisk, av_counts, av_reactive]


def calibrate(session_pct: float, weekly_pct: float) -> dict:
    """Anchor the on-disk gauge to a real /status reading: measure the current windowed cost NOW and
    store it beside the observed percent. The daemon then recomputes the numerator each beat and
    divides by cap = cost/pct — so this ONE observation frees the human from ever pasting again until
    it ages out. Zero-credential, opportunistic: any fresh /status (his, or a future authed poll) re-seeds."""
    win = _weighted_cost_windows()
    if not win:
        raise SystemExit("cannot calibrate: no transcripts found to measure current cost")
    cal = {
        "observed_at": NOW,
        "session": {"cost": win["session"], "pct": float(session_pct)},
        "weekly": {"cost": win["weekly"], "pct": float(weekly_pct)},
        "note": "cap = cost / (pct/100); numerator recomputed live each beat from transcripts",
    }
    p = _cal_path()
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(cal, indent=2))
    return cal


def resolve() -> dict:
    """Run every avenue best-first; the first with a usable used_percent wins. Always keep the
    full trail so a silently-dead avenue is VISIBLE, not forgotten."""
    trail = []
    resolved = None
    for fn in AVENUES:
        r = fn()
        trail.append(r)
        if resolved is None and r.get("used_percent") is not None:
            resolved = r
    if resolved is None:
        # every avenue dark → UNKNOWN, force conservative reading downstream
        return {"lane": "claude", "resolved": None, "trust": "unknown",
                "used_percent": None, "avenue": None, "avenues": trail,
                "note": "ALL avenues dark → read Claude pessimistically (shed early)"}
    return {"lane": "claude", "resolved": resolved, "trust": resolved["trust"],
            "used_percent": resolved["used_percent"], "avenue": resolved["avenue"],
            "avenues": trail}


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve Claude's usage gauge from a cascade of avenues.")
    ap.add_argument("--json", action="store_true", help="print the machine record")
    ap.add_argument("--no-write", action="store_true", help="don't write logs/claude-usage.json")
    ap.add_argument("--calibrate", nargs=2, metavar=("SESSION_PCT", "WEEKLY_PCT"), type=float,
                    help="anchor the on-disk gauge to a /status reading (the two percentages), then exit")
    args = ap.parse_args()
    if args.calibrate:
        cal = calibrate(args.calibrate[0], args.calibrate[1])
        print(f"calibrated: session {cal['session']['pct']:g}% ↔ {cal['session']['cost']:,.0f} cost, "
              f"weekly {cal['weekly']['pct']:g}% ↔ {cal['weekly']['cost']:,.0f} cost → {_cal_path()}")
        return 0
    report = resolve()
    if not args.no_write:
        try:
            out = ROOT / "logs" / "claude-usage.json"
            out.parent.mkdir(exist_ok=True)
            out.write_text(json.dumps({**report, "captured_at": NOW}, indent=2))
        except Exception:
            pass
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        r = report.get("resolved")
        head = f"claude gauge: {r['used_percent']:g}% via avenue={r['avenue']} trust={r['trust']}" if r \
            else "claude gauge: UNKNOWN — all avenues dark → shed early"
        print(head)
        for a in report["avenues"]:
            mark = "→" if r and a["avenue"] == r["avenue"] else " "
            pct = "" if a["used_percent"] is None else f"{a['used_percent']:g}%"
            print(f"  {mark} {a['avenue']:<9} {pct:<7} {a['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
