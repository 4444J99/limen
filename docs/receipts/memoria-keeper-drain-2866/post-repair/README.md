# Post-repair verification — #2866

Baseline evidence remains `24da5bffeefb855f1968e0c830c1ca5445a291cf`. The historical 11-case and 13-case reproductions in the parent directory are **unmodified**.

All runs below execute in a **controlled environment**: `env -i` with `LIMEN_ROOT` set to the checkout under test. That detail is the headline result — see *Environment finding*.

## Result

Suites: `cli/tests/test_tabularius_organ_memory.py` + `cli/tests/test_organ_health_defect.py`.

| Run | pytest exit | Outcome | Additional failures over repaired |
|---|---:|---|---:|
| **Repaired** | **0** | **43 passed** | — |
| Control A — diagnostic stamp restored | 1 | 6 failed, 37 passed | **+6** |
| Control B — invalid `MEMORY_DIR` import restored | 1 | 2 failed, 41 passed | **+2** |
| Control C — board-boundary injection disabled | 1 | 2 failed, 41 passed | **+2** |
| Control D — consumer defect reader removed | 1 | 2 failed, 41 passed | **+2** |

Every control adds only its intended mutation-specific failures to a fully green repaired run.

## Environment finding — the outstanding failure was never a code defect

The previously reported `StopIteration` in
`test_fast_wave_interval_reads_the_deployed_env_file` is caused by an **inherited environment
variable**, not by this patch, and not by either revision's code.

`scripts/organ-health.py` resolves its root at import time:

```python
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
SENSORS = ROOT / "institutio" / "governance" / "sensors.yaml"
```

The ambient shell carries `LIMEN_ROOT=/Users/4jp/Workspace/library/engine/organvm/limen`, a path
that **does not exist**. `_discover_doors()` converts an unreadable sensor registry into
`sensors = {}`, so no `diurnal` row is discovered and `next(...)` raises `StopIteration` before the
test ever reaches its interval assertion. The observed failure was therefore *"the expected sensor
row was not discovered"*, not *"the sample interval was read incorrectly"*.

Paired evidence, same controlled dependencies, both revisions:

| Revision | Stale `LIMEN_ROOT` | Controlled `LIMEN_ROOT` |
|---|---|---|
| `24da5bffe` (baseline) | `registry_exists: false` → fail | `registry_exists: true` → **2 passed** |
| `47bfb3ba8` (candidate) | `registry_exists: false` → fail | `registry_exists: true` → **2 passed** |

Under a controlled root, **both** revisions pass. Recorded in `limen-root-diagnosis.txt` with the
effective module path, `ROOT`, `SENSORS`, registry availability, and discovery result; the
uncontrolled reproduction is preserved as `uncontrolled-env-failure-reproduction.txt`.

**Disposition:** this failure was never attributable to the patch and was never a separate product
defect to hand off. It is invocation configuration. Recorded here rather than silently dropped; no
other owner is implicated. A follow-up worth filing separately: a test that asserts on
`_discover_doors` should control `LIMEN_ROOT` before importing the module under test, so an
inherited variable cannot decide its outcome.

## Repair

| Change | File |
|---|---|
| Removed `from limen.memoria import MEMORY_DIR` — no such constant exists, so the import always raised. Both call sites leave `memdir` unset so memoria's resolver stays authoritative. | `scripts/tabularius-organ.py` |
| `--check` no longer stamps; an inner `stamp()` suppresses the liveness stamp under `--dry-run`. Both report the memory outcome on stdout via `_describe()`. | `scripts/tabularius-organ.py` |
| Every normal-mode stamp carries the computed memory outcome; board outcomes stay independent. | `scripts/tabularius-organ.py` |
| `updated` emitted as a whole-second trailing-`Z` UTC stamp. **Compatibility for newly emitted stamps only** — not a general timestamp-parser repair, and not a correction of historical records. | `scripts/tabularius-organ.py` |
| TABVLARIVS gained a `defect=` reader over `memory_error`. | `scripts/organ-health.py` |

### Two real defects surfaced by the consumer wiring

**The state timestamp was unreadable by the consumer.** `_json_field_ts` honours a trailing `Z` and
otherwise parses a naive datetime as **local**; the keeper wrote
`datetime.now(timezone.utc).isoformat()`, emitting `+00:00`, which is not recognised as UTC. The
suffix read `(recorded -1.0h ago)` — a failure shown as happening in the future.

**macOS cannot resolve `/dev/fd` by `readlink`.** Probed directly: `EINVAL` on this host, so lock
attribution was silently yielding `paths: []` on macOS while working on Linux. The observer now
tries `/dev/fd` → macOS `F_GETPATH` (`fcntl.fcntl(fd, 50, bytes(1024))`) → `/proc/self/fd`, and
records `attributed: false` when none resolve. Unattributed records are **rejected** by the no-write
assertion rather than counted as evidence of safety.

## Consumer acceptance

Tests vary **only** the recorded memory outcome at equal freshness and assert the classification:

- fresh stamp + `memory_error` → `down`, note carries `memory_error` and the value, `age_h < 1`
- fresh stamp + successful memory counts → `green` (control; a hard-wired `down` would also pass)
- fresh stamp + no memory fields (lane disabled) → `green` (absence is not a recorded failure)
- failure recorded 3h ago → `down`, suffix names the artifact's own clock

## Method note

Mutation controls are produced from a **snapshot of the candidate files taken before any
mutation**, and restored only from that snapshot. An earlier run used `git checkout --` on
uncommitted repair work and destroyed the consumer change; the snapshot rule removes that failure
mode mechanically rather than by convention.

## Predicates

| Predicate | Status |
|---|---|
| Focused suites green | **Satisfied** — 43 passed, exit 0, controlled environment |
| `ruff-lint` under pinned `0.15.8` | **Satisfied locally** — `check-ruff-pin.py` exit 0; `ruff check cli/src cli/tests web/api mcp ianva apps organs` exit 0, run from a scratch venv at the pin |
| Consumer distinguishes recorded memory failure at equal freshness | **Satisfied** — Control D proves the wiring |
| Lock attribution proven; unattributed rejected | **Satisfied** |
| Exact-head CI acceptance | **Not yet observed** — the GitHub check-runs endpoint returned zero records at inspection |
| Live routing or activation | **Outside this unit; no acceptance claimed** |

Local pinned-Ruff verification is not CI acceptance. The two are recorded separately.

## Scope

Tests plus a bounded repair of `scripts/tabularius-organ.py` and one `defect=` registration in
`scripts/organ-health.py`. All execution in disposable temporary stores with no live credentials
and no remote keeper contact. No live memory routing, no launcher or credential configuration
change, no deployment, no worktree reclamation.