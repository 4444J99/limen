#!/usr/bin/env python3
"""
Cvrsvs Honorvm Rule #3 — Entity Register Integrity (the dual-entity boundary).
Cvrsvs Honorvm Rule #4 — Repo Registration + Promotion Rules (cursus standing in the entity
register and the structured promotion-rule contract).

The governance entity register (entities.yaml) lists every legal entity under governance,
its mandates, its forbidden acts, and the cursus standing of every registered repo.
This validator checks:

  Always active:
    Rule #3a — Entity structure: all required fields present per type (entity_taxonomy).
    Rule #3b — Dual-entity boundary: mandates are within the allowed set for the entity type.
    Rule #3c — Dual-entity boundary: forbidden_acts are within the standard forbidden set;
               no forbidden_acts overlap with mandates.
    Rule #3d — Entity cursus: every declared cursus office is a valid cursus stage.
    Rule #4a — Repo cursus: every repo's cursus office is a valid cursus stage.
    Rule #4b — Repo consistency: implementation_status matches cursus (no split office).
    Rule #4c — Repo entity reference: every repo references a known entity by id.

  Strict-graph mode (--strict-graph):
    Rule #4d — Promotion rules structure: every promotion map references valid cursus
               offices (from → to) and has well-formed prerequisites.

Usage:
  python organs/governance/validate-entities.py                    # validate default register
  python organs/governance/validate-entities.py path/to/entities.yaml
  python organs/governance/validate-entities.py --fleet            # check all governance registers
  python organs/governance/validate-entities.py --fleet --strict-graph  # + promotion rules check
  python organs/governance/validate-entities.py --quiet            # exit code only
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

# The cursus honorum — derived here, never hardcoded in two places.
# (Mirrors validate-seed.py. A future refactor should share one source.)
CURSUS: list[str] = ["INCUBATOR", "ALPHA", "BETA", "STABLE", "MATURE"]
CURSUS_SET: set[str] = set(CURSUS)

# Expected schema_version — semver-like pattern
SCHEMA_VERSION_PATTERN: str = r"^\d+\.\d+(\.\d+)?$"

# Expected updated field format — ISO-8601 date (YYYY-MM-DD) or datetime
DATE_PATTERN: str = r"^\d{4}-\d{2}-\d{2}"


# --------------------------------------------------------------------------- #
# Rule predicates                                                              #
# --------------------------------------------------------------------------- #

def _validate_one(path: Path, *, strict_graph: bool = False) -> list[str]:
    """Return a list of violation strings for one entities.yaml (empty = pass)."""
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

    # -- Schema-level checks ------------------------------------------------ #
    if doc.get("organ") != "governance":
        violations.append("top-level 'organ' must be 'governance'")

    sv = doc.get("schema_version")
    if not isinstance(sv, str):
        violations.append("missing or non-string 'schema_version'")
    elif not re.match(SCHEMA_VERSION_PATTERN, sv):
        violations.append(
            f"'schema_version' {sv!r} does not match expected pattern (e.g. '1.0', '1.0.0')"
        )

    updated = doc.get("updated")
    if updated is not None and (not isinstance(updated, str) or not re.match(DATE_PATTERN, str(updated))):
        violations.append("'updated' must be an ISO-8601 date string (YYYY-MM-DD) or omitted")

    # -- Entity taxonomy ---------------------------------------------------- #
    taxonomy = doc.get("entity_taxonomy")
    if not isinstance(taxonomy, dict):
        violations.append("missing or malformed 'entity_taxonomy' block")
        taxonomy = {}

    # -- Boundary matrix ---------------------------------------------------- #
    matrix = doc.get("boundary_matrix")
    if not isinstance(matrix, dict):
        violations.append("missing or malformed 'boundary_matrix' block — the dual-entity invariant")
        return violations  # can't continue without boundary rules

    allowed_by_type: dict[str, set[str]] = {}
    forbidden_by_type: dict[str, set[str]] = {}
    for etype, rules in matrix.items():
        if not isinstance(rules, dict):
            violations.append(f"boundary_matrix.{etype} must be a mapping")
            continue
        allowed = rules.get("allowed_mandates", [])
        forbidden = rules.get("always_forbidden", [])
        if isinstance(allowed, list):
            allowed_by_type[etype] = set(allowed)
        if isinstance(forbidden, list):
            forbidden_by_type[etype] = set(forbidden)

    # -- Entity checks ------------------------------------------------------ #
    entities = doc.get("entities")
    if not isinstance(entities, list):
        violations.append("missing or non-list 'entities' — at least one entity required")
        entities = []

    seen_ids: set[str] = set()
    for idx, entity in enumerate(entities):
        if not isinstance(entity, dict):
            violations.append(f"entities[{idx}] must be a mapping")
            continue

        eid = entity.get("id")
        if not isinstance(eid, str) or not eid.strip():
            violations.append(f"entities[{idx}] missing required field: 'id'")
        elif eid in seen_ids:
            violations.append(f"entities[{idx}] duplicate entity id: {eid!r}")
        else:
            seen_ids.add(eid)

        # Rule 3a — required fields per type (must be present and non-empty for string fields)
        etype = entity.get("type")
        if not isinstance(etype, str):
            violations.append(f"entities[{idx}] ({eid}) missing 'type'")
            continue

        type_req = taxonomy.get(etype, {}).get("required_fields") if isinstance(taxonomy, dict) else None
        if isinstance(type_req, list):
            for field in type_req:
                val = entity.get(field)
                if val is None:
                    violations.append(
                        f"entities[{idx}] ({eid}) of type {etype!r} missing required field: {field!r}"
                    )
                elif isinstance(val, str) and not val.strip():
                    violations.append(
                        f"entities[{idx}] ({eid}) required field {field!r} is empty"
                    )

        # Rule 3b — mandates are allowed for this type
        mandates = entity.get("mandates")
        if isinstance(mandates, list):
            if etype in allowed_by_type:
                for m in mandates:
                    if m not in allowed_by_type[etype]:
                        violations.append(
                            f"entities[{idx}] ({eid}) mandate {m!r} is not in the allowed set "
                            f"for type {etype!r}: {sorted(allowed_by_type[etype])}"
                        )

        # Rule 3c — forbidden_acts don't overlap with allowed mandates
        forbidden = entity.get("forbidden_acts")
        if isinstance(forbidden, list) and isinstance(mandates, list):
            overlap = set(forbidden) & set(mandates)
            if overlap:
                violations.append(
                    f"entities[{idx}] ({eid}) forbidden_acts overlap with mandates: {sorted(overlap)}"
                )
            if etype in forbidden_by_type:
                for fa in forbidden:
                    if fa not in forbidden_by_type[etype]:
                        violations.append(
                            f"entities[{idx}] ({eid}) forbidden_act {fa!r} is not in the standard "
                            f"forbidden set for type {etype!r}: {sorted(forbidden_by_type[etype])}"
                        )

        # Rule 3d — cursus office is valid
        cursus = entity.get("cursus")
        if isinstance(cursus, str):
            c_upper = cursus.upper()
            if c_upper not in CURSUS_SET:
                violations.append(
                    f"entities[{idx}] ({eid}) cursus {cursus!r} is not a recognized office "
                    f"({' → '.join(CURSUS)})"
                )

    # -- Repo registration checks (Rule #4) --------------------------------- #
    repos = doc.get("repos")
    if not isinstance(repos, list):
        violations.append("missing or non-list 'repos' — at least one repo registration required")
        repos = []

    for ridx, repo in enumerate(repos):
        if not isinstance(repo, dict):
            violations.append(f"repos[{ridx}] must be a mapping")
            continue

        rname = repo.get("repo", f"index {ridx}")

        # Rule 4a — cursus office is valid
        cursus = repo.get("cursus")
        if isinstance(cursus, str):
            c_upper = cursus.upper()
            if c_upper not in CURSUS_SET:
                violations.append(
                    f"repos[{ridx}] ({rname}) cursus {cursus!r} is not a recognized office "
                    f"({' → '.join(CURSUS)})"
                )

        # Rule 4b — implementation_status matches promotion_status
        impl = repo.get("implementation_status")
        promo = repo.get("cursus")  # the canonical cursus field
        if isinstance(impl, str) and isinstance(promo, str):
            if impl.upper() != promo.upper():
                violations.append(
                    f"repos[{ridx}] ({rname}) implementation_status ({impl!r}) and cursus ({promo!r}) "
                    "must match — a repo may not hold two offices simultaneously"
                )

        # Rule 4c — entity reference must exist
        eref = repo.get("entity")
        if isinstance(eref, str) and eref not in seen_ids:
            violations.append(
                f"repos[{ridx}] ({rname}) references unknown entity {eref!r}"
            )

    # -- Cursus office sequence integrity ----------------------------------- #
    offices = doc.get("cursus_offices")
    if not isinstance(offices, list):
        violations.append("missing or non-list 'cursus_offices'")
    elif offices != CURSUS:
        violations.append(
            f"cursus_offices {offices} does not match canonical sequence "
            f"({' → '.join(CURSUS)})"
        )

    # -- Rule 4d (strict-graph): promotion_rules structure ------------------ #
    if strict_graph:
        violations.extend(_validate_strict_graph(doc))

    return violations


def _validate_strict_graph(doc: dict[str, Any]) -> list[str]:
    """Rule #4d: validate promotion_rules structure. Return violations."""
    violations: list[str] = []
    promo = doc.get("promotion_rules")
    if not isinstance(promo, dict):
        violations.append("missing or non-dict 'promotion_rules'")
        return violations

    valid_pair: set[str] = set()
    for i in range(len(CURSUS) - 1):
        valid_pair.add(f"{CURSUS[i]}_to_{CURSUS[i+1]}")

    seen_rules: set[str] = set()
    for key, rule in promo.items():
        if not isinstance(key, str):
            violations.append(f"promotion_rules key {key!r} must be a string")
            continue
        if key in seen_rules:
            violations.append(f"promotion_rules duplicate key: {key!r}")
        seen_rules.add(key)

        # Check key format: FROM_to_TO
        if key not in valid_pair and key.upper() not in valid_pair:
            violations.append(
                f"promotion_rules.{key!r} does not match any valid cursus transition "
                f"({' → '.join(CURSUS)})"
            )

        if not isinstance(rule, dict):
            violations.append(f"promotion_rules.{key!r} must be a mapping")
            continue

        prereqs = rule.get("prerequisites")
        if not isinstance(prereqs, list):
            violations.append(f"promotion_rules.{key!r} missing or non-list 'prerequisites'")
        elif not prereqs:
            violations.append(f"promotion_rules.{key!r} 'prerequisites' list is empty")

        validated_by = rule.get("validated_by")
        if validated_by is not None and not isinstance(validated_by, str):
            violations.append(
                f"promotion_rules.{key!r} 'validated_by' must be a string"
            )

    return violations


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate entities.yaml against Cvrsvs Honorvm Rules #3 and #4. "
            "Rule #3 checks the dual-entity boundary; Rule #4 checks repo cursus registration."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        metavar="ENTITIES_YAML",
        help="one or more entities.yaml files to validate",
    )
    parser.add_argument(
        "--fleet",
        action="store_true",
        help="discover and validate all entities.yaml files under organs/governance/",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress per-file output; exit code only",
    )
    parser.add_argument(
        "--strict-graph",
        action="store_true",
        help="validate promotion_rules structure (Rule #4d)",
    )
    args = parser.parse_args()

    targets: list[Path] = []

    if args.fleet:
        targets = sorted(Path("organs/governance").rglob("entities.yaml"))
        if not targets:
            print("no entities.yaml files found under organs/governance/")
            return 0
    elif args.paths:
        targets = [Path(p) for p in args.paths]
    else:
        default = Path("organs/governance/entities.yaml")
        if default.exists():
            targets = [default]
        else:
            # fallback to cwd
            cwd_default = Path("entities.yaml")
            if cwd_default.exists():
                targets = [cwd_default]
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
            if args.strict_graph:
                print("  Cvrsvs Honorvm Rules #3 & #4 (strict-graph): all checks passed. Concordia.")
            else:
                print("  Cvrsvs Honorvm Rules #3 & #4: all checks passed. Concordia.")
        else:
            print("  Cvrsvs Honorvm Rules #3 & #4: violations found. Cursus not satisfied.")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
