# Authenticated dependency completion intake

Owner: Codex; shared workflow PR organvm/.github#26 and L-DEPENDABOT-DELIVERY-ARM.

Add a disabled-by-default hint intake to the existing keeper, scoped to repository ID 1154799938 and an exclusive dependency_observer principal. Persist bounded idempotent run/attempt/head hints atomically in keeper storage, with conductor-only readback. No task, capacity debit, provider invocation or merge is authorized by a hint. Ordinary conductor and observer credentials cannot submit hints.

Remaining implementation: conductor consumption must independently verify the current repository/run/attempt/PR and trusted metadata, submit one bounded assessment through existing broker admission, bind the terminal receipt, and reconcile ambiguous outcomes. The existing synchronous relay transaction remains relay-only. No workflow trigger, credential installation, protection change or deployed activation is included. Keep this candidate draft until the whole intake/consumer contract is implemented and verified; fixtures do not prove protected canaries.

## Receipt reconciliation

A conductor may bind a run lookup hint to the stored completion tuple. The keeper reads its own graph, requires the deterministic work key, exact source binding, a single nondelegating read-only packet, and an accepted receipt for the current lease generation. Caller-supplied receipts are rejected by the route shape. Missing or stale receipt authority remains unmeasured; recorded assessment never becomes merge acceptance. Replays preserve the historical accepted observation and conflicting bindings fail closed.

The actual source-bound assessor, packet submission/consumer and protected merge route remain unfinished; this reconciliation capability does not create or execute those components.

## Authenticated consumer

`limen conduct dependency-completions` reads hints. `limen conduct consume-dependency-completion --key KEY --packet REVIEWED_PACKET.json` validates the exact tuple/work key and nondelegating read-only scope, submits at most once through normal broker admission, then reconciles once. A prior run binding skips submission. Lost submit responses remain unmeasured; a later identical packet relies on the keeper work-key index rather than a local retry loop. Pending results exit 77. The consumer accepts no local broker fallback and no caller-supplied receipts.

The reviewed source-bound packet producer and isolated assessor deployment remain to integrate. The shared assessor now exists in organvm/.github PR 26, but that open source head is not a deployed trust pin. No new run was submitted live and no intake was activated.

## Pinned assessor source and isolated execution

The consumer now has a source-integrity and bounded execution library. A trusted
deployment must supply an independently reviewed source commit, SHA-256, and
explicit read credential. The library reads only the regular Git blob at that
commit, disables local replacement refs, and checks its bounded bytes and digest.
Working-tree changes are not execution inputs. Integrity is not review approval.

Execution uses the captured bytes in a private temporary directory, Python isolated
mode, an explicit minimal environment, and the existing bounded process-group
runner (95 seconds, 64 KiB stdout, 16 KiB stderr). It never inherits conductor or
ambient GitHub credentials. Results require exact repository/run/attempt/head
binding; HOLD remains HOLD and REVIEW_READY never authorizes acceptance or merge.
Temporary source cleanup, malformed pins/results, replacement refs, credential
isolation, and runner failure redaction have focused coverage.

The reviewed packet producer and deployment wiring remain implementation work.
No credential was minted, assessor pin approved, policy enabled, or live assessment
launched by this change. The full plan remains incomplete.

## Read-only packet production

`limen conduct compile-dependency-assessment --hint HINT --contract CONTRACT
--source-repository REPO` emits one packet without contacting the broker or
executing source. CONTRACT contains exactly identity, executor_session_id,
deadline, predicate, receipt_target, work_loan, source_commit, and script_sha256.
The caller supplies reviewed deployment inputs and a keeper-authenticated hint;
compilation itself establishes neither authentication nor independent approval.
The pinned source is captured from Git before compilation. No source bytes or
credentials enter the packet.

The compiler preserves the exact four-field hint binding, read-only repository
authority, source commit/digest, one attempt, no children, explicit executor
session and required dependency-assessment capability. Its finite deadline
reserves more than 150 seconds for assessment and reporting and is at most 900 seconds away.
Existing work-loan validation rejects missing underwriting, nonexecutable
predicates and nondurable receipt targets. Persist and replay the same packet
after ambiguous submission; do not generate a new deadline. A real in-memory
keeper test proves exact replay reuses the run and changed source pins conflict.

