#!/usr/bin/env python3
"""
Niche-Funnel Engine — Instance Rules #1-7.

Rule #1 — Completeness: every instance must carry the engine's required keys
(instance, engagement, niche, funnel, offers, cadence, kpis, human_gates).

Rule #2 — Gated Stages: the funnel is a non-empty stage list and every stage
names its level, entry/exit, method, artifact, and a human gate.

Rule #3 — Manual Mode: no autonomic-delivery language anywhere in the config.
The engine stages drafts; a human fires every outbound act.

Rule #4 — No Cold-Pressure Tactics: scraping/harvesting/bulk-DM language may
appear only under retired_tactics — never in a live method or cadence.

Rule #5 — Slot Integrity: every {{TOKEN}} placeholder in the file must be
declared under owed_slots (an owed human atom), never a silent fabrication.

Rule #6 — Offer Integrity: the offer ladder is non-empty, every tier is fully
specified, and no placeholder text stands in for a real offer.

Rule #7 — Engagement Link: the instance must point at an engagement record
that actually exists (the consulting organ's rules govern that record).

Usage:
  python organs/consulting/funnel/validate-funnel.py path/to/instance.yaml
  python organs/consulting/funnel/validate-funnel.py --fleet
  python organs/consulting/funnel/validate-funnel.py --fleet --quiet
  echo $?   # 0 = all pass, 1 = violations found
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

REQUIRED_KEYS: list[str] = [
    "instance",
    "engagement",
    "niche",
    "funnel",
    "offers",
    "cadence",
    "kpis",
    "human_gates",
]

REQUIRED_STAGE_KEYS: list[str] = [
    "level",
    "name",
    "entry",
    "exit",
    "method",
    "artifact",
    "human_gate",
]

AUTONOMIC_KEYWORDS: list[str] = [
    "autonomous",
    "auto-send",
    "auto-dm",
    "auto-reply",
    "auto-bill",
    "self-executing",
    "unattended",
]

COLD_PRESSURE_KEYWORDS: list[str] = [
    "scrap",
    "harvest",
    "bulk dm",
    "mass dm",
    "follower export",
    "cold blast",
]

PLACEHOLDER_PATTERNS: list[str] = [
    "todo",
    "tbd",
    "fixme",
    "placeholder",
    "to be determined",
]

SLOT_RE = re.compile(r"\{\{([A-Za-z0-9_]+)\}\}")

REQUIRED_TIER_KEYS: list[str] = ["tier", "name", "price", "delivery"]


def _negated(line: str) -> bool:
    """A line that forbids a tactic is not a violation of it."""
    stripped = line.strip().strip("-\"' ").lower()
    return stripped.startswith(("no ", "not ", "never ")) or "never" in stripped


def _walk_strings(node: Any) -> list[str]:
    """Flatten every string value in a YAML tree."""
    out: list[str] = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_walk_strings(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_walk_strings(item))
    return out


def _validate_one(path: Path) -> list[str]:
    """Return a list of violation strings for one instance file (empty = pass)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read file: {exc}"]

    try:
        doc: Any = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"]

    if not isinstance(doc, dict):
        return ["document is not a YAML mapping"]

    violations: list[str] = []

    # Rule #1 — Completeness
    for key in REQUIRED_KEYS:
        if not doc.get(key):
            violations.append(f"Rule #1 violation: missing required key {key!r}")

    # Rule #2 — Gated Stages
    funnel = doc.get("funnel")
    if not isinstance(funnel, list) or not funnel:
        violations.append("Rule #2 violation: funnel must be a non-empty stage list")
    else:
        for i, stage in enumerate(funnel):
            if not isinstance(stage, dict):
                violations.append(f"Rule #2 violation: stage {i} is not a mapping")
                continue
            label = str(stage.get("level", f"stage {i}"))
            for key in REQUIRED_STAGE_KEYS:
                value = stage.get(key)
                if not isinstance(value, str) or not value.strip():
                    violations.append(
                        f"Rule #2 violation: {label} missing or empty {key!r} — every stage names its gate and artifact"
                    )

    # Rule #3 — Manual Mode (checked per string, negation-aware)
    for text in _walk_strings(doc):
        lower = text.lower()
        for kw in AUTONOMIC_KEYWORDS:
            if kw in lower and not _negated(text):
                violations.append(
                    f"Rule #3 violation: autonomic keyword {kw!r} in {text[:60]!r} — "
                    "the engine stages drafts; humans fire every send"
                )

    # Rule #4 — No Cold-Pressure Tactics outside retired_tactics
    retired = doc.get("retired_tactics", [])
    live_doc = {k: v for k, v in doc.items() if k != "retired_tactics"}
    if not isinstance(retired, list):
        violations.append("Rule #4 violation: retired_tactics must be a list")
    for text in _walk_strings(live_doc):
        lower = text.lower()
        for kw in COLD_PRESSURE_KEYWORDS:
            if kw in lower and not _negated(text):
                violations.append(
                    f"Rule #4 violation: cold-pressure keyword {kw!r} in a live "
                    f"config value {text[:60]!r} — allowed only under retired_tactics"
                )

    # Rule #5 — Slot Integrity
    owed_slots = doc.get("owed_slots", [])
    owed_set = {str(s) for s in owed_slots} if isinstance(owed_slots, list) else set()
    for token in sorted(set(SLOT_RE.findall(raw))):
        if token not in owed_set:
            violations.append(
                f"Rule #5 violation: slot {{{{{token}}}}} is not declared in "
                "owed_slots — every empty slot must be an owed human atom"
            )

    # Rule #6 — Offer Integrity
    offers = doc.get("offers")
    ladder = offers.get("ladder") if isinstance(offers, dict) else None
    if not isinstance(ladder, list) or not ladder:
        violations.append("Rule #6 violation: offers.ladder must be a non-empty list")
    else:
        for i, tier in enumerate(ladder):
            if not isinstance(tier, dict):
                violations.append(f"Rule #6 violation: offer tier {i} is not a mapping")
                continue
            for key in REQUIRED_TIER_KEYS:
                if not str(tier.get(key, "")).strip():
                    violations.append(f"Rule #6 violation: offer tier {i} missing {key!r}")
        for text in _walk_strings(offers):
            lower = text.lower()
            for pat in PLACEHOLDER_PATTERNS:
                if pat in lower:
                    violations.append(f"Rule #6 violation: offers contain placeholder text {pat!r}")

    # Rule #7 — Engagement Link
    engagement = doc.get("engagement")
    if isinstance(engagement, str) and engagement.strip():
        if not Path(engagement).exists():
            violations.append(f"Rule #7 violation: engagement record {engagement!r} does not exist")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate niche-funnel instance files against Engine Rules #1-7. "
            "Run from the repo root (engagement paths resolve relative to it)."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="INSTANCE_YAML",
        help="one or more funnel instance YAML files to validate",
    )
    parser.add_argument(
        "--fleet",
        action="store_true",
        help="discover all instance YAML files under organs/consulting/funnel/instances/",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress per-file output; exit code only",
    )
    args = parser.parse_args()

    targets: list[Path] = []

    if args.fleet:
        inst_dir = Path("organs/consulting/funnel/instances")
        targets = sorted(inst_dir.rglob("*.yaml")) if inst_dir.exists() else []
        if not targets:
            if not args.quiet:
                print("no instance files found under organs/consulting/funnel/instances/")
                print("(this is normal before the first instance ships)")
            return 0
    elif args.paths:
        targets = [Path(p) for p in args.paths]
    else:
        parser.print_help()
        return 2

    total = len(targets)
    passed = 0
    failed = 0

    for path in targets:
        violations = _validate_one(path)
        if not violations:
            passed += 1
            if not args.quiet:
                print(f"PASS  {path}")
        else:
            failed += 1
            if not args.quiet:
                print(f"FAIL  {path}")
                for v in violations:
                    print(f"      violation: {v}")

    if not args.quiet:
        print(f"\n{'─' * 60}")
        print(f"  {passed}/{total} passed  |  {failed} violation(s)")
        if failed == 0:
            print("  Niche-Funnel Engine Rules #1-7: all checks passed.")
        else:
            print("  Niche-Funnel Engine Rules #1-7: violations found.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
