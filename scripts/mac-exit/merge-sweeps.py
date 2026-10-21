"""Carry a previous sweep's universe forward into a fresh one, so removals stay accounted for.

A fresh sweep lists only what exists now. Anything that vanished since the previous sweep silently leaves the universe, which is
exactly how a loss would hide. The merged TSV holds:
  * every row of the fresh sweep (fresh evidence wins), and
  * every row of the previous sweep whose path is absent from the fresh sweep AND no longer exists on disk (a vanished row, which
    the readiness predicate must see so it demands a rescue copy or a signed waiver for it).
A previous row whose path still exists but is missing from the fresh sweep means the sweep roots missed a live repository; it is
kept (from the older evidence) and listed loudly rather than dropped.

usage: python3 -I merge-sweeps.py <fresh git.tsv> <previous git.tsv> <out.tsv>
"""

from __future__ import annotations

import csv
import os
import sys


def main() -> int:
    fresh_path, old_path, out_path = sys.argv[1:4]
    with open(fresh_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader)
        fresh = list(reader)
    with open(old_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh, delimiter="\t")
        if next(reader) != header:
            print("FAIL: the two sweeps have different headers", file=sys.stderr)
            return 2
        old = list(reader)
    have = {r[0] for r in fresh}
    carried_vanished, carried_missed = [], []
    for r in old:
        if r[0] in have:
            continue
        (carried_missed if os.path.exists(r[0]) else carried_vanished).append(r)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        w.writerows(fresh)
        w.writerows(carried_vanished)
        w.writerows(carried_missed)
    print(f"fresh rows {len(fresh)}; carried forward as vanished {len(carried_vanished)}; "
          f"still on disk but missed by the fresh sweep {len(carried_missed)}; merged {len(fresh) + len(carried_vanished) + len(carried_missed)}")
    for r in carried_missed:
        print("  MISSED BY FRESH SWEEP (exists on disk):", r[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
