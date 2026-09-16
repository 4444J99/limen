#!/usr/bin/env python3
"""Read-only implementation coverage report; never changes lever lifecycle state."""

import argparse
import json
from pathlib import Path


def report(path: Path) -> dict:
    result = {
        "schema_version": 1,
        "total": None,
        "nonterminal": None,
        "covered": None,
        "covered_meaning": "implementation object present; not completed work",
        "decisions_selected": None,
        "requires_component_review": None,
        "with_acceptance_predicate": None,
        "needs_acceptance_definition": None,
        "unmeasured_implementation": None,
        "unmeasured": True,
        "errors": [],
        "rows": [],
    }
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        levers = document.get("levers") if isinstance(document, dict) else None
        if not isinstance(levers, list):
            raise ValueError("levers must be a list")
    except (OSError, ValueError) as exc:
        result["errors"] = [f"registry unreadable: {type(exc).__name__}"]
        return result
    rows = []
    for index, lever in enumerate(levers):
        if not isinstance(lever, dict):
            result["errors"].append(f"lever[{index}]: entry is not an object")
            lever = {}
        if not isinstance(lever.get("id"), str) or not lever["id"].strip():
            result["errors"].append(f"lever[{index}]: missing or malformed identity")
        if not isinstance(lever.get("status"), str) or not lever["status"].strip():
            result["errors"].append(f"lever[{index}]: missing or malformed lifecycle")
        rows.append(
            {"id": lever.get("id"), "status": lever.get("status"), "implementation": lever.get("implementation")}
        )
    nonterminal = [row for row in rows if row["status"] not in ("discharged", "retired")]
    implementations = [row["implementation"] for row in nonterminal]
    selected = sum(
        isinstance(value, dict) and value.get("decision_status") == "chosen_pending_evidence"
        for value in implementations
    )
    predicates = 0
    for value in implementations:
        acceptance = value.get("acceptance") if isinstance(value, dict) else None
        predicate = acceptance.get("predicate") if isinstance(acceptance, dict) else None
        predicates += isinstance(predicate, str) and bool(predicate.strip())
    invalid = sum(not isinstance(value, dict) for value in implementations)
    result.update(
        {
            "total": len(rows),
            "nonterminal": len(nonterminal),
            "covered": len(nonterminal) - invalid,
            "decisions_selected": selected,
            "requires_component_review": len(nonterminal) - selected,
            "with_acceptance_predicate": predicates,
            "needs_acceptance_definition": len(nonterminal) - predicates,
            "unmeasured_implementation": invalid,
            "unmeasured": bool(result["errors"] or invalid),
            "rows": rows,
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path(__file__).resolve().parents[1] / "his-hand-levers.json")
    args = parser.parse_args()
    result = report(args.registry)
    print(json.dumps(result, indent=2))
    return 1 if result["unmeasured"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
