# Post-repair verification — #2866

Baseline for this file's evidence remains `24da5bffeefb855f1968e0c830c1ca5445a291cf`. The
historical 11-case and 13-case reproductions in the parent directory are **unmodified**.

## Repair

Three changes to `scripts/tabularius-organ.py`:

1. **Import.** `from limen.memoria import MEMORY_DIR` removed. `memoria` exposes no such
   module-level constant, so the import always raised `ImportError`. Both call sites now
   leave `memdir` unset and let memoria's own resolver (`LIMEN_MEMORY_DIR`, else the
   workspace-derived default) stay authoritative. No new hardcoded constant was introduced.
2. **Diagnostic no-write contract.** `--check` no longer calls `_stamp()`. A new inner
   `stamp()` helper suppresses the liveness stamp entirely when `--dry-run` is set. Both
   modes now report the memory outcome on stdout only.
3. **Memory-result propagation.** Every normal-mode stamp (deferred, empty, processed)
   carries the computed memory outcome via `_stamp(**fields, **memory)`. Board outcomes stay
   independent: a memory failure does not stop the board pass.

Exit-status policy was deliberately left unchanged. The issue requires that a failing memory
pass not read as success in the *monitoring-visible status*, which the stamp now satisfies;
changing exit codes would alter caller contracts beyond the bounded repair.

## Result

| Run | pytest exit | Outcome |
|---|---:|---|
| Repaired | **0** | **23 passed** |
| Negative control A — diagnostic stamp restored | 1 | 6 failed, 17 passed |
| Negative control B — invalid `MEMORY_DIR` import restored | 1 | 1 failed, 22 passed |

## Negative controls

**A — re-break the diagnostic write.** Restoring `_stamp(pending=n, mode="check", **memory)`
in the `--check` branch fails exactly the six read-only assertions (four matrix cases with
memory absent, the bare-directory test, and the memoria-disabled control). No unrelated test
moved.

**B — re-break the import while keeping error propagation.** This is the gap identified in
review: a patch that suppresses diagnostic stamps and propagates the existing
`memory_error` into normal-mode stamps would satisfy a naive propagation test. Restoring
`from limen.memoria import MEMORY_DIR` fails **exactly one** test,
`test_memory_pass_succeeds`, while `test_memory_outcome_is_never_silently_absent` correctly
still passes. Success and error propagation are therefore tested separately.

Two further guards are covered by permanently passing tests rather than by mutation:

- `test_guard_rejects_child_that_never_reached_entry_point` rejects a child with the wrong
  exit status and a child killed by signal 9.
- `test_observer_refuses_to_satisfy_a_no_write_assertion` requires `ObservationUnavailable`
  when the observer produced no evidence, so "no writes" can never be reported by an observer
  that recorded nothing.

## Observer corrections

Confirmed by direct probe before and after: `os.lock` is **never emitted** by CPython, so the
committed observer's lock coverage was dead code; the real event is `fcntl.flock`, now
observed. `os.rename` carries four arguments and the observer recorded only `args[0]`, so a
destination-based check missed the file arriving in a protected directory; both endpoints are
now retained. The observer emits `observer_installed` / `observer_completed` markers and
raises rather than returning an empty list, so missing evidence is distinguishable from an
absence of mutation.

## Scope

Tests and one bounded repair of `scripts/tabularius-organ.py`. No live memory routing, no
launcher or credential configuration change, no deployment, no worktree reclamation. All
execution was in disposable temporary stores with no live credentials present.

`ruff` is clean on the changed `cli/tests` files. Host `ruff` is 0.17.1 while the estate pin
is 0.15.8 (`cli/pyproject.toml`), so the authoritative `ruff-lint` gate still needs a run under
the pinned version before merge.