# Stabilize Limen, prove remote dispatch, then offload

Authority: direct user approval in session 01a1327e-79a0-7f40-b50f-e4b61343de8e.
Owner: https://github.com/4444J99/limen/issues/2740. Existing source repair: PR2850.

## Contract

Retain the current public deterministic verification sandbox and all existing limits.
New remote requests bind the keeper's original attempt and verification deadlines
through request identity, persistence, workflow execution, receipts and harvest.
Reject expiry before dispatch and after queueing; preparation and execution share
the original remaining budget. Timeout must terminate the actual owned container.
Historical receipts remain readable; they do not authorize new unbounded execution.

### Task 1: Existing repair reconciliation

Compose PR2850 with dependency-fixed main once, observe implicated hosted checks,
and integrate only after the owning predicates pass. Review existing profile PRs
without duplicating them. Reuse #2745's existing exact-candidate hosted receipt.
Record live/public evidence failures separately from source validation.

### Task 2: Bound the remote adapter

Add request/receipt deadline binding and prelaunch/queued-expiry enforcement.
Share the remaining budget across preparation and predicate processes. Ensure
timeout removes the named owned Docker container. Add negative and recovery tests
before implementing; verify the existing remote execution suite plus scoped gates.
Do not advertise the lane before its complete contract is verified.

### Task 3: Hosted canary and follow-up

After verified implementation merge and genuine canonical terminal task custody,
dispatch python3 scripts/check-test-hygiene.py through the broker-managed adapter.
Accept only exact request/source/workflow/receipt matching and idempotent harvest.
Then select at most two distinct eligible verification jobs from approved capacity.
Never fabricate a parent task or terminal receipt to fit the adapter.

### Task 4: Independent operations and observation

Route the public/private Ops carrier correction to private ops#6, preserving
inspect/apply and pinned-source authorization. No production activation is included.
Observe submitted runs asynchronously; profile acceptance retains eight natural
daily scheduled successes. Preserve all active/dirty work and the primary checkout.

## Current receipts and implementation constraints

Policy addition preserves five prior outcomes; the first wave has one branch and
zero issue/worktree growth allowance. A clean, unoccupied existing isolation tree
is reused; its prior commit remains in three existing refs and on GitHub.
Run run-4ef082bfc8e3345fcbdf1b70f2e6b243 has original deadline
2026-10-13T01:09:24.343Z. Its root packet has no child fanout authority; a pilot
must use canonical task dependency custody and separately valid admission, rather
than silently expanding this packet. Record any resulting execution boundary.

Pre-flight: request producer, workflow consumer and harvest validator must use the
same deadline bytes; persisted request recovery must never allocate a fresh budget.
The existing PR2850 hosted technical-readiness failures are outside the deadline
change and remain visible in the existing owner.

## Attempt checkpoint — 2026-10-12 21:11 EDT

The original admitted attempt expired at 2026-10-13T01:09:24.343Z. Preserve this
branch as a draft, not a merge candidate or enabled capability. Actual full remote
suite result: 157 passed, 3 failed, 1 skipped. The three harvest regressions share
the newly introduced missing json import; Ruff independently reports F821.
Seven new deadline regressions cover identity, prelaunch expiry, queued expiry,
inverted bounds, container cleanup, altered receipt bounds and saved identity.
The early five-test deadline subset passed; the complete suite is not green.

Remaining implementation: fix the harvest import and malformed-custody handling;
bound all checkout/image/git preparation to the original deadline; validate actual
completion timing in attested receipts; integrate and test the narrow journaled
dispatch admission exception; prove historical receipt compatibility. Then run the
implicated scoped gates and obtain an independent review before considering merge.
The current native remote-provider gate intentionally remains closed.

Only after verified merge and genuine canonical terminal implementation Task
custody may a separately admitted verification child run. The root packet's zero
fanout authority must not be silently widened. Preserve original accounting and
charge any permitted corrective attempt to this same outcome; no automatic retry
or replacement deadline is authorized by this checkpoint.

Profile PRs were inspected but not integrated. #2745 already has its positive
historical receipt. Ops owner-run entrypoint and profile manual/natural execution
remain pending under their existing owners. Primary divergent checkout and the
other active recovery checkout are unchanged by this work.

## Corrective attempt — 2026-10-12 21:51 EDT

The direct continuation admits one changed-input corrective root,
run-9c99a5ee4cba4013cf660daf9dc36f25, under the same approved outcome. Original
accounting is retained: first attempt 1800 reserved seconds plus correction 1800;
the cumulative ceiling remains 7200. The corrective attempt expires at
2026-10-13T02:08:12.951Z and its verification reservation expires at
2026-10-13T01:54:51.786Z. The policy addition only adds the exact correction key;
all five previous outcomes, resource limits and recovery concurrency remain unchanged.

Draft PR: https://github.com/4444J99/limen/pull/2855 (owner 4444J99).
The corrected source now bounds checkout, image preparation, Git attestation and
container execution; cleanup has reserved runway and request-labelled ownership.
Receipts require ordered, deadline-bounded start/completion evidence. Recovery
loads original bounds and malformed custody fails closed. The journaled exception
is limited to GitHub Actions verification-only tasks; public visibility, genuine
implementation-parent custody and the original sandbox restrictions still apply.

Verification: all 17 cheap scoped gates passed; remote-admission shard 227 passed
with one local Docker-dependent skip. Additional remote/deadline/harvest/accounting
batch: 186 passed with one Docker-dependent skip. The heavy scoped wave returned
exit 75, heavy-lease-held, owned by a different verify-scoped process. No unchanged
heavy-admission retry or lease interference is permitted. The Linux containment
integration additionally verifies actual Docker container absence after timeout;
that added daemon test still requires hosted execution.

Review found an inherited probe-directory permission defect: the temporary probe
was mode 0700 while the sandbox runs as UID 65534. A red/green regression covers
making only that generated public probe readable. No host secrets or additional
mounts are exposed. A separate fresh reviewer has not been admitted; no merge or
accepted hosted canary is claimed. The required heavy verification and review
remain merge conditions on PR2855, not a claim of complete first-wave acceptance.
