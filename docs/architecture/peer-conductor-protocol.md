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
| `limen conduct canary full-mesh --receipt FILE` | authenticated protocol routes |
| `limen conduct campaign run --capsule FILE --terminal-predicate omega` | keeper graph registration and harvest |
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

Institutional campaigns use optional, backward-compatible typed extensions. `CampaignPacketV1`
binds a packet to its campaign ID, failed predicate, owner, next action, and byte output ceiling;
the packet's existing authority, work loan, and receipt target remain the authority scope,
value/cost case, and durable destination. `CampaignReceiptV1` records actual value alongside the
existing actual-spend map, content-free bounded-output evidence, precise blocker ownership, one
campaign boundary, and any successor-capsule reference. The keeper authorizes a campaign receipt
only when its campaign ID and output ceiling match the leased packet. Historical packets and
receipts without either extension remain readable and retain their original authorization rules.

Strict Omega supplies campaign leaves from declared data rather than a hard-coded rung table.
`institutio/governance/omega-remediations.json` must exactly cover the union of the core registry
and live sensor discovery. Each materialized remediation carries its current predicate, owner,
next action, required capabilities, attenuated non-delegating authority, work loan, output ceiling,
and receipt target. `logs/omega.json` schema 3 embeds that typed contract on every rung. A missing,
unknown, newly added, or tampered remediation makes the Omega contract invalid and cannot enter the
two-pass settlement proof.

Every live core or sensor rung declares exactly one fresh source-owned
`limen.omega_owner_receipt.v1` receipt. The shared runner maps source exit `0` to `PASS`, `1`
(and every non-protocol error) to `FAIL`, and `77` to `SKIP`; bounded evidence is hashed but never
stored in the receipt. Receipt validation binds the rung ID and predicate digest, rejects stale,
future, malformed, truncated, or non-passing evidence, and permits the two-pass convergence proof
to normalize only `observed_at`. Deterministic rungs may retain their source-specific semantic
inputs, but a live rung without exactly one standard owner receipt is an invalid Omega contract.

The canonical institutional supervisor joins those contracts without adding another keeper:

```bash
limen conduct campaign run \
  --capsule docs/continuations/EPOCH/workstream.json \
  --terminal-predicate omega
```

The command accepts only a tracked admitted capsule from a clean checkout at the exact live remote
default branch (currently `main`). It runs a fresh live strict-Omega evaluation, rejects untyped or inconsistent rung state,
derives provider-neutral packets from the current capability catalog, and submits the complete
root/leaf graph in one keeper transaction. Packet work IDs and work keys are deterministic for one
exact head, Omega contract, and evaluated state; a changed state receives a new identity while an
unchanged retry deduplicates. The supervisor accepts a reservation or harvest only when the keeper
acknowledges the exact graph.

Every invocation emits exactly one bounded boundary: `continue` after reservation and immediate
harvest, `switch` when no healthy accepting session can satisfy a required capability set,
`wait_relay` when a graph is busy or the capsule reaches T-30, `invalid` with a nonzero exit for
stale or malformed truth, or `settled` only after strict Omega holds and one `--run` plus two
unchanged `--check` receipts reproduce. T-30 admits no new leaves and marks the successor capsule
required; the continuation owner must publish and launch that successor before invoking another
epoch.

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
- workflow-injected `LIMEN_CONDUCT_RUNTIME_GIT_SHA` plus the `CF_VERSION_METADATA` binding;
- the `CONDUCT_KEEPER` Durable Object binding declared in `web/worker/wrangler.toml`.

Do not put token values in commands, capsules, receipts, commits, or PR text. Deployment and secret
installation are external effects and require their own authority/lease. Until the authenticated
remote endpoint is deployed, existing leased work and read-only inspection may continue, but new
canonical claims and transitions remain unavailable.

### Authenticated full-mesh canary

`limen conduct canary full-mesh --receipt FILE` is the fail-closed production protocol proof. It
accepts only the authenticated HTTPS client selected by `LIMEN_CONDUCT_URL` and
`LIMEN_CONDUCT_TOKEN`; the local SQLite adapter is rejected. The command does not launch providers,
install credentials, or deploy the Worker.

The caller supplies the exact runtime identity and credential reference names as JSON environment
contracts. Token values are hydrated separately through the named environment variables and must
never appear in either JSON contract:

```json
{
  "schema_version": "limen.conduct_runtime_identity.v1",
  "git_sha": "0123456789abcdef0123456789abcdef01234567",
  "deployment_id": "production-deployment-reference"
}
```

