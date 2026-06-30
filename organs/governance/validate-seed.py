#!/usr/bin/env python3
"""
Cvrsvs Honorvm Rule #1 — Valid Office (the sequential promotion invariant).
Cvrsvs Honorvm Rule #2 — Structured signal exchange edges (produces / consumes).

A seed.yaml must declare its promotion_status as one of the recognized offices in the
cursus sequence. Stages may not be skipped. implementation_status must match.

Usage:
  python organs/governance/validate-seed.py path/to/seed.yaml
  python organs/governance/validate-seed.py --fleet          # all seed.yaml in working tree
  python organs/governance/validate-seed.py --fleet --quiet  # exit code only
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

# The cursus honorum — the canonical sequence of offices. Order is law.
CURSUS: list[str] = ["INCUBATOR", "ALPHA", "BETA", "STABLE", "MATURE"]
CURSUS_SET: set[str] = set(CURSUS)

REQUIRED_TOP: list[str] = ["schema_version", "organ", "repo", "org"]
REQUIRED_META: list[str] = ["implementation_status", "promotion_status"]


# --------------------------------------------------------------------------- #
# Rule predicates                                                              #
# --------------------------------------------------------------------------- #

def _validate_one(path: Path, *, strict_graph: bool) -> list[str]:
    """Return a list of violation strings for one seed.yaml (empty = pass)."""
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

    # Rule 1a — required top-level fields
    for field in REQUIRED_TOP:
        if field not in doc:
            violations.append(f"missing required top-level field: {field!r}")

    # Rule 1b — required metadata fields
    meta = doc.get("metadata")
    if not isinstance(meta, dict):
        violations.append("missing or malformed 'metadata' block")
        return violations  # can't continue without metadata

    for field in REQUIRED_META:
        if field not in meta:
            violations.append(f"missing required metadata field: {field!r}")

    if violations:
        return violations

    impl_raw: str = str(meta["implementation_status"]).upper()
    promo_raw: str = str(meta["promotion_status"]).upper()

    # Rule 1c — promotion_status must name a recognized office
    if promo_raw not in CURSUS_SET:
        violations.append(
            f"promotion_status {promo_raw!r} is not a recognized office in the cursus "
            f"({' → '.join(CURSUS)})"
        )

    # Rule 1d — implementation_status must name a recognized office
    if impl_raw not in CURSUS_SET:
        violations.append(
            f"implementation_status {impl_raw!r} is not a recognized office in the cursus "
            f"({' → '.join(CURSUS)})"
        )

    if violations:
        return violations

    # Rule 1e — the two status fields must agree (no split declaration)
    if impl_raw != promo_raw:
        violations.append(
            f"implementation_status ({impl_raw!r}) and promotion_status ({promo_raw!r}) "
            "must match — a repo may not hold two offices simultaneously"
        )

    # Rule 1f — cursus reporting: current office and what comes next
    # (not a violation; emitted as advisory by the caller)

    if strict_graph:
        _validate_cvrsvs_edges(doc, violations)

    return violations


# --------------------------------------------------------------------------- #
# Cursus posture report (advisory, not a violation)                           #
# --------------------------------------------------------------------------- #

def _posture(meta: dict) -> str:
    promo = str(meta.get("promotion_status", "")).upper()
    if promo not in CURSUS_SET:
        return ""
    idx = CURSUS.index(promo)
    next_office = CURSUS[idx + 1] if idx + 1 < len(CURSUS) else "(terminus — no further office)"
    held = " → ".join(CURSUS[: idx + 1])
    return f"  cursus: {held}  |  next: {next_office}"


def _validate_cvrsvs_edges(doc: dict[str, Any], violations: list[str]) -> None:
    """Rule #2: require deterministic produces/consumes shape for governance edges."""
    if not isinstance(doc.get("schema_version"), str):
        # The richer edge policy applies to cvrsvs-honorvm contracts first.
        return

    for field, required in (("produces", "consumers"), ("consumes", "source")):
        items = doc.get(field, [])
        if not isinstance(items, list):
            if items != []:
                violations.append(f"{field!r} must be a list (or omitted)")
            continue
        for idx, item in enumerate(items):
            if isinstance(item, str):
                if not item.strip():
                    violations.append(f"{field}[{idx}] is an empty string")
                continue
            if not isinstance(item, dict):
                violations.append(
                    f"{field}[{idx}] must be a string or mapping with at least "
                    "'type' and partner keys"
                )
                continue

            item_type = item.get("type")
            if not isinstance(item_type, str) or not item_type.strip():
                violations.append(f"{field}[{idx}] is missing required key: 'type'")

            if required == "consumers":
                consumers = item.get("consumers")
                if not isinstance(consumers, list):
                    violations.append(
                        f"{field}[{idx}] requires 'consumers' list (or explicit "
                        "partner declarations)"
                    )
                    continue
                if not consumers:
                    violations.append(
                        f"{field}[{idx}] requires at least one declared consumer"
                    )
                    continue
                for cidx, consumer in enumerate(consumers):
                    if not isinstance(consumer, str) or not consumer.strip():
                        violations.append(
                            f"{field}[{idx}].consumers[{cidx}] must be a non-empty string"
                        )
            else:
                source = item.get("source")
                if not isinstance(source, str) or not source.strip():
                    violations.append(f"{field}[{idx}] requires 'source' string")


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate seed.yaml files against Cvrsvs Honorvm rules. "
            "Rule #1 is always active; Rule #2 is optional and explicit."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="SEED_YAML",
        help="one or more seed.yaml files to validate",
    )
    parser.add_argument(
        "--fleet",
        action="store_true",
        help="discover and validate all seed.yaml files under the current directory",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress per-file output; exit code only",
    )
    parser.add_argument(
        "--strict-graph",
        action="store_true",
        help="validate produces/consumes blocks as structured edge contracts",
    )
    args = parser.parse_args()

    targets: list[Path] = []

    if args.fleet:
        targets = sorted(Path(".").rglob("seed.yaml"))
        if not targets:
            print("no seed.yaml files found under current directory")
            return 0
    elif args.paths:
        targets = [Path(p) for p in args.paths]
    else:
        # default: look for seed.yaml in cwd
        default = Path("seed.yaml")
        if default.exists():
            targets = [default]
        else:
            parser.print_help()
            return 2

    total = len(targets)
    passed = 0
    failed = 0

    for path in targets:
        violations = _validate_one(path, strict_graph=args.strict_graph)
        if not violations:
            passed += 1
            if not args.quiet:
                # load metadata for posture advisory
                try:
                    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                    meta = doc.get("metadata", {})
                    posture = _posture(meta) if isinstance(meta, dict) else ""
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
            if args.strict_graph:
                print("  Cvrsvs Honorvm Rules #1 & #2: all checks passed. Concordia.")
            else:
                print("  Cvrsvs Honorvm Rule #1: all offices valid. Concordia.")
        else:
            print("  Cvrsvs Honorvm Rule #1: violations found. Cursus not satisfied.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
