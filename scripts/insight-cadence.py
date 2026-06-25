#!/usr/bin/env python3
"""insight-cadence — the insight producer organ.

DRAFTS insight reports at FOUR wall-clock cadences (hourly/daily/weekly/monthly)
by aggregating existing signal files READ-ONLY. The insight reports land in
logs/insight-cadence/ as JSON and markdown digest. Idempotent per tier per window.

PROPOSAL-ONLY and READ-ONLY on every signal — never mutates tasks.yaml or any source.

Usage:
  python3 scripts/insight-cadence.py            # run due tiers (proposal mode)
  python3 scripts/insight-cadence.py --once     # run due tiers once and exit
  python3 scripts/insight-cadence.py --dry-run  # print what would be produced
  python3 scripts/insight-cadence.py --force-tier hourly  # force a specific tier
"""

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
STATE_PATH = LOGS / "insight-cadence-state.json"
HEALTH_PATH = LOGS / "insight-cadence-health.json"
OUT_DIR = LOGS / "insight-cadence"

TIER_SECONDS = {"hourly": 3600, "daily": 86400, "weekly": 604800, "monthly": 2592000}

TIER_SCOPES = {
    "hourly": "fresh anomalies — stale organs, exhausted vendors, live failures",
    "daily": "digest — summary of the day's signals across all sources",
    "weekly": "trends — recurring patterns, spending drift, lane health over the week",
    "monthly": "strategic rollup — overall system health, worst sinks, revenue attribution gaps",
}


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).isoformat(timespec="seconds")


def _parse_ts(v):
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _load_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default if default is not None else {}


def _load_jsonl(path):
    out = []
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, p)


def _stamp_health():
    try:
        LOGS.mkdir(exist_ok=True)
        HEALTH_PATH.write_text(
            json.dumps({"timestamp": _iso(), "organ": "insight-cadence"}) + "\n"
        )
    except OSError:
        pass


def due_tiers(state, now, force=None):
    if force:
        return [force] if force in TIER_SECONDS else []
    last = (state or {}).get("last_run", {})
    due = []
    for tier, span in TIER_SECONDS.items():
        prev = _parse_ts(last.get(tier))
        if prev is None or (now - prev).total_seconds() >= span:
            due.append(tier)
    return due


def _owner_from_source(source, key):
    if source == "organ-health":
        return key if "/" in key else f"scripts/{key}"
    if source == "usage":
        m = {"codex": "organvm/codex", "claude": "organvm/claude", "jules": "organvm/jules",
             "gemini": "organvm/gemini", "opencode": "organvm/opencode", "agy": "organvm/agy"}
        return m.get(key, f"scripts/{key}")
    if source == "ledger":
        return key if key and "/" in key else "organvm/limen"
    if source == "self-improve":
        return f"scripts/{key}" if key else "scripts/self-improve.py"
    if source == "censor-decisions":
        return key if key and "/" in key else "scripts/censor.py"
    if source == "dispatch_log":
        return f"scripts/{key}" if key else "scripts/dispatch-parallel.py"
    return "scripts/insight-cadence.py"


def _severity_from_age(age_h, expected_h):
    if age_h is None or expected_h is None or expected_h <= 0:
        return "medium"
    ratio = age_h / expected_h
    if ratio >= 5:
        return "critical"
    if ratio >= 3:
        return "high"
    if ratio >= 1.5:
        return "medium"
    return "low"


def aggregate_hourly():
    insights = []
    health = _load_json(LOGS / "organ-health.json", {})
    for o in health.get("organs", []):
        status = o.get("status")
        if status in ("stale", "down"):
            key = o.get("key", "?")
            age_h = o.get("age_h")
            expected_h = o.get("expected_h")
            insights.append({
                "id": f"OH-{key}-{_iso(_now())[:13]}",
                "severity": _severity_from_age(age_h, expected_h),
                "title": f"{status} organ: {key}",
                "detail": f"Organ '{key}' is {status} (age={age_h}h, expected={expected_h}h). "
                          f"Last fired: {o.get('last_fired', 'never')}.",
                "owner": _owner_from_source("organ-health", key),
                "source": str(LOGS / "organ-health.json"),
                "suggested_action": f"Investigate why {key} has not fired within its expected cadence.",
                "healable": True,
            })
    usage = _load_json(LOGS / "usage.json", {})
    for vname, vdata in usage.get("vendors", {}).items():
        hp = vdata.get("headroom_pct")
        health_status = vdata.get("health")
        if hp is not None and hp <= 0:
            insights.append({
                "id": f"USG-{vname}-{_iso(_now())[:13]}",
                "severity": "high" if health_status in ("rate-limited", "throttle") else "medium",
                "title": f"vendor exhausted: {vname}",
                "detail": f"Vendor '{vname}' has 0% headroom (health={health_status}). "
                          f"Consumed {vdata.get('consumed', '?')} / {vdata.get('possible', '?')} "
                          f"in the current window.",
                "owner": _owner_from_source("usage", vname),
                "source": str(LOGS / "usage.json"),
                "suggested_action": f"Consider reducing dispatch to {vname} or increasing the budget.",
                "healable": True,
            })
        elif health_status in ("rate-limited", "throttle"):
            insights.append({
                "id": f"USG-{vname}-rate-{_iso(_now())[:13]}",
                "severity": "high",
                "title": f"rate-limited vendor: {vname}",
                "detail": f"Vendor '{vname}' is {health_status} with {hp}% headroom.",
                "owner": _owner_from_source("usage", vname),
                "source": str(LOGS / "usage.json"),
                "suggested_action": f"Throttle dispatch to {vname} until it recovers.",
                "healable": True,
            })
    return insights


