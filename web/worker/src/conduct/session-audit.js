// Read-only, bounded evidence over retained keeper state. Never return packets,
// prompts, context, credentials, principal records, or arbitrary receipt bodies.
const LIMIT = 250;
const text = (value) => typeof value === "string" ? value.slice(0, 256) : null;
const count = (value) => Number.isSafeInteger(value) && value > 0 ? value : 1;

export function sessionAudit(state, sessionId) {
  const session = state.sessions?.[sessionId];
  const ownLeaseRunIds = new Set(Object.values(state.leases || {})
    .filter((lease) => lease.executor?.session_id === sessionId).map((lease) => lease.run_id));
  const runs = Object.values(state.runs || {}).filter((run) => [
    run.executor_session_id,
    run.packet?.conductor?.session_id,
    run.packet?.initiator?.session_id,
  ].includes(sessionId) || ownLeaseRunIds.has(run.run_id));
  const runIds = new Set(runs.map((run) => run.run_id));
  const leases = Object.values(state.leases || {}).filter((lease) =>
    lease.executor?.session_id === sessionId || runIds.has(lease.run_id));
  const leaseIds = new Set(leases.map((lease) => lease.lease_id));
  const events = (state.events || []).filter((event) => [
    event.session_id, event.executor_session_id, event.requester_session_id,
    event.conductor_session_id, event.previous_session_id,
  ].includes(sessionId) || runIds.has(event.run_id) || leaseIds.has(event.lease_id));
  const kinds = Object.create(null);
  for (const event of events) {
    const kind = text(event.kind) || "unknown";
    kinds[kind] = (Object.hasOwn(kinds, kind) ? kinds[kind] : 0) + count(event.count);
  }
  const projections = new Map();
  for (const run of runs) {
    for (const projection of run.projection_receipts || []) {
      if (projection.status === "committed" && typeof projection.event_id === "string") {
        projections.set(projection.event_id, projection);
      }
    }
  }
  const kindRows = Object.entries(kinds);
  const truncated = events.length > LIMIT || runs.length > LIMIT || projections.size > LIMIT || kindRows.length > LIMIT;
  const registrations = events.filter((event) =>
    event.kind === "session.registered" && event.session_id === sessionId);
  return {
    schema_version: "limen.conduct_session_audit.v1",
    session_id: sessionId,
    session_present: Boolean(session),
    session: session ? {
      agent: text(session.identity?.agent),
      registered_at: text(session.registered_at),
      heartbeat_at: text(session.heartbeat_at),
    } : null,
    coverage: {
      scope: "retained-keeper-state",
      retained_state_complete: !truncated,
      request_history: "unmeasured",
      rejected_or_uncommitted_requests: "unmeasured",
      registration_witness: registrations.length ? "observed" : "unmeasured",
      projection_history: "latest-retained-receipts-per-run",
      truncated,
      row_limit: LIMIT,
      next_event_sequence: Number.isSafeInteger(state.next_event_sequence) ? state.next_event_sequence : null,
    },
    retained_event_count: events.length,
    retained_event_occurrences: events.reduce((total, event) => total + count(event.count), 0),
    retained_event_kind_count: kindRows.length,
    event_occurrence_counts: Object.fromEntries(kindRows.slice(0, LIMIT)),
    retained_run_count: runs.length,
    retained_committed_projection_count: projections.size,
    active_lease_count: leases.filter((lease) => ["reserved", "active"].includes(lease.state)).length,
    events: events.slice(-LIMIT).map((event) => ({
      sequence: Number.isSafeInteger(event.sequence) ? event.sequence : null,
      timestamp: text(event.timestamp), kind: text(event.kind),
      run_id: text(event.run_id), lease_id: text(event.lease_id),
      task_id: text(event.task_id), receipt_id: text(event.receipt_id),
      occurrences: count(event.count),
    })),
    runs: runs.slice(-LIMIT).map((run) => ({
      run_id: text(run.run_id), status: text(run.status),
      task_id: text(run.packet?.task_id),
      intent_kind: text(run.packet?.intent?.kind),
      created_at: text(run.created_at), updated_at: text(run.updated_at),
      authorized_receipt_count: (run.receipts || []).filter((receipt) => receipt.mutation_authorized === true).length,
    })),
    committed_projections: [...projections.values()].slice(-LIMIT).map((projection) => ({
      event_id: text(projection.event_id), mode: text(projection.mode),
      task_id: text(projection.task?.id), task_status: text(projection.task?.status),
      publication_sha: /^[0-9a-f]{40}$/.test(String(projection.publication?.sha || ""))
        ? projection.publication.sha : null,
    })),
  };
}
