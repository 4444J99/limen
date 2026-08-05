#!/usr/bin/env python3
"""DOCS-EXPORTS drift-predicate — hold institutio/governance/docs-exports.yaml to the tree.

docs-manifest.yaml governs the docs/ TOP-LEVEL surface; docs-exports.yaml governs the cross-repo
program at any depth — every limen doc whose SUBJECT another repository owns. It is a shrinking
work-list, not a parity claim: shipping an export DELETES its row, so the registry only ever moves
toward zero. Without a predicate the two halves of a move can drift apart silently — the file
leaves and the row lingers (a phantom work item), or the row retires and the file stays (a claimed
export that never happened). Exit 0 ⟺ every row still describes real, unshipped work:

  A schema   — schema_version present; exports is a list; every row carries path/target/tranche/
               leak_risk/patch/why with the right types, and no path appears twice.
  B reality  — every row's path is still tracked in git HEAD. A row whose file is gone means the
               export shipped without retiring its row; retire the row in the shipping commit.
  C target   — every target is a cross-repo destination ("<org>/<repo>:<path>/", trailing slash
               required) or the literal DELETE, so a row can never launder staying-put as a plan.
  D enums    — tranche in T1..T6 (execution order) and leak_risk in {high, low, none}.
  E patch    — every declared consumer to repoint is a real tracked path. A stale patch pointer
               sends the move's author at a file that no longer exists.

  python3 scripts/check-docs-exports.py          # gate (CI): exit 1 on any registry drift
  python3 scripts/check-docs-exports.py --work   # print the remaining rows by tranche (the work)

The pair mirrors the root: check-root-manifest.py answers "is this surface declared?", this answers
"is the declared work still real?". Same doctrine, one domain over.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "docs-exports.yaml"
TRANCHES = {"T1", "T2", "T3", "T4", "T5", "T6"}
LEAK_RISKS = {"high", "low", "none"}
CROSS_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:[^:\s]+/")

_failures: list[str] = []


def fail(check: str, msg: str) -> None:
    _failures.append(f"[{check}] {msg}")


def tracked_paths() -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip() for line in out.stdout.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", action="store_true", help="print the remaining rows by tranche and exit 0")
    args = parser.parse_args()

    if not REGISTRY.is_file():
        print(f"check-docs-exports: FAIL\n  [A] registry missing: {REGISTRY}")
        return 1
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}

    if "schema_version" not in data:
        fail("A", "schema_version missing")
    rows = data.get("exports")
    if not isinstance(rows, list):
        print("check-docs-exports: FAIL\n  [A] exports must be a list")
        return 1

    tracked = tracked_paths()
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            fail("A", f"row is not a mapping: {row!r}")
            continue
        path = row.get("path")
        if not isinstance(path, str) or not path.strip():
            fail("A", f"row missing a path: {row!r}")
            continue
        if not isinstance(row.get("why"), str):
            fail("A", f"{path}: why must be a string (empty is allowed — the target carries the reason)")
        if path in seen:
            fail("A", f"duplicate path: {path}")
        seen.add(path)

        if path not in tracked:
            fail("B", f"{path}: row exists but the file is not tracked — retire the row in the shipping commit")

        target = row.get("target")
        if not isinstance(target, str) or (target != "DELETE" and not CROSS_REPO.fullmatch(target)):
            fail("C", f"{path}: target {target!r} is not a cross-repo destination ('<org>/<repo>:<path>/') or DELETE")

        if row.get("tranche") not in TRANCHES:
            fail("D", f"{path}: tranche {row.get('tranche')!r} not in {sorted(TRANCHES)}")
        if row.get("leak_risk") not in LEAK_RISKS:
            fail("D", f"{path}: leak_risk {row.get('leak_risk')!r} not in {sorted(LEAK_RISKS)}")

        patch = row.get("patch")
        if not isinstance(patch, list):
            fail("E", f"{path}: patch must be a list (empty list = a free move)")
            continue
        for consumer in patch:
            if not isinstance(consumer, str) or consumer not in tracked:
                fail("E", f"{path}: patch consumer {consumer!r} is not a tracked path")

    if args.work and not _failures:
        by_tranche: dict[str, list[str]] = {}
        for row in rows:
            by_tranche.setdefault(row.get("tranche", "?"), []).append(row["path"])
        for tranche in sorted(by_tranche):
            print(f"{tranche} ({len(by_tranche[tranche])}):")
            for path in sorted(by_tranche[tranche]):
                print(f"  {path}")
        return 0

    if _failures:
        print("check-docs-exports: FAIL")
        for f in _failures:
            print(f"  {f}")
        return 1
    print(
        f"check-docs-exports: OK — {len(rows)} export rows, every path real and every target homed "
        "(shrink to zero by shipping tranches)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
