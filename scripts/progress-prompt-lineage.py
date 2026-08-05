#!/usr/bin/env python3
"""Publish the prompt/work-lineage source without exposing private prompt bodies."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[1]
CLI_SRC = REPO / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.progress_prompt_lineage import build_prompt_lineage_source  # noqa: E402
from limen.prompt_corpus import load_event_journal, load_jsonl_strict  # noqa: E402


OWNER_ROOT = Path(os.environ.get("LIMEN_ROOT", REPO))
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", OWNER_ROOT / ".limen-private" / "session-corpus"))
AUTHORITY_SEAL = OWNER_ROOT / "docs" / "prompt-authority-seal.json"
EVENT_JOURNAL = PRIVATE_ROOT / "prompt-atoms" / "prompt-events.jsonl"
OUTCOME_JOURNAL = PRIVATE_ROOT / "prompt-atoms" / "prompt-atom-outcomes.jsonl"
ESTATE_RECONCILIATION = PRIVATE_ROOT / "lifecycle" / "prompt-estate-reconciliation.json"
SOURCE_REPORT = REPO / "logs" / "progress-sources" / "prompt-lineage.json"
PRIVATE_FACTS = REPO / "logs" / "progress-prompt-lineage-facts.json"
TRACKED_PROJECTION = REPO / "docs" / "progress-prompt-lineage.json"


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _current_atoms(
    event_journal: Path,
    outcome_journal: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    _occurrences, atoms, event_errors = load_event_journal(event_journal)
    outcomes, outcome_errors = load_jsonl_strict(outcome_journal)
    outcome_by_id = {
        str(row.get("atom_id")): row for row in outcomes if isinstance(row, dict) and str(row.get("atom_id") or "")
    }
    successor_edges = {
        str(predecessor) for atom in atoms for predecessor in atom.get("predecessor_ids") or [] if str(predecessor)
    }
    rows: list[dict[str, Any]] = []
    for atom in atoms:
        atom_id = str(atom.get("atom_id") or "")
        rows.append(
            {
                **atom,
                "is_current_intent": atom_id not in successor_edges,
                "outcome": outcome_by_id.get(atom_id)
                or {
                    "disposition": "unassessed",
                    "owner": None,
                    "evidence": [],
                },
            }
        )
    return rows, [*event_errors, *outcome_errors]


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 unless prompt authority and joins are exact")
    parser.add_argument("--json", action="store_true", help="print the tracked summary")
    parser.add_argument("--write", action="store_true", help="write ignored source and private runtime receipts")
    parser.add_argument(
        "--write-tracked",
        action="store_true",
        help="keeper-only: also refresh the bounded tracked projection",
    )
    parser.add_argument("--public-limit", type=int, default=256)
    parser.add_argument("--authority-seal", type=Path, default=AUTHORITY_SEAL)
    parser.add_argument("--event-journal", type=Path, default=EVENT_JOURNAL)
    parser.add_argument("--outcome-journal", type=Path, default=OUTCOME_JOURNAL)
    parser.add_argument("--estate-reconciliation", type=Path, default=ESTATE_RECONCILIATION)
    parser.add_argument("--source-report", type=Path, default=SOURCE_REPORT)
    parser.add_argument("--private-output", type=Path, default=PRIVATE_FACTS)
    parser.add_argument("--tracked-output", type=Path, default=TRACKED_PROJECTION)
    args = parser.parse_args()
    if args.public_limit < 0 or args.public_limit > 4096:
        parser.error("--public-limit must be between 0 and 4096")

    seal = _load_object(args.authority_seal) or {}
    atoms: list[dict[str, Any]] = []
    input_failures: list[str] = []
    if seal.get("authority_ready") is True:
        atoms, input_failures = _current_atoms(args.event_journal, args.outcome_journal)
    reconciliation = _load_object(args.estate_reconciliation)
    full, tracked = build_prompt_lineage_source(
        seal,
        atoms,
        reconciliation,
        input_failures=input_failures,
        public_limit=args.public_limit,
    )
    if args.write or args.write_tracked:
        _atomic_write(args.source_report, full["source_report"])
        _atomic_write(args.private_output, full)
    if args.write_tracked:
        _atomic_write(args.tracked_output, tracked)
    if args.json:
        print(json.dumps({"source_report": full["source_report"], "summary": full["summary"]}, indent=2))
    else:
        report = full["source_report"]
        mark = "✓" if report["exhaustive"] else "✗"
        print(
            f"{mark} prompt-lineage: known={report['normalized_leaf_count']} "
            f"expected={report['cursor']['expected_atom_count']} "
            f"exhaustive={str(report['exhaustive']).lower()} failures={report['cursor']['failure_count']}"
        )
    return 1 if args.check and not full["source_report"]["exhaustive"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