```json
{
  "schema_version": "limen.conduct_canary_credential_refs.v1",
  "credentials": [
    {
      "session_id": "alpha-conductor-session",
      "role": "conductor",
      "token_env": "LIMEN_CANARY_ALPHA_CONDUCTOR_TOKEN"
    },
    {
      "session_id": "alpha-executor-session",
      "role": "executor",
      "token_env": "LIMEN_CANARY_ALPHA_EXECUTOR_TOKEN"
    }
  ]
}
```

Set those objects in `LIMEN_CONDUCT_CANARY_RUNTIME_IDENTITY` and
`LIMEN_CONDUCT_CANARY_CREDENTIAL_REFS`. The Worker builds its runtime identity from the exact
workflow-injected Git SHA and `CF_VERSION_METADATA.id`. Its additive capability fields are
`runtime_identity`, `authenticated_principal`, and `authenticated_session_ids`; the canary requires
the remote runtime identity to equal the installed contract exactly. Each conductor credential must
authenticate exactly the `observer` and `conductor` roles, each executor credential exactly the
`observer` and `executor` roles, and each named session must be among the authenticated principal's
bound session IDs with the same native identity. Principal IDs and credentials are distinct across
the manifest.

Fresh execution also requires a session-owned bridge named by
`LIMEN_CONDUCT_CANARY_WAKE_BIN`. The control process resolves that executable before its first graph
write. For each edge it sends one bounded, nonsecret JSON request containing the exact
run/lease/generation, packet deadline and predicate, runtime Git object, executor session,
`native_session_id`, `native_run_id`, and credential-reference name. The bridge routes the request
to that already-running native session; it receives a sanitized environment containing the
credential-reference name, never a bearer. Inside the session, the hidden
`limen conduct canary executor-edge` callback independently requires matching
`LIMEN_SESSION_ID`, `LIMEN_NATIVE_SESSION_ID`, and `LIMEN_NATIVE_RUN_ID`, hydrates its own remote
client only from the exact requested credential-reference environment variable (a generic conduct
token is not accepted), rechecks its registered session and exact installed/keeper runtime, then claims,
heartbeats, executes, and reports. A missing bridge, identity mismatch, stale runtime, timeout,
output overflow, malformed acknowledgement, or acknowledgement without the exact terminal receipt
fails closed. There is no coordinator-side or local-adapter execution fallback.

The live capability response defines the denominator: every native agent with a healthy, accepting,
non-protected conductor session and an executor session that also satisfies the packet capability,
quota, and `active_leases < concurrency` bounds. The credential references must cover that
denominator exactly, with distinct conductor and executor sessions for each lane. No provider or
model table participates in discovery.

For `N` eligible lanes the canary requires all `N × N` ordered edges, including every self edge.
Each edge submits one bounded read-effect packet targeted at the exact executor session, proves that
the conductor receives a reservation without capability material, proves that the conductor-only
principal receives the exact executor-role denial, and delegates all executor effects to the
credential-isolated native callback. That callback claims through the executor principal and
heartbeats the runtime head. It then actually executes the bounded edge-local
`/bin/test OBSERVED_HEAD = AUTHENTICATED_RUNTIME_HEAD` predicate and records its real exit
status before reporting an empty-path unchanged-head receipt and harvesting it through the conductor
route. Public reservation and harvest lease objects are rejected if capability tokens, token
hashes, or executor-principal material appears at any nesting depth. One failed or missing edge
fails the command.

The `limen.conduct_full_mesh_canary.v1` receipt binds the exact Git object, hashed deployment and
endpoint identities, control/callback implementation digests, capability evidence, live lane
denominator, and every ordered edge, including a hash of the exact callback acknowledgement. Public
credential evidence hashes the credential reference's authenticated
principal/session binding; neither the bearer nor a bearer-derived hash is persisted. An expired
deterministic edge may advance once, from retry generation zero to one, under the same canary and
edge identity but a distinct packet/run identity; another expiry fails closed. Deterministic active
duplicates resume only their exact authenticated lease, while terminal duplicates validate their
persisted rejection and execution evidence. Repeating the same identity against an existing receipt
uses capability reads plus harvest only—no negative claim POST—and returns the byte-identical
receipt after exact validation.

Receipt I/O resolves the canonical path before using a persistent mode-`0600` regular lock file, so
symlink aliases share one bounded POSIX `flock` and process exit releases ownership. Existing
receipts must be stable regular files no larger than 4 MiB; nonblocking, no-follow reads reject
special files, growth, and identity changes. A new receipt is fsynced before atomic replacement,
then its canonical parent directory is fsynced. The identity is rechecked while holding the same
lock, so concurrent different identities cannot overwrite one another.

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
