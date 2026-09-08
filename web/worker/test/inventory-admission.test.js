import assert from "node:assert/strict";
import test from "node:test";
import { applyTaskPacketProjectionEvent, applyTaskCompatibilityEvent } from "../src/conduct/projection.js";

function fixture(id = "GEN-fixture", labels = []) {
  const task = {
    id, title: "Routine build-out", status: "open", labels, target_agent: "codex", budget_cost: 2,
    repo: "example/fixture", origin: "system_debt", horizon: "present", value_case: "Verify admission",
    owner_surface: "example/fixture", predicate: "node --test", receipt_target: "git:example/fixture:receipt",
  };
  return {
    board: { portal: { budget: { daily: 10, per_agent: { codex: 10 }, track: { date: "2026-09-08", spent: 0, per_agent: {} } } }, tasks: [task] },
    event: {
      schema_version: "limen.task_packet_projection_event.v1", event_id: "fixture-inventory",
      timestamp: "2026-09-08T12:00:00.000Z", task_id: id, agent: "codex", session_id: "session-fixture",
      run_id: "run-fixture", lease_id: "lease-fixture", generation: 1,
      intent: { kind: "task.claim", task_id: id, expected_status: "open", patch: { status: "dispatched" } },
    },
  };
}

for (const [id, labels] of [["GEN-fixture", []], ["BLD-fixture", []], ["BLD2-fixture", []], ["legacy", ["generated", "build-out"]]]) {
  test(`routine ${id} cannot debit without canonical inventory authority`, () => {
    const { board, event } = fixture(id, labels);
    const before = structuredClone(board);
    event.intent.patch.labels = []; // A caller cannot strip a prior marker and claim.
    event.intent.inventory_verified = true;
    assert.throws(() => applyTaskPacketProjectionEvent(board, event), /inventory_admission_adapter_unavailable/);
    assert.deepEqual(board, before);
  });
}

test("routine legacy events and new dispatched upserts cannot bypass inventory admission", () => {
  const { board, event } = fixture();
  const legacy = { ...event, schema_version: "limen.task_projection_event.v1", kind: "run.started",
    status: "dispatched", from_statuses: ["open"], budget_action: "debit", output: "reserved" };
  assert.throws(() => applyTaskCompatibilityEvent(board, legacy), /inventory_admission_adapter_unavailable/);
  event.intent.kind = "task.upsert";
  event.intent.task = { ...board.tasks[0], status: "dispatched" };
  assert.throws(() => applyTaskPacketProjectionEvent({ tasks: [], portal: {} }, event), /inventory_admission_adapter_unavailable/);
});

test("non-routine claims and settlement of existing reservations remain available", () => {
  const { board, event } = fixture("FIXTURE");
  const claimed = applyTaskPacketProjectionEvent(board, event);
  assert.equal(claimed.board.portal.budget.track.spent, 2);
  claimed.board.tasks[0].id = "GEN-fixture";
  event.event_id = "fixture-settlement";
  event.task_id = "GEN-fixture";
  event.intent = { kind: "task.status", task_id: "GEN-fixture", expected_status: "dispatched", patch: { status: "in_progress" } };
  assert.equal(applyTaskPacketProjectionEvent(claimed.board, event).task.status, "in_progress");
});
