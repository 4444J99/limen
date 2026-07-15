#!/usr/bin/env python3
"""backblaze-exclusions — verify the crawl-storm exclusions are live (sensor 0p).

2026-07-15 host-thrash incident: after every reboot, Backblaze's ``bztransmit``
re-crawls the disk at ~95 % CPU, and the heaviest thing it crawls is regenerable
fleet state — ``.claude/worktrees`` (hundreds of thousands of small files), the
venvs, the ollama model blobs. None of it needs offsite copies: worktrees re-cut
from origin, venvs rebuild from lockfiles, models re-pull.

This sensor is the completion predicate for lever ``L-BACKBLAZE-EXCLUDE`` (the
Backblaze preferences pane is GUI-only and writes root-context state — his hand by
construction; the VERIFY side is this script). It parses the world-readable
``/Library/Backblaze.bzpkg/bzdata/bzinfo.xml`` and confirms every REQUIRED_EXCLUDES
entry appears as a ``<bzdirfilter dir="..." whichfiles="none"/>`` prefix filter
(Backblaze lowercases paths and stores exact directory prefixes — no globs; one
``.claude/worktrees/`` entry retires every worktree's node_modules/.venv beneath it).

READ-ONLY: never writes bzinfo.xml — the pane owns it. Fail-open on an unreadable
or unrecognized file (Backblaze may rewrite the format on upgrade): prints
``unknown`` and exits 0, never red on uncertainty. Exit 1 ⟺ readable and missing
required entries — the lever is still owed. Extend the estate by editing
REQUIRED_EXCLUDES only; the lever text and this predicate can never drift apart
because the lever cites this constant as its source of truth.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BZINFO = Path("/Library/Backblaze.bzpkg/bzdata/bzinfo.xml")

# The single source of truth for the exclusion estate (lowercased, trailing slash —
# the bzdirfilter storage form). Boot-disk regenerable trees only: /Volumes/Scratch
# carries no .bzvol (not in the backup set), and ~/Library/Caches is left out of the
# REQUIRED set because Backblaze excludes many cache paths via internal defaults that
# never appear in bzinfo.xml — requiring it would risk a permanently-red sensor.
REQUIRED_EXCLUDES = (
    "/users/4jp/workspace/limen/.claude/worktrees/",
    "/users/4jp/workspace/limen/.venv/",
    "/users/4jp/workspace/limen/cli/.venv/",
    "/users/4jp/.ollama/models/",
)


def _norm(path: str) -> str:
    p = path.strip().lower()
    return p if p.endswith("/") else p + "/"


def read_excluded_dirs(bzinfo: Path = BZINFO) -> list[str] | None:
    """The bzdirfilter whichfiles='none' prefixes, or None if unreadable/unrecognized."""
    try:
        root = ET.parse(bzinfo).getroot()
    except Exception:
        return None
    try:
        return [
            _norm(el.get("dir") or "")
            for el in root.iter("bzdirfilter")
            if (el.get("whichfiles") or "").lower() == "none" and el.get("dir")
        ]
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify (default action)")
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    parser.add_argument("--bzinfo", default=str(BZINFO), help="override for tests")
    args = parser.parse_args(argv)

    excluded = read_excluded_dirs(Path(args.bzinfo))
    if excluded is None:
        report = {
            "status": "unknown",
            "note": f"{args.bzinfo} unreadable or unrecognized — fail-open (pane owns the file)",
            "missing": [],
        }
        print(json.dumps(report, indent=2) if args.json else f"backblaze-exclusions: unknown — {report['note']}")
        return 0

    covered = set(excluded)
    # prefix coverage: an entry is satisfied if it or any parent prefix is excluded.
    missing = [req for req in REQUIRED_EXCLUDES if not any(req.startswith(exc) for exc in covered)]
    report = {
        "status": "ok" if not missing else "missing",
        "required": list(REQUIRED_EXCLUDES),
        "missing": missing,
        "excluded_count": len(covered),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    elif missing:
        print(
            "backblaze-exclusions: MISSING — pull L-BACKBLAZE-EXCLUDE "
            "(System Settings → Backblaze → Exclusions), still crawled:"
        )
        for m in missing:
            print(f"  - {m}")
    else:
        print(f"backblaze-exclusions: ok — all {len(REQUIRED_EXCLUDES)} required exclusions live")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
