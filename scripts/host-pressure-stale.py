#!/usr/bin/env python3
"""host-pressure-stale — watch the watcher (sensor 0o).

The VITALS gauge (memory + load axes) is the hand that throttles/sheds under host
pressure; if the gauge itself goes silent, the valve is flying blind and nothing else
notices — the exact failure mode the sensors registry warns about. This rung fails when
the vitals record in ``logs/vigilia/status.json`` (written by ``python3 -m limen.vigilia
beat`` each executive beat) is older than VITALS_STALE_BEATS worst-case beats
(x LIMEN_LOOP_MAX seconds, the heartbeat's adaptive ceiling), or absent entirely while
VIGILIA is on (LIMEN_VIGILIA unset counts as on — the heartbeat's own default).

The alarm is the staleness, not the pressure: the effector for pressure itself remains
the existing THROTTLE/SHED path in heartbeat-loop.sh. Exit 0 = gauge alive (or VIGILIA
deliberately off). Exit 1 = gauge silent — and since 2026-07-16 (IF-HOST-PRESSURE
form 4) a silent gauge also fires ONE onset-deduped macOS notification via
scripts/_notify.py: a blind valve was exactly the 7/15 gap, and an advisory line in a
log no one is reading is not an alarm. Read-only otherwise; advisory in the registry.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _notify  # noqa: E402

STALE_KEY = "vitals-stale"


def _root() -> Path:
    env = os.environ.get("LIMEN_ROOT")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[1]


def _stale(message: str) -> int:
    print(message)
    _notify.notify_once(_root(), STALE_KEY, message)
    return 1


def main() -> int:
    if os.environ.get("LIMEN_VIGILIA", "1") in ("0", "false", "False"):
        print("host-pressure-stale: VIGILIA off — nothing to watch")
        return 0

    stale_beats = float(os.environ.get("LIMEN_VITALS_STALE_BEATS", "3"))
    loop_max = float(os.environ.get("LIMEN_LOOP_MAX", "1800"))
    budget_s = stale_beats * loop_max

    status_path = _root() / "logs" / "vigilia" / "status.json"
    if not status_path.exists():
        return _stale(f"host-pressure-stale: STALE — {status_path} absent while VIGILIA on")

    try:
        ts_raw = json.loads(status_path.read_text()).get("ts") or ""
        ts = datetime.fromisoformat(ts_raw)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except Exception as exc:
        return _stale(f"host-pressure-stale: STALE — unreadable ts in {status_path} ({exc})")

    age_s = (datetime.now(timezone.utc) - ts).total_seconds()
    if age_s > budget_s:
        return _stale(
            f"host-pressure-stale: STALE — vitals record is {age_s / 60:.0f} min old "
            f"(budget {budget_s / 60:.0f} min = {stale_beats:g} x LIMEN_LOOP_MAX); "
            "the throttle/shed valve is flying blind"
        )

    _notify.clear_condition(_root(), STALE_KEY)
    print(f"host-pressure-stale: ok — vitals record {age_s / 60:.1f} min old (budget {budget_s / 60:.0f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
