# Peer-conductor mesh implementation receipt

This receipt owns the bounded implementation in
<https://github.com/organvm/limen/pull/1265>, branch
`work/peer-conductor-mesh-20260718`. It does not claim that the production broker was deployed or
that the whole-PR campaign reviewed, repaired, merged, or closed any pull request.

## Delivered substrate

- versioned session, packet, lease, and receipt contracts with generated JSON Schemas;
- a bounded-DAG coordination kernel with idempotency, authority attenuation, leases, fencing,
  adoption, cooperative stop, harvesting, and restart recovery;
- matching CLI and MCP conduct surfaces plus compatibility submission for legacy task operations;
- an authenticated Worker/Durable Object cutover scaffold with GitHub SHA compare-and-swap
  projection;
- agent-neutral lane discovery, fanout, workstream launch, session-source adapters, ianva config
  generation, and native context injection;
- an organization-level Copilot custom-agent profile source, preserved in
  <https://github.com/organvm/.github/pull/21>;
- a fully paginated, exact-head `organvm` PR census and deterministic campaign graph builder.

## Deliberately unclaimed

The Worker is not safe to deploy yet. Its shared bearer authenticates endpoint access but does not
bind a request to a server-derived principal, registered session, root authority, or caller role.
Reservation responses also expose the executor capability to the submitting conductor. Principal
binding and executor-only, loss-recoverable capability delivery are merge gates.

The five-by-five live Codex/Claude/Copilot/Agy/OpenCode matrix has not run. The checked-in matrix is
test evidence, not a live provider receipt. No campaign leaf is “reviewed,” “ready,” or “done” from
the census alone. Exact-head readiness remains owned by
<https://github.com/organvm/limen/pull/1171>.

Copilot billing reports no assigned organization seats. This work did not buy or assign a seat,
install a credential, deploy the Worker, merge or close a PR, spend paid overage, or mutate
`tasks.yaml`.

## Verification

Implementation checkpoint `e39a40dd` passed the focused protocol, broker restart, campaign, CLI,
fanout/cell, session-source, ianva, MCP/API, Worker, workstream, dispatch/harvest, instruction, and
direct-writer slices recorded in this PR's commit history. Current `main` was then integrated at
`b437fd1d58ac09a1bcc43a3a8512937781773714`, including the newer host-admission and finite-runway
workstream contract.

On that integrated head:

- `python3 scripts/task-writer-audit.py --check` passed with zero unauthorized Python, shell,
  Worker, or instruction-layer lifecycle writers;
- `git diff --check` passed;
- `tasks.yaml` was byte-identical to `origin/main`;
- `scripts/verify-scoped.sh --base origin/main --require-base` correctly escalated the
  deployment-surface diff to `verify-whole.sh`;
- machine-wide host admission denied that heavy local run on `backblaze-rss`, `swap-fraction`, and
  `disk-throughput`, so the governor was not bypassed and exact-head remote CI owns the heavy proof.
- the final complete GitHub census covered 307 repositories and 1,146 open-PR heads without API
  errors; the pass-2 to pass-3 comparison found 6 new keys, 5 missing keys, and 2 moved heads, so
  the active estate did not claim a false zero-growth fixed point.

This remains a draft receipt until PR #1265's remote checks pass and the explicit production-security
and live-mesh gates above are closed. The continuation capsule owns those residuals; no local-only
implementation state remains.
