#!/usr/bin/env python3
"""A-MAVS-OLEVM artist-organ rules #1-6."""

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


STANDINGS = ["RAW", "CATALOGED", "CURATED", "STAGED", "EXHIBITED", "DORMANT", "AT-RISK"]
ADVANCING = ["RAW", "CATALOGED", "CURATED", "STAGED", "EXHIBITED"]
REQUIRED_PRIMITIVES = ["member", "mandate", "standing", "standard", "governance"]
PLACEHOLDERS = ["todo", "tbd", "fixme", "placeholder", "to be determined"]
OVERREACH = [
    "autonomous publication",
    "publish without artist approval",
    "alter original source files",
    "create art on behalf",
    "treat generated output as original",
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


def _claim_doc(doc: dict[str, Any]) -> dict[str, Any]:
    claim = {k: v for k, v in doc.items() if k != "governance"}
    governance = doc.get("governance")
    if isinstance(governance, dict):
        claim["governance"] = {k: v for k, v in governance.items() if k != "forbidden_acts"}
    return claim


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
    if standing not in STANDINGS:
        violations.append(f"Rule #1 violation: standing {standing!r} is not a valid archive state")

    next_standing = str(doc.get("next_standing") or "").upper()
    if standing in ADVANCING and next_standing in ADVANCING:
        if ADVANCING.index(next_standing) <= ADVANCING.index(standing):
            violations.append(
                f"Rule #1 violation: next_standing {next_standing!r} does not advance {standing!r}"
            )

    governance = doc.get("governance")
    if not isinstance(governance, dict) or governance.get("artist_gate") is not True:
        violations.append("Rule #2 violation: governance.artist_gate must be true")

    gates = doc.get("human_gates")
    if not isinstance(gates, list) or not gates:
        violations.append("Rule #2 violation: human_gates must name at least one artist gate")

    standard = doc.get("standard")
    evidence = standard.get("evidence") if isinstance(standard, dict) else None
    if not isinstance(evidence, list) or not evidence:
        violations.append("Rule #4 violation: standard.evidence must name real evidence")
    else:
        for item in evidence:
            lowered = str(item).lower()
            for placeholder in PLACEHOLDERS:
                if placeholder in lowered:
                    violations.append(
                        f"Rule #4 violation: evidence item {item!r} contains placeholder {placeholder!r}"
                    )

    claims = _text(_claim_doc(doc)).lower()
    for phrase in OVERREACH:
        if phrase in claims:
            violations.append(f"Rule #5 violation: overreach claim present: {phrase!r}")

    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts.get("next_reviewable_output"):
        violations.append("Rule #6 violation: artifacts.next_reviewable_output is required")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--chambers", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    paths = sorted((base / "chambers").glob("*.yaml")) if args.chambers else args.paths
    if not paths:
        parser.error("provide path(s) or --chambers")

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

