#!/usr/bin/env python3
"""host-pressure-stale — watch the watcher (sensor 0o).

The VITALS gauge (memory + load axes) is the hand that throttles/sheds under host
pressure; if the gauge itself goes silent, the valve is flying blind and nothing else
notices — the exact failure mode the sensors registry warns about. This rung fails when
the ``sampled_at`` record in ``logs/vigilia/status.json`` (written by the heartbeat's
independent fast wave) misses VITALS_STALE_BEATS declared sample cadences
(x LIMEN_VITALS_SAMPLE_SECONDS), or is absent entirely while
VIGILIA is on (LIMEN_VIGILIA unset counts as on — the heartbeat's own default).

The alarm is the staleness, not the pressure: the effector for pressure itself remains
the existing THROTTLE/SHED path in heartbeat-loop.sh. Exit 0 = gauge alive (or VIGILIA
deliberately off). Exit 1 = gauge silent — and since 2026-07-16 (IF-HOST-PRESSURE
form 4) a silent gauge also fires ONE onset-deduped macOS notification via
scripts/_notify.py: a blind valve was exactly the 7/15 gap, and an advisory line in a
log no one is reading is not an alarm. Read-only otherwise; advisory in the registry.
"""

from __future__ import annotations

import argparse
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


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _stale(message: str, *, read_only: bool) -> int:
    print(message)
    if not read_only:
        _notify.notify_once(_root(), STALE_KEY, message)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="evaluate freshness without notification or dedupe-state writes",
    )
    args = parser.parse_args(argv)
    if os.environ.get("LIMEN_VIGILIA", "1") in ("0", "false", "False"):
        print("host-pressure-stale: VIGILIA off — nothing to watch")
        return 0

    stale_beats = _positive_float("LIMEN_VITALS_STALE_BEATS", 3)
    sample_seconds = _positive_float("LIMEN_VITALS_SAMPLE_SECONDS", 300)
    budget_s = stale_beats * sample_seconds

    status_path = _root() / "logs" / "vigilia" / "status.json"
    if not status_path.exists():
        return _stale(
            f"host-pressure-stale: STALE — {status_path} absent while VIGILIA on",
            read_only=args.read_only,
        )

    try:
        sampled_raw = json.loads(status_path.read_text()).get("sampled_at") or ""
        sampled_at = datetime.fromisoformat(sampled_raw)
        if sampled_at.tzinfo is None:
            sampled_at = sampled_at.replace(tzinfo=timezone.utc)
    except Exception as exc:
        return _stale(
            f"host-pressure-stale: STALE — unreadable sampled_at in {status_path} ({exc})",
            read_only=args.read_only,
        )

    age_s = (datetime.now(timezone.utc) - sampled_at).total_seconds()
    if age_s > budget_s:
        return _stale(
            f"host-pressure-stale: STALE — vitals record is {age_s / 60:.0f} min old "
            f"(budget {budget_s / 60:.0f} min = {stale_beats:g} x LIMEN_VITALS_SAMPLE_SECONDS); "
            "the throttle/shed valve is flying blind",
            read_only=args.read_only,
        )

    if not args.read_only:
        _notify.clear_condition(_root(), STALE_KEY)
    print(f"host-pressure-stale: ok — vitals record {age_s / 60:.1f} min old (budget {budget_s / 60:.0f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
