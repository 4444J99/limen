# Tabularius Writer Audit

<!-- tabularius-writer-audit:owner-recorded -->

Direct writer calls: `24`
Unclassified calls: `0`

## Owner Packets

| Packet | Tier | Calls | Owner | Predicate | Disposition |
|---|---|---:|---|---|---|
| `TAB-CREATION-FALLBACKS` | `creation-fallback` | `2` | `codex-integrator` | `python3 scripts/task-writer-audit.py` | remove or gate legacy direct fallback branches after producer parity is proven live |
| `TAB-HUMAN-ATOM-STATUS-WRITERS` | `human-atom-status` | `2` | `codex-integrator` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q` | convert continuity/routine needs_human atom upserts to keeper-owned status/upsert tickets |
| `TAB-MAINTENANCE-BOARD-FALLBACKS` | `board-maintenance` | `4` | `codex-integrator` | `python3 scripts/task-writer-audit.py` | decide whether each maintenance writer belongs to Tabularius/io allowlist or becomes a ticket producer |
| `TAB-ROUTE-RESIDUE-MUTATORS` | `routing-metadata` | `4` | `codex-integrator` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q` | convert routing, residue, and self-improve board patches to keeper-owned tickets |
| `TAB-STATUS-ASYNC-HEAL` | `status-result` | `4` | `codex-integrator` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py cli/tests/test_async_dispatch.py -q` | convert async reserve/reap/heal transitions to task.status tickets with no double-dispatch window |
| `TAB-STATUS-DISPATCH-RESULTS` | `status-result` | `5` | `codex-integrator` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q` | convert dispatch claim/result application to task.status tickets or keeper-drained status batches |
| `TAB-STATUS-HARVEST-RESULTS` | `status-result` | `3` | `codex-integrator` | `PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q` | convert harvest/Jules landing result application to task.status tickets |

## Direct Writers

| Path | Line | Call | Owner packet |
|---|---:|---|---|
| `cli/src/limen/cli.py` | `86` | `tasks_file.write_text` | `TAB-MAINTENANCE-BOARD-FALLBACKS` |
| `cli/src/limen/dispatch.py` | `2756` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/dispatch.py` | `3315` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/dispatch.py` | `3371` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/dispatch.py` | `3455` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/dispatch.py` | `3312` | `save_limen_file` | `TAB-STATUS-DISPATCH-RESULTS` |
| `cli/src/limen/harvest.py` | `163` | `save_limen_file` | `TAB-STATUS-HARVEST-RESULTS` |
| `scripts/dispatch-async.py` | `328` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/dispatch-async.py` | `799` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/dispatch-async.py` | `495` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/dispatch-continuity-check.py` | `334` | `save_limen_file` | `TAB-HUMAN-ATOM-STATUS-WRITERS` |
| `scripts/heal-board.py` | `251` | `atomic_write_text` | `TAB-MAINTENANCE-BOARD-FALLBACKS` |
| `scripts/heal-board.py` | `190` | `save_limen_file` | `TAB-MAINTENANCE-BOARD-FALLBACKS` |
| `scripts/heal-dispatch.py` | `147` | `save_limen_file` | `TAB-STATUS-ASYNC-HEAL` |
| `scripts/jules-land.py` | `228` | `save_limen_file` | `TAB-STATUS-HARVEST-RESULTS` |
| `scripts/jules-land.py` | `225` | `save_limen_file` | `TAB-STATUS-HARVEST-RESULTS` |
| `scripts/mine-backlog.py` | `212` | `save_limen_file` | `TAB-CREATION-FALLBACKS` |
| `scripts/quicken.py` | `491` | `save_limen_file` | `TAB-ROUTE-RESIDUE-MUTATORS` |
| `scripts/rewrite-owners.py` | `107` | `save_limen_file` | `TAB-ROUTE-RESIDUE-MUTATORS` |
| `scripts/route.py` | `677` | `save_limen_file` | `TAB-ROUTE-RESIDUE-MUTATORS` |
| `scripts/routine-freshness-audit.py` | `268` | `save_limen_file` | `TAB-HUMAN-ATOM-STATUS-WRITERS` |
| `scripts/self-heal.py` | `315` | `save_limen_file` | `TAB-CREATION-FALLBACKS` |
| `scripts/self-improve.py` | `435` | `save_limen_file` | `TAB-ROUTE-RESIDUE-MUTATORS` |
| `scripts/usage-telemetry.py` | `207` | `path.write_text` | `TAB-MAINTENANCE-BOARD-FALLBACKS` |

## Contract

- This receipt does not bless direct writers as done; it prevents hidden writer drift.
- Step 2.2 is owner-recorded when every remaining direct writer maps to a bounded packet and no row is unclassified.
- The burn-down remains complete only when this audit exits zero or the remaining writers are explicitly allowlisted as Tabularius/io ownership.