def aggregate_daily():
    insights = aggregate_hourly()
    censor_decisions = _load_jsonl(LOGS / "censor-decisions.jsonl")
    if censor_decisions:
        recent = [d for d in censor_decisions if 1 < len(censor_decisions) < 50]
        recent = recent[-20:] if not recent else censor_decisions[-20:]
        for d in recent:
            sig = d.get("signal", {})
            verdict = d.get("verdict", {})
            insights.append({
                "id": f"CEN-{uuid.uuid4().hex[:8]}",
                "severity": "low" if verdict.get("disposition") == "auto" else "medium",
                "title": f"censor decision: {sig.get('type', '?')} -> {verdict.get('branch', '?')}",
                "detail": f"Signal '{sig.get('subject', '?')}' → {verdict.get('disposition', '?')} "
                          f"({verdict.get('rationale', '?')}) · outcome={d.get('outcome', 'pending')}",
                "owner": _owner_from_source("censor-decisions", sig.get("subject", "")),
                "source": str(LOGS / "censor-decisions.jsonl"),
                "suggested_action": f"Review {verdict.get('disposition', 'pending')} signal if unresolved.",
                "healable": verdict.get("disposition") != "surface",
            })
    si = _load_json(LOGS / "self-improve-proposal.json", {})
    for adj in si.get("lane_adjustments", []):
        if adj.get("verdict") in ("down-weight", "low-sample"):
            insights.append({
                "id": f"SI-adj-{adj.get('lane', '?')}-{_iso(_now())[:13]}",
                "severity": "medium",
                "title": f"lane adjustment: {adj.get('lane')} → {adj.get('verdict')}",
                "detail": f"Lane '{adj.get('lane')}' adjusted to weight {adj.get('target_weight')}: "
                          f"{adj.get('reason', '')}",
                "owner": _owner_from_source("self-improve", adj.get("lane", "")),
                "source": str(LOGS / "self-improve-proposal.json"),
                "suggested_action": f"Keep weight at {adj.get('target_weight')} and re-evaluate next cycle.",
                "healable": True,
            })
    for rk in si.get("rerank", []):
        if rk.get("move") == "deprioritise":
            insights.append({
                "id": f"SI-rk-{rk.get('pattern', '?')}-{_iso(_now())[:13]}",
                "severity": "low",
                "title": f"deprioritised pattern: {rk.get('pattern')}",
                "detail": f"Pattern '{rk.get('pattern')}' deprioritised: {rk.get('reason', '')}",
                "owner": "scripts/self-improve.py",
                "source": str(LOGS / "self-improve-proposal.json"),
                "suggested_action": "Monitor if this pattern recovers before restoring priority.",
                "healable": True,
            })
    return insights


def aggregate_weekly():
    insights = aggregate_daily()
    ledger = _load_json(LOGS / "ledger.json", {})
    for lane_name, lane_data in ledger.get("lanes", {}).items():
        sr = lane_data.get("success_rate", 0)
        if sr is not None and sr < 0.3:
            insights.append({
                "id": f"LED-lane-{lane_name}-{_iso(_now())[:7]}",
                "severity": "high" if sr < 0.15 else "medium",
                "title": f"low success lane: {lane_name} ({sr:.0%})",
                "detail": f"Lane '{lane_name}' has {sr:.0%} success rate "
                          f"({lane_data.get('tasks', 0)} tasks, "
                          f"{lane_data.get('wasted', 0)} wasted, "
                          f"cost/shipped={lane_data.get('cost_per_shipped', 'N/A')}).",
                "owner": _owner_from_source("ledger", lane_name),
                "source": str(LOGS / "ledger.json"),
                "suggested_action": f"Re-route work away from {lane_name} or investigate root cause.",
                "healable": True,
            })
    worst = ledger.get("worst_sink")
    if worst:
        insights.append({
            "id": "LED-sink-weekly",
            "severity": "high",
            "title": f"worst sink: {worst}",
            "detail": f"'{worst}' is the highest waste repo this period.",
            "owner": _owner_from_source("ledger", worst),
            "source": str(LOGS / "ledger.json"),
            "suggested_action": "Audit wasted tasks on this repo and adjust priority or retire.",
            "healable": True,
        })
    return insights


