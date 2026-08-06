#!/usr/bin/env python3
"""dispatch-beat.py — the beat's jules dispatch valve rung.

The 2026-07-19 -> 08-06 starvation had four cuts; this file closes the wiring one: the only
`limen dispatch --live` call sites lived in metabolize.sh/saturate.sh, which no scheduler
invokes (unreachable-runners baseline), so zero autonomous dispatch existed at all. This rung
is declared in sensors.yaml (jules-dispatch, source metabolize) and runs on the heartbeat's
metabolize sensor pass.

The valve is logs/autonomy-policy.json, read through `autonomy-governor.py dispatch-ok` —
NOT the LIMEN_DISPATCH env lever, which stays exactly what his-hand-levers.json says it is:
the human valve for MANUAL metabolize/saturate runs. One governed valve, no second switch.

Posture:
  * governor says anything but ok -> print the reason, exit 0 (a quiet no-op, never a red beat);
  * wall-clock throttle (logs/.voice/dispatch_beat, LIMEN_DISPATCH_BEAT_MIN_SECS default 1800)
    bounds passes at <=48/day regardless of the adaptive beat tempo;
  * runs the SERIAL engine, jules only: a remote lane with no local checkout — the 16GB host
    takes no load, and per-pass volume (LIMEN_JULES_DISPATCH_LIMIT default 10) times ~48
    passes is hard-capped by per_agent.jules=100 and the throughput governor's landed-evidence
    clamp before it, so the quota drains across the whole day instead of bursting;
  * process-group timeout so a hung provider call cannot wedge the beat.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
GOVERNOR = ROOT / "scripts" / "autonomy-governor.py"
STAMP = ROOT / "logs" / ".voice" / "dispatch_beat"


def _throttled(min_secs: int) -> bool:
    try:
        age = time.time() - STAMP.stat().st_mtime
    except OSError:
        return False
    return age < min_secs


def _stamp() -> None:
    try:
        STAMP.parent.mkdir(parents=True, exist_ok=True)
        STAMP.write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
    except OSError:
        pass


def main() -> int:
    try:
        min_secs = int(os.environ.get("LIMEN_DISPATCH_BEAT_MIN_SECS", "1800") or "1800")
    except ValueError:
        min_secs = 1800
    if _throttled(min_secs):
        print("  dispatch-beat: throttled (ran within the last window) — skip")
        return 0

    gate = subprocess.run(
        [sys.executable, str(GOVERNOR), "dispatch-ok"],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if gate.returncode != 0:
        reason = (gate.stdout.strip() or gate.stderr.strip() or f"exit {gate.returncode}").splitlines()
        print(f"  dispatch-beat: governor holds the valve — {reason[-1] if reason else 'no reason'}")
        return 0

    limit = os.environ.get("LIMEN_JULES_DISPATCH_LIMIT", "10") or "10"
    try:
        timeout_secs = int(os.environ.get("LIMEN_DISPATCH_BEAT_TIMEOUT", "900") or "900")
    except ValueError:
        timeout_secs = 900
    _stamp()  # stamp before the engine run: a hung/killed engine must not un-throttle retries
    cmd = [sys.executable, "-m", "limen", "dispatch", "--agent", "jules", "--live", "--limit", str(limit)]
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(ROOT / "cli" / "src"))
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout_secs)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        proc.wait(timeout=30)
        print(f"  dispatch-beat: engine timed out after {timeout_secs}s — process group terminated")
        return 0
    tail = [line for line in (out or "").splitlines() if line.strip()][-6:]
    for line in tail:
        print(f"  dispatch-beat: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
