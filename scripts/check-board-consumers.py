#!/usr/bin/env python3
"""check-board-consumers.py — every local board reader resolves custody, or is baselined.

THE PREDICATE FOR THE PARTITION'S QUIETEST FAILURE. After the board partition cuts over,
the public ``tasks.yaml`` is the keeper's counts-only aggregate. A reader that parses it
directly does not crash — it gets ``tasks: []`` and reports **zero work**. Nothing is red;
the fleet simply believes it is finished. Measured 2026-08-15 before the sweep: 24 python
files resolved a board path and parsed it without going through the resolver, 19 of them
with raw ``yaml.safe_load`` (so no shared loader could have fixed them).

A file is CLEAN when it either

* routes through ``limen.private_board.operational_board_path`` / ``_board_custody.board_path``
  (the resolver: public projection pre-cutover, hydrated private custody after), or
* honors ``LIMEN_TASKS`` (the beat points that at custody), or
* is BASELINED below with the reason it legitimately reads a literal file.

The baseline is SHRINK-ONLY, the ratchet this estate already uses six times over in
``institutio/governance/gates.yaml``: a stale entry (the file is now routed) FAILS, so the
list cannot silently accumulate permission. New unrouted readers fail immediately.

    python3 scripts/check-board-consumers.py            # exit 0 iff every reader is clean
    python3 scripts/check-board-consumers.py --list     # show the classification
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SEARCH_ROOTS = ("scripts/", "cli/src/limen/")

# Resolves a board path AND parses a board out of it ⇒ a real consumer.
RESOLVES = re.compile(r'["\']tasks\.yaml["\']|LIMEN_TASKS')
PARSES = re.compile(r"load_limen_file|yaml\.safe_load|yaml\.load")
ROUTED = re.compile(r"operational_board_path|board_path\(")

# path -> why reading a literal file is correct here. Shrink-only.
BASELINE: dict[str, str] = {
    "cli/src/limen/jules_supply.py": (
        "loads the jules SUPPLY registry (limen.jules_supply.v1), not a board; names tasks.yaml "
        "only inside a forbidden-paths string"
    ),
    "cli/src/limen/tabularius.py": (
        "the relay never resolves a board path — every read uses the board_path parameter its "
        "caller supplies, so routing belongs to the caller"
    ),
    "scripts/check-operator-gates.py": (
        "deliberately reads the PUBLISHED projection out of its publication ref (git show "
        "<ref>:tasks.yaml) to judge authorship; substituting custody would defeat the check"
    ),
    "scripts/validate-task-board.py": (
        "the board validator must parse exactly the file it is handed; it is shape-aware and "
        "validates the aggregate on its own arm"
    ),
}


def consumers() -> list[str]:
    found = subprocess.run(
        ["grep", "-rl", "tasks.yaml", *SEARCH_ROOTS],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    out = []
    for rel in sorted(f for f in found if f.endswith(".py")):
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if RESOLVES.search(text) and PARSES.search(text):
            out.append(rel)
    return out


def classify() -> tuple[list[str], list[str], list[str], list[str]]:
    routed, honors, baselined, unrouted = [], [], [], []
    for rel in consumers():
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if ROUTED.search(text):
            routed.append(rel)
        elif rel in BASELINE:
            baselined.append(rel)
        elif "LIMEN_TASKS" in text:
            honors.append(rel)
        else:
            unrouted.append(rel)
    return routed, honors, baselined, unrouted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="print the full classification")
    args = parser.parse_args()

    routed, honors, baselined, unrouted = classify()

    if args.list:
        for label, group in (
            ("ROUTED (resolver)", routed),
            ("HONORS LIMEN_TASKS", honors),
            ("BASELINED", baselined),
            ("UNROUTED", unrouted),
        ):
            print(f"\n{label}: {len(group)}")
            for rel in group:
                suffix = f" — {BASELINE[rel]}" if rel in BASELINE else ""
                print(f"  {rel}{suffix}")

    stale = [rel for rel in BASELINE if rel in routed]
    if stale:
        print(
            f"check-board-consumers: {len(stale)} baseline entry/entries no longer needed "
            "(the file now routes through the resolver) — drop them; the baseline is shrink-only",
            file=sys.stderr,
        )
        for rel in stale:
            print(f"  {rel}", file=sys.stderr)
        return 1

    missing = [rel for rel in BASELINE if not (ROOT / rel).is_file()]
    if missing:
        print(f"check-board-consumers: {len(missing)} baselined file(s) no longer exist", file=sys.stderr)
        for rel in missing:
            print(f"  {rel}", file=sys.stderr)
        return 1

    if unrouted:
        print(
            f"check-board-consumers: {len(unrouted)} board reader(s) parse a resolved path without "
            "the custody resolver. After the partition cutover each returns ZERO tasks silently.",
            file=sys.stderr,
        )
        for rel in unrouted:
            print(f"  {rel}", file=sys.stderr)
        print(
            "\nFix: read through limen.private_board.operational_board_path (or "
            "_board_custody.board_path in scripts without cli/src on sys.path). Pre-cutover it "
            "returns the same path, so the change is a behavior-preserving no-op today.",
            file=sys.stderr,
        )
        return 1

    print(
        f"check-board-consumers: OK — {len(routed)} routed, {len(honors)} honor LIMEN_TASKS, "
        f"{len(baselined)} baselined, 0 unrouted"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
