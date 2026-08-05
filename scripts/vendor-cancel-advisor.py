#!/usr/bin/env python3
"""vendor-cancel-advisor.py — the portable, executable answer to "should we cancel a vendor?".

The recurring category error (docs/plan, memory: use-all-vendors-never-serialize): sessions keep
recommending "cancel codex to save money." That is wrong for this fleet — vendor subs are PARALLEL
CAPACITY POOLS, not duplicate chat apps. A pool that HITS ITS CAPS is the relief valve that carries
the fleet when another pool exhausts; cancelling it cuts capacity, not waste. The real overspend is
Fable-at-cap (a runtime tier, gated by the cap in docs/fable-allotment.md), not vendor count.

This is that verdict as an EXECUTABLE PREDICATE any repo/session can consult instead of re-deriving a
cost-based cut. For each vendor in cli/src/limen/census.py it emits KEEP / CANCEL-CANDIDATE from
UTILIZATION ONLY (rate-limit health + headroom across resets in logs/usage.json) — never sticker cost:

  * Hits its caps / rate-limited / low headroom  → KEEP (relief valve).
  * Persistently IDLE across resets              → CANCEL-CANDIDATE.
  * Unmetered / no utilization signal            → KEEP (no evidence to cut on).

It reads logs/fable-allotment.json and names Fable-at-cap as the binding cost constraint, so "save
money" routes to *cap/plan-gate Fable*, and codex = KEEP. Output: portable JSON + a one-line summary.

Exit non-zero if any "cancel a capped pool" recommendation is ever implied (a self-check that the
predicate never contradicts its own doctrine). READ-ONLY. Never prints a token.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))


def _load_census():
    # Load census from THIS repo tree (the script's own parent), not $LIMEN_ROOT, so the advisor
    # always reflects the vendor register it ships beside.
    path = Path(__file__).resolve().parents[1] / "cli" / "src" / "limen" / "census.py"
    modname = "_limen_census_advisor"
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load census from {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod  # dataclass decorator resolves cls.__module__ via sys.modules
    spec.loader.exec_module(mod)
    return mod


def _load_usage(path_override: str | None) -> dict:
    path = Path(path_override) if path_override else ROOT / "logs" / "usage.json"
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _vendor_usage(usage: dict, name: str) -> dict:
    for container in (usage, usage.get("vendors") or {}):
        if isinstance(container, dict) and isinstance(container.get(name), dict):
            return container[name]
    return {}


def _fable_over_cap() -> dict | None:
    path = os.environ.get("LIMEN_FABLE_BALANCE_PATH") or str(ROOT / "logs" / "fable-allotment.json")
    try:
        data = json.loads(Path(path).read_text())
    except Exception:
        return None
    return data if isinstance(data, dict) else None


# Utilization health signals that mean "this pool is being used / hits its caps" → KEEP.
_BUSY_HEALTH = {"rate-limited", "exhausted", "throttle", "low"}
# Headroom (percent of the pool still free) at/above which, WITH no busy signal, a metered pool
# looks idle. Env-tunable; conservative default (only a nearly-untouched pool is a cancel candidate).
_IDLE_HEADROOM_PCT = float(os.environ.get("LIMEN_VENDOR_IDLE_HEADROOM_PCT", "90"))


def _verdict_for(vendor, usage: dict) -> dict:
    """Utilization-only verdict for one vendor. Never reads sticker cost."""
    name = vendor.name
    u = _vendor_usage(usage, name)
    budget = vendor.budget
    metered = getattr(budget, "window", "none") != "none"

    health = str(u.get("health", "")).lower()
    headroom = u.get("headroom_pct")
    recent_rl = bool(u.get("recent_rate_limit") or u.get("rate_limit_events"))

    # A pool that hits its caps is the relief valve — KEEP, unconditionally.
    if health in _BUSY_HEALTH or recent_rl:
        return {
            "vendor": name,
            "verdict": "KEEP",
            "reason": f"hits its caps / active (health={health or 'active'}) — relief valve, cutting cuts capacity",
            "metered": metered,
        }

    if not metered or not u:
        # No utilization signal to cut on (unmetered floor, issue-assignment lane, or no telemetry).
        return {
            "vendor": name,
            "verdict": "KEEP",
            "reason": "no utilization signal (unmetered/no telemetry) — no evidence to cancel on",
            "metered": metered,
        }

    try:
        hr = float(headroom) if headroom is not None else None
    except (TypeError, ValueError):
        hr = None
    if hr is not None and hr >= _IDLE_HEADROOM_PCT:
        return {
            "vendor": name,
            "verdict": "CANCEL-CANDIDATE",
            "reason": f"persistently idle (headroom {hr:g}% ≥ {_IDLE_HEADROOM_PCT:g}%, no rate-limit health)",
            "metered": metered,
        }
    return {
        "vendor": name,
        "verdict": "KEEP",
        "reason": f"in active use (headroom {hr if hr is not None else 'n/a'}%) — capacity pool",
        "metered": metered,
    }


def advise(usage_path: str | None = None) -> dict:
    census = _load_census()
    usage = _load_usage(usage_path)
    verdicts = [_verdict_for(v, usage) for v in census.VENDORS]

    fable = _fable_over_cap()
    fable_pct = None
    fable_over = False
    if isinstance(fable, dict):
        fable_pct = fable.get("spent_pct")
        fable_over = bool(fable.get("over_cap")) or (
            isinstance(fable_pct, (int, float)) and float(fable_pct) >= float(fable.get("hard_cap", 50) or 50)
        )

    # Self-check: the predicate must never recommend cancelling a pool that hits its caps.
    contradictions = [
        v["vendor"]
        for v in verdicts
        if v["verdict"] == "CANCEL-CANDIDATE"
        and _vendor_usage(usage, v["vendor"]).get("health", "").lower() in _BUSY_HEALTH
    ]

    # codex must always resolve to KEEP (it is the second frontier pool; the memory-canonical answer).
    codex = next((v for v in verdicts if v["vendor"] == "codex"), None)
    codex_keep = bool(codex and codex["verdict"] == "KEEP")

    real_overspend = (
        f"Fable at {fable_pct}% of weekly cap — a RUNTIME tier, not a vendor. Route 'save money' to "
        "capping/plan-gating Fable (docs/fable-allotment.md), NOT to cancelling a capacity pool."
        if fable_over
        else "No vendor is the overspend by utilization; the binding cost constraint is the Fable "
        "runtime tier (cap it via docs/fable-allotment.md), not vendor count."
    )

    cancel = [v["vendor"] for v in verdicts if v["verdict"] == "CANCEL-CANDIDATE"]
    keep = [v["vendor"] for v in verdicts if v["verdict"] == "KEEP"]
    ok = not contradictions and codex_keep
    return {
        "ok": ok,
        "schema": "limen.vendor_cancel_advice.v1",
        "principle": "vendor subs are parallel CAPACITY POOLS; cancel only a pool utilization shows persistently idle; never a pool that hits its caps",
        "real_overspend": real_overspend,
        "fable_over_cap": fable_over,
        "fable_spent_pct": fable_pct,
        "keep": keep,
        "cancel_candidates": cancel,
        "verdicts": verdicts,
        "contradictions": contradictions,
        "codex_keep": codex_keep,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--usage", help="path to a usage.json fixture (default $LIMEN_ROOT/logs/usage.json)")
    ap.add_argument("--json", action="store_true", help="print the machine record")
    args = ap.parse_args(argv)

    report = advise(args.usage)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            f"vendor-cancel-advisor: KEEP={report['keep']} "
            f"CANCEL-CANDIDATE={report['cancel_candidates']} | {report['real_overspend']}"
        )
        if report["contradictions"]:
            print(f"  CONTRADICTION: would cancel a capped pool: {report['contradictions']}", file=sys.stderr)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
