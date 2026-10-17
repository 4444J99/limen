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

## Round 2 — three defects found at head `3441895b2` (`c6bbf6aad`)

The round-1 green suite (`43 passed`) did **not** establish completion: the three defects below
were all present in that head, and defect 2 specifically disqualified part of that evidence.

### 1. Deferred memory outcomes became green

`_memory_pass` returned only `pending/applied/rejected` and dropped `result.deferred` and
`result.note`. `drain_memory_once` defers while the memory lock is held, reporting pending with
nothing applied and nothing rejected — byte-identical to an empty inbox once the fields are
dropped, so a deferral rendered `pass OK`.

`deferred`/`note` are now preserved in the stamp as a **string** (a bare `true` would be written
and then silently un-readable by `_json_nested_error`), and `_describe` reports `DEFERRED`.

A branch that nothing reaches is not a fix: only `--check`/`--dry-run` call `_describe`, and
neither can produce a deferral (`--check` counts; `--dry-run` returns before locking). Normal
mode therefore also prints the outcome when deferred, which is what makes the branch reachable.

### 2. Lifecycle evidence leaked between runs

`writes.jsonl` is **append-only** and every child appends to it, and the readers took the *first*
matching record. After a second run they reported the first run's mutations — and its markers —
as the second run's, so a run that observed nothing inherited the previous run's proof. The
marker-completeness check had the same hole: once any earlier run had written both markers, a
later run whose observer never installed or never flushed still satisfied `require=True`.

Every record now carries its emitting pid and all readers are scoped to the current child.
`subprocess.run` does not expose a child pid, so `run`/`run_raw` go through `Popen` — the binding
cannot be guessed or inherited.

Separately, the lifecycle test asserted `state2.get("memory_applied", 0) == 0`, which a **missing
key** satisfies. The key must now be present before its value is asserted zero.

### 3. Dry-run counts appeared completed

`drain_memory_once(dry_run=True)` reports *applicable* and *unparseable* counts having written
nothing; `_describe` rendered them `applied`/`rejected`, reporting work that never happened on the
only channel `--dry-run` publishes. The dry-run fact now travels in the outcome dict
(`memory_dry_run`) rather than being re-derived from the caller's flag, so `--check --dry-run` —
whose count is a real count — is not relabelled.

### Controls — each defect is caught by exactly its own tests

Snapshot-and-restore, never `git checkout --` over uncommitted work: the repair was committed
first (`c6bbf6aad`), so every restore was from that commit.

| Run | pytest exit | Outcome | Fails |
|---|---:|---|---|
| **Repaired** | **0** | **48 passed** | — |
| Control E — defect 1 reverted | 1 | 1 failed, 47 passed | `…_deferred_memory_pass_is_published_as_deferred_not_as_success` |
| Control F — defect 2 reverted (readers unscoped) | 1 | 2 failed, 46 passed | `…_readers_are_scoped_to_the_current_child`, `…_cannot_inherit_an_earlier_runs_observer_markers` |
| Control G — defect 3 reverted | 1 | 1 failed, 47 passed | `…_dry_run_counts_are_labelled_would_be_not_completed` |

