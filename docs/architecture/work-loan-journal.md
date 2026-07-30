# Work-loan journal

The work-loan journal is Limen's append-only accounting source for scarce
execution capacity. It is not a second task queue. `tasks.yaml` remains the
state authority; this journal records what one selected task asked the fleet to
borrow, what was reserved, what a provider actually consumed, and whether the
result repaid the loan with verified durable credit.

## Event contract

Each JSONL event uses `limen.work_loan_journal_event.v1`, has a content-derived
SHA-256 identifier, and links to the prior event for that loan. Per-loan phases
are `requested`, `reserved`, `actual`, then `settled`:

- `requested` preserves source origin, horizon, value case, owner, executable
  predicate, durable receipt target, and forecast capacity;
- `reserved` binds a finite capacity debit to one executor and reservation;
- `actual` records provider-neutral runs, input/output/cache tokens, dollars,
  elapsed time, and local host resource-time measurements independently;
- `settled` joins the terminal outcome to keeper predicate and receipt proof.

Every capacity field distinguishes unknown (`null`) from measured zero. A task
earns credit only when the outcome is `done`, the predicate passed, and the
durable receipt was verified. Every other settlement—and every unsettled
request—remains explicit unrepaid debt.

The dispatcher writes the request and reservation before provider launch. A
reservation write failure denies that launch. It records actual wall time after
the provider returns. Existing focus and priority buckets remain authoritative;
external due dates and loan cost only break ties inside those buckets.

## Custody and publication

Runtime events live at ignored `logs/work-loan-journal.jsonl`, protected by an
exclusive process lock and mode `0600`. Runtime source and full facts also stay
under ignored `logs/`. The bounded tracked projection hashes loan identities,
contains no task title, owner surface, predicate, receipt target, executor, or
provider correlation, and is refreshed only by its keeper publication lane.

```bash
# Validate without mutation.
PYTHONPATH=cli/src python3 scripts/work-loan-journal.py --check --json

# Reconcile keeper-verified terminal tasks and write runtime receipts.
PYTHONPATH=cli/src python3 scripts/work-loan-journal.py --reconcile --write

# Keeper-only tracked projection refresh.
PYTHONPATH=cli/src python3 scripts/work-loan-journal.py --reconcile --write-tracked
```

The source registration is `config/progress-sources/work-loan.json`. Its report
conforms to `limen.progress-source-report.v1`, so missing, stale, or invalid
accounting remains universe coverage debt rather than becoming a zero.