def aggregate_monthly():
    insights = aggregate_weekly()
    ledger = _load_json(LOGS / "ledger.json", {})
    totals = ledger.get("totals", {})
    sr = totals.get("success_rate", 0)
    spent = totals.get("spent", 0)
    sunk = totals.get("sunk", 0)
    shipped = totals.get("worth_it", 0)
    net = ledger.get("net", "unknown")
    insights.append({
        "id": "LED-strategic-rollup",
        "severity": "medium" if sr >= 0.4 else "high",
        "title": f"strategic rollup: net {net} (shipped={shipped}, spent={spent}, sunk={sunk})",
        "detail": f"Over {totals.get('tasks', 0)} tasks: {sr:.0%} success rate, "
                  f"{sunk} sunk runs worth {ledger.get('worst_sink', '?')}. "
                  f"Cost per shipped: {totals.get('cost_per_shipped', 'N/A')}.",
        "owner": "organvm/limen",
        "source": str(LOGS / "ledger.json"),
        "suggested_action": "Continue rebalancing lanes away from waste sinks. "
                            "Prioritize revenue-attributed repos.",
        "healable": True,
    })
    revenue = ledger.get("revenue_attribution", [])
    for r in revenue:
        wasted = r.get("wasted", 0)
        if wasted > 10:
            insights.append({
                "id": f"LED-rev-{r.get('repo', '?')[:20]}",
                "severity": "medium",
                "title": f"waste on revenue repo: {r.get('repo')}",
                "detail": f"Product '{r.get('product')}' spent {r.get('spent', 0)} "
                          f"with {wasted} wasted ({r.get('shipped', 0)} shipped).",
                "owner": _owner_from_source("ledger", r.get("repo", "")),
                "source": str(LOGS / "ledger.json"),
                "suggested_action": "Triage wasted tasks on this revenue repo.",
                "healable": True,
            })
    return insights


_AGGREGATORS = {
    "hourly": aggregate_hourly,
    "daily": aggregate_daily,
    "weekly": aggregate_weekly,
    "monthly": aggregate_monthly,
}


def window_start_for(tier, now):
    span = TIER_SECONDS.get(tier, 3600)
    return _iso(datetime.fromtimestamp((now.timestamp() // span) * span, tz=timezone.utc))


def produce(tier, state, dry_run):
    now = _now()
    ws = window_start_for(tier, now)
    insights = _AGGREGATORS[tier]()
    report = {
        "tier": tier,
        "generated_at": _iso(now),
        "window_start": ws,
        "insights": insights,
    }
    if dry_run:
        print(f"[insight-cadence] dry-run: tier={tier} -> {len(insights)} insights")
        for ins in insights:
            print(f"  [{ins['severity']:>8}] {ins['title']} (owner={ins['owner']})")
        return report

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%S")
    json_path = OUT_DIR / f"{tier}-{stamp}.json"
    _atomic_write(json_path, json.dumps(report, indent=2))
    markdown = _render_markdown(report)
    md_path = OUT_DIR / f"{tier}-latest.md"
    _atomic_write(md_path, markdown)
    print(f"[insight-cadence] wrote {json_path} ({len(insights)} insights)")
    return report


def _render_markdown(report):
    lines = [
        f"# Insight Cadence: {report['tier']}",
        f"**Generated at:** {report['generated_at']}",
        f"**Window start:** {report['window_start']}",
        f"**Scope:** {TIER_SCOPES.get(report['tier'], '')}",
        "",
        f"**{len(report['insights'])} insights**",
        "",
    ]
    if not report["insights"]:
        lines.append("_No insights this window._")
    else:
        for ins in report["insights"]:
            lines.append(f"### [{ins['severity'].upper()}] {ins['title']}")
            lines.append(f"**Owner:** {ins['owner']}  ")
            lines.append(f"**Source:** {ins['source']}  ")
            lines.append(f"**Healable:** {ins['healable']}  ")
            lines.append("")
            lines.append(ins.get("detail", ""))
            lines.append("")
            if ins.get("suggested_action"):
                lines.append(f"> Suggested: {ins['suggested_action']}")
            lines.append("---")
            lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="insight-cadence — the insight producer organ")
    ap.add_argument("--once", action="store_true", help="run due tiers once and exit")
    ap.add_argument("--dry-run", action="store_true", help="print what would be produced without writing")
    ap.add_argument("--force-tier", choices=list(TIER_SECONDS), help="force a specific tier")
    args = ap.parse_args()

    state = _load_json(STATE_PATH, {})
    now = _now()
    tiers = [args.force_tier] if args.force_tier else due_tiers(state, now)

    if not tiers:
        print("[insight-cadence] no tiers due")
        _stamp_health()
        return 0

    print(f"[insight-cadence] tiers due: {tiers} · {'dry-run' if args.dry_run else 'live'}")
    for tier in tiers:
        produce(tier, state, dry_run=args.dry_run)
        if not args.dry_run:
            state.setdefault("last_run", {})[tier] = _iso(now)

    if not args.dry_run:
        _atomic_write(STATE_PATH, json.dumps(state, indent=2))
    _stamp_health()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
