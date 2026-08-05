#!/usr/bin/env python3
"""Reconcile and publish append-only work-capacity accounting."""

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

from limen.io import load_limen_file  # noqa: E402
from limen.work_loan_journal import (  # noqa: E402
    WorkLoanJournalError,
    WorkLoanJournalStore,
    build_work_loan_source,
    reconcile_terminal_tasks,
)


OWNER_ROOT = Path(os.environ.get("LIMEN_ROOT", REPO))
JOURNAL = OWNER_ROOT / "logs" / "work-loan-journal.jsonl"
SOURCE_REPORT = OWNER_ROOT / "logs" / "progress-sources" / "work-loan.json"
PRIVATE_FACTS = OWNER_ROOT / "logs" / "work-loan-facts.json"
TRACKED_PROJECTION = REPO / "docs" / "work-loan-journal.json"
TASKS = Path(os.environ.get("LIMEN_TASKS", OWNER_ROOT / "tasks.yaml"))


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
    parser.add_argument("--check", action="store_true", help="exit 1 unless the complete journal validates")
    parser.add_argument("--json", action="store_true", help="print the source report and summary")
    parser.add_argument("--write", action="store_true", help="write ignored source and private runtime receipts")
    parser.add_argument(
        "--write-tracked",
        action="store_true",
        help="keeper-only: also refresh the bounded tracked projection",
    )
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="settle terminal loans from keeper-verified task receipts before reporting",
    )
    parser.add_argument("--public-limit", type=int, default=256)
    parser.add_argument("--journal", type=Path, default=JOURNAL)
    parser.add_argument("--tasks", type=Path, default=TASKS)
    parser.add_argument("--source-report", type=Path, default=SOURCE_REPORT)
    parser.add_argument("--private-output", type=Path, default=PRIVATE_FACTS)
    parser.add_argument("--tracked-output", type=Path, default=TRACKED_PROJECTION)
    args = parser.parse_args()
    if args.public_limit < 0 or args.public_limit > 4096:
        parser.error("--public-limit must be between 0 and 4096")

    store = WorkLoanJournalStore(args.journal)
    try:
        if args.reconcile:
            limen = load_limen_file(args.tasks)
            reconcile_terminal_tasks(limen.tasks, store)
        full, tracked = build_work_loan_source(store.read(), public_limit=args.public_limit)
    except (OSError, ValueError, WorkLoanJournalError) as exc:
        print(f"work-loan journal failed: {exc}", file=sys.stderr)
        return 1

    if args.write or args.write_tracked:
        _atomic_write(args.source_report, full["source_report"])
        _atomic_write(args.private_output, full)
    if args.write_tracked:
        _atomic_write(args.tracked_output, tracked)
    if args.json:
        print(json.dumps({"source_report": full["source_report"], "summary": full["summary"]}, indent=2))
    else:
        report = full["source_report"]
        summary = full["summary"]
        mark = "✓" if report["exhaustive"] else "✗"
        print(
            f"{mark} work-loan: loans={report['normalized_leaf_count']} "
            f"events={summary['event_count']} earned={summary['earned_credit_count']} "
            f"unrepaid={summary['unrepaid_debt_count']} failures={summary['failure_count']}"
        )
    return 1 if args.check and not full["source_report"]["exhaustive"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
