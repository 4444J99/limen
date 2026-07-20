# Symmetric peer-conductor protocol

Limen conduct is one coordination protocol shared by every native agent lane. A conductor is a
temporary capability carried by a registered session and bounded work packet; it is not a master
role. TABVLARIVS remains the non-model keeper for idempotency, work graphs, leases, generations,
fencing, and task-board projection.

## Surfaces

The CLI and MCP expose the same operations:

| CLI | MCP |
| --- | --- |
| `limen conduct capabilities` | `conduct_capabilities` |
| `limen conduct register` | `conduct_register` |
| `limen conduct submit --packet FILE` | `conduct_submit` |
| authenticated `POST /api/conduct/graphs` | fanout graph registration |
| `limen conduct split RUN --packet FILE` | `conduct_split` |
| `limen conduct graph RUN` | `conduct_graph` |
| executor-authenticated `POST /api/conduct/leases/LEASE/claim` | executor lease claim |
| `limen conduct heartbeat LEASE` | `conduct_heartbeat` |
| `limen conduct report LEASE --receipt FILE` | `conduct_report` |
| `limen conduct harvest RUN` | `conduct_harvest` |
| `limen conduct adopt RUN` | `conduct_adopt` |
| `limen conduct cancel RUN` | `conduct_cancel` |
| `limen conduct request-stop RUN` | `conduct_request_stop` |

The canonical JSON Schemas live in `spec/contracts/conduct/`. Regenerate them with:

```bash
python3 scripts/generate-conduct-schemas.py
```

The local SQLite client is an explicit test/development adapter selected by
`LIMEN_CONDUCT_STATE`. Production and cross-host callers must use the authenticated HTTPS endpoint
selected by `LIMEN_CONDUCT_URL` and `LIMEN_CONDUCT_TOKEN`. New claims fail closed when neither is
configured.

## Records and graph rules

- `ConductorSessionV1` preserves the native agent, surface, provider/native run identity,
  capabilities, transport, worktree, liveness, concurrency, and `human_protected` flag.
- `WorkPacketV1` carries immutable intent/execution hashes, lineage, authority, resource claims,
  predicate, receipt target, deadline, spend, retry, depth, and fanout bounds.
- `LeaseV1` records the selected native executor and server-bound principal, exact resource
  generations, observed Git heads, a hashed capability token, heartbeat, and hard deadline.
- `RunReceiptV1` records exact executor/provider identity, old/new heads, changed paths, checks,
  reviews, predicate evidence, spend, children, and terminal outcome.
- `ExecutorAttemptV1` records one provider launch identity and monotonic lifecycle in keeper state.
  It is bound to the exact run, lease generation, and authenticated executor. Provider run IDs and
  URLs are durable and readable; lease capability tokens and their hashes are never returned.
  The keeper rejects attempts beyond the packet limit and refuses a new attempt while an earlier one
  remains live. A read-effect receipt is authorized only when its changed-path set is empty and its
  before/after head maps are identical.

Delegation is a bounded DAG. A child reserves through the broker before it consumes separate
capacity or mutates state. Its authority, repository/path scope, deadline, spend, retry, depth, and
fanout cannot exceed its parent. Repeated ancestry work keys are rejected. A dead conductor does
not cancel children; a healthy peer can adopt only after the keeper proves absence. Reserved work
may be cancelled, while started work accepts only a cooperative stop request.

## Resource leases

Claims are normalized and acquired in sorted order:

| Key | Coordination rule |
| --- | --- |
| `task/ID` | one executor and one budget debit |
| `pr/OWNER/REPO/N/write@HEAD` | one exact-head writer |
| `pr/OWNER/REPO/N/review/PROVIDER@HEAD` | one receipt per provider/head; other providers coexist |
| `branch/OWNER/REPO/BRANCH` | one branch writer |
| `path/OWNER/REPO/BASE/PREFIX` | overlapping prefixes serialize; disjoint prefixes coexist |
| `worktree/REALPATH` | one owning session |
| `repo-common-dir/OWNER/REPO/plumbing` | short fetch/worktree plumbing lock |
| `base/OWNER/REPO/BRANCH/integrate` | serial base integration |
| `agy-scratch/OWNER/REPO` | one Agy scratch writer |
| `external/EFFECT` | explicit side-effect lease |

A write packet without a recognized write scope receives a conservative repository-wide lease.
Review leases coexist with writers. Moved exact heads fence the lease, and a stale, transferred, or
expired receipt remains evidence only: it cannot update the run, task, budget, branch, or PR.

