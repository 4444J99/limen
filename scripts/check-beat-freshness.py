#!/usr/bin/env python3
"""Compatibility predicate for the retired resident heartbeat.

Freshness now comes from immutable content digests in ``limen observe --once`` receipts.
This check fails when a legacy heartbeat process is still resident and otherwise passes.
"""

from __future__ import annotations

import os
import subprocess


def _resident_pids() -> list[int]:
    result = subprocess.run(
        ["pgrep", "-f", "scripts/heartbeat-loop.sh"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return [int(value) for value in result.stdout.split() if value.isdigit()]


def main() -> int:
    if os.environ.get("LIMEN_BEAT_FRESHNESS", "1") == "0":
        print("  beat-freshness: gated off (LIMEN_BEAT_FRESHNESS=0) — skip")
        return 0
    pids = _resident_pids()
    if pids:
        print("  beat-freshness: FAIL — retired heartbeat descendants remain; run domus-limen-runtime retire-heartbeat")
        return 1
    print("  beat-freshness: OK — heartbeat retired; observer receipts carry content digests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
