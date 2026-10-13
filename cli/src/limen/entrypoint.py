"""Keep the scheduled entry path small and bound imports, probes and delivery."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

from limen import heartbeat_state


class TickDeadlineExceeded(BaseException):
    """Unwind owned child groups and admission leases before recording failure."""


def _scheduled_heartbeat(*, json_output: bool = False, wall_seconds: float = 120) -> int:
    # Five seconds of the original allowance belong to cleanup and failure evidence.
    started = time.monotonic()
    grace = min(5.0, wall_seconds / 4)
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    root = Path(".")
    state_root = Path(os.environ.get("LIMEN_HEARTBEAT_STATE_ROOT", Path.home() / ".local/share/limen/heartbeat"))
    failures_before = None

    def finish(receipt):
        if json_output:
            import json

            print(json.dumps(receipt, indent=2, sort_keys=True), flush=True)
        else:
            print(f"heartbeat: {receipt['status']} probe={receipt.get('probe') or 'none'}", flush=True)
        return int(receipt.get("status") == "failed")

    def expired(_signum, _frame):
        signal.signal(signal.SIGALRM, lambda *_: os._exit(78))
        signal.setitimer(signal.ITIMER_REAL, grace)
        raise TickDeadlineExceeded()

    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, wall_seconds - grace)
    try:
        candidates = [Path(os.environ["LIMEN_ROOT"]).expanduser()] if os.environ.get("LIMEN_ROOT") else []
        candidates += [Path(__file__).resolve().parents[3], Path.cwd()]
        root = next(path.resolve() for path in candidates if (path / "scripts/start-worktree-session.sh").is_file())
        try:
            failures_before = heartbeat_state._read_state(state_root / "state.json")["consecutive_system_failures"]
        except heartbeat_state.HeartbeatContractError:
            # Let the engine preserve corrupt state and enact its existing failure path.
            failures_before = None
        # Engine imports are bounded; failure accounting never reimports the engine.
        from limen import heartbeat

        receipt = heartbeat.heartbeat_once(root, state_root=state_root, started_monotonic=started)
        return finish(receipt)
    except TickDeadlineExceeded:
        receipt = heartbeat_state.record_tick_timeout(
            root, state_root, round((time.monotonic() - started) * 1000), failures_before
        )
        return finish(receipt)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            signal.setitimer(
                signal.ITIMER_REAL, max(0.001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1]
            )


def main():
    arguments = sys.argv[1:]
    if arguments in (
        ["heartbeat", "--once"],
        ["heartbeat", "--once", "--json-output"],
        ["heartbeat", "--json-output", "--once"],
    ):
        return _scheduled_heartbeat(json_output="--json-output" in arguments)
    from limen.cli import main as cli_main

    return cli_main()
