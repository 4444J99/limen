#!/usr/bin/env python3
"""_fast_lane — resolve whether a repository is a registry-declared single-owner fast lane.

Thin CLI over the ONE estate-class resolver (`single_owner_fast_lane_for_repo` in
scripts/setup-rulesets.py: overrides -> match globs -> match_facts, case-insensitive coordinates), so
`merge-policy.sh` derives the answer from `institutio/github/estate.yaml` instead of restating it.

  python3 scripts/_fast_lane.py OWNER/NAME     prints `true` or `false`, exit 0
                                               exit 1 (prints nothing on stdout) when the class
                                               cannot be derived — callers fail toward caution.
"""

import importlib.util
import sys
from pathlib import Path


def main(argv):
    if len(argv) != 2 or "/" not in argv[1]:
        print("usage: _fast_lane.py OWNER/NAME", file=sys.stderr)
        return 1
    repo = argv[1]
    here = Path(__file__).resolve().parent
    # setup-rulesets parses sys.argv at import (--apply/--repo/--contexts); present it a clean argv so a
    # caller's flags can never arm its mutation modes or force check contexts.
    sys.argv = ["setup-rulesets.py"]
    spec = importlib.util.spec_from_file_location("setup_rulesets", str(here / "setup-rulesets.py"))
    if spec is None or spec.loader is None:
        print("cannot load setup-rulesets.py", file=sys.stderr)
        return 1
    module = importlib.util.module_from_spec(spec)
    sys.modules["setup_rulesets"] = module
    try:
        spec.loader.exec_module(module)
        value = module.single_owner_fast_lane_for_repo(repo)
    except Exception as exc:  # noqa: BLE001 - every failure means "underivable"; the caller holds
        print(f"fast-lane class unresolved for {repo}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("true" if value else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
