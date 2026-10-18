# Conduct persistence and quota recovery

Owner: Limen fleet engineering, [issue #2054](https://github.com/4444J99/limen/issues/2054).

Cold lifecycle changes use differential records. Map entries are separate records; audit events occupy pages of at most 64 sequence numbers. A storage transaction commits changed chunks and one authoritative manifest together. Unchanged history is retained. The generic snapshot store remains the private-board store and legacy rollback reader.

A simple registration after migration, without pending overlays, expiry or supersession, writes six rows and deletes none. Steady heartbeats remain one row and no deletes. General storage write cost follows changed record chunks, event pages and folded overlays. CPU still scans/canonicalizes state, and a cold restart reads the selected record population.

## Deploy and accept

1. Pass focused conduct/record/snapshot tests and the registry-owned scoped Worker gate at the exact PR head. Use sanctioned merge and deployment rails.
2. Before rollout, measure a representative current broker snapshot: bytes, sessions/runs/leases, events, migration rows/bytes, cold restart CPU and peak memory. The 12,000-event fixture needs 194 initial puts and no deletes; this is not a live-population measurement.
3. Migration atomically retains snapshot chunks and legacy values. The prior manifest is retained at conduct_state.v3.legacy_checkpoint. The old selector receives an unsupported schema so an older binary fails closed instead of serving stale state.
4. An exhausted provider write allowance prevents migration. Recheck once after its reset; deployment alone is not quota recovery.
5. Verify deployed runtime identity, authentic capabilities, native non-Codex Agy registration, one newly leased read leaf and an accepted schema-valid receipt. Rerun #2165's predicate. Keep #2054 open until every owning completion predicate is satisfied.

## Roll back

Deploy current record-aware code with LIMEN_CONDUCT_STEADY_HEARTBEAT_OVERLAY=0. This selects legacy cold persistence and disables new heartbeat overlays.

Perform one successful state-changing request, such as registration of the actual native session. Verify its accepted response and authoritative reread. That mutation atomically folds selected overlays into an exact legacy checkpoint and removes the v3 selector. Capabilities, graph, session audit, unsupported requests and idempotent no-ops remain read-only and cannot materialize rollback state.

Only then may an older binary be restored. Direct old-binary rollback is fenced. If a step fails, retain the record-aware binary and all generations. Do not delete state or infer the retained old checkpoint is current.

Re-enabling record persistence rewrites and reconciles retained rows during migration; it does not trust unselected rows solely because their digest envelopes match.

## Delivery holds

Full scoped verification, representative migration/restart measurement, governed deployment, quota recovery and the native Agy receipt remain independent gates owned by #2054. Preserve launcher census admission. Billing, credential, support and provider-plan changes are outside this repair.
