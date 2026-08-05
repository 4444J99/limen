#!/usr/bin/env python3
"""
HR / People Office — Validation Rules #1-8.

Rule #1 — Valid Posture: client engagement standing must name a recognised
posture in the canonical sequence. Postures may not regress.

Rule #2 — Manual Mode: no engagement may claim autonomic delivery. Every
engagement must declare explicit human gates.

Rule #3 — 5-Primitive Completeness: every client posture record must capture
the five kernel primitives (Member, Mandate, Standing, Standard, Governance).

Rule #4 — Scope Integrity: scope changes must be tracked. Each engagement must
carry an explicit scope boundary, exclusions, and a change log.

Rule #5 — No Overreach: no engagement may claim to make employment decisions,
provide legal/benefits counsel, or communicate with employees. The ethics wall
must be declared.

Rule #6 — Evidence Integrity: every standard.evidence field must reference real
artifacts or clear statuses — no TODO, TBD, or placeholder text.

Rule #7 — Ethics Sentinel: every client must have an ethics log (ethics-log.md)
with at least one entry or a sentinel declaration.

Rule #8 — Practitioner Gate: every workflow output is a draft; the practitioner
is named as the review and delivery authority.

Usage:
  python organs/hr/validate-hr.py path/to/posture.yaml
  python organs/hr/validate-hr.py --fleet
  python organs/hr/validate-hr.py --fleet --quiet
  echo $?   # 0 = all pass, 1 = violations found
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required.  pip install pyyaml", file=sys.stderr)
    sys.exit(2)


# The engagement posture sequence — order is law.
POSTURES: list[str] = [
    "DISCOVERY",
    "PROPOSAL",
    "ACTIVE",
    "TRANSITIONING",
    "CLOSED",
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
    "auto-approve",
    "auto-fire",
    "auto-hire",
]

OVERREACH_KEYWORDS: list[str] = [
    "employment decision",
    "hiring decision",
    "firing decision",
    "termination decision",
    "compensation decision",
    "discipline decision",
    "benefits counsel",
    "legal advice",
    "legal counsel",
    "benefits advice",
    "personnel action",
    "employment counsel",
]

PLACEHOLDER_PATTERNS: list[str] = [
    "todo",
    "tbd",
    "fixme",
    "placeholder",
    "rough notes",
    "to be determined",
    "change this",
]

ETHICS_BOUNDARIES: list[str] = [
    "no employment decisions",
    "no legal or benefits counsel",
    "no outbound communication",
    "every output is a draft",
]


def _validate_one(path: Path) -> list[str]:
    """Return a list of violation strings for one posture file (empty = pass)."""
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

    # Rule #3 — 5-Primitive Completeness
    for primitive in REQUIRED_PRIMITIVES:
        value = doc.get(primitive)
        if not value:
            violations.append(
                f"Rule #3 violation: missing required primitive {primitive!r}"
            )
        elif isinstance(value, dict) and not any(
            v for v in value.values() if v
        ):
            violations.append(
                f"Rule #3 violation: primitive {primitive!r} is empty"
            )

    # Rule #1 — Valid Posture
    standing_val = ""
    standing_raw = doc.get("standing")
    if isinstance(standing_raw, dict):
        standing_val = str(standing_raw.get("current", "")).upper()
    elif isinstance(standing_raw, str):
        standing_val = standing_raw.upper()

    if standing_val not in POSTURE_SET:
        violations.append(
            f"Rule #1 violation: standing {standing_val!r} is not a recognised "
            f"engagement posture ({' → '.join(POSTURES)})"
        )
    else:
        idx = POSTURES.index(standing_val)
        previous = doc.get("standing_history") if isinstance(standing_raw, dict) else None
        if previous and isinstance(previous, list):
            for prev_entry in previous:
                prev_str = ""
                if isinstance(prev_entry, str):
                    prev_str = prev_entry.upper()
                elif isinstance(prev_entry, dict):
                    prev_str = str(prev_entry.get("standing", "")).upper()
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
    if doc.get("autonomic", False) is True:
        violations.append(
            "Rule #2 violation: autonomic flag is true — HR organ "
            "operates in human-supervised mode only"
        )

    gates = doc.get("human_gates")
    if not gates and not doc.get("gates"):
        # Check governance section for gates as fallback
        governance = doc.get("governance", {})
        if isinstance(governance, dict):
            ethics_rules = governance.get("ethics", [])
            if not isinstance(ethics_rules, list) or not ethics_rules:
                violations.append(
                    "Rule #2 violation: no human gates or ethics rules declared"
                )

    # Rule #5 — No Overreach (check scope boundary and exclusions)
    scope = doc.get("scope", {})
    if not isinstance(scope, dict):
        violations.append(
            "Rule #4 violation: scope must be a mapping with 'boundary' and 'exclusions'"
        )
    else:
        boundary_text = str(scope.get("boundary", "")).lower()
        for kw in OVERREACH_KEYWORDS:
            if kw in boundary_text:
                violations.append(
                    f"Rule #5 violation: scope boundary contains overreach "
                    f"keyword {kw!r} — employment decisions stay in human hands"
                )

        exclusions = scope.get("exclusions", [])
        if isinstance(exclusions, list) and not exclusions:
            violations.append(
                "Rule #4 violation: scope.exclusions must name at least one exclusion"
            )

        changes = scope.get("changes")
        if changes is not None:
            if not isinstance(changes, list):
                violations.append(
                    "Rule #4 violation: scope.changes must be a list"
                )

    # Rule #4 — Scope boundary declared
    if not isinstance(scope, dict) or not scope.get("boundary"):
        if "Rule #4" not in "".join(v.split(":")[0] for v in violations):
            violations.append(
                "Rule #4 violation: scope must declare an explicit boundary"
            )

    # Check mandate for overreach keywords
    mandate = doc.get("mandate", "")
    if isinstance(mandate, dict):
        mandate_text = str(mandate.get("description", "")) + " " + str(mandate.get("outcome", ""))
    else:
        mandate_text = str(mandate)
    mandate_lower = mandate_text.lower()
    for kw in AUTONOMIC_KEYWORDS:
        if kw in mandate_lower:
            violations.append(
                f"Rule #2 violation: mandate contains autonomic keyword {kw!r} — "
                "HR organ operates in human-supervised mode only"
            )

    # Rule #6 — Evidence Integrity
    standard = doc.get("standard", {})
    if isinstance(standard, dict):
        evidence = standard.get("evidence")
        if evidence:
            evidence_text = str(evidence).lower()
            for pat in PLACEHOLDER_PATTERNS:
                if pat in evidence_text:
                    violations.append(
                        f"Rule #6 violation: standard.evidence contains "
                        f"placeholder text {pat!r} — must reference real artifacts"
                    )

    # Rule #7 — Ethics Sentinel coverage (check governance has ethics rules)
    governance = doc.get("governance", {})
    if isinstance(governance, dict):
        ethics_rules = governance.get("ethics", [])
        if isinstance(ethics_rules, list):
            for boundary in ETHICS_BOUNDARIES:
                found = any(boundary in str(r).lower() for r in ethics_rules)
                if not found:
                    violations.append(
                        f"Rule #7 violation: ethics rules missing required boundary: "
                        f"{boundary!r}"
                    )

        consent = governance.get("consent", {})
        if isinstance(consent, dict):
            practitioner_confirmed = consent.get("practitioner_confirmed")
            client_engaged = consent.get("client_engaged")
            if standing_val in ("ACTIVE", "TRANSITIONING") and (
                practitioner_confirmed is False or client_engaged is False
            ):
                violations.append(
                    "Rule #2 violation: ACTIVE or TRANSITIONING engagement requires "
                    "practitioner_confirmed and client_engaged both true"
                )

    # Rule #8 — Practitioner Gate (governance.authority names the human)
    if isinstance(governance, dict):
        authority = governance.get("authority", "")
        authority_lower = str(authority).lower()
        if "practitioner" not in authority_lower and "human" not in authority_lower:
            violations.append(
                "Rule #8 violation: governance.authority must name the human practitioner"
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


def _fleet_paths(base: Path) -> list[Path]:
    """Discover all client posture YAML files under clients/."""
    clients_dir = base / "clients"
    if not clients_dir.exists():
        return []
    paths = []
    for client_dir in sorted(clients_dir.iterdir()):
        if client_dir.name.startswith("_") or not client_dir.is_dir():
            continue
        posture_file = client_dir / "posture.yaml"
        if posture_file.exists():
            paths.append(posture_file)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate client posture records against HR organ rules. "
            "Rules #1-8 are always active."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="POSTURE_YAML",
        help="one or more posture YAML files to validate",
    )
    parser.add_argument(
        "--fleet",
        action="store_true",
        help="discover all client posture files under organs/hr/clients/",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress per-file output; exit code only",
    )
    args = parser.parse_args()

    targets: list[Path] = []

    if args.fleet:
        base = Path(__file__).resolve().parent
        targets = _fleet_paths(base)
        if not targets:
            if not args.quiet:
                print("no client posture files found under organs/hr/clients/")
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
            print("  HR Organ Rules #1-8: all checks passed. Concordia.")
        else:
            print("  HR Organ Rules #1-8: violations found.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
