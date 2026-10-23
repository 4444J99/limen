# pytest-cli repair review

Owner: verify / [issue #3162](https://github.com/4444J99/limen/issues/3162).
Status: partial; no claim that the original Mac timeout is resolved.

The implementation preserves the full CLI suite, assertion outcomes, gate deadline,
hermetic environment, machine-wide admission and process-group cleanup. It adds an
opt-in controller observer and a build-local YAML snapshot in avtopoiesis.

Review checks performed:

- An assertion failure followed by a deliberately hung test retains both the failure
  and the unfinished test after group termination, serially and with two xdist workers.
- Setup, call and teardown assertion failures retain their own phase and traceback;
  collection errors persist before session completion.
- Heartbeats remain visible under pytest fd capture, name teardown, and survive a
  test that replaces the global monotonic clock. Disabled diagnostics create no journal.
- Journals use separate private directories and line flushing. Their summary tolerates
  only an incomplete final record; it does not label a killed run complete or successful.
- The avtopoiesis load-count regression failed before the change (five loads for three
  synthetic doors instead of two). It passes after the change; edits appear in the next
  build and an exception cannot leak a stale snapshot. Existing idempotence and strict
  exit checks remain. Before/after real audit JSON bytes are identical.
- The observer does not execute subprocesses or install signal handlers. Its duplicated
  console descriptor is non-inheritable and closes at unconfigure. Xdist workers do not
  create competing writers for the controller journal.

Limits: the original nine Mac failures are still unnamed; Linux failures are not an
explanation for them. The Mac connection was offline. Artifact-upload source configuration
is not proof of a completed remote artifact upload. Dependency audit #3145 is separate.
Use `measurements.json` for exact run outcomes and named baseline failures.

Merge remains contingent on the repository's exact-head verification and merge policy.
Keep #3162 open until the affected host completes an instrumented run and any residual
failures receive evidence-backed disposition. Do not undraft or merge #3161 based on
this repair's focused tests.
