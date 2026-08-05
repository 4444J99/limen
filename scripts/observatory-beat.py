#!/usr/bin/env python3
"""observatory-beat.py — the heartbeat's hand on OBSERVATORY.

A thin, self-contained wrapper the beat sensor calls (``sensors.yaml`` →
``observatory-run``). It puts ``cli/src`` on ``sys.path`` (the gitvs.py idiom) so it runs
regardless of whether the ``limen`` package is pip-installed in the beat environment, then
convenes the organ's executive for one beat. It ALWAYS exits 0 — an organ fault must never
wedge the heartbeat.

  python3 scripts/observatory-beat.py           # run the whole loop (dry by default)
  python3 scripts/observatory-beat.py --apply   # arm the human-gated proposal write
  python3 scripts/observatory-beat.py --doctor  # the offline self-verifying predicate
  python3 scripts/observatory-beat.py --check   # require every operational stage to be ok
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
SRC = ROOT / "cli" / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--doctor", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.doctor:
            from limen.observatory import doctor

            report = doctor.run(offline=True)
            print(f"observatory-beat: doctor ok={report['ok']}")
            return 0 if report["ok"] else 1
        from limen.observatory import executive

        status = executive.run_beat(apply=args.apply and not args.check)
        print(executive.summary_line(status))
        if args.check:
            stages = status.get("stages")
            if not isinstance(stages, list) or not stages or any(stage.get("status") != "ok" for stage in stages):
                return 1
    except Exception as exc:  # fail-open: never wedge the beat
        print(f"observatory-beat: error — {str(exc)[:160]}")
        if args.check or args.doctor:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
