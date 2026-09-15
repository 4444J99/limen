#!/usr/bin/env python3
"""Read-only implementation coverage report; never changes lever lifecycle state."""

import argparse
import json
from pathlib import Path


def report(path: Path) -> dict:
    levers = json.loads(path.read_text())["levers"]
    rows = [
        {"id": lever["id"], "status": lever["status"], "implementation": lever.get("implementation")}
        for lever in levers
    ]
    nonterminal = [row for row in rows if row["status"] not in ("discharged", "retired")]
    return {
        "schema_version": 1,
        "total": len(rows),
        "nonterminal": len(nonterminal),
        "covered": sum(isinstance(row["implementation"], dict) for row in nonterminal),
        "requires_component_review": sum(
            not isinstance(row["implementation"], dict)
            or row["implementation"].get("decision_status") == "requires_component_review"
            for row in nonterminal
        ),
        "unmeasured_implementation": sum(not isinstance(row["implementation"], dict) for row in nonterminal),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path(__file__).resolve().parents[1] / "his-hand-levers.json")
    args = parser.parse_args()
    print(json.dumps(report(args.registry), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
