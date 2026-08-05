#!/usr/bin/env python3
"""backblaze-exclusions — keep the crawl-storm exclusions live (sensor 0p).

2026-07-15 + 2026-07-16 host-thrash incidents: Backblaze's ``bztransmit`` crawl and
stats passes walk the disk, and the heaviest thing they touch is regenerable fleet
state — the worktree pools (hundreds of thousands of small files), the venvs, the
ollama model blobs. None of it needs offsite copies: worktrees re-cut from origin,
venvs rebuild from lockfiles, models re-pull.

Ground truth 2026-07-16: ``/Library/Backblaze.bzpkg/bzdata/bzinfo.xml`` is USER-owned
(mode 666), so the exclusion estate is organ-owned — the 7/15 premise that the
preferences pane was "his hand by construction" is retired, and with it lever
L-BACKBLAZE-EXCLUDE. Exclusions are ``<bzdirfilter dir="..." whichfiles="none"/>``
prefix filters inside ``<do_backup>`` (Backblaze lowercases paths and stores exact
directory prefixes — no globs; one worktree-pool entry retires every node_modules/
.venv beneath it), listed ahead of the ``dir="/" whichfiles="all"`` catch-all.

Verbs:
  --check   verify every REQUIRED_EXCLUDES entry is covered (default; exit 1 ⟺ missing)
  --apply   self-heal: back up bzinfo.xml alongside itself, insert the missing entries
            before the catch-all, XML-validate the result, atomically replace, and
            re-verify. Idempotent no-op when already green.

Fail-open on an unreadable or unrecognized file (Backblaze may rewrite the format on
upgrade): prints ``unknown`` and exits 0, never red on uncertainty. An --apply that
cannot land (file re-rooted, catch-all not found, post-insert parse failure) writes
nothing, exits 1, and names the preferences-pane fallback. Extend the estate by
editing REQUIRED_EXCLUDES only — the beat's armed valve (LIMEN_BACKBLAZE_APPLY)
applies it on the next daily rung.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time
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
    "/users/4jp/workspace/.limen-worktrees/",  # dispatch worktree pool — the 2026-07-16 crawl fuel the 7/15 set missed
    "/users/4jp/workspace/limen-worktrees/",  # conductor worktree pool (no-dot sibling)
    "/users/4jp/workspace/limen/.venv/",
    "/users/4jp/workspace/limen/cli/.venv/",
    "/users/4jp/.ollama/models/",
)

# The "back up everything else" terminator of the <do_backup> filter list; new
# exclusions must land before it. Matched line-wise so insertion preserves the
# file's own indentation and never reserializes untouched content.
CATCHALL_RE = re.compile(r'^(?P<indent>[ \t]*)<bzdirfilter\s+dir="/"\s+whichfiles="all"\s*/>', re.MULTILINE)

PANE_FALLBACK = "fallback: Backblaze pane → Settings → Exclusions → Add Folder"


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


def _missing(excluded: list[str]) -> list[str]:
    # prefix coverage: an entry is satisfied if it or any parent prefix is excluded.
    covered = set(excluded)
    return [req for req in REQUIRED_EXCLUDES if not any(req.startswith(exc) for exc in covered)]


def apply_excludes(bzinfo: Path = BZINFO) -> dict:
    """Insert missing REQUIRED_EXCLUDES into bzinfo.xml; never leaves a torn file.

    Returns a report dict; status ∈ ok | applied | unknown | blocked. Only
    ``blocked`` means the estate is still owed (exit 1 at the CLI).
    """
    excluded = read_excluded_dirs(bzinfo)
    if excluded is None:
        return {
            "status": "unknown",
            "note": f"{bzinfo} unreadable or unrecognized — fail-open",
            "added": [],
            "missing": [],
        }
    missing = _missing(excluded)
    if not missing:
        return {"status": "ok", "added": [], "missing": []}
    if not (os.access(bzinfo, os.W_OK) and os.access(bzinfo.parent, os.W_OK)):
        return {
            "status": "blocked",
            "note": f"{bzinfo} is not user-writable (re-rooted?); {PANE_FALLBACK}",
            "added": [],
            "missing": missing,
        }
    text = bzinfo.read_text()
    match = None
    for match in CATCHALL_RE.finditer(text):
        pass  # keep the LAST catch-all — everything before it is the exclusion list
    if match is None:
        return {
            "status": "blocked",
            "note": f'no dir="/" whichfiles="all" catch-all found — format unrecognized; {PANE_FALLBACK}',
            "added": [],
            "missing": missing,
        }
    indent = match.group("indent")
    insertion = "".join(f'{indent}<bzdirfilter dir="{d}" whichfiles="none" />\n' for d in missing)
    new_text = text[: match.start()] + insertion + text[match.start() :]
    try:
        ET.fromstring(new_text)
    except ET.ParseError as exc:
        return {
            "status": "blocked",
            "note": f"post-insert XML failed to parse ({exc}) — nothing written; {PANE_FALLBACK}",
            "added": [],
            "missing": missing,
        }
    backup = bzinfo.with_name(f"{bzinfo.name}.limen-bak-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(bzinfo, backup)
    fd, tmp = tempfile.mkstemp(prefix=".bzinfo-limen-", dir=str(bzinfo.parent))
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(new_text)
        os.chmod(tmp, os.stat(bzinfo).st_mode & 0o777)
        os.replace(tmp, bzinfo)
    except Exception as exc:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        return {
            "status": "blocked",
            "note": f"atomic replace failed ({exc}); original untouched, backup at {backup}",
            "added": [],
            "missing": missing,
        }
    still = _missing(read_excluded_dirs(bzinfo) or [])
    return {
        "status": "applied" if not still else "blocked",
        "added": missing,
        "missing": still,
        "backup": str(backup),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify (default action)")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="insert missing REQUIRED_EXCLUDES into bzinfo.xml (backup + validate + atomic replace)",
    )
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    parser.add_argument("--bzinfo", default=str(BZINFO), help="override for tests")
    args = parser.parse_args(argv)

    if args.apply:
        report = apply_excludes(Path(args.bzinfo))
        if args.json:
            print(json.dumps(report, indent=2))
        elif report["status"] == "ok":
            print(f"backblaze-exclusions: ok — all {len(REQUIRED_EXCLUDES)} required exclusions live")
        elif report["status"] == "applied":
            print(
                f"backblaze-exclusions: applied — {len(report['added'])} exclusion(s) inserted "
                f"(backup: {report['backup']})"
            )
        elif report["status"] == "unknown":
            print(f"backblaze-exclusions: unknown — {report['note']}")
        else:
            print(f"backblaze-exclusions: BLOCKED — {report['note']}")
            for m in report["missing"]:
                print(f"  - {m}")
        return 1 if report["status"] == "blocked" else 0

    excluded = read_excluded_dirs(Path(args.bzinfo))
    if excluded is None:
        report = {
            "status": "unknown",
            "note": f"{args.bzinfo} unreadable or unrecognized — fail-open",
            "missing": [],
        }
        print(json.dumps(report, indent=2) if args.json else f"backblaze-exclusions: unknown — {report['note']}")
        return 0

    missing = _missing(excluded)
    report = {
        "status": "ok" if not missing else "missing",
        "required": list(REQUIRED_EXCLUDES),
        "missing": missing,
        "excluded_count": len(set(excluded)),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    elif missing:
        print(
            "backblaze-exclusions: MISSING — run `python3 scripts/backblaze-exclusions.py --apply` "
            "(bzinfo.xml is user-owned; organ-tended since 2026-07-16), still crawled:"
        )
        for m in missing:
            print(f"  - {m}")
    else:
        print(f"backblaze-exclusions: ok — all {len(REQUIRED_EXCLUDES)} required exclusions live")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
