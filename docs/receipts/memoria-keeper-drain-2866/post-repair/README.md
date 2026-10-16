# Post-repair verification — #2866

Baseline evidence remains `24da5bffeefb855f1968e0c830c1ca5445a291cf`. The historical 11-case and 13-case reproductions in the parent directory are **unmodified**.

## Result

Focused suites: `cli/tests/test_tabularius_organ_memory.py` + `cli/tests/test_organ_health_defect.py`.

| Run | pytest exit | Outcome |
|---|---:|---|
| Repaired | 1 | **1 failed, 42 passed** — the single failure is pre-existing at `origin/main` (see below) |
| Control A — diagnostic stamp restored | 1 | 7 failed, 36 passed |
| Control B — invalid `MEMORY_DIR` import restored | 1 | 3 failed, 40 passed |
| Control C — board-boundary injection disabled | 1 | 3 failed, 40 passed |
| Control D — consumer defect reader removed | 1 | 3 failed, 40 passed |

Each control is one above the pre-existing failure, i.e. it fails only what it is meant to fail.

### The pre-existing failure is not ours

`test_fast_wave_interval_reads_the_deployed_env_file` fails with `StopIteration`. Reproduced in a
detached worktree at `origin/main` with the unmodified test and script; output preserved as
`baseline-pre-existing-failure.txt`. It is a `LIMEN_VITALS_SAMPLE_SECONDS` / `_discover_doors`
matter, untouched by this unit.

## Repair

| Change | File |
|---|---|
| Removed `from limen.memoria import MEMORY_DIR` — no such constant exists, so the import always raised. Both call sites leave `memdir` unset so memoria's resolver stays authoritative. | `scripts/tabularius-organ.py` |
| `--check` no longer stamps; an inner `stamp()` suppresses the liveness stamp under `--dry-run`. Both report the memory outcome on stdout via `_describe()`. | `scripts/tabularius-organ.py` |
| Every normal-mode stamp carries the computed memory outcome. Board outcomes stay independent. | `scripts/tabularius-organ.py` |
| `updated` now uses the trailing-`Z` UTC form. | `scripts/tabularius-organ.py` |
| TABVLARIVS gained a `defect=` reader over `memory_error`. | `scripts/organ-health.py` |

### Two real defects surfaced by the consumer wiring

**The state timestamp was unreadable by the consumer.** `_json_nested_error(..., stamp="updated")`
computes its "recorded Nh ago" suffix through `_json_field_ts`, which honours a trailing `Z` and
otherwise parses a naive datetime as **local**. The keeper wrote
`datetime.now(timezone.utc).isoformat()`, which emits `+00:00` — not recognised as UTC. The result
was `(recorded -1.0h ago)`: a failure shown as having happened in the future. The producer now
emits the trailing-`Z` form the reader documents, matching the other UTC producers.

**macOS cannot resolve `/dev/fd` by `readlink`.** Probed directly: `os.readlink("/dev/fd/N")`
raises `EINVAL` on this host, so the lock-attribution path was silently producing
`paths: []` on macOS while working on Linux. The observer now resolves via `/dev/fd` → macOS
`F_GETPATH` (`fcntl.fcntl(fd, 50, bytes(1024))`) → `/proc/self/fd`, and reports
`attributed: false` when none resolve.

## Consumer acceptance

`build()` derives status from freshness and gating, then overrides to `down` when a configured
`defect` probe returns a failure. Before this change the TABVLARIVS entry had no `defect`
callback, so adding or removing `memory_error` could not change its classification. Tests vary
**only** the recorded memory outcome at equal freshness and assert the resulting classification:

- fresh stamp + `memory_error` → `down`, note carries `memory_error` and the value, `age_h < 1`
- fresh stamp + successful memory counts → `green` (the control; without it a hard-wired `down`
  would also pass)
- fresh stamp + no memory fields (lane disabled) → `green` (absence is not a recorded failure)
- recorded age names the artifact's own clock, not the voice stamp

Control D removes the reader and fails exactly the two classification tests, so the wiring is
load-bearing rather than decorative.

## Guard corrections

- Entry-point guard reads structured self-reported evidence (executed entry point + imported
  `limen` module paths) bound to this checkout. Any non-empty stdout no longer satisfies it.
- `inventory()` records its root, so an absent protected area differs from an existing empty one.
- Read-only matrix asserts `root`, `mem`, and `board`, and rejects **unattributed** mutation
  records so a path-less event can never satisfy a no-write assertion.
- `test_lock_events_are_attributed_to_the_protected_file` asserts attribution, which event
  capture alone does not establish.
- Valid `MemoryTicket` fixture; success requires a pending ticket to be counted (an all-zero
  result is not success); a lifecycle test verifies the ticket is applied, its atom appears, and
  a second run applies nothing and leaves atom bytes unchanged.

## Predicates

| Predicate | Status |
|---|---|
| `ruff-lint` under pinned `0.15.8` | **Satisfied.** `check-ruff-pin.py` exit 0; `ruff check cli/src cli/tests web/api mcp ianva apps organs` exit 0, "All checks passed!" |
| Consumer distinguishes memory failure from success at equal freshness | **Satisfied**, with Control D as proof |
| Lock self-test proves attribution and rejects unattributed | **Satisfied** |
| Live routing or activation | **Outside this unit; no acceptance claimed** |

`ruff` was run from a scratch venv pinned to `0.15.8`; the host's `0.17.1` is not the estate pin.

## Scope

Tests plus a bounded repair of `scripts/tabularius-organ.py` and one `defect=` registration in
`scripts/organ-health.py`. All execution in disposable temporary stores with no live credentials
and no remote keeper contact. No live memory routing, no launcher or credential configuration
change, no deployment, no worktree reclamation.