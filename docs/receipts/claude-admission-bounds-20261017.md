# Claude admission boundary receipt

Owner: this branch's draft PR; Limen native hook source only. No deployment,
native trust changes, admission claim, or new hook registration.

Existing Codex repair remains owned by PR #2900 at
`c3b62bb891c901e876dbea981133d1b3f1edd629`; this change does not duplicate it.
Domus retains mandatory shared guard registration and its `onFailure: block` policy.

Implemented Claude admission's 1 MiB stdin ceiling, eight-second total deadline,
strict event/tool envelope, and structured denial on unevaluated requests.
The timer restores the prior handler and preserves any earlier process deadline.
Admission classification, writer ownership, and SessionEnd behavior are unchanged.

Validation:

- `cli/.venv/bin/python -m pytest cli/tests/test_claude_hook_boundary.py cli/tests/test_provider_owner_process.py -q`:
  20 passed, using the existing isolated Codex repair checkout's interpreter.
- Scoped verification against origin/main: all nine cheap gates passed, including
  whole-estate Ruff lint/format, syntax, runner coverage, and test hygiene.
- Scoped heavy verification exited 75: host admission denied for
  `swap-fraction,disk-throughput`; no retry or bypass. Full pytest-cli/api remains
  required before merge and belongs to the draft PR's acceptance predicate.

Retention: `/Volumes/Archive4T/limen-hook-bounds-20261017` remains retained for the
root session's custody-aware release; no checkout retirement was attempted here.
