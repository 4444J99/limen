#!/usr/bin/env python3
"""check-session-phase.py — the predicate for the plan→issue→PR chain.

Exit ``0`` ⟺ every plan held to the chain declares its GitHub issue and declares the state
of its implementing PR. This is the executable half of the operator's standing ask ("a plan
should always be implemented, and a GitHub issue should be logged, a PR should be open") —
the charter's § Definition of Done requires exactly this shape: *an executable predicate,
never hand-maintained prose*.

WHAT IT HOLDS (offline, text-only — a gate that needs network is a gate that gets disabled):

  1. ``Issue: #N`` — a real issue number. ``#TBD`` and a missing line both fail. This is the
     "an issue should be logged" half, and it is unconditional.
  2. ``PR:`` — declared, in one of three legitimate states:
       ``PR: #M``        the implementing PR (stamped by ``session-plan.py close``)
       ``PR: (pending)`` open plan, implementation not yet landed — a real steady state
       ``Status: superseded|abandoned|folded — <reason>``  dispositioned, with a reason
     A *missing* ``PR:`` line fails: silence about implementation is what let 19 plans
     accumulate with no answer to "was this built?".

WHAT IT DOES NOT HOLD: the 19 pre-existing plans, listed in
``institutio/governance/session-plan-baseline.txt``. This is the ratchet pattern this
registry already uses six times over (orphan-params, test-hygiene, ungated-effectors,
unreachable-runners, board-partition, atom-residue) — history is recorded, not rewritten;
new work is held.

``--live`` adds the one check that needs GitHub: a plan whose issue is **closed** must name a
real PR (or a disposition), because "pending" stopped being true when the issue closed.
Off by default, fail-open on any ``gh`` error — the offline half is the ratchet.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from importlib import util as _import_util

_spec = _import_util.spec_from_file_location("_session_plan", Path(__file__).resolve().parent / "session-plan.py")
if _spec is None or _spec.loader is None:  # pragma: no cover - defensive
    print("check-session-phase: cannot load scripts/session-plan.py", file=sys.stderr)
    sys.exit(1)
_sp = _import_util.module_from_spec(_spec)
_spec.loader.exec_module(_sp)

ROOT = _sp.ROOT
BASELINE = _sp.BASELINE


def evaluate(*, live: bool = False) -> tuple[list[dict], list[dict]]:
    """Return (violations, held) — held is every plan the chain actually binds."""
    base = _sp.baseline_names()
    violations: list[dict] = []
    held: list[dict] = []

    for path in _sp.all_plans():
        if path.name in base:
            continue
        chain = _sp.read_chain(path)
        held.append(chain)
        rel = chain["plan"]

        if not chain["issue"]:
            violations.append(
                {
                    "plan": rel,
                    "rule": "issue-declared",
                    "detail": "no `Issue: #N` line — open one with `scripts/session-plan.py open <slug> --title ...`",
                }
            )
        if not chain["pr_declared"] and not chain["status"]:
            violations.append(
                {
                    "plan": rel,
                    "rule": "pr-declared",
                    "detail": "no `PR:` line — use `PR: (pending)` while open, `PR: #M` once implemented, "
                    "or `Status: superseded|abandoned|folded — <reason>`",
                }
            )
        if chain["status"] and not chain["status_reason"]:
            violations.append(
                {"plan": rel, "rule": "status-reason", "detail": f"`Status: {chain['status']}` carries no reason"}
            )

        if live and chain["issue"] and chain["pr_pending"] and not chain["status"]:
            state = _issue_state(chain["issue"])
            if state == "CLOSED":
                violations.append(
                    {
                        "plan": rel,
                        "rule": "pending-past-close",
                        "detail": f"issue #{chain['issue']} is CLOSED but `PR:` is still (pending) — "
                        f"stamp it: `scripts/session-plan.py close <slug> --pr <N>`",
                    }
                )
    return violations, held


def _issue_state(number: int) -> str | None:
    """Issue state via gh; None on any failure (fail-open — the offline half is the ratchet)."""
    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["gh", "issue", "view", str(number), "--json", "state", "-q", ".state"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip().upper() or None if proc.returncode == 0 else None


def write_baseline() -> int:
    """Seed the baseline with every plan that predates the chain."""
    names = [p.name for p in _sp.all_plans()]
    header = (
        "# session-plan-baseline.txt — plans that predate the plan→issue→PR chain.\n"
        "#\n"
        "# Held OUT of scripts/check-session-phase.py. The ratchet pattern used six times over in\n"
        "# this registry: history is recorded, not rewritten; every NEW plan is held to the chain.\n"
        "# A line is removed from this file only by retro-fitting that plan with a real Issue:/PR:\n"
        "# header — never to silence a fresh violation.\n"
    )
    BASELINE.parent.mkdir(parents=True, exist_ok=True)
    BASELINE.write_text(header + "\n".join(names) + "\n", encoding="utf-8")
    print(f"check-session-phase: baselined {len(names)} plans → {BASELINE.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="also cross-check issue state via gh (fail-open)")
    ap.add_argument("--json", action="store_true", help="machine-readable violations")
    ap.add_argument("--write-baseline", action="store_true", help="(re)seed the baseline from current plans")
    args = ap.parse_args(argv)

    if args.write_baseline:
        return write_baseline()

    violations, held = evaluate(live=args.live)

    if args.json:
        print(json.dumps({"held": len(held), "violations": violations}, indent=2))
        return 1 if violations else 0

    if not violations:
        print(f"check-session-phase: PASS — {len(held)} plans held to the chain, all declare issue + PR state")
        return 0

    print(f"check-session-phase: FAIL — {len(violations)} violation(s) across {len(held)} held plans")
    for v in violations:
        print(f"  [{v['rule']}] {v['plan']}\n      {v['detail']}")
    print("\n  The chain is one command: scripts/session-plan.py open <slug> --title '...'")
    return 1


if __name__ == "__main__":
    sys.exit(main())
