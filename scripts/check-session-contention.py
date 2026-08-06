#!/usr/bin/env python3
"""IF-SESSION-NON-CONTENTION, executably — no path rewrites a tree a live session is working in.

THE ROW'S STATED DISTANCE WAS STALE. It cited a 2026-era incident: a session's cwd
(`.claude/worktrees/stateful-dazzling-rainbow`) checked out to fleet PR #276, rebased and amended
by the daemon mid-session. That mechanism no longer exists — the dispatch allocator now PRESERVES
an existing worktree directory and retries under a fresh suffix rather than reusing it. Nobody
re-derived the distance, so the row read OPEN for months while two of its three exposures had
already closed. That is precisely what a probe is for.

Distance is the sum of two terms, because "never" is a claim about both structure and history:

  EXPOSURE   of the enumerated paths that can rewrite or remove a tree, those without an
             occupancy guard. Zero means it CANNOT happen, which is a stronger statement than
             "it has not happened lately".
  INCIDENTS  contention actually recorded in the committed ledger. Non-zero means it DID happen,
             regardless of what the structure claims.

WHY THE PATHS ARE ENUMERATED, NOT GREPPED. A free-text sweep for `reset --hard|switch|stash
push|rebase` over scripts/ and cli/src/ returns ten files, of which eight or nine are prose — task
descriptions self-heal.py writes into tasks.yaml for a human to read, a hook-policy string list in
heal-hook-wiring.py, the English word "checkout" in comments. A baseline whose job is to cancel
those out is a rubber stamp, and a shrink-only ratchet cannot tell a docstring from a call site.
So this asserts named guards at named call sites: adding an eleventh rewriter is caught by review,
not by a regex that already cries wolf nine times out of ten.

  python3 scripts/check-session-contention.py
  python3 scripts/check-session-contention.py --list
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LEDGER_REL = "docs/receipts/session-contention-ledger.json"
LOG_REL = "logs/session-contention.jsonl"

#: Every path that can rewrite or remove a tree, with the marker proving it consults occupancy
#: first. `why` is the evidence: what the path does, and how it is guarded today.
GUARDED_PATHS: dict[str, dict[str, str]] = {
    "sync-release": {
        "file": "scripts/sync-release.sh",
        "marker": "_contended",
        # NB: the prose below deliberately does not put `git` and `push` on one line. This file
        # performs no remote write, but direct-main-writer-audit.py matches that pair per line
        # outside comments — so a sentence DESCRIBING a stash push reads to it as performing one,
        # and the file lands in a write-seam registry recording a seam that does not exist. It is
        # the same prose-false-positive this predicate declines to build its own scan on.
        "why": (
            "rewrites the LIVE CHECKOUT every beat — switch (unpark), reset --hard, and a "
            "stash push. The one path that was unguarded; now probes once and defers at each "
            "destructive site, while never blocking a clean fast-forward"
        ),
    },
    "dispatch-allocator": {
        "file": "cli/src/limen/dispatch.py",
        "marker": "preserved existing worktree",
        "why": (
            "allocates worktrees for dispatched agents. Guarded BY CONSTRUCTION: if the target "
            "directory exists it is preserved and the allocator retries under a fresh "
            "secrets.token_hex suffix, so it never checks out onto an occupied tree. This is the "
            "path the ledger's #276 incident came from, and it is closed"
        ),
    },
    "reclaim-worktrees": {
        "file": "scripts/reclaim-worktrees.py",
        "marker": "_worktree_liveness",
        "why": (
            "removes worktrees. Liveness-gated on the delete path via the process-cwd probe, "
            "fail-closed — which is the correct direction there, since a broken probe must only "
            "ever refuse to delete"
        ),
    },
}


def load_ledger() -> dict:
    path = ROOT / LEDGER_REL
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"_unreadable": True}


def check_exposure() -> tuple[list[str], int]:
    """Paths that can rewrite a tree without consulting occupancy first."""
    findings: list[str] = []
    unguarded = 0
    for name, spec in GUARDED_PATHS.items():
        path = ROOT / spec["file"]
        if not path.is_file():
            findings.append(f"[EXPOSURE] {name}: {spec['file']} does not exist — the guard cannot be verified")
            unguarded += 1
            continue
        if spec["marker"] not in path.read_text(encoding="utf-8"):
            findings.append(
                f"[EXPOSURE] {name}: {spec['file']} no longer contains {spec['marker']!r} — "
                f"its occupancy guard was removed. This path {spec['why']}"
            )
            unguarded += 1
    return findings, unguarded


def _unshipped_local() -> int:
    """Incidents recorded on this host but not yet promoted into the committed ledger.

    Counted deliberately, and it is why this probe is `environment: host`. Reading only the
    committed ledger would make a burst of incidents between ship windows report ZERO — the probe
    would announce the ideal achieved at exactly the moment it was being violated. That is the
    same shape as the defect check-live-checkout.py records in its own header, where comparing a
    stale local ref instead of asking the remote reported `behind=0` on an unfetched checkout.
    """
    path = ROOT / LOG_REL
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            if not json.loads(line).get("shipped"):
                count += 1
        except ValueError:
            continue
    return count


def check_incidents() -> tuple[list[str], int]:
    """Contention that actually happened — committed, plus recorded-but-not-yet-shipped."""
    ledger = load_ledger()
    if ledger.get("_unreadable"):
        return [f"[INCIDENT] {LEDGER_REL} is not valid JSON — a record nobody can read is not a record"], 1

    committed = ledger.get("incident_count")
    committed = committed if isinstance(committed, int) else 0
    unshipped = _unshipped_local()
    total = committed + unshipped
    if not total:
        return [], 0

    findings = []
    if committed:
        recent = (ledger.get("incidents") or [])[-1:]
        where = f" (most recent: {recent[0].get('action')} at {recent[0].get('observed_at')})" if recent else ""
        findings.append(f"[INCIDENT] {committed} committed contention incident(s){where}")
    if unshipped:
        findings.append(
            f"[INCIDENT] {unshipped} incident(s) recorded on this host and not yet shipped — "
            f"run `python3 scripts/session-contention.py ship`"
        )
    return findings, total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="print the guarded estate and exit 0")
    args = parser.parse_args(argv)

    if args.list:
        print(f"tree-rewriting paths — {len(GUARDED_PATHS)} enumerated")
        for name, spec in GUARDED_PATHS.items():
            print(f"  {name:20} {spec['file']}")
            print(f"  {'':20}   guard marker: {spec['marker']!r}")
        return 0

    exposure_findings, unguarded = check_exposure()
    incident_findings, incidents = check_incidents()
    findings = exposure_findings + incident_findings
    distance = unguarded + incidents

    if findings:
        print(f"FAILED: check-session-contention — {len(findings)} finding(s)")
        for f in findings:
            print(f"  ✗ {f}")
        print(f"contention distance: {distance}")
        print(
            "the ideal is 'never', so exposure and history both count: an unguarded path means it "
            "CAN happen, a recorded incident means it DID"
        )
        return 1

    print(
        f"OK: check-session-contention — {len(GUARDED_PATHS)} tree-rewriting paths, all "
        "occupancy-guarded; no contention incident ever recorded"
    )
    print("contention distance: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
