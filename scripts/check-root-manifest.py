#!/usr/bin/env python3
"""ROOT-MANIFEST drift-predicate — hold the repo root to institutio/governance/root-manifest.yaml.

The repo root is a curated surface, not a landing strip: every tracked top-level entry is DECLARED
(the parameter-panel pattern — GATES/SENSORS/PARAMETERS/MAIL-TIERS, one domain over). An undeclared
root entry is a red check, not a memory chore; admitted fat is a counted `grandfathered` row that
carries its target home, so the remaining cleanup reads from the registry, never from a chat list.
Exit 0 ⟺ the registry is well-formed and the tracked root matches it exactly:

  A schema      — schema_version present; every sanctioned row has path/kind/owner/why with kind in
                  the enum; every grandfathered row has path/target_home/why; no duplicate paths and
                  no path in both blocks.
  B coverage    — every tracked top-level entry (git ls-tree HEAD) appears in sanctioned or
                  grandfathered. New fat cannot land silently: declare it or rehome it.
  C reverse     — every declared path still exists in the tracked root. A rehomed or deleted entry
                  must take its row with it (grandfathered rows: deleting the row IS the receipt
                  that the fat was sucked out).
  D homes       — every grandfathered target_home is a relative directory destination ("<dir>/",
                  trailing slash required), a cross-repo destination ("<org>/<repo>:<path>/" —
                  the doc's subject lives in another repository of the estate), or the literal
                  DELETE (git history is the archive; the row's why names the receipt authority),
                  so a row can never launder staying-put as a plan.

  python3 scripts/check-root-manifest.py                 # gate (CI): exit 1 on any root drift
  python3 scripts/check-root-manifest.py --fat           # list only the grandfathered rows (the work)
  python3 scripts/check-root-manifest.py --surface docs  # same predicate, one surface below:
                                                         # docs/ top level vs docs-manifest.yaml

One checker, N curated surfaces: `--surface` selects which registry judges which tracked
listing. docs/ earned its own manifest the same way the root did — 177 loose files beside
17 proper subdirs, accumulated with no predicate watching the surface.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SURFACES: dict[str, dict[str, object]] = {
    "root": {
        "registry": ROOT / "institutio" / "governance" / "root-manifest.yaml",
        "ls_args": (),
        "strip": "",
        "label": "root",
    },
    "docs": {
        "registry": ROOT / "institutio" / "governance" / "docs-manifest.yaml",
        "ls_args": ("--", "docs/"),
        "strip": "docs/",
        "label": "docs/",
    },
}
SANCTIONED_KINDS = {"doc", "registry", "config", "package", "tooling", "data", "dir"}

_failures: list[str] = []
_notes: list[str] = []


def fail(check: str, msg: str) -> None:
    _failures.append(f"[{check}] {msg}")


def tracked_surface_entries(ls_args: tuple[str, ...], strip: str) -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", "--name-only", "HEAD", *ls_args],
        capture_output=True,
        text=True,
        check=True,
    )
    return {line.strip().removeprefix(strip) for line in out.stdout.splitlines() if line.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fat", action="store_true", help="print grandfathered rows and exit 0")
    parser.add_argument("--surface", choices=sorted(SURFACES), default="root", help="which curated surface to judge")
    args = parser.parse_args()
    surface = SURFACES[args.surface]
    registry: Path = surface["registry"]  # type: ignore[assignment]
    label: str = surface["label"]  # type: ignore[assignment]

    if not registry.is_file():
        print(f"check-root-manifest: FAIL\n  [A] registry missing: {registry}")
        return 1
    data = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}

    if "schema_version" not in data:
        fail("A", "schema_version missing")
    sanctioned = data.get("sanctioned") or []
    grandfathered = data.get("grandfathered") or []
    if not isinstance(sanctioned, list) or not isinstance(grandfathered, list):
        fail("A", "sanctioned and grandfathered must be lists")
        sanctioned, grandfathered = [], []

    declared: dict[str, str] = {}
    for row in sanctioned:
        path = row.get("path") if isinstance(row, dict) else None
        if not path or not all(
            isinstance(row.get(k), str) and row.get(k, "").strip() for k in ("kind", "owner", "why")
        ):
            fail("A", f"sanctioned row malformed (needs path/kind/owner/why): {row!r}")
            continue
        if row["kind"] not in SANCTIONED_KINDS:
            fail("A", f"{path}: kind {row['kind']!r} not in {sorted(SANCTIONED_KINDS)}")
        if path in declared:
            fail("A", f"duplicate path: {path}")
        declared[path] = "sanctioned"
    for row in grandfathered:
        path = row.get("path") if isinstance(row, dict) else None
        if not path or not all(isinstance(row.get(k), str) and row.get(k, "").strip() for k in ("target_home", "why")):
            fail("A", f"grandfathered row malformed (needs path/target_home/why): {row!r}")
            continue
        if path in declared:
            fail(
                "A",
                f"{path}: appears in both sanctioned and grandfathered"
                if declared[path] == "sanctioned"
                else f"duplicate path: {path}",
            )
        declared[path] = "grandfathered"
        home = row["target_home"].strip()
        cross_repo = re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+:[^:\s]+/", home) is not None
        if (
            home != "DELETE"
            and not cross_repo
            and (not home.endswith("/") or home.startswith("/") or not home.strip("/"))
        ):
            fail(
                "D",
                f"{path}: target_home {home!r} is not a directory destination "
                "(want '<dir>/', '<org>/<repo>:<path>/', or DELETE)",
            )

    if args.fat:
        for row in grandfathered:
            if isinstance(row, dict) and row.get("path"):
                print(f"{row['path']}  →  {row.get('target_home', '?')}  ({row.get('why', '')})")
        print(f"check-root-manifest: {len(grandfathered)} grandfathered row(s) remaining")
        return 0

    actual = tracked_surface_entries(surface["ls_args"], surface["strip"])  # type: ignore[arg-type]
    for entry in sorted(actual - declared.keys()):
        fail("B", f"undeclared {label} entry (fat): {entry} — declare it in {registry.name} or rehome it")
    for path, block in sorted(declared.items()):
        if path not in actual:
            verb = "deleting the row IS the receipt" if block == "grandfathered" else "remove the stale row"
            fail("C", f"{path}: declared ({block}) but not in the tracked {label} surface — {verb}")

    for note in _notes:
        print(f"check-root-manifest: note — {note}")
    if _failures:
        print("check-root-manifest: FAIL")
        for f in _failures:
            print(f"  {f}")
        return 1
    print(
        f"check-root-manifest [{label}]: OK — {len([p for p, b in declared.items() if b == 'sanctioned'])} sanctioned, "
        f"{len(grandfathered)} grandfathered fat remaining (shrink to zero via rehoming PRs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
