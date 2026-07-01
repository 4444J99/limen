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
  2. ondisk     any Claude-native rate_limits on disk (parity with codex's rate_limits; not present today).
  3. poll       one authed usage call — ONLY when a sanctioned ENV token is present and LIMEN_CLAUDE_POLL=1
                (daemon-set). Never reads the Keychain; off by default so it can't worsen the login-flap race.
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


# ── avenue 2: on-disk rate_limits (codex parity; not present for claude today) ─
def av_ondisk() -> dict:
    return _reading("ondisk", None, None, None, None, "claude writes no rate_limits to disk")


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


AVENUES = [av_proxy, av_ondisk, av_poll, av_counts, av_reactive]


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
    args = ap.parse_args()
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
