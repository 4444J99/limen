# Claude admission — admitted verification attempt

Owner: https://github.com/4444J99/limen/pull/2901
Source: f41a47e95480c25df77ced72bf9599a779283927.

On 2026-10-17 at 17:16 UTC, refreshed host evidence allowed one scoped run:
`bash scripts/verify-scoped.sh` from the retained branch checkout.
This followed the earlier pressure denial; no admission override was used.

All ten cheap gates passed, including whole-estate Ruff lint/format, changed-file
syntax, hygiene, writer contract, runner coverage and documentation checks.
The CLI gate then ran for 300.09 seconds and failed at its existing deadline.
Progress reached approximately 99%; two failing test markers appeared before
termination. No final failure names or summary were emitted. Neither ordinary
pytest cache location contained lastfailed state after termination. Failure
identity is unmeasured; no assertion is made that these were unrelated failures.

The overall verifier exited 1. API verification did not execute because the
CLI wave failed. Earlier focused boundary checks remain passing evidence only
for their own scope. The branch remains draft and unmerged.

No deadline, admission threshold, test selection, cleanup assertion or provider
capability was weakened. No unchanged retry was launched. Required next work
belongs to this PR: preserve first-failure diagnostics within the existing
bounded verifier, identify/correct failures, then obtain all implicated gates.
Native trust, interception, complete enforcement, observation, deployment and
session release remain separate acceptance requirements.
