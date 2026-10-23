# Diagnosing pytest-cli

Owner: verify. Tracking: [#3162](https://github.com/4444J99/limen/issues/3162).
The related OpenCode reader change is [draft #3161](https://github.com/4444J99/limen/pull/3161).
Dependency audit [#3145](https://github.com/4444J99/limen/issues/3145) is independent.

`timeout_seconds: 1500` is a finite verification limit, not a measured runtime promise.
The former ten-minute description is obsolete. Do not increase it, skip tests, or
classify assertions as pre-existing just because a run reached 99%.

## Evidence during a run

The hermetic wrapper loads the opt-in `scripts/pytest_diagnostics.py` plugin.
The registry enables it for pytest-cli and requests the slowest 30 phase durations.
No test selection, assertion result, maxfail setting, worker count or deadline is
changed by instrumentation. The wrapper uses unbuffered Python output. The gate
separately selects xdist's work-stealing scheduler to redistribute queued tests
from busy workers to idle workers during the expensive tail.

Each invocation creates a separate private run directory under
`.pytest_cache/limen-diagnostics/` and prints its absolute journal path. The
controller writes line-flushed JSONL records for starts, setup/call/teardown
reports, finishes, collection failures and session completion. Failed reports
retain full traceback text and captured sections. A heartbeat every 30 seconds
prints the ten longest active test phases and records all active tests plus the
30 longest completed phases. This includes fixture setup and teardown, not just
test bodies. Xdist reports include worker identity. Per-test fd capture cannot
hide the heartbeat: it owns a duplicate of the original session output descriptor.

The PR Gate uploads these journals with `always()` after gate success or failure.
An externally killed job/runner may prevent the upload step itself; no artifact
upload can guarantee survival of a destroyed runner. Local journals survive the
verifier's temporary console-log directory. They are not tracked source files.
Review failure/capture content before publishing local journals.

Summarize a completed or interrupted run without importing pytest:

```bash
python3 scripts/pytest_diagnostics.py .pytest_cache/limen-diagnostics/run-EXACT/events.jsonl
```

`complete: false` and `exitstatus: null` mean no terminal pytest verdict was
recorded. Earlier assertion failures remain failures, and unfinished nodeids are
separate. A partial final JSON record from a kill is ignored; other corrupt records
are errors. The summary does not turn an interrupted run into a pass.

## Controlled measurement

Check `limen host-admission status` and use the existing guarded heavy entrypoint.
Keep the source tree, full Git history, interpreter, dependencies, worker count,
host pressure and competing workload recorded for each comparison. A shallow
checkout creates spurious historical-registry failures.

The ordinary scoped gate remains:

```bash
bash scripts/verify-scoped.sh
```

To diagnose the entire suite after an early failure, acquire the existing heavy
lease and run the hermetic wrapper with an external finite process-group deadline:

```bash
bash scripts/run-pytest-hermetic.sh cli/tests -q -n auto --dist=worksteal --maxfail=0 --tb=short --durations=30 --limen-diagnostics=.pytest_cache/limen-diagnostics
```

Here `--maxfail=0` is a diagnostic run that continues through failures, not a
replacement gate. The gate still uses `--maxfail=20`. Do not let any measurement
outlive its lease or platform deadline. Rerun named failures against clean main
and the exact candidate head before attributing a regression. A Linux measurement
does not establish the deadline required by a Mac with different I/O/pressure.

## Measured finding, 2026-10-22

A Linux/Python 3.12 run of main's CLI code at
`13a7934bd18fe933e359e741110dda15ec8fa976`, with diagnostic instrumentation,
collected 9,469 tests and completed in 245.26 seconds: 9,245 passed, 133 failed,
91 skipped (plus 10 subtests). It exited 1, not timeout. This exploratory run
overlapped a fetch that completed the initial shallow clone; the final receipt
records a separate clean-main run after that fetch. Neither establishes the
identities of the Mac's previously unnamed nine failures.

The full-history clean-main comparison completed in 254.25 seconds with the
same 133 failures. PR #3161 at `b84cfd7e1a2c96a60590317a60af5a2283ae21f2`
completed in 250.65 seconds: 9,243 passed, 133 failed, 91 skipped. The failed
nodeid/phase sets are identical, with no PR-only failure in this environment.
Exact outcomes and all named main failures are retained in
`docs/receipts/pytest-cli-3162/measurements.json`.

The candidate with work-stealing and the avtopoiesis snapshot completed in 124.33
seconds: 9,247 passed (including two new regressions), the same 133 failed
nodeid/phase pairs, and 91 skipped. This is a 51% reduction from the clean-main
load-scheduler run on this Linux host. A separate unchanged-main work-stealing
control completed in 145.60 seconds with the identical 133 failures: 43% less wall
time than unchanged main with the load scheduler. This isolates a substantial
scheduling contribution; the candidate with its YAML fix completed in 124.33 seconds.
These single-run comparisons are evidence for the chosen improvements, not
statistical benchmarks or a new Mac timeout budget.

The configured command with `--maxfail=20` also completed, in 229.79 seconds,
with pytest exit 2 after its maxfail interruption: 72 failed, 9,204 passed,
91 skipped. Xdist had in-flight work beyond the threshold; every reported
failed nodeid/phase was already in the clean-main inventory. This was not a
timeout and was not a passing or fully completed suite. The API suite passed
52 tests; focused instrumentation and audit regressions passed 24 tests.

Scoped verification passed 40 of 43 cheap predicates on its initial batch.
The new plan's missing issue/PR metadata was corrected and its predicate passed.
Two remaining failures reproduce on unchanged main: public-live GitHub
observation fails closed without the required execution access, and private-vault
cannot start gpg-agent in this container. The scoped resolver therefore did not
enter its heavy wave. Separate full CLI/API results do not make that scoped
receipt green. Keep the proposed repair in draft pending host acceptance.

Summed phase time is different from suite wall time under xdist:

| File | Summed phase time before improvements |
|---|---:|
| `test_overnight_trial.py` | 234.58 s |
| `test_avtopoiesis.py` | 92.10 s |
| `test_agent_state_file_provider.py` | 50.57 s |
| `test_workstream_command.py` | 49.05 s |
| `test_check_knowledge_alive.py` | 48.94 s |

The slowest individual calls were avtopoiesis idempotence (21.57 s), strict exit
(19.67 s), autonomous Jules workstream (14.01 s), and open-stream readiness parity
(13.84 s). Overnight-trial tests dominated the final stretch through repeated
synthetic eight-hour custody histories, rather than one observed infinite test.
They remain enabled. Host evidence is needed before assigning them a separate gate.

Profiling one avtopoiesis audit showed 77 YAML loads: the same sensor registry was
parsed once for each of 75 doors. YAML loading consumed 22.79 of 25.56 profiled
seconds. A build-scoped snapshot reduces this to two YAML loads; it is reset even
on exceptions and is not retained for the next audit. The corresponding profile
completed in 3.06 seconds. This is a measured hot-path improvement, not proof that
the Mac's overall timeout is repaired. Existing idempotence and strict-exit tests
remain, with new regression checks for load count, freshness and exception cleanup.

Remaining acceptance belongs to #3162: execute the instrumented gate on the Mac,
compare named failures with clean main, and use repeated quiet-host measurements
to decide whether further test repair, scheduling/isolation, or timeout margin is
justified. #3161's focused tests and successful remote PR Gate do not replace this
host evidence, and pip-audit supplies no evidence about pytest performance.
