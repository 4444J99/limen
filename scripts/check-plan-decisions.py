#!/usr/bin/env python3
"""PLAN-DECISIONS drift predicate — a decision recorded only in prose binds nothing.

THE MEASURED DEFECT. On 2026-07-30 the operator restated two decisions in chat, prefaced with "we
decided ... I literally don't want to say it again." Both were already correct, already written
down, and already committed to main — decisions 4 and 5 of
`docs/plans/2026-07-30-portvs-astra-consolidation.md` (PR #1682), in his own words. He had to say
them again anyway, because a plan document is prose, and prose binds nothing. The registries are
law; `docs/plans/` is a Tier-2 surface that nothing reads and no predicate enforces.

That is the same failure this estate has already named twice — `PREC-2026-07-09-sensor-without-effector`
(alerts whose only consumer is the operator) and `PREC-2026-07-10-declared-but-unwired-is-a-defect`
— arriving one level up: not a declared sensor with no effector, but a declared DECISION with no
registry. Writing a third precedent about it and stopping would be the very mistake it describes,
so this is the executable half.

THE RULE. A plan may RECORD a decision. It may never be that decision's only home. Every numbered
decision under a `## Decision...` heading must name where it actually binds:

  a registry path      institutio/**/*.yaml, *.json — the thing a consumer derives from
  a predicate          scripts/*.py|*.sh — the thing that fails when the decision is violated
  a lever id           L-SOMETHING — a human gate that is filed, not floating
  a precedent id       PREC-YYYY-MM-DD-slug — case law
  `owed:`              an explicit admission that it is NOT yet homed

`owed:` is a first-class answer, not a loophole. Rule #1 of the constitution is that a vacuum is
never a resting state but must be NAMED; an unhomed decision that says so is honest, and an
unhomed decision that says nothing is the defect. This check exists to make the difference visible.

THE BASELINE. Decisions already in the tree when this shipped are recorded in the baseline below
rather than retro-annotated, which is this estate's established ratchet (check-params' undeclared
baseline, check-root-manifest's grandfathered rows). Two reasons: annotating another lane's
decisions would mean guessing at homes their owner has not chosen, and a baseline that must shrink
is a better record of the debt than a silent pass. New decisions get no such grace.

  python3 scripts/check-plan-decisions.py          # report
  python3 scripts/check-plan-decisions.py --check  # exit 1 on any unhomed NEW decision
  python3 scripts/check-plan-decisions.py --all    # exit 1 on any unhomed decision, baseline included
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
PLANS = ROOT / "docs" / "plans"

# Decisions present when this predicate shipped (2026-07-30). Each entry is "<file>#<number>".
# This list may SHRINK (home the decision, drop the row) and must never grow.
BASELINE = {
    "2026-07-30-portvs-astra-consolidation.md#1",  # limen -> astra rename (sibling lane, ARC 3)
    "2026-07-30-portvs-astra-consolidation.md#2",  # converge on PORTVS (sibling lane, ARC 2)
    "2026-07-30-portvs-astra-consolidation.md#3",  # SVBTERRANEA is a stratum (sibling lane)
    "2026-07-30-portvs-astra-consolidation.md#6",  # domains live in persistent dirs (sibling ARC 4)
    "2026-07-30-portvs-astra-consolidation.md#7",  # nothing deleted from GitHub (sibling lane)
    "2026-07-30-docs-subject-ownership-export-program.md#1",  # personal tranche routing
    "ci-bounded-shards.md#1",  # jurisdiction field on GATES/SENSORS
    "ci-bounded-shards.md#2",  # reusable scoped-verify workflows in dot-github--*
    "ci-bounded-shards.md#3",  # GITVS doctor class for member-repo CI
}

DECISION_HEADING = re.compile(r"^#{2,4}\s+.*\bDecisions?\b", re.I)
ANY_HEADING = re.compile(r"^#{1,4}\s+")
NUMBERED = re.compile(r"^(\d+)\.\s+(.*)$")

HOMES = (
    (re.compile(r"institutio/[\w./-]+\.(?:yaml|json)"), "registry"),
    (re.compile(r"\b[\w-]+\.(?:yaml|json)\b(?!\s*—\s*never)"), "registry"),
    (re.compile(r"scripts/[\w./-]+\.(?:py|sh)"), "predicate"),
    # a bare script name in backticks (`verify-hot-cache.sh`) names its predicate just as well as
    # a full path does, and that is how these plans are actually written
    (re.compile(r"`[\w-]+\.(?:py|sh)`"), "predicate"),
    (re.compile(r"\bL-[A-Z][A-Z0-9-]{3,}\b"), "lever"),
    (re.compile(r"\bPREC-\d{4}-\d{2}-\d{2}-[a-z0-9-]+\b"), "precedent"),
    (re.compile(r"(?i)\bowed:"), "owed"),
)


def decisions_in(path: Path) -> list[dict]:
    """Every numbered decision under a Decision heading, with the body that belongs to it.

    A decision's body runs to the next numbered sibling or the next heading — so a home named in a
    continuation line still counts, which matters because these are written as prose paragraphs.
    """
    out: list[dict] = []
    in_block = False
    current: dict | None = None

    for line in path.read_text(encoding="utf-8").splitlines():
        if ANY_HEADING.match(line):
            if current:
                out.append(current)
                current = None
            in_block = bool(DECISION_HEADING.match(line))
            continue
        if not in_block:
            continue
        m = NUMBERED.match(line)
        if m:
            if current:
                out.append(current)
            current = {"file": path.name, "n": m.group(1), "body": m.group(2)}
        elif current is not None:
            current["body"] += "\n" + line

    if current:
        out.append(current)
    return out


def home_of(body: str) -> str | None:
    for rx, kind in HOMES:
        if rx.search(body):
            return kind
    return None


def scan() -> list[dict]:
    rows = []
    for path in sorted(PLANS.glob("*.md")):
        for d in decisions_in(path):
            key = f"{d['file']}#{d['n']}"
            rows.append({**d, "key": key, "home": home_of(d["body"]), "baselined": key in BASELINE})
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 on any unhomed NEW decision")
    ap.add_argument("--all", action="store_true", help="exit 1 on any unhomed decision, baseline included")
    args = ap.parse_args()

    rows = scan()
    homed = [r for r in rows if r["home"]]
    unhomed_new = [r for r in rows if not r["home"] and not r["baselined"]]
    unhomed_base = [r for r in rows if not r["home"] and r["baselined"]]

    # A baseline row that has since been homed must be dropped, or the baseline rots into a place
    # decisions hide. Same rule the estate applies to every other ratchet.
    stale = [r["key"] for r in rows if r["home"] and r["baselined"]]
    missing = sorted(BASELINE - {r["key"] for r in rows})

    print(
        f"check-plan-decisions: {len(rows)} decision(s) in {len(list(PLANS.glob('*.md')))} plan(s) — "
        f"{len(homed)} homed, {len(unhomed_new)} unhomed, {len(unhomed_base)} baselined"
    )
    for r in homed:
        print(f"  ok    {r['key']:52s} → {r['home']}")
    for r in unhomed_base:
        print(f"  base  {r['key']:52s} → unhomed (baselined; shrink, never grow)")
    for r in unhomed_new:
        first = r["body"].splitlines()[0][:70]
        print(f"  UNHOMED {r['key']:50s} {first}")

    fails = list(unhomed_new)
    for key in stale:
        print(f"  STALE-BASELINE {key} is homed now — drop it from BASELINE")
    for key in missing:
        print(f"  STALE-BASELINE {key} no longer exists — drop it from BASELINE")

    if stale or missing:
        return 1
    if fails:
        print(
            f"\ncheck-plan-decisions: {len(fails)} decision(s) with no binding home. A plan may "
            "RECORD a decision; it may never be its only home. Name a registry, a predicate, a "
            "lever, or a precedent — or write `owed:` and say so out loud."
        )
        return 1
    if args.all and unhomed_base:
        print(f"\ncheck-plan-decisions: {len(unhomed_base)} baselined decision(s) still unhomed")
        return 1
    print("\ncheck-plan-decisions: OK — every new decision names where it binds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
