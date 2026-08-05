# TABVLARIVS — the remote conduct keeper

TABVLARIVS is the deterministic record keeper and lease authority for Limen. It is a capability,
not a model rank: the authenticated Cloudflare Worker and its Durable Object serialize conduct
graphs, resource leases, generations, idempotency, and task projection events. No local agent,
MCP process, API process, or beat owns an independent lifecycle writer.

This single-writer boundary prevents both torn bytes and lost updates. Multiple processes may
submit immutable events concurrently, but only the keeper may fold them onto the canonical board.
A lock around only the final file save is insufficient because it does not serialize the complete
read-modify-write transaction.

## Canonical flow

```text
agent/API/MCP
    │ bounded WorkPacketV1 or compatibility ticket
    ▼
authenticated conduct endpoint
    │ Durable Object reservation + generation
    ▼
GitHub tasks.yaml read at observed SHA
    │ validate exact revision, transition, budget, authority
    ▼
GitHub compare-and-swap
    │
    └─ acknowledge projection receipt only after the CAS succeeds
```

`tasks.yaml` in a checkout is a read-only hot cache. Inspection and already-leased work may continue
when the broker is unavailable, but a new claim or transition fails closed. A remote receipt may be
used by a separate cache-hydration path; locally recomputing, sealing, committing, pushing, resetting,
or restoring the canonical projection is not authorized.

## Default-branch integration

Keeper authority does not bypass repository integration. TABVLARIVS coalesces accepted events and
publishes only `tasks.yaml` through the stable, fast-forward-only
`tabularius/board-projection` branch. It opens or advances one exact-head PR; it never pushes
`main`, force-pushes a competing projection, or uses an admin bypass.

The repository merge queue serializes that immutable projection head with the latest `main` and
queued predecessors, and `pr-gate` validates the resulting synthetic `merge_group`. New accepted
events may coalesce into a later projection head while an earlier one is in flight. The remote
no-bypass `pull_request` rule is the final enforcement boundary for every default-branch writer,
including automation.

## Compatibility ticket relay

Legacy producers may append immutable outbound tickets under `logs/tickets/inbox/`. This is local
queue custody, not board authority.

```text
logs/tickets/inbox/<id>.json
    │ scripts/tabularius-organ.py
    ▼
cli/src/limen/tabularius.py
    │ register authenticated relay session
    │ submit exact task/<id> packet
    ▼
remote projection receipt
    ├─ acknowledged: move ticket to archive/
    ├─ invalid/fenced: move ticket to rejected/ with reason
    └─ broker unavailable: leave ticket and unattempted suffix in inbox
```

The relay reads the local board only to derive an optimistic task revision. A stale revision is
fenced by the remote owner. Board metadata, ordering, removal, server-owned history/timestamps, and
unknown task fields have no compatibility transition and fail closed.

`apply_limen_file_sync()` is the synchronous migration seam for callers that still construct an
in-memory `LimenFile`. It diffs task fields, submits bounded packets, and returns only after projection
receipts arrive. It does not write or refresh the local cache. Server-owned budget-window metadata is
not relayed; the keeper derives reset/debit/refund state from canonical events.

Local restore is retired. Projection publication, when invoked by the authenticated keeper, must
return an exact remote branch/commit/PR receipt and obey the serialized integration contract above.

## Components

| Piece | Owner | Contract |
|---|---|---|
| Serialized kernel | `web/worker/src/conduct/keeper.js` | sessions, graphs, leases, generations, idempotency, adoption, fencing |
| Resource algebra | `web/worker/src/conduct/resources.js` | exact task/PR/branch/path/worktree/external overlap rules |
| Projection | `web/worker/src/conduct/projection.js` | canonical transitions and budget logic; GitHub SHA compare-and-swap |
| Remote routes | `web/worker/src/index.js` | authenticated conduct and owner compatibility surfaces |
| Python protocol | `cli/src/limen/conduct/` | shared schemas, CLI, MCP client, explicit local test kernel |
| Ticket relay | `cli/src/limen/tabularius.py` | immutable outbound custody and receipt-gated archive |
| Beat adapter | `scripts/tabularius-organ.py` | bounded relay pass and counts-only liveness stamp |
| Zero gate | `scripts/task-writer-audit.py` | rejects unauthorized YAML, Git, remote PUT, and instruction bypasses |
| Receipt | `docs/tabularius-writer-audit.md` | deterministic current authorized-writer inventory |

## Executable invariants

- The Worker projection is the sole logical lifecycle writer.
- `cli/src/limen/io.py` may serialize only explicitly noncanonical cache/export files from production
  call sites; `save_derived_limen_projection()` rejects the canonical target.
- TABVLARIVS has no audit exemption. A reintroduced local board write, raw default-branch write, or
  instruction bypass in the relay fails the writer predicate.
- Projection failure prevents the conduct state/lease from being acknowledged or committed.
- Duplicate work IDs/keys return the stored projection receipt and cannot debit twice.
- Exact revision and moved-head guards fence stale work.
- A broker outage never archives an unacknowledged ticket.
- Unsupported lifecycle jumps remain rejected; compatibility must not fabricate intermediate
  transitions or budget history.
- Default-branch publication is exact-head, queue-serialized, and never admin-bypassed.

Run:

```bash
python3 scripts/task-writer-audit.py --enforce-zero
uv run --project cli --extra test pytest -q \
  cli/tests/test_tabularius.py \
  cli/tests/test_task_writer_audit.py \
  cli/tests/test_conduct_protocol.py \
  cli/tests/test_mcp_server.py
(cd web/worker && npm run check)
```

## Remaining cutover boundary

Serial dispatch and stale-release still construct some legacy final-state deltas. The relay correctly
rejects any delta that the canonical Worker transition graph cannot apply atomically with the right
generation and budget semantics. Do not synthesize intermediate claims, execution, or spend merely
to preserve a legacy local test expectation.

The live-cutover continuation owns conversion of those callers to reserve before execution and report
through the same lease. Until that predicate is green, broker-backed paths fail closed and local
`tasks.yaml` remains untouched.
