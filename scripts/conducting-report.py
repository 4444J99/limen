#!/usr/bin/env python3
"""conducting-report — the answer to "did it use all the usage overnight?" arrives BEFORE you ask.

Once a day this distills logs/usage.json into a per-vendor verdict — consumed vs the safe steady-state
rate vs the reserve floor — and a one-line headline: did the fleet conduct at FULL FORCE (burned each
window toward the reserve drops) or did it IDLE at a full tank (and why)? It also counts how many repos
got value-discovery work. Delivery is CASCADED (never-"NO"): a local macOS notification AND, if
LIMEN_NTFY_TOPIC is set, an ntfy.sh push to your phone. Idempotent: fires at most once per day (tracks
logs/.conducting-report-state.json); --force re-emits now. Fail-open: a missing/torn feed prints what it
can and never crashes the beat. Read-only on the fleet's data; writes only its own state file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _notify import notify

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
USAGE = LOGS / "usage.json"
TASKS = Path(os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
STATE = LOGS / ".conducting-report-state.json"
HANDOFF = LOGS / "handoff.json"
CONTINUITY = LOGS / "dispatch-continuity.json"
ROUTING_REASONS = frozenset(
    {"routable", "admission_blocked", "capacity_blocked", "auth_blocked", "keeper_unavailable"}
)
TELEMETRY_MAX_AGE_SECONDS = 5400


def _load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _notify_macos(title, msg):
    notify(ROOT, msg, title=title)


def _notify_ntfy(title, msg):
    topic = os.environ.get("LIMEN_NTFY_TOPIC")
    if not topic:
        return
    base = os.environ.get("LIMEN_NTFY_URL", "https://ntfy.sh").rstrip("/")
    try:
        req = urllib.request.Request(f"{base}/{topic}", data=msg.encode("utf-8"),
                                     headers={"Title": title, "Tags": "battery"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def _fresh_timestamp(payload: object, instant: datetime) -> bool:
    if not isinstance(payload, dict):
        return False
    generated = _parse_timestamp(payload.get("generated") or payload.get("generated_at"))
    if generated is None:
        return False
    age = (instant.astimezone(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= TELEMETRY_MAX_AGE_SECONDS


def _safe_count(value: object) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _continuity_summary(instant: datetime) -> str:
    payload = _load(CONTINUITY, {})
    if not _fresh_timestamp(payload, instant):
        return "continuity unavailable or stale"
    lanes = payload.get("lanes") if isinstance(payload, dict) else None
    if not isinstance(lanes, dict):
        return "continuity unavailable"
    counts: dict[str, int] = {}
    for row in lanes.values():
        if not isinstance(row, dict):
            continue
        verdict = str(row.get("verdict") or "unknown")
        counts[verdict] = counts.get(verdict, 0) + 1
    return "continuity " + ", ".join(f"{key}={counts[key]}" for key in sorted(counts))


def _routing_reason(now: datetime | None = None) -> tuple[str, str]:
    """Classify routing from keeper-owned admission, never from vendor consumption."""
    handoff = _load(HANDOFF, None)
    if not isinstance(handoff, dict):
        return "keeper_unavailable", "handoff missing or unreadable"
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    if not _fresh_timestamp(handoff, instant):
        return "keeper_unavailable", "handoff missing a fresh keeper timestamp"

    admission = handoff.get("dispatch_admission")
    if not isinstance(admission, dict) or admission.get("schema_version") != "limen.dispatch_admission.v1":
        return "keeper_unavailable", "canonical dispatch admission unavailable"

    provider_headroom = handoff.get("provider_headroom")
    if not _fresh_timestamp(provider_headroom, instant):
        return "keeper_unavailable", "provider-headroom telemetry unavailable or stale"

    admissible = _safe_count(admission.get("admissible"))
    open_considered = _safe_count(admission.get("open_considered"))
    continuity = _continuity_summary(instant)
    if admissible > 0 or admission.get("dispatchable_next"):
        return "routable", f"admissible={admissible}; {continuity}"

    reasons = admission.get("reason_counts")
    reasons = reasons if isinstance(reasons, dict) else {}
    active_reasons = {str(key): _safe_count(value) for key, value in reasons.items() if _safe_count(value)}
    reason_keys = {key.lower() for key in active_reasons}
    explicit_auth_block = any("auth" in key or "credential" in key for key in reason_keys)
    provider_health_block = "provider_health" in reason_keys

    vendors = provider_headroom.get("vendors", {}) if isinstance(provider_headroom, dict) else {}
    provider_states = {
        str(row.get("health") or row.get("state") or row.get("status") or "").lower().replace("-", "_")
        for row in vendors.values()
        if isinstance(row, dict)
    }
    if explicit_auth_block or provider_health_block and provider_states & {
        "auth_needed",
        "auth_blocked",
        "unauthenticated",
    }:
        reason = "auth_blocked"
    else:
        capacity_keys = {"budget_global", "budget_agent", "provider_health", "capacity"}
        reason = "capacity_blocked" if reason_keys and reason_keys <= capacity_keys else "admission_blocked"
    detail = f"open={open_considered}; gates=" + (
        ",".join(f"{key}={active_reasons[key]}" for key in sorted(active_reasons))
        if active_reasons
        else "board_empty"
    )
    return reason, f"{detail}; {continuity}"

def _local_day(now: datetime | None = None) -> str:
    """Daily dedupe follows the host's local calendar, not a UTC usage timestamp."""
    instant = now or datetime.now().astimezone()
    return instant.date().isoformat()


