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
  python3 scripts/check-board-partition.py --update   # re-pin after a real broker scrub
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
BASELINE = ROOT / "institutio" / "governance" / "board-partition-baseline.txt"

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
    )
    BASELINE.write_text(header + "\n".join(current) + ("\n" if current else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit 1 on a finding outside the baseline")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--update", action="store_true", help="re-pin the baseline to current findings")
    args = parser.parse_args()

    try:
        current = findings()
    except PartitionRegistryError as exc:
        # An unverifiable boundary is never a green one.
        print(f"FAIL board-partition: registry unreadable — {exc}")
        return 1

    if args.update:
        _write_baseline(current)
        print(f"board-partition: baseline re-pinned with {len(current)} finding(s) -> {BASELINE.relative_to(ROOT)}")
        return 0

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
