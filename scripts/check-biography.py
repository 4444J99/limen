#!/usr/bin/env python3
"""BIOGRAPHY registry drift-predicate — hold biography.yaml to its own contract.

Exit 0 ⟺ the registry is well-formed, every provenance is legal, and (where this host
can prove it) the declared store matches. Sibling of check-corpora.py and
check-personal-facts.py; same lettered-check shape, same CUSTODY axis.

The checks, and the defect each one answers:

  A schema      every fact row carries the required fields, and `home`/`atom` are declared.
  B provenance  every row's provenance is in the vocabulary. `inferred` is NOT in it — that
                is the whole point of the file, so a row claiming it is a hard failure
                rather than a lint.
  C signals     every `derived` row names `derived_from` signals that epoch_signals declares.
                A deriver may only consume metadata; a boundary drawn from content is the
                defect the registry exists to prevent.
  D meaning     no `derived` provenance on a meaning/circumstance row. Boundaries are
                arithmetic; what they MEANT is not derivable and may not be written by a
                deriver, only by `operator` or `cited`.
  E store       where absence is PROVABLE (the estate root exists on this host), a required
                applicable row with no home on disk is reported. On a CI runner with no
                ~/Workspace, absence of evidence stays a host fact — the custody
                distinction check-corpora.py draws for store roots.
  F retrieval   every `cited` row presupposes reachable corpora. If corpus_resolve reports
                no populated home, citations cannot be verified and that is stated — "I
                found nothing" and "I read nothing" must not read the same. Custody-gated
                like E: the corpora are a local-only gitignored store, so an unreachable
                corpus is drift only where this host could have held one.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "institutio" / "governance" / "biography.yaml"
STORE_BASE = Path(os.environ.get("LIMEN_WORKSPACE", str(Path.home() / "Workspace")))

REQUIRED_FIELDS = ("domain", "home", "atom", "tier", "applicable", "required", "verify", "provenance")
VALID_TIER = {"public", "private", "sensitive", "crown-jewel"}
VALID_APPLICABLE = {True, False, "unknown"}
# `inferred` is deliberately absent. A row may not claim an agent reasoned its value out.
BANNED_PROVENANCE = {"inferred", "assumed", "reconstructed", "estimated"}
# Rows whose value is a MEANING rather than a measurement — never deriver-writable.
MEANING_ATOM_MARKERS = ("meaning", "circumstance", "narrative")

_failures: list[str] = []
_advisories: list[str] = []


def fail(check: str, msg: str) -> None:
    _failures.append(f"{check}: {msg}")


def advise(check: str, msg: str) -> None:
    _advisories.append(f"{check}: {msg}")


def check_a_schema(facts: dict) -> None:
    if not facts:
        fail("A", "registry declares no facts")
        return
    for cid, row in facts.items():
        if not isinstance(row, dict):
            fail("A", f"fact {cid!r} is not a mapping")
            continue
        for field in REQUIRED_FIELDS:
            if row.get(field) in (None, ""):
                fail("A", f"fact {cid!r} missing required field {field!r}")
        if row.get("tier") and row["tier"] not in VALID_TIER:
            fail("A", f"fact {cid!r} invalid tier {row['tier']!r} (valid: {sorted(VALID_TIER)})")
        if row.get("applicable") not in VALID_APPLICABLE:
            fail("A", f"fact {cid!r} invalid applicable {row.get('applicable')!r}")


def check_b_provenance(facts: dict, kinds: dict) -> None:
    legal = set(kinds or {})
    if not legal:
        fail("B", "registry declares no provenance_kinds")
        return
    for banned in BANNED_PROVENANCE & legal:
        fail("B", f"provenance_kinds declares {banned!r} — an agent's reasoning is not a provenance")
    for cid, row in facts.items():
        if not isinstance(row, dict):
            continue
        prov = row.get("provenance")
        if prov in BANNED_PROVENANCE:
            fail("B", f"fact {cid!r} claims provenance {prov!r}; legal kinds are {sorted(legal)}")
        elif prov and prov not in legal:
            fail("B", f"fact {cid!r} has undeclared provenance {prov!r} (declared: {sorted(legal)})")


def check_c_signals(facts: dict, signals: list) -> None:
    declared = {str(s.get("id")) for s in (signals or []) if isinstance(s, dict) and s.get("id")}
    if not declared:
        fail("C", "registry declares no epoch_signals")
        return
    for cid, row in facts.items():
        if not isinstance(row, dict) or row.get("provenance") != "derived":
            continue
        froms = row.get("derived_from") or []
        if not froms:
            fail("C", f"fact {cid!r} is provenance:derived but names no derived_from signals")
            continue
        for sig in froms:
            if str(sig) not in declared:
                fail("C", f"fact {cid!r} derives from undeclared signal {sig!r} (declared: {sorted(declared)})")


def check_d_meaning_not_derived(facts: dict) -> None:
    for cid, row in facts.items():
        if not isinstance(row, dict):
            continue
        target = f"{cid} {row.get('atom', '')}".lower()
        if any(marker in target for marker in MEANING_ATOM_MARKERS) and row.get("provenance") == "derived":
            fail(
                "D",
                f"fact {cid!r} is a meaning row with provenance:derived — boundaries are arithmetic, "
                "what they meant is not; only `operator` or `cited` may fill it",
            )


def _absence_is_provable() -> bool:
    """True when THIS machine is the one that would hold the private estate."""
    if os.environ.get("LIMEN_LIFE_HOST") == "1":
        return True
    if os.environ.get("CI"):
        return False
    return STORE_BASE.is_dir()


def check_e_store(facts: dict) -> None:
    if not _absence_is_provable():
        advise("E", f"estate root {STORE_BASE} not present — store parity unverifiable here, not drift")
        return
    for cid, row in facts.items():
        if not isinstance(row, dict):
            continue
        if row.get("applicable") is not True or not row.get("required"):
            continue
        home = STORE_BASE / str(row.get("home", "")).lstrip("/")
        if not home.exists():
            fail("E", f"fact {cid!r} is applicable+required but its home does not exist: {home}")


def check_f_retrieval(facts: dict) -> None:
    cited = [cid for cid, row in facts.items() if isinstance(row, dict) and row.get("provenance") == "cited"]
    if not cited:
        return
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import corpus_resolve
    except ImportError as exc:
        fail("F", f"{len(cited)} cited row(s) but corpus_resolve is not importable: {exc}")
        return
    home = corpus_resolve.corpus_home()
    populated = corpus_resolve.populated_corpora_including_undeclared(home)
    if not populated:
        # The CUSTODY distinction check E already draws, applied here too. The session
        # corpora are a local-only, gitignored store: a CI runner has never held one and
        # never will, so "no populated corpus" there is a HOST fact, not registry drift.
        # Without this the gate is red on every runner by construction — which is how a
        # guard gets trained into background noise. check-corpora.py resolves the same
        # store the same way ("absence is not provable here").
        report = fail if _absence_is_provable() else advise
        report(
            "F",
            f"{len(cited)} cited row(s) but no populated corpus under {home} — citations are "
            "unverifiable, and an unreachable corpus reads exactly like an empty one"
            + ("" if _absence_is_provable() else " (no estate root on this host — unverifiable, not drift)"),
        )
    else:
        advise("F", f"{len(cited)} cited row(s); {len(populated)} corpus/corpora reachable at {home}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BIOGRAPHY registry drift-predicate")
    ap.add_argument("--quiet", action="store_true", help="print only failures")
    args = ap.parse_args(argv)

    if not REGISTRY.exists():
        print(f"FAIL  registry missing: {REGISTRY}", file=sys.stderr)
        return 1
    try:
        doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        print(f"FAIL  registry unreadable: {exc}", file=sys.stderr)
        return 1

    facts = doc.get("facts") or {}
    check_a_schema(facts)
    check_b_provenance(facts, doc.get("provenance_kinds") or {})
    check_c_signals(facts, doc.get("epoch_signals") or [])
    check_d_meaning_not_derived(facts)
    check_e_store(facts)
    check_f_retrieval(facts)

    if not args.quiet:
        for item in _advisories:
            print(f"  ↑ {item}")
    for item in _failures:
        print(f"FAIL  {item}", file=sys.stderr)
    if _failures:
        return 1
    if not args.quiet:
        print(f"OK: check-biography — {len(facts)} fact classes, checks A-F clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
