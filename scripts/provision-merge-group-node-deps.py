#!/usr/bin/env python3
"""Provision node-gate deps for the merge-group integration verify.

``ci.yml`` (which ``npm ci``s the node projects) does NOT run on ``merge_group``, and
``pr-gate``'s integration step runs node gates *directly* (no ``--skip-ci-covered``)
so it can block the merge on a real composition failure. Nothing else installs those
gates' ``node_modules`` in the merge-group runner, so the first PR to compose a node
gate's paths fails it with ``ERR_MODULE_NOT_FOUND`` — even though its exact-head CI is
green (that path defers node gates to their ``ci.yml`` jobs, which do install deps).

This derives the node project dirs to install from the SAME GATES registry and
implication logic ``verify.py --integration`` uses: for every gate the merge-group diff
implicates whose command ``cd``s into a dir and runs ``npm`` (``cd <dir> && npm ...``),
run ``npm ci`` there. Deriving — not hardcoding a dir list — keeps this in lockstep:
a new node gate is covered the moment it lands in ``gates.yaml``, with no second edit.

Idempotent and cheap: a diff that implicates no node gate is an instant no-op. Exit 0
unless an ``npm ci`` actually fails.

Usage:
  provision-merge-group-node-deps.py --base <merge_group.base_sha>
"""

from __future__ import annotations

import argparse
import importlib
import re
import subprocess
import sys
from pathlib import Path

# Reuse verify.py's registry loader, diff resolver, and gate-selection logic verbatim,
# so "which node gates are implicated" is decided by exactly one authority.
sys.path.insert(0, str(Path(__file__).resolve().parent))
verify = importlib.import_module("verify")

# A node gate's command provisions its project by cd-ing into a dir then invoking npm:
#   bash -c 'cd web/worker && npm run check'
#   bash -c 'cd web/app && npm run generate:data && npm run build' && node scripts/...
# Gates that only run root-level `node script.mjs` on built-ins need no install and are
# correctly excluded (no `cd <dir> && npm` match).
_CD_NPM = re.compile(r"cd\s+([^\s&|;]+)\s*&&\s*npm\b")


def node_dirs_for(registry: dict, changed: list[str]) -> list[str]:
    """The unique project dirs whose (implicated) node gates need `npm ci`, in order."""
    selected, _skipped = verify.select(registry, changed)
    gates = registry.get("gates") or {}
    dirs: list[str] = []
    for gate_id in selected:
        command = gates.get(gate_id, {}).get("command", "") or ""
        for match in _CD_NPM.finditer(command):
            directory = match.group(1)
            if directory not in dirs:
                dirs.append(directory)
    return dirs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="the merge_group base_sha")
    args = parser.parse_args()

    registry = verify.load_registry()
    changed = verify.changed_set(args.base)
    dirs = node_dirs_for(registry, changed)

    if not dirs:
        print("provision-node-deps: no node gate implicated by the merge-group diff — no-op")
        return 0

    root = Path(verify.git("rev-parse", "--show-toplevel").strip())
    for directory in dirs:
        target = root / directory
        print(f"provision-node-deps: {directory} implicated → npm ci")
        result = subprocess.run(["npm", "ci"], cwd=target)
        if result.returncode != 0:
            print(f"provision-node-deps: npm ci failed in {directory}", file=sys.stderr)
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