def _value_verdict() -> str | None:
    """The ledger's net value verdict (worth-it vs sunk money). Fail-open to None — so the burn
    report still fires even before the ledger has scored anything."""
    rep = _load(LOGS / "ledger.json", {})
    if isinstance(rep, dict) and rep.get("verdict"):
        return str(rep["verdict"])
    return None


def _discovery_count() -> int:
    """Open value-discovery tasks (cheap YAML scan; fail-open to 0)."""
    try:
        import yaml
        data = yaml.safe_load(TASKS.read_text()) or {}
        tasks = data.get("tasks", []) if isinstance(data, dict) else (data or [])
        return sum(1 for t in tasks if isinstance(t, dict)
                   and t.get("status") == "open" and str(t.get("id", "")).startswith("DISCOVER-"))
    except Exception:
        return 0


def _verdict(v: dict) -> tuple[str, bool]:
    """One-line per-vendor verdict + whether this vendor was 'burned' (consumed past half its window)."""
    hr = v.get("headroom_pct")
    reserve = v.get("reserve_pct", 15)
    consumed = v.get("consumed", 0)
    burn = v.get("burn_rate_per_h", 0)
    safe = v.get("safe_rate_per_h", 0)
    if hr is None:
        return ("usage unknown (meter source unreadable — assuming healthy)", False)
    used_pct = 100 - hr
    if hr <= reserve + 5:
        return (f"burned {used_pct}% — down to the reserve drops ✓", True)
    if consumed == 0:
        return (f"IDLE — full tank, 0 consumed (headroom {hr}%)", False)
    pace = f"{burn:,}/h vs safe {safe:,}/h" if safe else f"{burn:,}/h"
    return (f"used {used_pct}% (headroom {hr}%, pace {pace})", used_pct >= 50)


def build_report() -> tuple[str, str, str, str]:
    """Returns (headline, full_text, local_day_key, canonical_routing_reason)."""
    usage = _load(USAGE, {}) or {}
    vendors = usage.get("vendors", {})
    day = _local_day()
    routing_reason, routing_detail = _routing_reason()
    lines, burned, idle = [], 0, 0
    for name in sorted(vendors):
        v = vendors[name]
        if not isinstance(v, dict):
            continue
        verdict, was_burned = _verdict(v)
        if was_burned:
            burned += 1
        elif "IDLE" in verdict:
            idle += 1
        lines.append(f"  {name:9} {verdict}")
    disc = _discovery_count()
    tracked = burned + idle
    if tracked and burned >= max(1, tracked - 1):
        headline = f"FULL FORCE — {burned}/{len(lines)} lanes burned to the drops"
    elif idle:
        if routing_reason == "routable":
            headline = f"ROUTABLE WORK EXISTS — fleet admission is open while {idle} lane(s) are idle"
        else:
            headline = f"IDLED — {idle} lane(s) sat at a full tank ({routing_reason})"
    else:
        headline = f"partial — {burned}/{len(lines)} lanes burned"
    if disc:
        headline += f"; {disc} repos in value-discovery"
    # the credit side: did the spend earn its keep? (the "was it worth my money?" answer)
    value = _value_verdict()
    body = f"Conducting report {day}\n{headline}\n  routing: {routing_reason} — {routing_detail}\n"
    if value:
        body += f"  value: {value}\n"
    body += "\n".join(lines)
    return headline, body, day, routing_reason


def census() -> dict:
    """Counts-only public census for report liveness; no vendor names, task titles, or headlines."""
    usage = _load(USAGE, {}) or {}
    vendors = usage.get("vendors", {}) if isinstance(usage, dict) else {}
    vendor_rows = [row for row in vendors.values() if isinstance(row, dict)] if isinstance(vendors, dict) else []
    verdicts = [_verdict(row) for row in vendor_rows]
    return {
        "usage_present": USAGE.exists(),
        "vendor_count": len(vendor_rows),
        "vendors_with_headroom": sum(1 for row in vendor_rows if row.get("headroom_pct") is not None),
        "vendors_burned": sum(1 for _verdict_text, burned in verdicts if burned),
        "vendors_idle": sum(1 for verdict_text, _burned in verdicts if "IDLE" in verdict_text),
        "value_verdict_present": _value_verdict() is not None,
        "open_value_discovery": _discovery_count(),
        "state_present": STATE.exists(),
        "routing_reason": _routing_reason()[0],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="emit now even if already sent today")
    ap.add_argument("--print", dest="print_only", action="store_true", help="print only; no push")
    ap.add_argument("--census", action="store_true", help="print counts-only public census JSON")
    args = ap.parse_args(argv)
    if args.census:
        print(json.dumps(census(), indent=2, sort_keys=True))
        return 0

    headline, body, day, routing_reason = build_report()
    print(body)
    if args.print_only:
        return 0

    usage = _load(USAGE, {})
    instant = datetime.now(timezone.utc)
    if not _fresh_timestamp(usage, instant):
        print("conducting-report: usage telemetry unavailable or stale; delivery withheld")
        return 0
    usage_generated = str(usage.get("generated") or usage.get("generated_at"))

    state = _load(STATE, {})
    if not args.force and state.get("last_day") == day:
        return 0  # already reported for this fresh local-day snapshot

    _notify_macos("Limen — conducting", headline)
    _notify_ntfy("Limen — conducting", body)
    try:
        STATE.write_text(
            json.dumps(
                {
                    "last_day": day,
                    "usage_generated": usage_generated,
                    "headline": headline,
                    "routing_reason": routing_reason,
                }
            )
        )
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
