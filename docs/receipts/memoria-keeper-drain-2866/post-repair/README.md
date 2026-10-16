# Post-repair verification — #2866

Baseline evidence remains `24da5bffeefb855f1968e0c830c1ca5445a291cf`. The historical 11-case
and 13-case reproductions in the parent directory are **unmodified**.

## Repair

| Change | Detail |
|---|---|
| Import | `from limen.memoria import MEMORY_DIR` removed — `memoria` exposes no such constant, so the import always raised `ImportError`. Both call sites leave `memdir` unset so memoria's own resolver stays authoritative. No hardcoded constant introduced. |
| Diagnostic no-write contract | `--check` no longer calls `_stamp()`. An inner `stamp()` helper suppresses the liveness stamp under `--dry-run`. Both now report the memory outcome on stdout via `_describe()`, verified. |
| Memory propagation | Every normal-mode stamp carries the computed memory outcome. Board outcomes stay independent of the memory result. |

Exit-status policy unchanged by choice: the issue requires the failure be visible in
monitoring-visible status, which the stamp now satisfies, without altering caller contracts
beyond this bounded repair. **This does not establish that any downstream monitoring consumer
interprets the new fields correctly** — that is a separate, unverified consumer question.

## Result

| Run | pytest exit | Outcome |
|---|---:|---|
| Repaired | **0** | **25 passed** |
| Control A — diagnostic stamp restored | 1 | 6 failed, 19 passed |
| Control B — invalid `MEMORY_DIR` import restored | 1 | 2 failed, 23 passed |
| Control C — board-boundary injection disabled | 1 | 2 failed, 23 passed |

## Negative controls

**A — re-break the diagnostic write.** Restoring `_stamp(pending=n, mode="check", **memory)`
fails exactly the six read-only assertions. No unrelated test moved.

**B — re-break the import while keeping error propagation.** Fails `test_memory_pass_succeeds`,
which now requires a pending ticket to be counted and an all-zero result is explicitly not
success. Error-propagation assertions still pass, so success and propagation remain separate.

**C — disable the board-boundary injection.** This is the control for the coverage regression
found in review. Removing the injection fails **exactly** `test_memory_outcome_is_never_silently_absent[deferred]`
and `[processed]`, and nothing else. Before this control existed, the injection had been
silently dead: all three parameterisations fell through to the same empty-inbox branch while
still passing. Branch-specific assertions (`deferred is True`, `pending == 3`; `applied == 2`,
`rejected == 1`, `wrote == 2`) now bind the claim to execution evidence rather than to test
names and environment variables.

## Corrections made in this pass

- **Board injection restored.** `REPRO_BOARD_MODE` / `REPRO_SRC` were being set by the sandbox
  but consumed by nothing; the deferred and processed branches were never reached.
- **Entry-point guard strengthened.** The old condition accepted any non-empty stdout. The
  observer now self-reports the executed entry point and the imported `limen` module paths, and
  the guard requires both to bind to this checkout when the memory lane is enabled. A child
  printing unrelated text is rejected (`test_guard_rejects_unrelated_output`).
- **Junk assertion removed.** `assert x is None or True` could not fail; it is replaced by a
  real self-report assertion.
- **Inventory includes its root.** An absent protected area and an existing empty one previously
  had identical inventories; root existence and metadata are now recorded.
- **Lock events are actionable.** `fcntl.flock` records resolve the descriptor to its target via
  `/dev/fd`, so a lock record can satisfy a path-based assertion. Recording was previously not
  asserting.
- **All protected areas asserted.** The read-only matrix checks `root`, `mem`, and `board`, not
  just `LIMEN_ROOT`.
- **Dry-run now prints the memory outcome.** The earlier receipt claimed both diagnostic modes
  report it; only `--check` did. Verified by probe, not by assertion of intent.
- **Lifecycle verified.** A valid pending ticket must be applied (`memory_applied >= 1`), its
  atom `<slug>.md` must exist, and a second run must apply nothing and leave atom bytes
  unchanged. Idempotence concerns ticket effects; the `updated` liveness timestamp legitimately
  changes and is not compared.

## Scope

Tests plus one bounded repair of `scripts/tabularius-organ.py`. All execution in disposable
temporary stores with no live credentials and no remote keeper contact. No live memory routing,
no launcher or credential configuration change, no deployment, no worktree reclamation.

## Pending

`ruff` is clean on the changed `cli/tests` files, but host `ruff` is **0.17.1** while the estate
pin is **0.15.8** (`cli/pyproject.toml`, issue #1658). `gates.yaml`'s `ruff-lint` runs
`scripts/check-ruff-pin.py` first and fails loud on mismatch, so the authoritative gate needs a
pinned-version run before merge. This is a **repair candidate pending acceptance**, not a
completed closeout: no authoritative merge gate has been executed, and no live activation or
routing acceptance is claimed.