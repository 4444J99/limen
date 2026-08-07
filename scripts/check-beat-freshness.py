#!/usr/bin/env python3
"""Beat freshness — the resident daemon must be newer than the loop body it runs.

The 2026-08-06 -> 08-07 lesson: seven flywheel PRs merged, the governor self-restored,
every wire was connected — and zero dispatch happened for 18 more hours, because
`scripts/heartbeat-loop.sh` is a resident `while true` under launchd KeepAlive that
never re-execs, and the running process predated the merged loop body by three days.
Bash parses the loop once; edits to the file on disk never reach a live loop. The
15-day starvation before it ended the same way: the one restart atom sat unrun with
nothing alarming on it.

This predicate is that alarm. Exit 1 ⟺ the running `heartbeat-loop.sh` process
started BEFORE the loop file's last content change on disk (mtime — which is also
what a sync-release checkout rewrite updates), meaning the daemon is executing a
stale body. The remedy is always the same single command, printed in the output:

    launchctl kickstart -k gui/$(id -u)/com.limen.heartbeat

Deliberately NOT auto-kickstarting: the sensor may run inside the very process tree
it would kill, and a mid-beat self-restart could interrupt a merge rung. Advisory
alarm + one visible command is the whole cure.

Exit 0: fresh (daemon newer than the file), or no daemon running (LAUNCH_AGENT_LIVENESS
owns dead-daemon detection — this predicate answers only "is the live one stale"),
or gated off via LIMEN_BEAT_FRESHNESS=0.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "scripts" / "heartbeat-loop.sh"
KICKSTART = "launchctl kickstart -k gui/$(id -u)/com.limen.heartbeat"


def _daemon_start_epoch() -> float | None:
    """Start time of the oldest running heartbeat-loop.sh process, or None."""
    pids = subprocess.run(
        ["pgrep", "-f", "scripts/heartbeat-loop.sh"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    starts: list[float] = []
    for pid in pids.stdout.split():
        etime = subprocess.run(
            ["ps", "-o", "etime=", "-p", pid],
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw = etime.stdout.strip()
        if not raw:
            continue
        # etime forms: [[dd-]hh:]mm:ss — parse to seconds-of-age, derive start epoch.
        days, rest = (raw.split("-", 1) + [""])[:2] if "-" in raw else ("0", raw)
        parts = [int(p) for p in rest.split(":")]
        while len(parts) < 3:
            parts.insert(0, 0)
        age = int(days) * 86400 + parts[0] * 3600 + parts[1] * 60 + parts[2]
        starts.append(time.time() - age)
    return min(starts) if starts else None


def main() -> int:
    if os.environ.get("LIMEN_BEAT_FRESHNESS", "1") == "0":
        print("  beat-freshness: gated off (LIMEN_BEAT_FRESHNESS=0) — skip")
        return 0
    try:
        file_mtime = LOOP.stat().st_mtime
    except OSError as exc:
        print(f"  beat-freshness: cannot stat {LOOP}: {exc}")
        return 1
    started = _daemon_start_epoch()
    if started is None:
        print(
            "  beat-freshness: no heartbeat-loop.sh process — liveness is LAUNCH_AGENT_LIVENESS's verdict, not staleness — skip"
        )
        return 0
    fmt = lambda t: datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
    if started >= file_mtime:
        print(f"  beat-freshness: OK — daemon started {fmt(started)} ≥ loop body changed {fmt(file_mtime)}")
        return 0
    print(
        f"  beat-freshness: STALE — daemon started {fmt(started)} but scripts/heartbeat-loop.sh "
        f"changed {fmt(file_mtime)}; the resident loop never re-reads its body, so every loop-body "
        f"merge since then is dead code until: {KICKSTART}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
