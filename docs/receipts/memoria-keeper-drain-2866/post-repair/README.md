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

## Round 3 — deferral classification: tolerated, then degraded

Round 2 preserved `memory_deferred` but read nothing, which fixes *reporting* and leaves the
monitoring false-green open from the other side: a lane that deferred forever stayed green.

### The rule

Deferring is memoria's designed behaviour under contention — `drain_memory_once` defers to the
next beat rather than blocking — so **one recent deferral must not read `down`.** It is an
*advisory*: named in the note, status untouched.

Degradation requires **both** conditions, since each alone has a healthy explanation:

| Condition | Alone it means |
|---|---|
| repetition: `memory_defer_streak >= 2` | a one-beat lock collision — the other drainer finishes |
| persistence: `memory_deferred_since` older than 1h | a stamp nobody rewrote, which freshness already reports |

Only both together mean no drain is succeeding.

### Three design decisions worth naming

**A new `advisory` hook, not a new status.** `defect` forces `down` for ANY non-empty string, so a
tolerated deferral cannot be routed through it. Adding a `deferred` *status* would require the
dot/label maps, the summary counts, and every downstream reader to learn it — the file's own
comment at the defect branch already rejects that for the same reason.

**The keeper carries the streak.** The stamp is overwritten every run, so one deferral and the
hundredth consecutive one produced identical fields. Repetition was unmeasurable until the keeper
read its own prior stamp and carried the streak forward.

**The reset is explicit `= 0`, not absence.** If a clean run merely omitted the field, a single
contended beat between two clean ones would restart the count at 1, and no streak could ever
cross the threshold. A reader also has to distinguish "never deferred" from "deferred and
recovered" — that requires the reset to be visible.

### Controls

| Run | exit | Outcome | Fails |
|---|---:|---|---|
| **Repaired** | **0** | **60 passed** | — |
| Control H — deferral routed through `defect` | 1 | 4 failed, 21 passed | every tolerated-deferral case |
| Control I — streak reset dropped | 1 | 2 failed, 33 passed | both streak tests |
| Control J — streak increment dropped | 1 | 3 failed, 32 passed | streak tests + the stdout streak assertion |
| Control K — persistence condition dropped | 1 | 1 failed, 24 passed | `test_either_deferral_condition_alone_stays_green[9-0.0]` |

Control K failing **only** the persistence case is the proof that the two conditions are
independent: repetition alone is genuinely insufficient.

### A vacuous assertion this round's controls caught

The carry-forward control — removing `since or` from the keeper — left the suite **green**, proving
the streak-preservation assertions caught nothing. Cause: whole-second stamps. Two deferred runs
inside one second write identical strings, so "the start was preserved" and "the start was
rewritten to now" were indistinguishable.

Fixed by sleeping past a second boundary, and by adding the sequence those tests could not express:
**defer, succeed, defer**. That one needed the inbox re-seeded too — the recovery drain *consumes*
the ticket, and an empty inbox returns before locking, so it would never have deferred and the
sequence would have tested nothing. Re-ran the same control after strengthening: **1 failed**, as
required.

A test that passes whether or not the fix is present is not evidence, and this one was found only
because a control was run rather than assumed.

## Predicates

