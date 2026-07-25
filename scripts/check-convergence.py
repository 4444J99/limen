#!/usr/bin/env python3
"""CONVERGENCE registry drift-predicate — one owner per capability, executably.

Makes the ledger's rule — "never build the 7th; a new engine is a regression" — a gate
instead of a memory. Exit 0 ⟺ institutio/governance/convergence.yaml is coherent and its
owners actually exist:

  A schema      — every capability row carries status/owner_of_record/note; a non-unresolved
                  row carries an owner; an unresolved row carries owner: null (a COUNTED
                  vacuum, never an implicit one); every duplicate carries a valid disposition.
  B reachable   — every owner resolves: an in-repo path exists, a local path exists, or an
                  `org/repo` appears in the estate census. Prose owners are advisories.
  C residue     — a `converged` row carrying `lift` duplicates is ratchet residue: allowed,
                  counted, expected to shrink. `unresolved` rows are counted loudly.

  python3 scripts/check-convergence.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "convergence.yaml"
CENSUS = ROOT / "logs" / "constellation" / "estate-census.json"

VALID_STATUS = {"converged", "lifting", "unresolved"}
VALID_DISPOSITION = {"retire", "tenant", "lift"}

failures: list[str] = []
advisories: list[str] = []


def _census_repos() -> set[str]:
    if not CENSUS.is_file():
        return set()
    data = json.loads(CENSUS.read_text(encoding="utf-8"))
    return {r["nameWithOwner"] for r in data.get("repos", [])}


def _owner_reachable(owner: str, repos: set[str]) -> str:
    """'ok', 'missing', or 'prose' (unverifiable by construction)."""
    candidate = owner.split("::")[0].strip()
    if candidate.startswith("~"):
        return "ok" if Path(candidate).expanduser().exists() else "missing"
    if (ROOT / candidate).exists():
        return "ok"
    parts = candidate.split()
    if parts and "/" in parts[0]:
        head = parts[0]
        if head in repos:
            return "ok"
        if (ROOT / head).exists():
            return "ok"
        if head.count("/") == 1 and not head.endswith((".py", ".md", ".yaml")):
            return "missing"
    return "prose"


def main() -> int:
    if not REGISTRY.is_file():
        print(f"FAILED: check-convergence — registry missing at {REGISTRY}")
        return 1
    doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    caps = doc.get("capabilities") or {}
    repos = _census_repos()

    residue = 0
    unresolved = []
    for cid, row in caps.items():
        status = row.get("status")
        if status not in VALID_STATUS:
            failures.append(f"A: {cid}: invalid status {status!r}")
            continue
        for field in ("owner_of_record", "note"):
            if not row.get(field):
                failures.append(f"A: {cid}: missing {field}")
        owner = row.get("owner")
        if status == "unresolved":
            unresolved.append(cid)
            if owner is not None:
                failures.append(f"A: {cid}: unresolved rows must declare owner: null")
        elif not owner:
            failures.append(f"A: {cid}: status {status} requires an owner")
        else:
            state = _owner_reachable(str(owner), repos)
            if state == "missing":
                failures.append(f"B: {cid}: owner not found — {owner}")
            elif state == "prose":
                advisories.append(f"B: {cid}: owner is prose, unverifiable ({owner})")
        for dup in row.get("duplicates") or []:
            disp = dup.get("disposition")
            if disp not in VALID_DISPOSITION:
                failures.append(f"A: {cid}: duplicate {dup.get('impl')!r} has invalid disposition {disp!r}")
            if status == "converged" and disp == "lift":
                residue += 1

    for a in advisories:
        print(f"  ↑ {a}")
    if failures:
        print(f"FAILED: check-convergence — {len(failures)} drift(s)")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print(
        f"OK: check-convergence — {len(caps)} capabilities "
        f"({sum(1 for r in caps.values() if r.get('status') == 'converged')} converged, "
        f"{sum(1 for r in caps.values() if r.get('status') == 'lifting')} lifting, "
        f"{len(unresolved)} unresolved vacuum(s): {', '.join(unresolved) or 'none'}); "
        f"{residue} ratchet-residue duplicate(s) in converged rows"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
