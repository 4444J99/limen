#!/usr/bin/env python3
"""FACT-WALL — a consumer may only read personal facts the registry HOMES (the credential-wall.py shape).

Kills the phi.pdf defect at its root: the instant a form-filler declares it consumes a personal-fact
class that isn't a homed row in personal-facts.yaml, this is RED — before any fill is attempted, so
the un-homed atom becomes a build failure, never a chat ask.

Contract (declared consumption, NOT fragile static AST — the critic's requirement):
  every form-filler that reads personal facts declares a module-level `CONSUMES = ["class.id", ...]`.
  fact-wall asserts CONSUMES ⊆ registry classes for every such consumer.

  fact-wall.py --check    # exit 0 iff every consumer's CONSUMES is fully homed
"""
import argparse
import ast
import glob
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY = os.path.join(ROOT, "institutio", "governance", "personal-facts.yaml")
SCRIPTS = os.path.join(ROOT, "scripts")


def registry_classes():
    with open(REGISTRY) as f:
        return set((yaml.safe_load(f) or {}).get("facts", {}).keys())


def declared_consumes(path):
    """Extract a module-level CONSUMES = [...] list literal without importing the module."""
    try:
        tree = ast.parse(open(path).read(), filename=path)
    except (SyntaxError, OSError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "CONSUMES":
                    try:
                        return list(ast.literal_eval(node.value))
                    except (ValueError, SyntaxError):
                        return []
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.parse_args()

    homed = registry_classes()
    failures = []
    consumers_seen = 0
    for path in sorted(glob.glob(os.path.join(SCRIPTS, "fill-*.py"))):
        consumes = declared_consumes(path)
        if consumes is None:
            # a form-filler that reads facts but declares no manifest is itself a gap
            failures.append(f"  ✗ {os.path.basename(path)}: no CONSUMES manifest (declare the facts it reads)")
            continue
        consumers_seen += 1
        for cid in consumes:
            if cid not in homed:
                failures.append(f"  ✗ {os.path.basename(path)}: consumes un-homed class {cid!r} — add a registry row")

    if failures:
        print("fact-wall: RED — un-homed personal-fact consumption")
        print("\n".join(failures))
        sys.exit(1)
    print(f"fact-wall: OK ({consumers_seen} form-filler(s), all consumed classes homed)")
    sys.exit(0)


if __name__ == "__main__":
    main()
