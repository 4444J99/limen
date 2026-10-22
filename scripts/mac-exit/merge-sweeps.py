#!/usr/bin/env python3
"""Carry a previous sweep's universe forward into a fresh one, so removals stay accounted for.

A fresh sweep lists only what exists now. Anything that vanished since the previous sweep silently leaves the universe, which is
exactly how a loss would hide. The merged TSV holds:
  * every row of the fresh sweep (fresh evidence wins), and
  * every row of the previous sweep whose path is absent from the fresh sweep AND no longer exists on disk (a vanished row, which
    the readiness predicate must see so it demands a rescue copy or a signed waiver for it).
A previous row whose path still exists but is missing from the fresh sweep means the sweep roots missed a live repository; it is
kept (from the older evidence) and listed loudly rather than dropped.

Each sweep has a roots file beside it: the sweep path with its last suffix replaced by `.roots` (git.tsv -> git.roots), listing
the roots that sweep walked and ending in a completion row `#END rows=N`. The merged sweep gets one too, holding the union of both
inputs' roots, so the predicate's fresh scan covers everything either sweep covered. A roots file that is missing, or has no valid
completion row, refuses the whole merge and writes nothing: the merged universe must not claim coverage nobody recorded.
One exception keeps the carry-forward chain alive across the tool upgrade: a previous sweep made before roots files existed has
none, and with MERGE_SWEEPS_LEGACY_OLD=1 it is accepted, the merged roots are then the fresh sweep's only, and one stderr line
says the old sweep's roots were unknown. The fresh sweep must always have a valid roots file, and a previous roots file that
exists but is malformed is refused even then.

usage: python3 -I merge-sweeps.py <fresh git.tsv> <previous git.tsv> <out.tsv>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


LEGACY_ENV = "MERGE_SWEEPS_LEGACY_OLD"


def roots_path(sweep: str) -> str:
    return str(Path(sweep).with_suffix(".roots"))


def load_roots(sweep: str) -> list[str]:
    """The roots a sweep recorded. Raises ValueError unless the file ends in exactly one `#END rows=N` with N the root count."""
    path = roots_path(sweep)
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except OSError as exc:
        raise ValueError(f"no usable roots file for {sweep}: {exc.strerror} ({path})") from exc
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    ends = [i for i, ln in enumerate(lines) if ln.startswith("#END")]
    if len(ends) != 1 or ends[0] != len(lines) - 1:
        raise ValueError(f"{path}: needs exactly one completion row `#END rows=N`, as its last line")
    roots = lines[:-1]
    if lines[-1] != f"#END rows={len(roots)}":
        raise ValueError(f"{path}: completion row {lines[-1]!r} does not match its {len(roots)} root(s)")
    for root in roots:
        if not root.startswith("/"):
            raise ValueError(f"{path}: root {root!r} is not an absolute path")
    return roots


def read_rows(path: str) -> tuple[list[str], list[list[str]]]:
    # Plain tab splitting: a path is a join key, and csv quoting would rewrite one that holds a quote character.
    with open(path, encoding="utf-8", newline="") as fh:
        lines = fh.read().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    header = lines[0].split("\t") if lines else []
    return header, [ln.split("\t") for ln in lines[1:] if ln]


def write_atomic(path: str, text: str) -> None:
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    os.replace(tmp, path)


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 64
    fresh_path, old_path, out_path = sys.argv[1:4]
    for p in (fresh_path, old_path):
        if not os.path.isfile(p):
            print(f"no such sweep file: {p}", file=sys.stderr)
            return 66
    header, fresh = read_rows(fresh_path)
    old_header, old = read_rows(old_path)
    if old_header != header:
        print("FAIL: the two sweeps have different headers", file=sys.stderr)
        return 2
    try:
        fresh_roots = load_roots(fresh_path)
        if os.path.lexists(roots_path(old_path)):
            old_roots = load_roots(old_path)  # present but malformed: refused, legacy switch or not
        elif os.environ.get(LEGACY_ENV) == "1":
            old_roots = []
            print(
                f"merge-sweeps: {old_path} has no roots file ({LEGACY_ENV}=1): its roots are unknown, "
                "so the merged roots are the fresh sweep's only",
                file=sys.stderr,
            )
        else:
            raise ValueError(
                f"no usable roots file for {old_path}: {roots_path(old_path)} does not exist "
                f"(a sweep made before roots files existed can be carried forward with {LEGACY_ENV}=1)"
            )
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    have = {r[0] for r in fresh}
    carried_vanished, carried_missed = [], []
    for r in old:
        if r[0] in have:
            continue
        (carried_missed if os.path.exists(r[0]) else carried_vanished).append(r)
    merged_roots = list(dict.fromkeys([*fresh_roots, *old_roots]))
    rows = [header, *fresh, *carried_vanished, *carried_missed]
    write_atomic(out_path, "".join("\t".join(r) + "\n" for r in rows))
    write_atomic(roots_path(out_path), "".join(f"{r}\n" for r in merged_roots) + f"#END rows={len(merged_roots)}\n")
    merged = len(fresh) + len(carried_vanished) + len(carried_missed)
    print(
        f"fresh rows {len(fresh)}; carried forward as vanished {len(carried_vanished)}; "
        f"still on disk but missed by the fresh sweep {len(carried_missed)}; merged {merged}; "
        f"roots {len(merged_roots)} -> {roots_path(out_path)}"
    )
    for r in carried_missed:
        print("  MISSED BY FRESH SWEEP (exists on disk):", r[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