| Predicate | Status |
|---|---|
| Focused suites green | **Satisfied** — 60 passed, exit 0, controlled environment |
| Every direct consumer of both changed scripts green | **Satisfied** — 170 tests, exit 0 (see "Blast radius of the held heavy gate") |
| Session-release predicate satisfied | **NOT satisfied** — `BrokerUnavailable`, `status: unmeasured`, fail-closed. Named atom below; `CLOSEOUT COMPLETE` therefore withheld. |
| One recent deferral reads green and is named | **Satisfied** — Control H |
| Repeated deferrals with no drain degrade | **Satisfied** — Control K proves the conditions are independent |
| A recovered lane reads clean | **Satisfied** — Controls I and J |
| Reader fail-open on odd shapes | **Satisfied** |
| Each of the three defects caught by its own tests | **Satisfied** — Controls E/F/G plus the lifecycle vacuity pair |
| `ruff-lint` under pinned `0.15.8` | **Satisfied** — `check-ruff-pin.py` exit 0; `ruff check cli/src cli/tests web/api mcp ianva apps organs` → `All checks passed!` |
| `ruff-format` under pinned `0.15.8` | **Satisfied** — `ruff format --check …` → `790 files already formatted` |
| `scripts/verify-scoped.sh` | **Cheap wave PASS** (all 13 cheap gates); **heavy wave exit 75** — `Host admission denied scoped heavy verification: heavy-lease-held`, held by `claude-lane-j-foa-live` (pid 74553, surface `tmb-foa-live-browser`, alive). **At closeout the holder had changed:** pid 74553 released its lease, and the heavy surface was then held by a different live session — `limen-verify-61933` (pid 61933, `verify.py --changed`, worktree `closeout-runtime-test-20261017`). The surface remains occupied by a co-equal session, so the gate is still unavailable here and was not retried. Not killed: at most one heavy surface machine-wide, and existing work is never killed. Exit 75 is the prescribed fail-open "blocked on a held condition", not a defect. The held gate is `pytest-cli` (whole `cli/tests`, `tier: heavy`, `serialize: true`). |
| `APPLY FAILED: 4444J99/limen:estate-contract` in the gate log | **Not a failure.** It is the suppressed stdout of a deliberate negative control inside `merge-queue-contract-test` (`test_repository_plan_failure_refuses_all_mutations`, which mocks `gh_json_checked` to fail and asserts every mutation is refused). That gate reported `186 passed` / `FINISH status=PASS`. |
| Heavy `pytest-cli` blast radius | **Measured, not assumed** — see "Blast radius of the held heavy gate" below. Every test file in the repository that loads either changed script was run directly and is green. |
| Consumer distinguishes recorded memory failure at equal freshness | **Satisfied** — Control D proves the wiring |
| Lock attribution proven; unattributed rejected | **Satisfied** |
| Exact-head CI acceptance | **Not yet observed** — the GitHub check-runs endpoint returned zero records at inspection |
| Live routing or activation | **Outside this unit; no acceptance claimed** |

## Delivery disposition — PR #2869

