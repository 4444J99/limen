#!/usr/bin/env python3
"""RESIDUE census — what this machine is holding that it should not be.

The Meeseeks law (2026-07-30, decision 5 of the PORTVS/ASTRA plan): every summoned surface is born
for one purpose, returns its result to source, and self-erases. Residue is a defect caught by
predicates, never a periodic cleanup chore.

`scripts/verify-hot-cache.sh` is that law's court, and it is honest about its own blind spot — R5
excludes worktrees and quarantines "by marker, named here so the exclusion is visible, never
silent", because those have their own reap organs. Which left nothing measuring whether those
organs are KEEPING UP. They were not: 10 GiB of agent runtime whose reaper is written and wired to
nothing, a 571 MiB append-only ledger with no reaper at all, 1,616 remote branches behind an
acceptance ledger that has never been written to once.

This measures the pressure and names the owner. It is READ-ONLY: it deletes nothing, arms nothing,
and touches no reaper. Deleting is the reapers' job and a human-gated one where it is destructive;
knowing is this organ's job, and nobody had it.

WHAT A CAP MEANS. A cap is the disposable-machine ideal, not a promise about today. Distance from
it is the measurement `IF-HOT-CACHE` exists to track — the ideal-forms registry is built to hold a
row that is honestly far from its ideal, and forbids hand-written status precisely so the distance
stays derived. Every cap lives in the parameter panel, so tightening one is a registry edit rather
than a code edit.

WHAT THIS DOES NOT MEASURE: whether a given worktree or branch is *reclaimable*. That question
belongs to the organ that owns it (`reclaim-worktrees.py`, `reap-branches.py`), each of which
already ships its own `--check`. Duplicating their logic here would be a second copy that rots.
The census measures pressure; the owner column says who relieves it.

  python3 scripts/residue-census.py            # the census
  python3 scripts/residue-census.py --check    # exit 1 if any cap is breached
  python3 scripts/residue-census.py --json     # machine-readable, incl. breaches=N for the probe
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
MIB = 1024 * 1024


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _git(*args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _du_kb(path: Path) -> int | None:
    """Apparent disk usage in KiB, or None when the path is absent/unreadable (never a breach)."""
    if not path.exists():
        return None
    try:
        r = subprocess.run(["du", "-sk", str(path)], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return None
        return int(r.stdout.split()[0])
    except Exception:
        return None


def _count_worktrees() -> int | None:
    out = _git("worktree", "list", "--porcelain")
    if not out:
        return None
    # every entry begins with a `worktree ` line; the first is the main checkout, not residue
    return max(0, sum(1 for line in out.splitlines() if line.startswith("worktree ")) - 1)


def _count_refs(pattern: str) -> int | None:
    out = _git("for-each-ref", "--format=%(refname)", pattern)
    if not out:
        return None
    return sum(1 for line in out.splitlines() if line.strip())


def _count_remote_branches() -> int | None:
    n = _count_refs("refs/remotes/")
    # refs/remotes/<remote>/HEAD is a symref, not a branch
    return None if n is None else max(0, n - 1)


def classes() -> list[dict]:
    """Every residue class: what it is, what it measures, its cap, and who relieves it.

    `report_only` marks a class whose relief is gated behind a filed human lever — counting it is
    useful, calling it a breach every run is not: the census would be permanently red on something
    it is not allowed to act on, and a permanently-red predicate is one nobody reads.
    """
    runtime = ROOT / ".agent-runtime"
    logs = ROOT / "logs"
    ledger = ROOT / "docs" / "prompt-atom-ledger.json"

    return [
        {
            "id": "worktrees",
            "unit": "count",
            "what": "git worktrees beyond the live checkout",
            "value": _count_worktrees(),
            "cap": _env_int("LIMEN_RESIDUE_WORKTREES", 8),
            "owner": "scripts/reclaim-worktrees.py (beat-wired via drain.sh; silent no-op until 3e0d1692)",
        },
        {
            "id": "local_branches",
            "unit": "count",
            "what": "local branch refs",
            "value": _count_refs("refs/heads/"),
            "cap": _env_int("LIMEN_RESIDUE_LOCAL_BRANCHES", 40),
            "owner": "scripts/reap-branches.py (beat-wired via clone-maintenance.sh, armed)",
        },
        {
            "id": "remote_branches",
            "unit": "count",
            "what": "remote-tracking branch refs",
            "value": _count_remote_branches(),
            "cap": _env_int("LIMEN_RESIDUE_REMOTE_BRANCHES", 100),
            "owner": "scripts/reap-remote-branches.py — DOUBLE-DARK behind a filed lever; "
            "docs/remote-branch-reap-acceptance.jsonl has never been written to",
            "report_only": True,
        },
        {
            "id": "agent_runtime_mib",
            "unit": "MiB",
            "what": "harness runtime state (.agent-runtime)",
            "value": (lambda kb: None if kb is None else kb // 1024)(_du_kb(runtime)),
            "cap": _env_int("LIMEN_RESIDUE_AGENT_RUNTIME_MIB", 2048),
            "owner": "scripts/agent-state-metabolism.py — WRITTEN AND WIRED TO NOTHING. Not a "
            "one-line sensor row: it needs the Archive4T vault mounted, dual-restoration "
            "verification and private receipts, and carries its own "
            "RETIREMENT_AUTHORIZATION_REQUIRED gate. Retiring it is ARC 5's human-gated "
            "archive-then-delete step, not this organ's call.",
        },
        {
            "id": "logs_mib",
            "unit": "MiB",
            "what": "local receipt/log tree (logs/, gitignored)",
            "value": (lambda kb: None if kb is None else kb // 1024)(_du_kb(logs)),
            "cap": _env_int("LIMEN_RESIDUE_LOGS_MIB", 256),
            "owner": "scripts/disk-capacity.py (beat-wired, armed) — but it only reaps gitignored "
            "probes and truncates one error log; the rest of logs/ has no rotation",
        },
        {
            "id": "atom_ledger_mib",
            "unit": "MiB",
            "what": "the prompt-atom ledger snapshot (gitignored, append-only)",
            "value": (lambda kb: None if kb is None else kb // 1024)(_du_kb(ledger)),
            "cap": _env_int("LIMEN_RESIDUE_ATOM_LEDGER_MIB", 128),
            "owner": "NOBODY — the single largest residue on this machine has no reaper at all. "
            "It is a regenerable SNAPSHOT of the private corpus (cli/src/limen/prompt_corpus.py "
            "writes both halves), which is exactly what the Meeseeks law calls a hot cache.",
        },
    ]


def census() -> dict:
    rows = []
    breaches = 0
    unmeasured = 0
    for c in classes():
        value, cap = c["value"], c["cap"]
        if value is None:
            state = "unmeasured"
            unmeasured += 1
        elif value <= cap:
            state = "within"
        elif c.get("report_only"):
            state = "over-report-only"
        else:
            state = "BREACH"
            breaches += 1
        rows.append({**c, "state": state})
    return {"rows": rows, "breaches": breaches, "unmeasured": unmeasured}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if any cap is breached")
    ap.add_argument("--json", action="store_true", help="machine-readable census")
    args = ap.parse_args()

    result = census()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if (args.check and result["breaches"]) else 0

    print(f"residue-census: breaches={result['breaches']}")
    for r in result["rows"]:
        value = "?" if r["value"] is None else f"{r['value']}"
        mark = {"within": "  ok  ", "BREACH": " BREACH", "over-report-only": " over ", "unmeasured": " skip "}[
            r["state"]
        ]
        print(f" {mark} {r['id']:22s} {value:>8s} / {r['cap']:<8d} {r['unit']:<5s} {r['what']}")
        if r["state"] in ("BREACH", "over-report-only"):
            print(f"          owner: {r['owner']}")

    if result["breaches"]:
        print(
            f"\nresidue-census: {result['breaches']} cap(s) breached — this machine is holding "
            "state it should be able to re-summon. Each breach names its owner above."
        )
        return 1 if args.check else 0
    print("\nresidue-census: every cap holds — nothing is sprawling")
    return 0


if __name__ == "__main__":
    sys.exit(main())
