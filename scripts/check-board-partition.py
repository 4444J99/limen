#!/usr/bin/env python3
"""BOARD-PARTITION predicate — client work must not ride the public board.

``tasks.yaml`` is 5.8 MB, tracked, and lives in a PUBLIC repo (``organvm/limen``). It is the
largest published artifact in the estate and it was not a consumer of a single publication gate.
Thirteen scripts derive from ``scripts/publication-policy.py``, whose own doctrine says:

    Subject-matter-sensitive content (internal strategy, raw session artifacts, NAMED THIRD
    PARTIES) on a PUBLIC surface stays OFF the public HEAD.

The board publishes it anyway. That is the defect this predicate closes: a declared invariant with
no enforcement path into the actual artifact.

THREE FINDING CLASSES, because they are three different wrongs:

  row       A task row attributed to a partner lane. The engagement's own work items -- titles,
            context, base SHAs, owner role names -- published to the world.
  content   A row on some OTHER repo whose free text names a partner. The leak travels even when
            the attribution is clean.
  slug      The board spells a partner lane with an owner it no longer has. This is the ROOT CAUSE
            of the other two going unnoticed for a month: ``4444J99/victoroff-os`` was transferred
            out of ``organvm`` in 2026-07, estate.yaml keys its protective override on the new
            slug, and the board still writes ``organvm/victoroff-os`` -- which misses the override
            and falls through to the ``organvm/**`` glob to ``governed_public``. One repository,
            two names, opposite verdicts. estate.yaml:750 had already written this hazard down
            ("Without this row the 4444J99/** portal glob classed it desired-PUBLIC — a latent
            flip hazard"); it arrived through a door nobody was watching.

WHY A BASELINE. Remediating the published rows means rewriting ``tasks.yaml``, and agents never
write the board -- TABVLARIVS is its only logical writer and transitions go through the broker. So
this predicate cannot fix what it finds. It pins the known leak, fails on anything NEW, and the
baseline may only shrink. The existing rows are homed on the broker scrub, not on a chat list.

  python3 scripts/check-board-partition.py            # report
  python3 scripts/check-board-partition.py --check    # exit 1 on a finding outside the baseline
  python3 scripts/check-board-partition.py --json     # machine-readable, for a doctor rung
  python3 scripts/check-board-partition.py --update   # re-pin after a real broker scrub (SHRINK-ONLY)

``--update`` is shrink-only and refuses to add: growing this baseline accepts a new disclosure on a
public head, which is a human decision and needs an explicit ``--accept-new-disclosures`` to say so.
The refusal exists because ``--check``'s own "run --update to drop it" hint would otherwise launder
new findings into the baseline as a routine re-pin — see ``_update``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.partition_lanes import (  # noqa: E402
    PartitionRegistryError,
    canonical_slug,
    is_partner_lane,
    partner_keywords,
    partner_lanes,
    repo_tail,
)

BOARD = Path(os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
# Redirectable INDEPENDENTLY of ROOT, and that is the point rather than a convenience. `--update` is
# this predicate's only write, so its target was the only thing a test had to redirect to exercise the
# shrink-only ratchet — and it could not: overriding LIMEN_ROOT relocates the partner-lane registries
# too, which makes `findings()` raise PartitionRegistryError before any baseline logic runs. So the one
# surface that could violate the invariant was also the one surface no test could reach, and the
# invariant went unenforced through three separate written statements of it. An untestable write is how
# a stated rule survives with no code behind it.
BASELINE = Path(
    os.environ.get(
        "LIMEN_BOARD_PARTITION_BASELINE",
        str(ROOT / "institutio" / "governance" / "board-partition-baseline.txt"),
    )
)

# Fields scanned for a partner name. Deliberately NOT the whole row: a `urls` entry pointing at a
# partner repo is a reference, not a disclosure, and flagging it would bury the real findings.
TEXT_FIELDS = ("id", "title", "context", "type", "workstream")


def _fold(text: str) -> str:
    """Collapse to alphanumerics so ``mirror mirror``, ``mirror-mirror`` and ``MirrorMirror`` agree."""
    return "".join(ch for ch in str(text).lower() if ch.isalnum())


def _disclosure_markers(lanes: frozenset[str], keywords: frozenset[str]) -> dict[str, str]:
    """The tokens that actually IDENTIFY a partner lane, mapped to the lane they identify.

    A keyword qualifies only when it names the lane itself -- folded, it must be a substring of the
    lane's own slug. The constellation register's keywords exist for ROUTING and discovery, not
    confidentiality, so most of them are ordinary vocabulary: "hydration" (elevate-align) matched
    every task mentioning ``creds-hydrate``, "podcast" (hospes) matched four hokage-chess tasks,
    and "salon", "spiral" and "potato" behaved the same way.

    Reusing a word list built for one purpose as evidence for another is exactly the category
    error that put a client engagement at the top of the dispatch queue -- ``_LIFECYCLE_TEXT_TERMS``
    was a lifecycle vocabulary pressed into service as a value signal. The rule, not a hand-pruned
    list, is the fix: ``victoroff`` is a marker because it names ``victoroff-os``; ``hydration`` is
    not, because it names nothing.
    """
    markers: dict[str, str] = {}
    for lane in sorted(lanes):
        folded_lane = _fold(lane)
        tail = repo_tail(lane)
        if tail:
            markers.setdefault(_fold(tail), lane)
        for keyword in sorted(keywords):
            folded = _fold(keyword)
            if len(folded) >= 4 and folded in folded_lane:
                markers.setdefault(folded, lane)
    return markers


def _board_rows() -> list[dict[str, object]]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - PyYAML is a hard dependency
        raise SystemExit(f"board-partition: PyYAML unavailable: {exc}") from exc
    try:
        data = yaml.safe_load(BOARD.read_text())
    except (OSError, ValueError) as exc:
        raise SystemExit(f"board-partition: {BOARD}: {exc}") from exc
    rows = (data or {}).get("tasks")
    if not isinstance(rows, list):
        raise SystemExit(f"board-partition: {BOARD}: no tasks list")
    return [row for row in rows if isinstance(row, dict)]


def findings() -> list[str]:
    """One stable, greppable line per leak. Sorted, so the baseline diff is readable.

    Lines carry the task id and repo but NEVER the title or context: this file is committed to the
    same public repo the leak is in, so a finding that quoted the content would republish it.
    """
    lanes = partner_lanes(ROOT)
    markers = _disclosure_markers(lanes, partner_keywords(ROOT))
    out: set[str] = set()

    for row in _board_rows():
        task_id = str(row.get("id") or "?")
        repo = str(row.get("repo") or "").strip()

        if repo and is_partner_lane(repo, ROOT):
            canonical = canonical_slug(repo, ROOT)
            out.add(f"row board-partition: {task_id} is attributed to partner lane {canonical}")
            if canonical and repo.lower() != canonical:
                out.add(
                    f"slug board-partition: {task_id} spells {canonical} as {repo} — "
                    "the stale owner misses estate.yaml's private override"
                )
            continue

        folded = _fold(" ".join(str(row.get(field) or "") for field in TEXT_FIELDS))
        for marker, lane in sorted(markers.items()):
            if marker in folded:
                out.add(f"content board-partition: {task_id} on {repo or '(no repo)'} names partner lane {lane}")
                break

    return sorted(out)


def _baseline() -> set[str]:
    if not BASELINE.is_file():
        return set()
    return {
        line.strip() for line in BASELINE.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")
    }


def _baseline_label() -> str:
    """Repo-relative when the baseline is the shipped one, absolute when it has been redirected.

    Not cosmetic: the redirect exists so a test can exercise the only write this predicate makes, and a
    run that re-pinned somewhere other than the tracked file should say so in the line a human reads.
    """
    try:
        return str(BASELINE.relative_to(ROOT))
    except ValueError:
        return str(BASELINE)


def _write_baseline(current: list[str]) -> None:
    header = (
        "# board-partition-baseline — client/partner work already published on the PUBLIC board\n"
        "# (organvm/limen is public and tasks.yaml is tracked). Known and owned rather than\n"
        "# silently tolerated. The gate fails on any NEW finding; this list may only SHRINK.\n"
        "#\n"
        "# This file names task ids and repo slugs, and it is committed to the SAME public repo as\n"
        "# the leak it indexes — so it discloses nothing tasks.yaml does not already disclose\n"
        "# beside it. That is a deliberate trade, not an oversight: a hashed baseline could not be\n"
        "# audited or ratcheted down, and titles/context (where the actual client substance lives)\n"
        "# are never copied here. When the broker scrub lands, this file shrinks with it.\n"
        "#\n"
        "# These rows cannot be fixed by this predicate: TABVLARIVS is the board's only logical\n"
        "# writer and agent sessions never push tasks.yaml. Their owner is the broker scrub.\n"
        "# After a real scrub lands, re-pin with:\n"
        "#   python3 scripts/check-board-partition.py --update\n"
        "#\n"
        "# That re-pin is SHRINK-ONLY and refuses to add. Growing this list accepts a new disclosure\n"
        "# on a public head, so it takes an explicit --accept-new-disclosures; a bare --update can\n"
        "# only drop cleared entries. Do not hand-append rows here to clear a red gate.\n"
    )
    BASELINE.write_text(header + "\n".join(current) + ("\n" if current else ""))


def _update(current: list[str], *, accept_new: bool) -> int:
    """Re-pin the baseline, SHRINK-ONLY — the invariant this file states three times and never enforced.

    The docstring, the baseline header, and a test title all say the list may only shrink. The code
    said otherwise: ``--update`` called ``_write_baseline(current)``, which re-pins to whatever is on
    the board right now, additions included. So the one surface that can actually violate the ratchet
    was the one surface with no guard on it, and ``test_the_baseline_only_shrinks`` tests ``--check``
    (where a cleared finding is reported stale rather than failing) — the invariant was verified
    exactly where it could not be broken.

    That gap is not theoretical, it is a loaded trap sitting in this gate's own output. When a finding
    clears, ``--check`` prints ``note baseline entry no longer reproduces (run --update to drop it)``.
    Measured 2026-08-07 on PR #2001 (the board publication backlog): 15 entries had cleared and were
    advertising exactly that instruction, while 8 NEW partner-lane findings were failing in the same
    run. Following the gate's own advice to clear the noise would have silently accepted all 8 —
    new disclosures on a PUBLIC head, landed by an agent trying to tidy up, with the diff reading as
    a routine re-pin.

    So growth is refused by default and named line by line. It stays *possible* (a genuinely accepted
    disclosure, or a newly onboarded partner lane whose rows are already public) but only behind an
    explicit ``--accept-new-disclosures``, because that is a disclosure decision and it should have to
    be spelled out in the command someone ran. Shrinking needs no flag: dropping a cleared finding
    tightens the gate, which is the direction the ratchet is supposed to turn.
    """
    baseline = _baseline()
    added = [line for line in current if line not in baseline]
    dropped = sorted(baseline - set(current))

    if added and not accept_new:
        print(f"FAIL board-partition: --update would GROW the baseline by {len(added)} finding(s).")
        for line in added:
            print(f"  would-add {line}")
        print(
            "The baseline may only SHRINK. Growing it accepts a NEW disclosure on a public head — a "
            "human decision, not a re-pin. These rows' owner is the broker scrub, not this predicate "
            "(TABVLARIVS is the board's only logical writer). If the disclosure is genuinely accepted, "
            "say so explicitly: --update --accept-new-disclosures."
        )
        if dropped:
            print(
                f"note {len(dropped)} cleared entry(ies) would have been dropped by this re-pin; "
                "the refusal keeps them pinned. Shrink alone is available once the new findings are gone."
            )
        return 1

    _write_baseline(current)
    verb = "re-pinned" if not added else f"re-pinned with {len(added)} ACCEPTED new disclosure(s)"
    print(
        f"board-partition: baseline {verb} — {len(current)} finding(s), {len(dropped)} dropped -> {_baseline_label()}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 on a finding outside the baseline")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--update", action="store_true", help="re-pin the baseline to current findings (shrink-only)")
    parser.add_argument(
        "--accept-new-disclosures",
        action="store_true",
        help="with --update: also ADD new findings. Accepting a new disclosure on a public head is a "
        "human decision, never a re-pin — see the growth refusal for why this needs saying out loud.",
    )
    args = parser.parse_args()

    try:
        current = findings()
    except PartitionRegistryError as exc:
        # An unverifiable boundary is never a green one.
        print(f"FAIL board-partition: registry unreadable — {exc}")
        return 1

    if args.update:
        return _update(current, accept_new=args.accept_new_disclosures)

    baseline = _baseline()
    new = [line for line in current if line not in baseline]
    stale = sorted(baseline - set(current))
    counts = {kind: sum(1 for line in current if line.startswith(kind)) for kind in ("row", "content", "slug")}

    if args.json:
        print(json.dumps({"counts": counts, "new": new, "stale": stale, "total": len(current)}, indent=2))
    else:
        print(f"board-partition: {len(current)} finding(s) — {counts}")
        for line in new:
            print(f"FAIL {line}")
        for line in stale:
            print(f"note baseline entry no longer reproduces (run --update to drop it): {line}")
        if not new:
            print(f"ok    no new partner-lane content on the public board ({len(baseline)} baselined)")

    if args.check and new:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
