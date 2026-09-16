# Authenticated dependency completion intake

Owner: Codex; shared workflow PR organvm/.github#26 and L-DEPENDABOT-DELIVERY-ARM.

Add a disabled-by-default hint intake to the existing keeper, scoped to repository ID 1154799938 and an exclusive dependency_observer principal. Persist bounded idempotent run/attempt/head hints atomically in keeper storage, with conductor-only readback. No task, capacity debit, provider invocation or merge is authorized by a hint. Ordinary conductor and observer credentials cannot submit hints.

Remaining implementation: conductor consumption must independently verify the current repository/run/attempt/PR and trusted metadata, submit one bounded assessment through existing broker admission, bind the terminal receipt, and reconcile ambiguous outcomes. The existing synchronous relay transaction remains relay-only. No workflow trigger, credential installation, protection change or deployed activation is included. Keep this candidate draft until the whole intake/consumer contract is implemented and verified; fixtures do not prove protected canaries.

## Receipt reconciliation

A conductor may bind a run lookup hint to the stored completion tuple. The keeper reads its own graph, requires the deterministic work key, exact source binding, a single nondelegating read-only packet, and an accepted receipt for the current lease generation. Caller-supplied receipts are rejected by the route shape. Missing or stale receipt authority remains unmeasured; recorded assessment never becomes merge acceptance. Replays preserve the historical accepted observation and conflicting bindings fail closed.

The actual source-bound assessor, packet submission/consumer and protected merge route remain unfinished; this reconciliation capability does not create or execute those components.