Control E's failure output is the defect verbatim: the stamp reads `pending=0, applied=0,
rejected=0` with no `memory_deferred`. Control G's likewise — a `--dry-run` that wrote nothing
printed `pass OK (1 pending, 1 applied, 0 rejected)`.

**Removing an assertion cannot prove one catches anything**, so defect 2's second half was proved
by injecting the defective condition instead: a keeper that omits `memory_applied` whenever
`applied == 0`.

| Lifecycle assertion, same defective stamp | Result |
|---|---|
| old — `state2.get("memory_applied", 0) == 0` | **passed — vacuous** |
| new — `"memory_applied" in state2`, then `== 0` | **failed**, naming the absent field |

### Open question left to the owner, not silently decided

`organ-health.py`'s TABVLARIVS entry registers only the `("memory_error",)` trail. A deferral is
now recorded and reported on stdout, but **does not yet turn the health row down**. Whether
lock contention should read as a defect is a judgement call — a concurrent successful drainer
would make `down` a false alarm — so it is stated here rather than decided in either direction.
Wiring it is a one-line addition of a `("memory_deferred",)` trail plus its control.

## Predicates

| Predicate | Status |
|---|---|
| Focused suites green | **Satisfied** — 48 passed, exit 0, controlled environment |
| Each of the three defects caught by its own tests | **Satisfied** — Controls E/F/G plus the lifecycle vacuity pair |
| `ruff-lint` under pinned `0.15.8` | **Satisfied** — `check-ruff-pin.py` exit 0; `ruff check cli/src cli/tests web/api mcp ianva apps organs` → `All checks passed!` |
| `ruff-format` under pinned `0.15.8` | **Satisfied** — `ruff format --check …` → `790 files already formatted` |
| `scripts/verify-scoped.sh` | **Cheap wave PASS**; **heavy wave exit 75** — `Host admission denied scoped heavy verification: heavy-lease-held`, held by `claude-lane-j-foa-live` (pid 74553, surface `tmb-foa-live-browser`, alive). Not killed: at most one heavy surface machine-wide, and existing work is never killed. Exit 75 is the prescribed fail-open "blocked on a held condition", not a defect. The held gate is `pytest-cli` (whole `cli/tests`, `tier: heavy`, `serialize: true`). |
| Heavy `pytest-cli` blast radius | **Contained** — `tabularius_organ_fixtures` is imported by exactly one file, `cli/tests/test_tabularius_organ_memory.py` (verified by full-repo grep; the other hits are receipt prose). `scripts/organ-health.py` is untouched this round. So the held gate exercises no changed path beyond the two files driven directly here. Full-suite confirmation is left to `pr-gate`. |
| Consumer distinguishes recorded memory failure at equal freshness | **Satisfied** — Control D proves the wiring |
| Lock attribution proven; unattributed rejected | **Satisfied** |
| Exact-head CI acceptance | **Not yet observed** — the GitHub check-runs endpoint returned zero records at inspection |
| Live routing or activation | **Outside this unit; no acceptance claimed** |

## Delivery disposition — PR #2869

Branch `test/tabularius-organ-memory-2866` at `1cf2333fc4a0537c80471f4e8ba9fbd6914790f8`, pushed,
`origin/main` integrated once (`249b89b1c`, no conflict — main touched none of the changed paths).

`scripts/merge-drain.py --repo 4444J99/limen --pr 2869 --expected-head 1cf2333fc…` was submitted
**once**, per protocol, and returned:

```
MERGE-SUBMISSION 4444J99/limen#2869@1cf2333fc…: DEFERRED — BLOCKED
```

`BLOCKED` is `assess()`'s fallthrough for `mergeable != "MERGEABLE"` (`merge-drain.py:433`). A
read taken immediately after returned `mergeable: MERGEABLE`, so the classification caught
GitHub's transient `UNKNOWN` while it recomputed mergeability after the push and PR-body edit —
not a durable hold and not a rejection of the head. **This is a `DEFERRED` hold, not a `MERGED`
receipt.** It is preserved for the beat's own drain to re-assess; re-submitting here would be the
retry the protocol forbids, so it was not retried and no check was polled.

`gh pr checks` at submission: `pr-gate`, `python`, `web`, `worker` and `semgrep` pending;
`npm-audit` ×2 and CodeRabbit passed; `Sourcery review` and `compat` skipped. Remote checks and
automated reviews are advisory.

**No password rotation and no worktree removal were performed.** Both remain barred until the
relevant gates pass, and the heavy `pytest-cli` gate has not yet run at this head.

### Not claimed

Landing. No merge is claimed until the exact head is an ancestor of `origin/main`, verified by
`git merge-base --is-ancestor` against the merged ref — not by this PR's state, its age, or the
absence of an open PR.

Local pinned-Ruff verification is not CI acceptance. The two are recorded separately.

## Scope

Tests plus a bounded repair of `scripts/tabularius-organ.py` and one `defect=` registration in
`scripts/organ-health.py`. All execution in disposable temporary stores with no live credentials
and no remote keeper contact. No live memory routing, no launcher or credential configuration
change, no deployment, no worktree reclamation.