Branch `test/tabularius-organ-memory-2866`, pushed. **Local, remote, and PR head all agree** at
`063cc615d9c95463911c2237c7b146e73e5969c5` (PR #2869, `state: OPEN`, `mergeable: MERGEABLE`).

`origin/main` was integrated once during round 2 (`249b89b1c`, no conflict — main touched none of the
changed paths). At round 3, `git merge-base --is-ancestor origin/main HEAD` exits 0, so there was
nothing to re-integrate.

### Three submissions, one per head — none retried

| Head | Submitted | Result |
|---|---|---|
| `1cf2333fc` (round 1) | once | `DEFERRED — BLOCKED` — **stranded**: submitted before the commit that recorded it, so that receipt never captured this submission |
| `67c46345f` (round 2) | twice | `DEFERRED — BLOCKED` — identical, not a retry of a changed head but a resubmission after the head moved |
| `063cc615d` (round 3) | once | `DEFERRED — BLOCKED` — not retried, no check polled |

`BLOCKED` is `assess()`'s fallthrough for `mergeable != "MERGEABLE"` (`merge-drain.py:433`).
`gh pr checks 2869 --required` reports **no required checks** on this branch, and reads taken after
each submission returned `mergeable: MERGEABLE` — the classification caught GitHub's transient
`UNKNOWN` while it recomputes mergeability after a push. Not a rejection of the head.

**Verified at closeout:** `git merge-base --is-ancestor 063cc615d origin/main` exits **1**, and
`gh pr view 2869` reports `mergedAt: null`. **The work has not landed.**

### merge-drain persists nothing on DEFERRED

Read directly from `submit_one` (`merge-drain.py:639-689`): every terminal branch, including both
`DEFERRED` returns, only prints and returns an exit code. There is no submission ledger — the
`_save_ci_red_ledger` helper belongs to the unrelated CI-red subject path. So the claim that a
`DEFERRED` hold is "preserved for the beat's own drain" is true only insofar as the open PR itself is
visible to that drain; **no separate durable record of these three submissions exists.** The durable
owner is therefore the open PR plus its named merge condition, which is a valid closure form.

**No password rotation and no worktree removal were performed.** Both remain barred until the
relevant gates pass, and the heavy `pytest-cli` gate has not yet run at this head.

### Not claimed

Landing. **No merge is claimed and none is asserted here.** `DEFERRED — BLOCKED` is not a receipt,
and a later `mergeable: MERGEABLE` read proves nothing about landing — it is GitHub's own
compatibility field, which reads `UNKNOWN` while it recomputes after a push. Landing requires the
exact head to be an ancestor of `origin/main`:

```bash
git merge-base --is-ancestor <exact-head> origin/main   # exit 0 ⟺ landed
```

Not by this PR's state, its age, the absence of an open PR, or a passing merge-drain line.

Local pinned-Ruff verification is not CI acceptance. The two are recorded separately.

## Blast radius of the held heavy gate

An earlier revision of this receipt claimed `scripts/organ-health.py` was "untouched this round".
**That was false** — round 3 changed it substantially: a new `advisory` hook in `build()`, three new
readers (`_memory_deferral_facts`, `_memory_deferral_defect`, `_memory_deferral_advisory`), and the
TABVLARIVS rung's `defect` lambda. The claim contradicted this receipt's own Round 3 section and is
corrected here rather than left standing.

A corrected claim is still a claim, so the blast radius was measured. Every test file in the
repository that loads either changed script, found by grepping for both filenames under `cli/`:

| Consumer | Loads | Result |
|---|---|---|
| `cli/tests/test_organ_health_defect.py` | `organ-health.py` | **25 passed** |
| `cli/tests/e2e/test_ecosystem_liveness.py` | `organ-health.py` | **27 passed** |
| `cli/tests/test_vigilia.py` | `organ-health.py` | **pass** (in the 83) |
| `cli/tests/test_positioning_organ.py` | `organ-health.py` | **pass** (in the 83) |
| `cli/tests/test_tabularius_organ.py` | `tabularius-organ.py` | **pass** (in the 83) |
| `cli/tests/test_memoria.py` | `tabularius-organ.py` | **pass** (in the 83) |
| `cli/tests/test_tabularius_organ_memory.py` | `tabularius_organ_fixtures.py` | **34 passed** |
| `cli/tests/tabularius_organ_fixtures.py` | the fixture module itself (one importer) | exercised above |

**170 tests, all green**, covering every direct consumer of both changed scripts — 60
(`test_tabularius_organ_memory` + `test_organ_health_defect`), 27 (e2e), 83
(`test_tabularius_organ` + `test_memoria` + `test_vigilia` + `test_positioning_organ`).

Two of these were genuinely at risk and had never been run before this closeout:
`test_ecosystem_liveness.py::test_tier2_08` asserts a self-reported defect still forces `down`
despite a fresh timestamp — the exact branch round 3 edited — and `test_tier2_09` asserts
`_json_nested_error`'s trail precedence and timestamp parsing, the function whose neighbours round 3
added to. Both pass, which is the substantive half of the evidence the heavy gate would have
produced for these files.

**What this does not prove:** the heavy gate as a whole has still not run. The remaining ~1,000 tests
do not reference either changed script, so the residual risk is now *bounded and stated* rather than
*assumed away* — but a bounded risk is not a satisfied gate, and the gate is not marked satisfied here.

## Session closeout — 2026-10-17

### Parity

| Surface | Local | Remote | PR | Agreement |
|---|---|---|---|---|
| `test/tabularius-organ-memory-2866` | `063cc615d` | `063cc615d` | `063cc615d` | **1:1** |
| `main` (this checkout) | — | `1df15fa1b` | — | **behind 1** — a fast-forward, not lane-local state |

Working tree clean, including `--untracked-files=all`: no local-only scratch, no orphan files.
`scripts/credential-wall.py --check` → exit 0, 32 secret atoms registered.

### Done and evidenced

- Three original defects (rounds 1–2) fixed, each caught by its own control (E/F/G plus the
  lifecycle vacuity pair).
- Deferral classification (round 3): tolerated-then-degraded, controls H/I/J/K, plus one vacuous
  assertion the controls exposed and that is now closed.
- 170 tests green across every direct consumer of both changed scripts.
- `ruff-lint` and `ruff-format` clean under the pinned `0.15.8`; `verify-scoped.sh` cheap wave PASS.
- Receipt, branch, and PR comment all carry the exact-head evidence.

### Open, each with its durable owner

| Atom | State | Owner | Next command |
|---|---|---|---|
| **PR #2869 not landed** | `OPEN`, `mergedAt: null`, `merge-base --is-ancestor` exits 1 | the recurring merge drain (open PR + named merge condition is a valid closure form) | drain re-assesses; do not re-submit from this lane |
| **Heavy `pytest-cli` not run** | denied, `heavy-lease-held` | `verify` gate; machine-wide admission | `./scripts/verify-scoped.sh` once when admission allows |
| **Session-release predicate unmeasured** | `BrokerUnavailable`, `status: unmeasured` — fail-closed | **credential wall** | set `LIMEN_CONDUCT_URL` + `LIMEN_CONDUCT_TOKEN`, then re-run the predicate |
| **`no-tasks-on-me.sh` wrapper picks a dep-less interpreter** | exits `ModuleNotFoundError: rfc8785` | gate/tooling hygiene | see below |

### Two infrastructure defects found while auditing (named, not silently absorbed)

1. **`scripts/no-tasks-on-me.sh` cannot run as invoked.** It resolves bare `python3`, which on this
   host is `/opt/homebrew/bin/python3` — the one interpreter *without* `rfc8785`; `/usr/local/bin/python3`,
   `/opt/homebrew/bin/python3.14`, and the limen venv all have it. The committed closeout predicate
   therefore crashes with a stack trace instead of reporting a verdict. Worked around here by calling
   `scripts/session-closeout.py` directly under `/usr/local/bin/python3`. **Not fixed in this lane** —
   it is a shared-tooling change outside a bounded memory-pass repair, and filing it silently inside
   this repair would hide a machine-wide defect behind an unrelated diff.

2. **The conduct broker is unconfigured.** `LIMEN_CONDUCT_URL` and `LIMEN_CONDUCT_TOKEN` are unset,
   so `client_from_env()` raises `BrokerUnavailable` and the session predicate fails closed at
   `status: unmeasured`. Credentials belong to the credential organ, never to this transcript, so
   this is a `BLOCKED` atom by owner rather than something to work around.

### Consequence for the terminal statement

The closeout **cannot** declare `CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items`.
That statement requires a satisfied session predicate, and the predicate returns `unmeasured` while the
broker is unconfigured and its wrapper cannot resolve an interpreter. Per the charter, "unknown
ownership fails closed; estate diagnostics do not substitute for session proof." The work is durably
homed and its evidence is complete; the *session release* is not, and that gap is named above rather
than papered over.

## Scope

Tests plus a bounded repair of `scripts/tabularius-organ.py` and one `defect=` registration in
`scripts/organ-health.py`. All execution in disposable temporary stores with no live credentials
and no remote keeper contact. No live memory routing, no launcher or credential configuration
change, no deployment, no worktree reclamation.