Executor callback/CLI wiring, independently reviewed deployment inputs, and
protected activation remain required before readiness. No live capacity was
reserved or provider launched while producing this implementation.

## Keeper-admitted executor callback

`limen conduct execute-dependency-assessment --run-id RUN --contract CONTRACT
--source-repository REPO` consumes an already reserved single-root packet. Its
separate reviewed executor contract supplies executor identity, source commit and
SHA-256, repository coordinate/ID, predicate, broker URL, and two distinct named
credential references (`executor_credential_env`, `read_credential_env`). Generic
GitHub, conductor, and relay credentials are not fallback credentials. No secret
values are part of the contract or packet.

The callback reconstructs and compares the whole packet against its deployment
inputs, claims only the selected lease generation, and atomically registers one
new attempt before launching captured source. Simultaneous callbacks, ambiguous
admission, settled runs and changed contracts cannot launch a second assessment.
The accepted heartbeat must retain the 150-second execution/reporting runway.
Execution failure is a redacted blocked receipt; REVIEW_READY is an assessment
success with automatic_acceptance=false. Lost report responses preserve keeper
evidence and never trigger another execution. Real-broker tests cover these
paths and actual isolated child execution.

Independent source review, credential provisioning, bounded transport review,
executor registration/wake routing, and protected production activation still
require evidence. The production policy remains disabled. No live callback or
new provider launch was performed to test this implementation.

## Bounded callback transport

The callback, hint-read and hint-consume commands now use `AssessmentHttpClient`, preserving existing protocol methods
while isolating each HTTP exchange in Python -I. Secrets and request data arrive
over bounded stdin, never argv or ambient environment. Each request has a
20-second process wall limit, a 15-second socket timeout, 1 MiB request/response
limits, and bounded process output/cleanup. Redirects and ambient proxies are
disabled. HTTP error bodies are discarded and uncertainty never retries.
The reviewed endpoint cannot contain userinfo, query, fragment or a path prefix.

The packet and admitted lease must retain more than 150 seconds, covering the
95-second assessor plus bounded terminal heartbeat/report calls and cleanup.
Missing attempt, receipt, or child projection fields are unmeasured rather than
assumed empty. Tests use actual local HTTP exchanges for redirect, proxy,
oversize, malformed-response and authorization failures, plus timeout injection
against the already-tested bounded-process primitive. No live service was called.

## Cross-language handoff evidence

The actual Worker hint store/reconciler and Python keeper now have one integration
predicate spanning session registration, hint intake, packet reservation, isolated
callback execution, accepted receipt reconciliation and consumer restart. Another
human-protected executor is refused before launch. A dedicated cheap gate includes
all implicated Python, Worker and policy paths so a Worker-only change cannot
miss this boundary. Details and the finite deployment sequence are in
`docs/architecture/dependency-completion-assessment.md`.

A bounded authenticated capability read at 2026-09-16T09:58:52.196Z observed zero
registered dependency assessors and zero healthy unprotected assessors. Existing
registration is sufficient as a protocol; no alternate registrar or protection
bypass is needed. The production native wake route remains deployment work owned
by PR #2651, conditional on the existing #269/#1995 admission evidence and isolated
reviewed credentials. No live registration, lease, provider launch or activation
occurred during this verification. The full plan remains incomplete.

## Verification refusal: paired-custody cleanup

The first full CLI batch for the cross-language gate failed at
`test_single_rail_output_is_rejected_at_limit_plus_one` (stdout case): cleanup
returned `single-rail-check-termination-failed` instead of the original output
limit error. This recurred despite the existing five-second kill/reap budget.
The batch had 7,835 passing tests and two skips; it is not a green receipt.

Owner: Codex / this implementation PR and the paired-custody component. The root
cause remains unverified. The bounded cleanup now attaches a path-free stage
reason (TERM refusal, KILL refusal, unreaped leader, or surviving process group),
and the failing test preserves the original exception chain and those reasons.
Four deterministic tests assert that each stage still fails closed. Neither the
cleanup requirement nor the output ceiling or deadline was relaxed. The next
predicate is the admitted full CLI shard through `scripts/verify-scoped.sh`,
with focused paired-custody verification preceding it. Any later green run does
not by itself explain this intermittent refusal.
