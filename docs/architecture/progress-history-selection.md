# Progress history and dynamic selection

This surface persists content-addressed work-universe snapshots, compares any
two stored observations, and ranks next work from live facts. It does not claim,
dispatch, mutate `tasks.yaml`, or select a model.

Historical source adapters live under `config/progress-history-sources/`. They
map runtime-discovered source documents into one private-safe leaf contract.
Source identity, document paths, field names, and terminal semantics are data;
renaming, adding, removing, or reordering a source does not require code edits.
Private leaf identities are immediately hashed. Missing adapters, missing or
hash-mismatched documents, truncation, stale registry receipts, invalid leaves,
and non-exhaustive sources remain explicit history coverage debt.

Snapshots use `limen.progress-history-snapshot.v1`. Their filename is the
SHA-256 of the canonical snapshot material, and publication is atomic and
idempotent under ignored `logs/progress-history-snapshots/`. Each snapshot
contains the exact source cursors and hashes, normalized leaves, actual
work-loan usage, verified value, ask/outcome counts, live capacity facts, host
pressure, and the ranking explanation used at that observation.

Arbitrary-window deltas keep distinct ledgers for arrivals, closures, reopened
debt, disappearance without a terminal receipt, aging, runs/tokens/dollars/
elapsed/host spend, verified value, ask arrivals, verified ask outcomes, and
coverage debt. A negative cumulative spend delta is recorded as reconciliation
debt; it is never silently clamped away.

Selection considers numeric live value, cost of delay, dependency impact,
confidence, due-date urgency, provider headroom, capacity cost, and host
pressure. Missing metrics are visible on each candidate. Provider rows and
locality come from the live capability registry; there is no fixed lane or
model table. Host pressure filters local capacity only when live remote
capacity is available, and otherwise leaves the task explicitly ineligible.

```bash
# Read-only current view.
PYTHONPATH=cli/src python3 scripts/progress-history-selection.py --json

# Persist a private content-addressed observation.
PYTHONPATH=cli/src python3 scripts/progress-history-selection.py --write

# Compare arbitrary stored boundaries.
PYTHONPATH=cli/src python3 scripts/progress-history-selection.py --from 2026-07-17T00:00:00Z --json
```

`--check` succeeds only when the source registry and every normalized history
contribution are exhaustive. A zero eligible ranking is proof of no work only
when the complete board contains no open tasks; unavailable capacity is a
blocker, not an empty queue.
