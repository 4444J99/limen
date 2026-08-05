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
import subprocess
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
USAGE = LOGS / "usage.json"
TASKS = Path(os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
STATE = LOGS / ".conducting-report-state.json"


def _load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _notify_macos(title, msg):
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "{msg.replace(chr(34), chr(39))}" with title "{title}"'],
                       capture_output=True, timeout=10)
    except Exception:
        pass


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


def build_report() -> tuple[str, str, str]:
    """Returns (headline, full_text, day_key)."""
    usage = _load(USAGE, {}) or {}
    vendors = usage.get("vendors", {})
    day = (usage.get("generated", "") or datetime.now().isoformat())[:10]
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
        headline = f"IDLED — {idle} lane(s) sat at a full tank (no routable work)"
    else:
        headline = f"partial — {burned}/{len(lines)} lanes burned"
    if disc:
        headline += f"; {disc} repos in value-discovery"
    # the credit side: did the spend earn its keep? (the "was it worth my money?" answer)
    value = _value_verdict()
    body = f"Conducting report {day}\n{headline}\n"
    if value:
        body += f"  value: {value}\n"
    body += "\n".join(lines)
    return headline, body, day


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
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="emit now even if already sent today")
    ap.add_argument("--print", dest="print_only", action="store_true", help="print only; no push")
    ap.add_argument("--census", action="store_true", help="print counts-only public census JSON")
    args = ap.parse_args()
    if args.census:
        print(json.dumps(census(), indent=2, sort_keys=True))
        return 0

    headline, body, day = build_report()
    print(body)
    if args.print_only:
        return 0

    state = _load(STATE, {})
    if not args.force and state.get("last_day") == day:
        return 0  # already reported for this usage-day

    _notify_macos("Limen — conducting", headline)
    _notify_ntfy("Limen — conducting", body)
    try:
        STATE.write_text(json.dumps({"last_day": day, "headline": headline}))
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
