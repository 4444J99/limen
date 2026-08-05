#!/usr/bin/env python3
"""PERSONAL-FACTS drift predicate — holds the registry to its own rules (the check-gates.py shape).

Exit 0 iff institutio/governance/personal-facts.yaml is internally coherent:
  A  every fact row carries the required fields with valid enums (tier/verify/applicable).
  B  crown-jewel rule: tier:crown-jewel => home is an op:// ref, verify is shadow_present,
     and a `shadow` atom is declared (the raw value may never rest on disk).
  C  single-home: no two classes declare the same (home, atom) pair (no double-owning an atom).
  D  consumer parity: every file named in a `consumers:` list exists under scripts/.
  E  home shape: a non-op home path sits under a _*-private store (federation-not-fusion).
  F  referenced_by shape: single-home citing stores are declared data — each entry names a
     _*-private store/collection/field, and a crown-jewel is never cited by a plaintext store.
     (SHAPE only, store-free so it runs in CI; MEMBERSHIP is enforced by `identity.py reconcile`
     at the beat, where the ARCA-sealed store actually exists.)

Run directly, via pr-gate, or verify-whole. Fails toward caution: a broken registry is RED.
"""
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "institutio", "governance", "personal-facts.yaml")
SCRIPTS = os.path.join(ROOT, "scripts")

VALID_TIERS = {"public", "private", "sensitive", "crown-jewel"}
VALID_VERIFY = {"non_empty", "shadow_present", "pointer_resolves"}
VALID_APPLICABLE = {True, False, "unknown"}
REQUIRED_FIELDS = ("domain", "home", "atom", "tier", "applicable", "required", "verify")

failures = []


def fail(check, msg):
    failures.append(f"  ✗ [{check}] {msg}")


def main():
    with open(REGISTRY) as f:
        doc = yaml.safe_load(f) or {}
    facts = doc.get("facts", {})
    if not facts:
        fail("A", "registry has no `facts` block")

    seen_home_atom = {}
    for cid, fct in facts.items():
        # A: required fields + enums
        for field in REQUIRED_FIELDS:
            if field not in fct:
                fail("A", f"{cid}: missing `{field}`")
        if fct.get("tier") not in VALID_TIERS:
            fail("A", f"{cid}: tier {fct.get('tier')!r} not in {sorted(VALID_TIERS)}")
        if fct.get("verify") not in VALID_VERIFY:
            fail("A", f"{cid}: verify {fct.get('verify')!r} not in {sorted(VALID_VERIFY)}")
        if fct.get("applicable") not in VALID_APPLICABLE:
            fail("A", f"{cid}: applicable {fct.get('applicable')!r} not in true/false/unknown")
        if not isinstance(fct.get("required"), bool):
            fail("A", f"{cid}: required must be a boolean")

        home = fct.get("home", "")
        # B: crown-jewel rule
        if fct.get("tier") == "crown-jewel":
            if not home.startswith("op://"):
                fail("B", f"{cid}: crown-jewel home must be an op:// ref, got {home!r}")
            if fct.get("verify") != "shadow_present":
                fail("B", f"{cid}: crown-jewel verify must be shadow_present")
            if not fct.get("shadow"):
                fail("B", f"{cid}: crown-jewel must declare a `shadow` atom (the only on-disk trace)")
        else:
            # a non-crown-jewel must NOT hide a raw value behind an op:// home without shadow semantics
            if home.startswith("op://") and fct.get("verify") != "shadow_present":
                fail("B", f"{cid}: op:// home requires verify shadow_present")

        # C: single-home (no two classes own the same at-rest (home, atom))
        if not home.startswith("op://"):
            key = (home, fct.get("atom"))
            if key in seen_home_atom:
                fail("C", f"{cid}: (home,atom) {key} already owned by {seen_home_atom[key]} — double-home")
            else:
                seen_home_atom[key] = cid

        # D: consumer files exist
        for consumer in fct.get("consumers", []) or []:
            if not os.path.isfile(os.path.join(SCRIPTS, consumer)):
                fail("D", f"{cid}: consumer scripts/{consumer} not found")

        # E: non-op home shape
        if home and not home.startswith("op://"):
            top = home.split("/", 1)[0]
            if not (top.startswith("_") and top.endswith("-private")):
                fail("E", f"{cid}: home {home!r} is not under a _*-private store")

        # F: referenced_by shape (single-home citing stores as declared data; membership is a beat check)
        refs = fct.get("referenced_by")
        if refs is not None:
            if fct.get("tier") == "crown-jewel":
                fail("F", f"{cid}: crown-jewel must never be referenced_by a plaintext store")
            if not isinstance(refs, list):
                fail("F", f"{cid}: referenced_by must be a list")
            else:
                for i, ref in enumerate(refs):
                    if not isinstance(ref, dict):
                        fail("F", f"{cid}: referenced_by[{i}] must be a mapping")
                        continue
                    for k in ("store", "collection", "field"):
                        if not isinstance(ref.get(k), str) or not ref.get(k):
                            fail("F", f"{cid}: referenced_by[{i}] missing string `{k}`")
                    store = ref.get("store", "")
                    stop = store.split("/", 1)[0]
                    if store and not (stop.startswith("_") and stop.endswith("-private")):
                        fail("F", f"{cid}: referenced_by[{i}] store {store!r} not under a _*-private store")

    if failures:
        print("personal-facts registry: DRIFT")
        print("\n".join(failures))
        sys.exit(1)
    print(f"personal-facts registry: OK ({len(facts)} fact-classes coherent)")
    sys.exit(0)


if __name__ == "__main__":
    main()
