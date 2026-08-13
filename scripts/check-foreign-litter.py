#!/usr/bin/env python3
"""check-foreign-litter.py — foreign-agent session litter never squats in the live checkout.

The 2026-07-24 mess audit: an Antigravity teamwork-preview run against victoroff-os planted its
entire orchestration state (~35 untracked `.agents/` dirs: orchestrator/, sentinel/,
teamwork_preview_*/, ORIGINAL_REQUEST.md) inside THIS repo's live checkout and died mid-milestone;
a misnamed SQLite database (`1`, a stray shell redirect) sat beside it at the repo root. Nothing
watched for either class, so they polluted `git status` for a day and blocked sync-release's
clean-park test. This sensor is the durable answer: detect the two litter classes every beat,
loudly; reap into a dated quarantine (move, never delete — reversible) only when armed.

The 2026-08-07 sequel: an npm user-config carrying `prefix=${XDG_DATA_HOME}/npm` was read by a child
process whose environment had been filtered down to an allowlist that dropped `XDG_*`. npm only
substitutes `${VAR}` for variables actually present, so the prefix stayed literal, became a relative
path, and resolved against cwd — planting 121 MB of `@google/gemini-cli` in a directory named
`${XDG_DATA_HOME}` at this repo's root. This sensor reported CLEAN over it: class 1 looks only under
`.agents/`, and class 2 considers only single-component *files*. An untracked root-level DIRECTORY
fell between them, which is class 3 below.

Litter classes (all must be UNTRACKED — tracked content, e.g. `.agents/skills/`, is never litter):
  1. foreign orchestration state under `.agents/` — the Antigravity teamwork-preview layout
     (orchestrator/sentinel/teamwork_preview_*/per-agent BRIEFING/handoff scratch), or any other
     vendor's session tree that lands there uninvited;
  2. repo-root droppings — bare-numeral filenames (`1`, `2>`-style redirect accidents), stray
     `*.sqlite`/`*.db` files, or any root-level file whose magic bytes say SQLite;
  3. repo-root directories git tracks nothing under — a foreign toolchain or vendor tree installed
     into the checkout by a misconfigured prefix. "Tracks nothing under" is the whole predicate:
     grouping untracked paths by first component alone would flag every tracked directory that
     happens to hold one untracked file (`docs/`, `studium/`).

Read-only by default; exit 0 ⟺ clean, exit 1 ⟺ litter found (advisory in the beat — never breaks
it). `--reap` moves findings to logs/foreign-litter-quarantine/<stamp>/ and stamps
logs/foreign-litter.json (organs must stamp — gauges lie). Armed on the beat only via
LIMEN_FOREIGN_LITTER_REAP=1 (SAFE-OFF: detection earns trust first, the orphan-watcher precedent).

  python3 scripts/check-foreign-litter.py            # detect, print, exit 0/1
  python3 scripts/check-foreign-litter.py --reap     # quarantine findings, stamp, exit 0
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__import__("os").environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
QUARANTINE = ROOT / "logs" / "foreign-litter-quarantine"
STAMP = ROOT / "logs" / "foreign-litter.json"
SQLITE_MAGIC = b"SQLite format 3\x00"

# Untracked top-level names under .agents/ that are legitimate (tracked content never reaches
# this list — the git untracked filter already excludes it; this guards non-tracked-but-expected).
AGENTS_ALLOWED = {"skills"}


def _untracked(prefix: str = "") -> list[str]:
    """Untracked, non-ignored paths (git's own litter definition), optionally under a prefix."""
    args = ["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard"]
    if prefix:
        args += ["--", prefix]
    try:
        out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return []  # fail open: a broken git can not fabricate litter
    return [line for line in out.splitlines() if line.strip()]


def find_agents_litter() -> list[Path]:
    """Class 1: untracked orchestration state under .agents/, grouped at its top entry."""
    tops: dict[str, Path] = {}
    for rel in _untracked(".agents"):
        parts = Path(rel).parts
        if len(parts) < 2:
            continue  # a bare file directly under .agents/ still counts below
        top = parts[1]
        if top in AGENTS_ALLOWED:
            continue
        tops.setdefault(top, ROOT / parts[0] / top)
    # bare files like .agents/ORIGINAL_REQUEST.md
    for rel in _untracked(".agents"):
        p = Path(rel)
        if len(p.parts) == 2 and not (ROOT / rel).is_dir():
            tops.setdefault(p.parts[1], ROOT / rel)
    return sorted(tops.values())


def find_root_droppings() -> list[Path]:
    """Class 2: untracked repo-root files that are redirect accidents or stray databases."""
    found: list[Path] = []
    for rel in _untracked():
        p = Path(rel)
        if len(p.parts) != 1:
            continue
        full = ROOT / rel
        if not full.is_file():
            continue
        name = p.name
        if name.isdigit() or name.endswith((".sqlite", ".sqlite3", ".db")):
            found.append(full)
            continue
        try:
            with open(full, "rb") as fh:
                if fh.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC:
                    found.append(full)
        except OSError:
            continue
    return sorted(found)


def _tracks_nothing_under(prefix: str) -> bool:
    """True ⟺ git tracks no file under `prefix` — i.e. the directory is wholly foreign to the repo."""
    args = ["git", "-C", str(ROOT), "ls-files", "--", prefix]
    try:
        out = subprocess.run(args, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return False  # fail open: a broken git can not fabricate litter
    return not out.strip()


def find_root_dirs() -> list[Path]:
    """Class 3: untracked repo-root directories git tracks nothing under, grouped at the top entry."""
    tops: dict[str, Path] = {}
    seen: set[str] = set()  # decided components — a tracked dir must not be re-probed per file
    for rel in _untracked():
        parts = Path(rel).parts
        if len(parts) < 2:
            continue  # single-component paths are class 2's job
        top = parts[0]
        if top in seen:
            continue
        seen.add(top)
        if (ROOT / top).is_dir() and _tracks_nothing_under(top):
            tops[top] = ROOT / top
    return sorted(tops.values())


def _label(path: Path) -> str:
    name = path.name
    if name in {"orchestrator", "sentinel"} or name.startswith("teamwork_preview_"):
        return "antigravity-style orchestration state"
    if path.parent.name == ".agents":
        return "foreign agent session state"
    if path.is_dir():
        return "repo-root directory git tracks nothing under (foreign toolchain install)"
    return "repo-root dropping (redirect accident / stray database)"


def reap(findings: list[Path]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_root = QUARANTINE / stamp
    dest_root.mkdir(parents=True, exist_ok=True)
    moved = []
    for path in findings:
        dest = dest_root / path.name
        shutil.move(str(path), str(dest))
        moved.append({"from": str(path.relative_to(ROOT)), "to": str(dest.relative_to(ROOT))})
    STAMP.parent.mkdir(parents=True, exist_ok=True)
    STAMP.write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "reaped": moved}, indent=2))
    return dest_root


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--reap",
        action="store_true",
        help="quarantine findings into logs/foreign-litter-quarantine/<stamp>/ (move, never delete)",
    )
    args = ap.parse_args()

    findings = find_agents_litter() + find_root_droppings() + find_root_dirs()
    if not findings:
        print("foreign-litter: clean — no untracked foreign session state or root droppings")
        return 0

    for path in findings:
        print(f"foreign-litter: {path.relative_to(ROOT)}  [{_label(path)}]")

    if args.reap:
        dest = reap(findings)
        print(
            f"foreign-litter: {len(findings)} item(s) quarantined under {dest.relative_to(ROOT)} "
            f"(reversible move; stamped logs/foreign-litter.json)"
        )
        return 0

    print(
        "foreign-litter: excavate first (handoffs may carry findings owed to another repo), "
        "then reap — arm LIMEN_FOREIGN_LITTER_REAP=1 for the beat, or run --reap once by hand"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
