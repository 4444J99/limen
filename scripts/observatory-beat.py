#!/usr/bin/env python3
"""observatory-beat.py — the heartbeat's hand on OBSERVATORY.

A thin, self-contained wrapper the beat sensor calls (``sensors.yaml`` →
``observatory-run``). It puts ``cli/src`` on ``sys.path`` (the gitvs.py idiom) so it runs
regardless of whether the ``limen`` package is pip-installed in the beat environment, then
convenes the organ's executive for one beat. It ALWAYS exits 0 — an organ fault must never
wedge the heartbeat.

  python3 scripts/observatory-beat.py            # run the whole loop (dry by default)
  python3 scripts/observatory-beat.py --apply    # arm the human-gated proposal write
  python3 scripts/observatory-beat.py --doctor    # the offline self-verifying predicate
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
SRC = ROOT / "cli" / "src"
if SRC.exists() and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if "--doctor" in argv:
            from limen.observatory import doctor

            report = doctor.run(offline=True)
            print(f"observatory-beat: doctor ok={report['ok']}")
            return 0
        from limen.observatory import executive

        status = executive.run_beat(apply="--apply" in argv)
        print(executive.summary_line(status))
    except Exception as exc:  # fail-open: never wedge the beat
        print(f"observatory-beat: error — {str(exc)[:160]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
