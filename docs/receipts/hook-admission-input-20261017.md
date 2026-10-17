# Limen admission boundary repair

Date: 2026-10-17. Owner: Limen lifecycle. Source: user-supplied hook-estate
implementation design. Native session: 01a14ab2-92e3-7303-9d6f-aba7c66863ed.

## Scope and evidence

Malformed mutation input previously produced only a warning; an open stdin pipe
outlived the native hook timeout. Process fixtures reproduced both failures before
the repair. The repository runner also silently skipped a missing policy script.

The admission reader now limits input to 1 MiB and shares an eight-second evaluation
deadline across stdin, parsing, capability discovery, delegation and local policy.
Cancellation crosses lower-level error recovery; owned child groups are terminated
through the existing bounded subprocess owner. Delegate stdout is capped at 64 KiB,
stderr at 8 KiB. Invalid verdicts, crashes and unavailable mandatory entrypoints
produce one native denial; known informational lifecycle events remain nonblocking.
The existing startup, read-only action and exact Stop lease-release contracts remain
covered by the original admission suite.

The project registrations bind their event with `--event`, independently of JSON
payloads. Input cannot downgrade a registered PreToolUse event to a lifecycle event.
Error evidence contains class/reason metadata, never copied input or child stderr.

Focused predicate:
`cli/.venv/bin/python -m pytest cli/tests/test_hook_admission_boundary.py cli/tests/test_codex_host_admission_hook.py -q`
passed 61 tests in 22.44 seconds. The suite covers malformed, oversized and invalid
UTF-8 input, stalled stdin, shared input/delegate deadline, invalid and multiple
verdicts, crashing/flooding delegates, descendant cleanup, registered runner execution,
missing policy script, and original action-admission/lifecycle regressions.
The new scoped gate keeps those fixtures selected for future entrypoint changes.
`check-gates.py` and `check-test-hygiene.py` passed; the complete scoped batch is the
publication gate and its result must be recorded separately.

The first complete scoped batch passed all 31 cheap gates, including the 61-test
admission shard, then exited 75 before either heavy suite: pressure sensors were
unavailable with the deliberately narrowed verification PATH (which omitted
`/usr/sbin`). The corrective batch restores the original host PATH while selecting
the isolated test environment. It also covers a reproduced missing-interpreter
case: the shell runner now emits a native denial rather than exiting 127 silently.

The corrective batch on `c0c23c7d` exited 1: 30 cheap gates passed, including
62 admission tests in 22.68 seconds and whole-estate Python lint/format. The sole
failure was `verify-parallel-test` / `timeout-process-group`: the timeout fixture
never recorded its descendant. That exact failure and venv-launch sensitivity
already have an open owner, [Limen #2886](https://github.com/4444J99/limen/issues/2886).
The full CLI/API suites did not execute because the cheap wave failed. Neither
batch is reported as a green scoped result. No unchanged retry or merge is
authorized by these partial results; preserve the draft for that verification
owner and native hook acceptance. Documentation-only publication of this result
does not change the tested source paths; passing shard evidence remains scoped
to the recorded source commit.

## Integration and acceptance

This is an independent Limen packet. The concurrent Domus branch
`fix/hook-estate-evolution-20261017` owns shared inventory, dispatcher and adapters.
Its checkout and changes were preserved. The global wrapper's exact project-command
recognition must account for the added event argument before it can suppress itself;
until then it retains its conservative global fallback. This packet does not assert
that duplicate admission is resolved.

Changing a registered command may require native trust review. No trust state was
manufactured or enabled, no deployed configuration was edited, and no client was
restarted. Deployment, interception, consumed denial, permitted-action success, two
fresh sessions per surface and the 24-hour/20-event observation gates remain pending
with the hook-estate rollout owner. Fixtures establish source behavior only.

Retain the isolated topic checkout through publication and acceptance. The primary
Limen checkout's one-commit drift and unrelated files belong to the existing release
owner; this session did not fast-forward or otherwise alter that checkout.
