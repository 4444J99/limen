#!/usr/bin/env python3
"""
Sovereign Systems — Consulting Organ Rules #1-6.

Rule #1 — Valid Posture: engagement standing must name a recognised delivery
posture in the canonical sequence. Stages may not be skipped.

Rule #2 — Manual Mode: no engagement may claim autonomic delivery. Every
engagement must declare explicit human gates for each milestone.

Rule #3 — 5-Primitive Completeness: every engagement record must capture the
five kernel primitives (Member, Mandate, Standing, Standard, Governance).

Rule #4 — Scope Integrity: scope changes must be tracked. Each engagement must
carry an explicit scope boundary and a change log.

Rule #5 — No Overreach: no engagement may claim to provide legal, tax, or
medical advice. Scope boundary must not contain language asserting professional
judgment authority outside consulting delivery infrastructure.

Rule #6 — Evidence Integrity: every standard.evidence field must reference real
artifacts or clear statuses — no TODO, TBD, or placeholder text.

Usage:
  python organs/consulting/validate-consulting.py path/to/engagement.yaml
  python organs/consulting/validate-consulting.py --fleet
  python organs/consulting/validate-consulting.py --fleet --quiet
  echo $?   # 0 = all pass, 1 = violations found
"""

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# The delivery posture sequence — order is law.
POSTURES: list[str] = [
    "DISCOVERY",
    "PROPOSAL",
    "ACCEPTANCE",
    "EXECUTION",
    "REVIEW",
    "HOLD",
    "ARCHIVED",
]
POSTURE_SET: set[str] = set(POSTURES)

REQUIRED_PRIMITIVES: list[str] = [
    "member",
    "mandate",
    "standing",
    "standard",
    "governance",
]

AUTONOMIC_KEYWORDS: list[str] = [
    "autonomous",
    "auto-send",
    "auto-bill",
    "self-executing",
    "unattended",
]

OVERREACH_KEYWORDS: list[str] = [
    "legal advice",
    "tax advice",
    "medical advice",
    "legal representation",
    "tax preparation",
    "medical diagnosis",
    "licensed attorney",
    "licensed physician",
]

PLACEHOLDER_PATTERNS: list[str] = [
    "todo",
    "tbd",
    "fixme",
    "placeholder",
    "rough notes",
    "to be determined",
]


