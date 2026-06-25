"""``python -m limen.vigilia`` — the heartbeat's handle on the autonomic executive.

Subcommands (both fail-open; they always exit 0 so an organ bug never wedges the beat):

  vitals-gate   Print 'shed' if the beat should go idle under memory pressure
                (else 'ok'); sheds ollama under critical pressure. The heartbeat
                reads stdout to decide whether to open new dispatch lanes.
  beat          Run the full executive (vitals+continuity+integrity), write the
                seat status file, print a one-line summary.
"""
from __future__ import annotations

import argparse
import sys


def _vitals_gate() -> int:
    try:
        from . import vitals

        decision = vitals.beat_gate(shed=True)
        print(decision.get("action", vitals.OK))
    except Exception:
        # fail-open: never idle the beat because the sensor faulted.
        print("ok")
    return 0


def _beat() -> int:
    try:
        from . import executive

        status = executive.run_beat()
        print(executive.summary_line(status))
    except Exception as exc:
        print(f"vigilia: beat error — {str(exc)[:160]}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="limen.vigilia")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("vitals-gate", help="idle-beat decision under memory pressure")
    sub.add_parser("beat", help="run the full autonomic executive for this beat")
    args = parser.parse_args(argv)

    if args.cmd == "vitals-gate":
        return _vitals_gate()
    if args.cmd == "beat":
        return _beat()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
