#!/usr/bin/env python3
"""Observation Organism rules #1-6.

Validates the Observation Organ governance, 5-primitive kernel mapping,
Bifrons portal status, and unified observation feed integrity.

Rules:
  Rule #1 - Observation Standing: Valid state (RAW -> OBSERVING -> ANALYZED -> RECONCILED -> PROPOSED -> CLOSED)
            with forward next_standing before CLOSED.
  Rule #2 - Human Gate: Every record must be human-gated (governance.human_gated: true) and name at least one human gate.
  Rule #3 - 5-Primitive Completeness: Every record must capture Member, Mandate, Standing, Standard, and Governance.
  Rule #4 - Evidence Integrity: Real evidence artifacts referenced; no placeholder text.
  Rule #5 - No Overreach: Read-only external research boundary; no autonomous sends or PR creations.
  Rule #6 - Feed Schema Validation: logs/observation/feed-latest.json and feed.jsonl adhere to schema limen.observation.feed.v1.

Usage:
  python organs/observation/validate-observation.py path/to/record.yaml
  python organs/observation/validate-observation.py
  python organs/observation/validate-observation.py --fleet
  python organs/observation/validate-observation.py --fleet --quiet
  python organs/observation/validate-observation.py --checklist
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Any

# Ensure PyYAML is available
try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# Ensure cli/src is on sys.path
ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.observation import SCHEMA_V1, check_feed, emit_feed_record  # noqa: E402

STANDINGS = ["RAW", "OBSERVING", "ANALYZED", "RECONCILED", "PROPOSED", "CLOSED"]
ADVANCING = ["RAW", "OBSERVING", "ANALYZED", "RECONCILED", "PROPOSED"]
REQUIRED_PRIMITIVES = ["member", "mandate", "standing", "standard", "governance"]
PLACEHOLDER_PATTERNS = ["todo", "tbd", "fixme", "placeholder", "to be determined"]
OVERREACH_PATTERNS = [
    "autonomous send",
    "autonomous message",
    "autonomous outreach",
    "autonomous pr",
    "publish without operator approval",
    "alter original source files",
    "unauthorized mutation",
]

RULES: list[tuple[int, str]] = [
    (1, "Observation Standing: valid state, forward next_standing before CLOSED"),
    (2, "Human Gate: governance.human_gated true plus at least one human gate"),
    (3, "5-Primitive Completeness: member, mandate, standing, standard, governance"),
    (4, "Evidence Integrity: real standard.evidence, no placeholder text"),
    (5, "No Overreach: read-only research boundary; no autonomous sends or PR creation"),
    (6, f"Feed Schema Validation: logs/observation/ matches {SCHEMA_V1}"),
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


def _validate_record(path: Path) -> list[str]:
    """Validate a single Observation Organ YAML record against Rules #1-5."""
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"cannot read file: {exc}"]
    except yaml.YAMLError as exc:
        return [f"YAML parse error: {exc}"]

    if not isinstance(doc, dict):
        return ["document is not a YAML mapping"]

    violations: list[str] = []

    # Rule #3: 5-Primitive Completeness
    for primitive in REQUIRED_PRIMITIVES:
        if not doc.get(primitive):
            violations.append(f"Rule #3 violation: missing required primitive {primitive!r}")

    # Rule #1: Observation Standing
    standing = _standing(doc)
    if standing not in STANDINGS:
        violations.append(
            f"Rule #1 violation: standing {standing!r} is not a valid observation standing ({' -> '.join(STANDINGS)})"
        )

    next_standing = str(doc.get("next_standing") or "").upper()
    if standing in ADVANCING:
        if not next_standing:
            violations.append("Rule #1 violation: next_standing is required until reaching CLOSED")
        elif next_standing not in STANDINGS:
            violations.append(f"Rule #1 violation: next_standing {next_standing!r} is not in {' -> '.join(STANDINGS)}")
        elif STANDINGS.index(next_standing) <= STANDINGS.index(standing):
            violations.append(f"Rule #1 violation: next_standing {next_standing!r} does not advance {standing!r}")
    elif standing == "CLOSED" and next_standing and next_standing != "CLOSED":
        violations.append(f"Rule #1 violation: CLOSED is terminal; got next_standing {next_standing!r}")

    # Rule #2: Human Gate
    governance = doc.get("governance")
    if not isinstance(governance, dict) or governance.get("human_gated") is not True:
        violations.append("Rule #2 violation: governance.human_gated must be true")

    gates = doc.get("human_gates")
    if not isinstance(gates, list) or not gates:
        violations.append("Rule #2 violation: human_gates must name at least one human gate")

    # Rule #4: Evidence Integrity
    standard = doc.get("standard")
    evidence = standard.get("evidence") if isinstance(standard, dict) else None
    if not isinstance(evidence, list) or not evidence:
        violations.append("Rule #4 violation: standard.evidence must name real evidence")
    else:
        for item in evidence:
            lowered = str(item).lower()
            for placeholder in PLACEHOLDER_PATTERNS:
                if placeholder in lowered:
                    violations.append(f"Rule #4 violation: evidence item {item!r} contains placeholder {placeholder!r}")

    # Rule #5: No Overreach
    claim_doc = {k: v for k, v in doc.items() if k != "governance"}
    if isinstance(governance, dict):
        claim_doc["governance"] = {k: v for k, v in governance.items() if k != "forbidden_acts"}
    claims = _text(claim_doc).lower()
    for phrase in OVERREACH_PATTERNS:
        if phrase in claims:
            violations.append(f"Rule #5 violation: overreach claim present: {phrase!r}")

    # Reviewable output check
    artifacts = doc.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts.get("next_reviewable_output"):
        violations.append("Rule #4 violation: artifacts.next_reviewable_output is required")

    return violations


