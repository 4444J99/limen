#!/usr/bin/env python3
"""Social Organism rules #1-6.

Usage:
  python organs/social/validate-social.py path/to/engagement.yaml
  python organs/social/validate-social.py --fleet
  python organs/social/validate-social.py --fleet --quiet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(2)


POSTURES = ["ACTIVE", "WARM", "DORMANT", "STRAINED", "BROKEN", "PROTECTED"]
POSTURE_SET = set(POSTURES)
REQUIRED_PRIMITIVES = ["member", "mandate", "standing", "standard", "governance"]
PLACEHOLDER_PATTERNS = ["todo", "tbd", "fixme", "placeholder", "to be determined"]
OVERREACH_PATTERNS = [
    "autonomous send",
    "autonomous message",
    "autonomous outreach",
    "surveillance",
    "manipulat",
    "score of a person",
]


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_text(v) for v in value)
    return str(value or "")


def _standing(doc: dict[str, Any]) -> str:
    raw = doc.get("standing")
    if isinstance(raw, dict):
        return str(raw.get("current", "")).upper()
    return str(raw or "").upper()


def _validate_one(path: Path) -> list[str]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"cannot read file: {exc}"]
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"]

    if not isinstance(doc, dict):
        return ["document is not a YAML mapping"]

    violations: list[str] = []

    for primitive in REQUIRED_PRIMITIVES:
        if not doc.get(primitive):
            violations.append(f"Rule #3 violation: missing required primitive {primitive!r}")

    standing = _standing(doc)
    if standing not in POSTURE_SET:
        violations.append(
            f"Rule #1 violation: standing {standing!r} is not in {' -> '.join(POSTURES)}"
        )

    next_standing = str(doc.get("next_standing") or "").upper()
    if standing in POSTURE_SET and next_standing in POSTURE_SET:
        idx = POSTURES.index(standing)
        nidx = POSTURES.index(next_standing)
        if next_standing != "PROTECTED" and nidx <= idx:
            violations.append(
                f"Rule #1 violation: next_standing {next_standing!r} does not advance {standing!r}"
            )

    governance = doc.get("governance")
    if not isinstance(governance, dict) or governance.get("manual_mode") is not True:
        violations.append("Rule #2 violation: governance.manual_mode must be true")

    gates = governance.get("human_gates") if isinstance(governance, dict) else None
    if not isinstance(gates, list) or not gates:
        violations.append("Rule #2 violation: human_gates must name at least one human gate")

    never_auto = governance.get("never_autonomous") if isinstance(governance, dict) else None
    if not isinstance(never_auto, list) or not never_auto:
        violations.append(
            "Rule #2 violation: governance.never_autonomous must list forbidden autonomous acts"
        )

    standard = doc.get("standard")
    evidence = doc.get("artifacts", {}).get("evidence") if isinstance(doc.get("artifacts"), dict) else None
    if not isinstance(evidence, list) or not evidence:
        violations.append("Rule #4 violation: artifacts.evidence must list at least one evidence item")
    else:
        for item in evidence:
            lowered = str(item).lower()
            for pattern in PLACEHOLDER_PATTERNS:
                if pattern in lowered:
                    violations.append(
                        f"Rule #4 violation: evidence item {item!r} contains placeholder {pattern!r}"
                    )

    claim_doc = {k: v for k, v in doc.items() if k != "governance"}
    if isinstance(governance, dict):
        claim_doc["governance"] = {
            k: v for k, v in governance.items() if k != "forbidden_acts"
        }
    blob = _text(claim_doc).lower()
    for pattern in OVERREACH_PATTERNS:
        if pattern in blob:
            violations.append(f"Rule #5 violation: overreach pattern present: {pattern!r}")

    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts.get("next_reviewable_output"):
        violations.append("Rule #6 violation: artifacts.next_reviewable_output is required")

    return violations


def _fleet_paths(base: Path) -> list[Path]:
    return sorted((base / "engagements").glob("*.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--fleet", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    paths = _fleet_paths(base) if args.fleet else args.paths
    if not paths:
        parser.error("provide path(s) or --fleet")

    failures = 0
    for path in paths:
        violations = _validate_one(path)
        if violations:
            failures += 1
            print(f"FAIL  {path}")
            for violation in violations:
                print(f"  - {violation}")
        elif not args.quiet:
            print(f"PASS  {path}")

    if not args.quiet:
        print()
        print(f"{len(paths) - failures}/{len(paths)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
