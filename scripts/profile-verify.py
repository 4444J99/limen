#!/usr/bin/env python3
"""profile-verify.py — the executable predicate for the 4444J99 profile (exit 0 ⟺ provable).

Holds the generated README to its sources. Checks:
  1. no third-party widget hot-links (the owner wants our own self-hosted versions);
  2. every image src is a local ./assets file (nothing loaded from a remote widget host);
  3. every statistical number in the README is backed by stats-manifest.json (api- or repo-attested);
  4. the banned "top-tier creative" nothing-phrase is gone;
  5. every ./assets file the README references actually exists and parses (SVG well-formed, JSON valid).

    python scripts/profile-verify.py --out _profile-build      # exit 0 = the page is provable
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import xml.dom.minidom
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _profile as P  # noqa: E402


def _referenced_assets(readme: str) -> list[str]:
    refs = []
    for m in re.finditer(r'(?:<img[^>]+src=|\]\()\s*["\']?(\.?/?assets/[^"\')\s>]+)', readme):
        refs.append(m.group(1).lstrip("./"))
    return sorted(set(refs))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify the generated profile is provable and self-hosted.")
    ap.add_argument("--out", default=os.environ.get("LIMEN_PROFILE_OUT", "_profile-build"))
    args = ap.parse_args(argv)

    out = Path(args.out)
    readme_path = out / "README.md"
    manifest_path = out / "assets" / "stats-manifest.json"
    problems: list[str] = []

    if not readme_path.exists():
        print(f"profile-verify: missing {readme_path}", file=sys.stderr)
        return 2
    if not manifest_path.exists():
        print(f"profile-verify: missing {manifest_path}", file=sys.stderr)
        return 2

    readme = readme_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    problems += P.verify_readme(readme, manifest)

    # referenced assets exist and parse
    for rel in _referenced_assets(readme):
        path = out / rel
        if not path.exists():
            problems.append(f"referenced asset missing: {rel}")
            continue
        try:
            if path.suffix == ".svg":
                xml.dom.minidom.parse(str(path))
            elif path.suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            problems.append(f"referenced asset does not parse: {rel} ({exc})")

    if problems:
        print(f"profile-verify: FAIL — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1

    n_api = sum(1 for s in manifest.get("stats", {}).values() if s.get("attest") == "api")
    n_repo = sum(1 for s in manifest.get("stats", {}).values() if s.get("attest") == "repo")
    print(f"profile-verify: PASS — README provable & self-hosted "
          f"({n_api} api-attested + {n_repo} repo-attested stats, "
          f"{len(_referenced_assets(readme))} local assets).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
