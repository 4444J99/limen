# Seven-Agent Whole-Estate Session Review

This directory contains the reproducible, redacted source for the frozen
2026-07-19 whole-estate review of Codex, Claude, Agy, OpenCode, Gemini,
Copilot, and Jules.

The two half-open windows overlap and are never added:

- completed calendar week: `2026-07-06T04:00:00Z` through
  `2026-07-13T04:00:00Z`;
- latest seven days: `2026-07-12T15:11:00Z` through the frozen snapshot at
  `2026-07-19T15:11:00Z`.

## Reproduction

From this directory:

```bash
python3 -m unittest -v test_model.py
python3 collect.py
python3 reconcile.py
python3 build_report.py
```

`collect.py` reads native provider stores and the Limen board without mutating
them. It writes only aggregate metadata to tracked source; the short-lived
ask-to-receipt link index is private and ignored. `reconcile.py` dynamically
enumerates the registry owners, resolves repository transfers, and classifies
GitHub receipts at the frozen snapshot. `build_report.py` produces the
canonical Data Analytics artifact.

## Files

- `model.py` — pure time, token, receipt, and outcome rules.
- `test_model.py` — boundary, token-delta, concurrency, lineage, redirect,
  receipt, late-write, and deduplication tests.
- `collect.py` — native-store and task-ledger collectors.
- `reconcile.py` — live estate census and exact remote receipt reconciliation.
- `snapshot.json` — public-safe frozen analytical snapshot.
- `artifact.json` — canonical self-contained report manifest and bounded data.
- `validation.json` — reconciliation, test, validator, and hosting receipts.

Raw prompts, secrets, machine-local paths, private receipt URLs, and full
commit hashes are excluded. Unknown duration and token meters remain unknown
rather than being rendered as zero.
