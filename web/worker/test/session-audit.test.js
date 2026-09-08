import assert from "node:assert/strict";
import test from "node:test";
import { sessionAudit } from "../src/conduct/session-audit.js";

function fixture() {
  return {
    sessions: { owner: { identity: { agent: "codex" }, registered_at: "2026-09-08T00:00:00Z", worktree: "private-path" } },
    runs: {
      owned: { run_id: "owned", executor_session_id: "owner", status: "succeeded",
        packet: { task_id: "TASK", intent: { kind: "task.mutate", context: "private-context" } },
        projection_receipts: [{ status: "committed", event_id: "event-owned", mode: "private-canonical",
          task: { id: "TASK", status: "open", context: "private-context" },
          publication: { sha: "a".repeat(40) } }],
        receipts: [{ mutation_authorized: true, secrets: "private-token" }],
      },
      peer: { run_id: "peer", executor_session_id: "peer", packet: { task_id: "PEER-PRIVATE" } },
    },
    leases: { own: { lease_id: "own", run_id: "owned", state: "released", capability_token_hash: "private-hash" } },
    events: [
      { sequence: 1, kind: "session.registered", session_id: "owner", principal_id: "private-principal" },
      { sequence: 2, kind: "run.reserved", run_id: "owned" },
      { sequence: 3, kind: "lease.heartbeat", run_id: "owned", count: 5 },
      { sequence: 4, kind: "run.reserved", run_id: "peer", context: "peer-private-context" },
    ],
    next_event_sequence: 4,
  };
}

test("audit is read-only, scoped and contains no arbitrary private bodies", () => {
  const state = fixture();
  const before = structuredClone(state);
  const result = sessionAudit(state, "owner");
  assert.deepEqual(state, before);
  assert.equal(result.retained_run_count, 1);
  assert.equal(result.retained_event_count, 3);
  assert.equal(result.retained_event_occurrences, 7);
  assert.equal(result.event_occurrence_counts["lease.heartbeat"], 5);
  assert.equal(result.retained_committed_projection_count, 1);
  assert.equal(result.committed_projections[0].publication_sha, "a".repeat(40));
  assert.equal(result.coverage.retained_state_complete, true);
  assert.equal(result.coverage.request_history, "unmeasured");
  assert.equal(result.coverage.registration_witness, "observed");
  assert.doesNotMatch(JSON.stringify(result), /private-(path|context|token|hash|principal)|PEER-PRIVATE|capability_token_hash/);
});

test("unknown session is absent only from retained state, never a clean request history", () => {
  const result = sessionAudit(fixture(), "absent");
  assert.equal(result.session_present, false);
  assert.equal(result.retained_run_count, 0);
  assert.equal(result.coverage.registration_witness, "unmeasured");
  assert.equal(result.coverage.rejected_or_uncommitted_requests, "unmeasured");
});

test("missing registration evidence stays unmeasured even for a retained session", () => {
  const state = fixture();
  state.events.shift();
  assert.equal(sessionAudit(state, "owner").coverage.registration_witness, "unmeasured");
});

test("output bounds cannot turn truncated evidence into a complete audit", () => {
  const state = fixture();
  state.events = Array.from({ length: 251 }, (_, sequence) => ({ sequence, kind: "session.registered", session_id: "owner" }));
  const result = sessionAudit(state, "owner");
  assert.equal(result.retained_event_count, 251);
  assert.equal(result.events.length, 250);
  assert.equal(result.coverage.truncated, true);
  assert.equal(result.coverage.retained_state_complete, false);
});

test("conductor and prior lease ownership are visible after executor routing changes", () => {
  const state = fixture();
  state.runs.owned.executor_session_id = "new-executor";
  state.runs.owned.packet.conductor = { session_id: "owner" };
  assert.equal(sessionAudit(state, "owner").retained_run_count, 1);
  delete state.runs.owned.packet.conductor;
  state.leases.own.executor = { session_id: "owner" };
  state.events.push({ sequence: 5, kind: "lease.claimed", lease_id: "own" });
  assert.equal(sessionAudit(state, "owner").events.at(-1).kind, "lease.claimed");
  assert.equal(sessionAudit(state, "owner").retained_run_count, 1);
});