def _validate_organ_structure(base: Path) -> list[str]:
    """Validate Observation Organ markdown doctrine and kernel mapping."""
    violations: list[str] = []
    kernel_md = base / "KERNEL.md"
    charter_md = base / "CHARTER.md"
    macro_face_md = base / "MACRO-FACE.md"
    micro_face_md = base / "MICRO-FACE.md"

    for required_file in (kernel_md, charter_md, macro_face_md, micro_face_md):
        if not required_file.exists():
            violations.append(f"Rule #3 violation: missing organ doctrine file {required_file.relative_to(ROOT)}")

    if kernel_md.exists():
        content = kernel_md.read_text(encoding="utf-8").lower()
        for prim in REQUIRED_PRIMITIVES:
            if prim not in content:
                violations.append(f"Rule #3 violation: KERNEL.md does not define 5-primitive mapping for {prim!r}")

    bifrons_dir = base / "bifrons"
    if not (bifrons_dir / "PORTAL.md").exists():
        violations.append(f"Rule #3 violation: missing Bifrons portal surface {bifrons_dir / 'PORTAL.md'}")

    return violations


def _validate_bifrons_status() -> list[str]:
    """Probe Bifrons portal status (fail-open)."""
    script_path = ROOT / "scripts" / "bifrons-organ.py"
    if not script_path.exists():
        return ["missing scripts/bifrons-organ.py"]
    try:
        spec = importlib.util.spec_from_file_location("bifrons_organ_val", script_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            res = mod.portal_counts()
            if not isinstance(res, dict):
                return ["bifrons portal_counts() did not return a dict"]
    except Exception as exc:
        return [f"bifrons portal probe error: {exc}"]
    return []


def _validate_feed(base_root: Path) -> list[str]:
    """Validate Observation Feed against schema limen.observation.feed.v1."""
    log_dir = base_root / "logs" / "observation"
    if not (log_dir / "feed.jsonl").exists() or not (log_dir / "feed-latest.json").exists():
        try:
            emit_feed_record(base_dir=base_root)
        except Exception as exc:
            return [f"Rule #6 violation: auto-bootstrap feed failed: {exc}"]
    ok, errors = check_feed(base_dir=base_root)
    if not ok:
        return [f"Rule #6 violation: {err}" for err in errors]
    return []


def _fleet_paths(base: Path) -> list[Path]:
    records_dir = base / "records"
    if records_dir.is_dir():
        return sorted(records_dir.glob("*.yaml"))
    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Observation Organ governance, 5-primitive kernel mapping, and telemetry feed."
    )
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--fleet", action="store_true", help="validate all records and organ health")
    parser.add_argument("--quiet", action="store_true", help="suppress success output")
    parser.add_argument("--checklist", action="store_true", help="print the six executable rules and exit")
    parser.add_argument("--root", type=Path, default=ROOT, help="custom repository root")

    args = parser.parse_args()

    if args.checklist:
        for number, rule in RULES:
            print(f"Rule #{number}: {rule}")
        return 0

    base = Path(__file__).resolve().parent
    repo_root = args.root.resolve()

    # When run bare (no paths and no explicit flag), default to --fleet mode
    is_fleet = args.fleet or len(args.paths) == 0
    paths = _fleet_paths(base) if is_fleet else args.paths

    failures = 0
    all_violations: dict[str, list[str]] = {}

    # 1. Validate individual YAML records
    for path in paths:
        violations = _validate_record(path)
        if violations:
            failures += 1
            all_violations[str(path)] = violations
        elif not args.quiet:
            print(f"PASS  {path}")

    # 2. In fleet / bare mode, validate organ structure, bifrons status, and observation feed
    if is_fleet:
        struct_violations = _validate_organ_structure(base)
        if struct_violations:
            failures += 1
            all_violations["organ_structure"] = struct_violations
        elif not args.quiet:
            print("PASS  organ_structure (KERNEL.md, CHARTER.md, 5-primitive mapping)")

        bifrons_violations = _validate_bifrons_status()
        if bifrons_violations:
            failures += 1
            all_violations["bifrons_status"] = bifrons_violations
        elif not args.quiet:
            print("PASS  bifrons_status (portal store probe)")

        feed_violations = _validate_feed(repo_root)
        if feed_violations:
            failures += 1
            all_violations["observation_feed"] = feed_violations
        elif not args.quiet:
            print(f"PASS  observation_feed ({SCHEMA_V1})")

    # Output results
    if failures:
        print()
        for target, viols in all_violations.items():
            print(f"FAIL  {target}")
            for v in viols:
                print(f"  - {v}")
        if not args.quiet:
            print()
            print(f"Validation FAILED: {failures} check(s) failed.")
        return 1

    if not args.quiet:
        print()
        total_checks = len(paths) + (3 if is_fleet else 0)
        print(f"{total_checks}/{total_checks} passed — Observation Organ fully valid.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
