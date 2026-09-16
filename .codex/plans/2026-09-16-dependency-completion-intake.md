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
