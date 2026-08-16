# Scope: Milestone 1 — Review-Loop Circuit Breaker & Quarantine

## Architecture
Milestone 1 quarantines review-looping PRs (C04 #2414 and C05 #139) from blocking autonomous positioning lanes, resolves residual defects via single-push exact-tree fixes, and syncs synthetic test receipts to ensure 100% clean test suite execution.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 2 | Review-Loop Circuit Breaker | Quarantine C04 (#2414) and C05 (#139) review loops and enforce single-push exact-tree resolution | M1 | ORIGINAL_REQUEST §R2 |
| 3 | C04 Defensive Guard | Fix P2 dictionary lookup guard in `scripts/positioning-proof-preflight.py:973` | M1 | Survey 1 (PR #2414) |
| 4 | C05 Schema Alignment | Align 5 template & finding schema fields in `collaboration-operations-platform` validator | M1 | Survey 1 (PR #139) |
| 5 | Synthetic Receipt Sync | Update stale receipt hash in `docs/receipts/positioning/preflights/` restoring 100% test pass (252/252) | M1 | Survey 2 (`test_positioning_c10_readiness.py`) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1.1 | Investigation (3 Explorers) | Investigate C04 guard, C05 schema, C10 synthetic receipt | None | IN_PROGRESS |
| 1.2 | Worker Implementation | Apply code fixes to scripts/positioning-proof-preflight.py, collaboration platform, and synthetic receipt | 1.1 | PLANNED |
| 1.3 | Verification Gate | 2 Reviewers, 2 Challengers, 1 Forensic Auditor | 1.2 | PLANNED |

## Interface Contracts
- `scripts/positioning-proof-preflight.py` must guard all artifact dictionary lookups against non-dict items.
- `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` must match exact deterministic hash of `institutio/positioning/program.yaml`.
- All 252 tests in `pytest scripts/tests/test_positioning_*.py cli/tests/test_positioning_*.py` must PASS with exit code 0.