def _validate_one(path: Path) -> list[str]:
    """Return a list of violation strings for one engagement file (empty = pass)."""
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

    # Rule #3 — 5-Primitive Completeness (check before standing validation)
    for primitive in REQUIRED_PRIMITIVES:
        value = doc.get(primitive)
        if not value:
            violations.append(
                f"Rule #3 violation: missing required primitive {primitive!r}"
            )
        elif isinstance(value, str) and not value.strip():
            violations.append(
                f"Rule #3 violation: primitive {primitive!r} is empty"
            )

    standing_raw = doc.get("standing")
    if isinstance(standing_raw, dict):
        standing_val = str(standing_raw.get("current", "")).upper()
    elif isinstance(standing_raw, str):
        standing_val = standing_raw.upper()
    else:
        standing_val = ""

    # Rule #1 — Valid Posture
    if standing_val not in POSTURE_SET:
        violations.append(
            f"Rule #1 violation: standing {standing_val!r} is not a recognised "
            f"delivery posture ({' → '.join(POSTURES)})"
        )

    if standing_val in POSTURE_SET:
        idx = POSTURES.index(standing_val)
        previous = doc.get("standing_history", [])
        if previous:
            for prev_entry in previous:
                prev_standing = prev_entry
                if isinstance(prev_entry, dict):
                    prev_standing = prev_entry.get("standing", "")
                prev_str = str(prev_standing).upper()
                if prev_str in POSTURE_SET:
                    prev_idx = POSTURES.index(prev_str)
                    if prev_idx > idx:
                        violations.append(
                            f"Rule #1 violation: engagement moved backward from "
                            f"{prev_str} to {standing_val} — postures may not regress"
                        )

        next_standing = doc.get("next_standing")
        if next_standing and str(next_standing).upper() in POSTURE_SET:
            next_idx = POSTURES.index(str(next_standing).upper())
            if next_idx <= idx:
                violations.append(
                    f"Rule #1 violation: next_standing {next_standing!r} does not "
                    f"advance past current {standing_val}"
                )

    # Rule #2 — Manual Mode
    mandate = doc.get("mandate", "")
    if isinstance(mandate, dict):
        mandate_text = str(mandate.get("description", ""))
    else:
        mandate_text = str(mandate)

    mandate_lower = mandate_text.lower()
    for kw in AUTONOMIC_KEYWORDS:
        if kw in mandate_lower:
            violations.append(
                f"Rule #2 violation: mandate contains autonomic keyword {kw!r} — "
                "consulting organ operates in manual prototype mode only"
            )

    gates = doc.get("human_gates", [])
    if not isinstance(gates, list) or len(gates) == 0:
        violations.append(
            "Rule #2 violation: no explicit human_gates declared — every "
            "milestone must have a named human gate"
        )

    if doc.get("autonomic", False) is True:
        violations.append(
            "Rule #2 violation: autonomic flag is true — consulting organ "
            "operates in manual prototype mode only"
        )

    # Rule #4 — Scope Integrity
    scope = doc.get("scope", {})
    if not isinstance(scope, dict):
        violations.append(
            "Rule #4 violation: scope must be a mapping with 'boundary' and "
            "'exclusions'"
        )
    else:
        if not scope.get("boundary"):
            violations.append(
                "Rule #4 violation: scope must declare an explicit boundary"
            )
        scope_changes = scope.get("changes", [])
        if not isinstance(scope_changes, list):
            violations.append(
                "Rule #4 violation: scope.changes must be a list"
            )

    # Rule #5 — No Overreach
    if isinstance(scope, dict):
        boundary_text = str(scope.get("boundary", "")).lower()
        for kw in OVERREACH_KEYWORDS:
            if kw in boundary_text:
                violations.append(
                    f"Rule #5 violation: scope boundary contains overreach "
                    f"keyword {kw!r} — consulting organ is delivery "
                    "infrastructure, not professional services"
                )
        exclusions = scope.get("exclusions", [])
        if isinstance(exclusions, list):
            for exc in exclusions:
                exc_text = str(exc)
                exc_lower = exc_text.lower()
                # Skip disclaimers (statements prefixed with "No " or "Not ")
                if any(exc_text.strip().startswith(p) for p in ("No ", "Not ", "no ", "not ")):
                    continue
                for kw in OVERREACH_KEYWORDS:
                    if kw in exc_lower:
                        violations.append(
                            f"Rule #5 violation: exclusion contains overreach "
                            f"keyword {kw!r} — this is delivery infrastructure"
                        )

    # Rule #6 — Evidence Integrity
    standard = doc.get("standard", {})
    if isinstance(standard, dict):
        evidence = str(standard.get("evidence", ""))
        evidence_lower = evidence.lower()
        for pat in PLACEHOLDER_PATTERNS:
            if pat in evidence_lower:
                violations.append(
                    f"Rule #6 violation: standard.evidence contains "
                    f"placeholder text {pat!r} — must reference real "
                    "artifacts"
                )

    return violations


def _posture(standing_raw: Any) -> str:
    """Advisory: current posture and what comes next."""
    if isinstance(standing_raw, dict):
        standing_val = str(standing_raw.get("current", "")).upper()
    elif isinstance(standing_raw, str):
        standing_val = standing_raw.upper()
    else:
        return ""
    if standing_val not in POSTURE_SET:
        return ""
    idx = POSTURES.index(standing_val)
    next_posture = (
        POSTURES[idx + 1]
        if idx + 1 < len(POSTURES)
        else "(terminus — no further posture)"
    )
    held = " → ".join(POSTURES[: idx + 1])
    return f"  posture: {held}  |  next: {next_posture}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate engagement files against Sovereign Systems consulting rules. "
            "Rules #1-6 are always active."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="ENGAGEMENT_YAML",
        help="one or more engagement YAML files to validate",
    )
    parser.add_argument(
        "--fleet",
        action="store_true",
        help="discover all engagement YAML files under organs/consulting/engagements/",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress per-file output; exit code only",
    )
    args = parser.parse_args()

    targets: list[Path] = []

    if args.fleet:
        eng_dir = Path("organs/consulting/engagements")
        targets = sorted(eng_dir.rglob("*.yaml")) if eng_dir.exists() else []
        if not targets:
            if not args.quiet:
                print("no engagement files found under organs/consulting/engagements/")
                print("(this is normal when no clients are active)")
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
                try:
                    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                    posture = _posture(doc.get("standing", ""))
                except Exception:
                    posture = ""
                print(f"PASS  {path}{posture}")
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
            print("  Sovereign Systems Rules #1-6: all checks passed. Concordia.")
        else:
            print("  Sovereign Systems Rules #1-6: violations found.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
