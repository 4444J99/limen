# MEMORIA keeper drain — reproduction bundle and failing regression baseline

Issue: #2866
Baseline revision: `24da5bffeefb855f1968e0c830c1ca5445a291cf` (identical to `origin/main` at the time of capture)
Scope: tests and evidence only. **No production repair, no live memory routing, no deployment, no worktree reclamation.**

## What is here

| Path | Contents |
|---|---|
| `MANIFEST.json` | SHA-256 of every artifact, bound to the pinned revision, entry point, interpreter, and exact execution command |
| `harness/sitecustomize.py` | The **original** 11-case observer: mode-string-only `open` filter; no board injection |
| `harness/runner.py` | The **original** 11-case matrix driver |
| `evidence/results.json` | Per-case raw records: exit code, stdout, stderr, before/after state records, inventory delta, controlled env |
| `evidence/writes.jsonl` | Raw PEP 578 audit-event log from the child interpreters |
| `permanent-tests-baseline.txt` | Output of the permanent regression suite against this baseline |

## Reproduced results (11 cases, original harness)

| Group | Created | Overwritten |
|---|---:|---:|
| B — eight `--check`/`--dry-run` combinations | 4 | 4 |
| A, C, D | 3 | 0 |
| **All eleven** | **7** | **4** |

All 8 B cases report a health-state write. All 11 invocations exited `0`.

Two defects, kept separate:

1. `--check` and `--dry-run` create `LIMEN_ROOT/logs/tabularius-organ-state.json` and overwrite it when present. The control case (C, MEMORIA disabled) shows the outer write is **unconditional** — not a consequence of the memory import failure.
2. Normal mode computes the memory result and discards it: no memory outcome reaches any state stamp or return decision in the deferred, empty, or processed branches.

Observed write attempts: 36 against the sandbox state path; **0 against the memory store**, with synthetic tickets intact.

## Permanent regression baseline

`cli/tests/test_tabularius_organ_memory.py` asserts the **desired** contract and is **expected to fail here**. Result at this baseline: **8 failed, 6 passed** (pytest exit 1).

The 8 failures are the contract tests. The 6 passes are provenance, protective memory-store, path-agreement, and observation-limit guards.

Two traps found and closed while building these tests, both of which initially produced *vacuous* passes:

- A child interpreter that resolves PyYAML from user site-packages dies once the sandbox redirects `HOME`. `assert_child_started` now fails any test whose child did not start, so a crashed child can never satisfy a no-write assertion.
- The sandbox initially checked `sandbox/logs/` while the entry point writes `LIMEN_ROOT/logs/`. `test_fixture_state_path_agrees_with_limen_root` now pins the two.

The tests are **not** made to pass by expecting the unwanted write, by suppressing `_stamp()`, or by weakening an assertion.

## Observation limits (carried forward)

PEP 578 audit hooks observe events raised by the child interpreter only. They are **not** an OS-wide write trace and **not** a sandbox**, cannot detect a concurrent external writer, and cannot exclude a create-then-delete between snapshots. `test_write_observer_limits_are_documented` keeps this caveat attached to the suite.

No memory-store mutation was observed in these executions. That does **not** establish the safety of a repaired memory path, because every enabled-memory execution here stopped at the import failure. Re-run the no-write tests after repair.