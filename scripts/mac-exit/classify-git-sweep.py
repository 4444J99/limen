#!/usr/bin/env python3
"""Classify a scripts/mac-exit/git-sweep.sh TSV by whether each entry's work is provably elsewhere.

Repo-level facts (a remote, unpushed commits, stashes) come from kind=repo rows only: in a worktree row
`rev-list --branches` and `stash list` report the shared repository, so counting them per worktree repeats
one repo's exposure on every row. Worktree rows contribute what is truly per-worktree: uncommitted entries
and a detached HEAD that no remote branch contains.

Entries under cache, probe, fixture and already-preserved-copy paths are split off as disposable.

  python3 scripts/mac-exit/classify-git-sweep.py git.tsv --out real.tsv     # exit 0; the TSV is the finding
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

DISPOSABLE_MARKERS = (
    "/_agents/cache/",
    "/.tmp/plugins",
    "/.staging/",
    "/custody-staging/",
    "/pytest-fixtures",
    "/legacy-home/preserved-repos/",
    "/.agent-runtime/codex/.tmp/",
)
FIELDS = ("path", "kind", "branch", "remote", "dirty", "unpushed", "stashes", "reasons")


def reasons_for(row: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    if row["kind"] == "repo":
        if row["remote"] == "NONE":
            reasons.append("no-origin")
        if row["unpushed"] not in ("0", ""):
            reasons.append("unpushed")
        if row["stashes"] not in ("0", ""):
            reasons.append("stash")
    if row["dirty"] not in ("0", ""):
        reasons.append("dirty")
    if row["kind"] == "worktree" and row["branch"] == "(detached)" and row["head_remote_branches"] == "0":
        reasons.append("detached-head-on-no-remote-branch")
    return reasons


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tsv", type=Path, help="git.tsv written by git-sweep.sh")
    parser.add_argument("--out", type=Path, required=True, help="where to write the real-exposure TSV")
    args = parser.parse_args()

    with args.tsv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    tally: Counter[str] = Counter()
    safe = {"repo": 0, "worktree": 0}
    disposable = 0
    real: list[dict[str, str]] = []
    for row in rows:
        reasons = reasons_for(row)
        if not reasons:
            safe[row["kind"]] += 1
            continue
        if any(marker in row["path"] for marker in DISPOSABLE_MARKERS):
            disposable += 1
            continue
        for reason in reasons:
            tally[f"{row['kind']}:{reason}"] += 1
        real.append({**row, "reasons": ",".join(reasons)})

    with args.out.open("w", encoding="utf-8") as out:
        out.write("\t".join(FIELDS) + "\n")
        for row in sorted(real, key=lambda r: r["path"]):
            out.write("\t".join(row[f] for f in FIELDS) + "\n")

    kinds = Counter(r["kind"] for r in rows)
    print(f"entries={len(rows)} repos={kinds['repo']} worktrees={kinds['worktree']}")
    print(f"safe repos={safe['repo']} safe worktrees={safe['worktree']} disposable={disposable} real={len(real)}")
    for key, val in sorted(tally.items()):
        print(f"  {key}: {val}")
    print(f"real-exposure TSV: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