Direct human sessions register as protected. Other peers can observe them but cannot select, adopt,
cancel, signal, retune, stash, reset, or reap them.

## Remote keeper and board projection

`web/worker/src/conduct/` implements the authenticated Cloudflare Worker endpoint and a singleton
Durable Object. The Durable Object serializes lifecycle transitions. Task compatibility events are
committed to the GitHub-owned `tasks.yaml` projection with Contents API SHA compare-and-swap before
the corresponding keeper state is acknowledged.

The checked-in keeper derives every caller from the credential-wall principal registry, binds
sessions to principals server-side, authorizes lifecycle operations by role and owning conductor,
and never returns a lease capability to a conductor. The selected executor claims a deterministic
HMAC capability through its own authenticated route; the capability is bound to lease ID,
generation, and executor principal, so a lost response is recoverable while cross-principal and
stale-generation replays fail closed. Graph submission is one serialized all-or-nothing keeper
transition and excludes task-board packets, keeping direct fanout board-independent.

Production fanout is admitted only through a freshly deployed Worker with credential-wall secrets
and a native-lane canary receipt for that exact merged runtime.

Required production configuration is credential-wall owned:

- one conductor-only client-side `LIMEN_CONDUCT_TOKEN` per native lane;
- a distinct executor-only token per remote executor service;
- secret Worker `LIMEN_CONDUCT_PRINCIPAL_REGISTRY` binding bearers to principal metadata and roles;
- secret Worker `LIMEN_CONDUCT_CAPABILITY_SECRET`;
- `LIMEN_GITHUB_REPO`, `LIMEN_GITHUB_BRANCH`, and `LIMEN_GITHUB_PATH`;
- secret `LIMEN_GITHUB_TOKEN`;
- the `CONDUCT_KEEPER` Durable Object binding declared in `web/worker/wrangler.toml`.

Do not put token values in commands, capsules, receipts, commits, or PR text. Deployment and secret
installation are external effects and require their own authority/lease. Until the authenticated
remote endpoint is deployed, existing leased work and read-only inspection may continue, but new
canonical claims and transitions remain unavailable.

`tasks.yaml` and former cell boards are projections, never independent writers. Legacy task
add/status/claim tools submit compatibility packets through the same keeper. The direct-writer
predicate is:

```bash
python3 scripts/task-writer-audit.py --enforce-zero
```

## Native lane wiring

The live lane registry in `limen.census` owns capabilities, transport, native fanout, harvest,
concurrency, metering, health, and authentication references. Dispatch and fanout query that
registry; they do not carry a Codex/Claude fallback hierarchy or fixed model table.

ianva generates native configuration for Codex, Claude, Copilot CLI, Agy, and OpenCode. Workstream
launch accepts `--agent auto|LANE --conduct`, registers a protected direct session, and injects
executor identity plus root/parent/run, conductor, task, lease-generation, and execution-hash
context. The broker credential is removed before the native model process starts.

The canonical Copilot cloud profile source is
`integrations/copilot/limen-conductor.agent.md`. It is published to
`organvm/.github:/agents/limen-conductor.agent.md`, not to Limen's repository-level
`.github/agents/` directory, so Limen does not override the organization profile. Its URL and bearer
are Agents variable/secret references, and the profile leaves model choice to provider Auto.

## Whole-PR campaign

`scripts/conduct-pr-campaign.py census` enumerates every organization repository and paginates every
open-PR connection beyond GitHub's 100-node page. Each leaf is keyed as
`OWNER/REPO#NUMBER@HEAD`, gets a disposition and durable receipt target, and can be converted into a
root/cohort/exact-head leaf graph. A second complete census is a fixed point only when it introduces
no new work key or moved head.

The census is admission evidence, not a review receipt. Exact-head readiness additionally requires
the review-gate owner to prove stable head/base, green exact-head checks, Copilot plus independent
peer review, fully paginated unresolved-thread count of zero, no effective requested-changes state,
and a nontrivial intended diff. Campaign execution must fail closed until that owner predicate and
the authenticated broker are live.

Run:

```bash
python3 scripts/conduct-pr-campaign.py census \
  --owner organvm \
  --output docs/receipts/pr-campaign/current.json
python3 scripts/conduct-pr-campaign.py verify \
  --previous docs/receipts/pr-campaign/previous.json \
  --current docs/receipts/pr-campaign/current.json
```
