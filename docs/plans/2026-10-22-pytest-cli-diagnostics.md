# pytest-cli diagnosis and repair

Issue: #3162
PR: (pending)

Goal: resolve #3162 using named test/phase evidence without weakening verification.
Spec: https://github.com/4444J99/limen/issues/3162 and the current direct-session request.

- [x] Measure clean main 13a7934bd18fe933e359e741110dda15ec8fa976 on Linux, Python 3.12,
  using the mandatory wrapper, xdist auto, incremental names and phase durations. Preserve
  the exact command, exit code and environmental limits. Do not infer a Mac budget from Linux.
- [x] Add subprocess regression tests first: serial and xdist setup/call/teardown failures,
  collection errors, and a failure followed by a hung test terminated as a process group.
- [x] Add opt-in diagnostics through the hermetic runner: controller-side line-flushed JSONL
  reports with nodeids, phase durations and failure detail; periodic active-test heartbeat;
  bounded console summary. Keep pytest exit codes and gate deadlines intact.
- [x] Wire diagnostics into pytest-cli, register their own focused regression predicate, and
  replace the unsupported ten-minute note with measured evidence and the profiling procedure.
- [x] Use observed slow tests to identify an underlying cause. Compare candidate fixes and
  failures on clean main and PR #3161's exact head b84cfd7e1a2c96a60590317a60af5a2283ae21f2.
  Separate platform/access failures, genuine assertion failures and aggregate timeouts.
- [ ] Run focused coverage and the scoped verification batch. Publish through the repository
  PR rail only with the required evidence; keep unresolved host execution owned by #3162.

Review focus: xdist controller receives starts before a hung worker; teardown remains visible;
failed collection persists; hard termination leaves valid completed JSONL records; nested
runner tests keep environment isolation. Failure journals may contain captured test output and
must be reviewed before publication. No production secrets or raw host logs belong in git.

Implemented improvements: xdist work-stealing distributes the expensive tail;
avtopoiesis reads each YAML document once per build and releases that snapshot
even on errors. Native Mac acceptance remains owned by #3162.
