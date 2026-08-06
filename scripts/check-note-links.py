#!/usr/bin/env python3
"""check-note-links.py — the predicate for ``[[wikilink]]`` citations that point at nothing.

Exit ``0`` ⟺ every **newly cited** note slug resolves to a real tracked file.

WHY THIS GATE EXISTS
--------------------
This is the generalization of the defect that produced the six-week ``ClaudeCode.app is
damaged`` loop (``IF-GATEKEEPER-INERT``, PR #1848). The root-cause knowledge for that class
was homed in ``[[macos-tcc-gatekeeper-dialogs-solved]]`` — a wikilink cited from **five**
registry surfaces (``dialogs-silenced.sh`` ×2, ``sensors.yaml``, ``parameters.yaml``,
``his-hand-levers.json`` ×2) that **did not exist on disk**. Every session followed it, found
nothing, and re-derived the root cause from the effector's header comment — which carried a
false premise. Five cures shipped against that false premise.

**The false belief propagated because its refutation had no home**, and nothing anywhere
could tell the difference between "cited and written" and "cited into a void". A citation
that resolves and a citation that dangles are byte-identical at the call site; only the
filesystem knows, and nothing was asking it.

That is the same shape as the ledger's founding complaint — *a status living in a field with
nothing to check it* — so it gets the same remedy: a predicate, plus the shrink-only baseline
ratchet this registry already uses eight times over (orphan-params, test-hygiene,
ungated-effectors, unreachable-runners, board-partition, atom-residue, corpus-root-literals,
session-plan).

WHAT IT HOLDS
-------------
1. A citation ``[[<slug>]]`` in any tracked prose/registry/source file must resolve
   to a tracked file whose **stem** is that slug (any directory, any extension). That is how
   ``[[macos-tcc-gatekeeper-dialogs-solved]]`` resolves to
   ``docs/architecture/macos-tcc-gatekeeper-dialogs-solved.md``.
2. Pre-existing dangling slugs are listed in
   ``institutio/governance/note-link-baseline.txt`` and do not fail. History is recorded, not
   rewritten; every NEW citation is held.
3. The baseline is **shrink-only**. A baselined slug that now resolves is a FAILURE telling
   you to delete its line — otherwise the ratchet silently accumulates permission.

SCOPE, STATED IN THE OUTPUT (never silently)
--------------------------------------------
A note slug in this estate is kebab-case with at least two segments (``foo-bar``). A
single-token ``[[link]]`` is overwhelmingly prose or source syntax — Python's ``[[0], [1, 2]]``
in ``check-danse.py`` is the live example — so single-token citations are **not** gated.

They are not silently dropped either: every run prints them under ``unclassified``. A
narrow filter used as safety is precisely what let the mid-write bundle state sail past
``condemnable()`` for six weeks; the fix there was to widen the filter and report the
unmeasured case rather than score it green, and the same rule applies here. If a real
single-token note ever appears, it shows up in that list rather than vanishing.

Offline and text-only by construction: a gate that needs the network is a gate that gets
disabled.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "institutio" / "governance" / "note-link-baseline.txt"

# Files whose text can carry a citation. Everything else (binaries, lockfiles, notebooks)
# is skipped — a citation nobody can read is not a citation.
SCANNED_SUFFIXES = {".md", ".py", ".sh", ".yaml", ".yml", ".json", ".txt", ".ts", ".tsx", ".mjs"}

# Directories that are vendored, generated, or archival — a dangling link there is not a
# governance signal about this estate's own knowledge homes.
#
# Measured 2026-08-05 so the exclusion is stated rather than assumed: `node_modules/` and
# `web/app/out/` currently match ZERO tracked files (they are defensive, for the day something
# gets committed there), and `corpus/` matches exactly one — a Persian epic. So this list is
# presently near-vacuous and removes nothing real. Recorded because an exclusion whose reach
# nobody has measured is how a gate quietly stops covering what it claims to.
SKIP_PREFIXES = ("node_modules/", "web/app/out/", "corpus/")

CITATION = re.compile(r"\[\[([A-Za-z0-9][A-Za-z0-9._/-]*)\]\]")
# A note slug: kebab-case, two or more segments. See SCOPE in the module docstring.
NOTE_SLUG = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        print("check-note-links: not a git repo / git ls-files failed", file=sys.stderr)
        sys.exit(2)
    return [line for line in out.stdout.splitlines() if line]


def load_baseline(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip() for line in path.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]


# `root` and `baseline` are parameters, not module constants, so the contracts in
# cli/tests/test_check_note_links.py can build a whole fake repo in tmp_path and assert on
# a set they control. A gate whose only test is "it passes against the live repo today"
# cannot tell you it still bites tomorrow — the lesson from this gate's own lineage, where
# 17 effector contracts were only worth writing because they FAIL against the prior logic.
def scan(root: Path = ROOT) -> dict:
    files = tracked_files(root)
    stems: dict[str, list[str]] = defaultdict(list)
    for f in files:
        stems[Path(f).stem].append(f)

    cited: dict[str, set[str]] = defaultdict(set)
    unclassified: dict[str, set[str]] = defaultdict(set)

    for f in files:
        if f.startswith(SKIP_PREFIXES) or Path(f).suffix not in SCANNED_SUFFIXES:
            continue
        try:
            text = (root / f).read_text(errors="ignore")
        except OSError:
            continue
        for match in CITATION.finditer(text):
            slug = match.group(1)
            if NOTE_SLUG.match(slug):
                cited[slug].add(f)
            else:
                unclassified[slug].add(f)

    resolved = {s: sorted(v) for s, v in cited.items() if s in stems}
    dangling = {s: sorted(v) for s, v in cited.items() if s not in stems}
    return {
        "scanned_files": len(files),
        "cited": {s: sorted(v) for s, v in cited.items()},
        "resolved": resolved,
        "dangling": dangling,
        "unclassified": {s: sorted(v) for s, v in unclassified.items()},
    }


def verdict(scanned: dict, baseline: list[str]) -> dict:
    """Split the dangling set against the baseline. Pure — no filesystem, no git."""
    baseline_set = set(baseline)
    dangling = scanned["dangling"]
    return {
        "fresh": sorted(s for s in dangling if s not in baseline_set),
        "stale": sorted(s for s in baseline_set if s not in dangling),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="emit the full scan as JSON")
    ap.add_argument(
        "--ideal",
        action="store_true",
        help="IF-NOTE-HOMED's probe: exit 0 only when NOTHING dangles (the baseline is empty)",
    )
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help="rewrite the baseline to the current dangling set (bootstrap only — never to silence a fresh break)",
    )
    args = ap.parse_args()

    scanned = scan(ROOT)
    dangling = scanned["dangling"]
    baseline = load_baseline(BASELINE)

    if args.write_baseline:
        header = (
            "# note-link-baseline.txt — note slugs cited as [[wikilinks]] with no file on disk.\n"
            "#\n"
            "# Held OUT of scripts/check-note-links.py. The ratchet pattern this registry already\n"
            "# uses eight times over: history is recorded, not rewritten; every NEW citation is held.\n"
            "#\n"
            "# A line leaves this file exactly one way: by WRITING the note it names. The gate FAILS\n"
            "# on a stale line, so the baseline can only shrink. Never add a line to silence a fresh\n"
            "# dangling citation — that is the failure mode this whole gate exists to stop\n"
            "# (see IF-GATEKEEPER-INERT: five cures shipped against a premise whose refutation had\n"
            "# no home, because [[macos-tcc-gatekeeper-dialogs-solved]] was cited from five surfaces\n"
            "# and existed nowhere).\n"
        )
        BASELINE.write_text(header + "".join(f"{s}\n" for s in sorted(dangling)))
        print(f"check-note-links: baseline written — {len(dangling)} slug(s) recorded")
        return 0

    if args.json:
        print(json.dumps({**scanned, "baseline": baseline}, indent=2))

    split = verdict(scanned, baseline)
    fresh, stale = split["fresh"], split["stale"]

    total_cited = len(scanned["cited"])
    print(
        f"check-note-links: {total_cited} note slug(s) cited across {scanned['scanned_files']} tracked files — "
        f"{len(scanned['resolved'])} resolve, {len(dangling)} dangle "
        f"({len(dangling) - len(fresh)} baselined, {len(fresh)} fresh)"
    )

    if scanned["unclassified"]:
        names = ", ".join(sorted(scanned["unclassified"]))
        print(f"  unclassified (single-token, not gated — see SCOPE): {names}")

    ok = True

    if fresh:
        ok = False
        print(f"\nFAIL — {len(fresh)} citation(s) point at a note that does not exist:")
        for slug in fresh:
            print(f"  [[{slug}]]")
            for citer in dangling[slug]:
                print(f"      cited by {citer}")
        print(
            "\n  Write the note (a tracked file whose stem is the slug), or remove the citation.\n"
            "  Do NOT add it to the baseline: a cited-but-unwritten note is exactly how a false\n"
            "  premise propagates for six weeks with nothing able to notice."
        )

    if stale:
        ok = False
        print(f"\nFAIL — {len(stale)} baseline line(s) are stale (the note now exists):")
        for slug in stale:
            print(f"  {slug}")
        print(f"\n  Delete those lines from {BASELINE.relative_to(ROOT)} — the baseline is shrink-only.")

    if ok:
        print("OK — every gated citation resolves; the baseline is exact.")

    # Two questions, two exit codes — the same split as `claude-identity-bundle.py --strict`.
    #
    # Bare: the RATCHET. "Did this change make it worse?" Exit 0 at the baseline, which is what
    # a CI gate must do or it blocks every PR on inherited debt.
    #
    # --ideal: IF-NOTE-HOMED's probe. "Does the estate cite nothing into a void?" A baselined
    # dangle is still a dangle — the next session still follows it and still finds nothing. A
    # probe that answered 0 with 49 dangling links would be measuring the ratchet and calling it
    # the ideal, and the ledger is explicit that *measuring the wrong question is worse than
    # declaring the vacuum*. So the distance this derives is the baseline's own length, and
    # `at-ideal` means one thing only: the baseline is empty.
    if args.ideal:
        if dangling:
            print(
                f"\ndistance-remains — {len(dangling)} cited note(s) have no home. "
                f"IF-NOTE-HOMED is at ideal only when that count is 0."
            )
            return 1
        print("at-ideal — nothing is cited into a void.")
        return 0

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
