import assert from "node:assert/strict";
import test from "node:test";
import { applyTaskPacketProjectionEvent, applyTaskCompatibilityEvent } from "../src/conduct/projection.js";

function fixture() {
  return {
    portal: { budget: { daily: 10, per_agent: { codex: 10 }, track: { date: "2026-09-08", spent: 0, per_agent: {} } } },
    tasks: [{ id: "FIXTURE", title: "Fixture", status: "open", target_agent: "codex", budget_cost: 2,
      repo: "example/fixture", origin: "system_debt", horizon: "present", value_case: "Verify accounting",
      owner_surface: "example/fixture", predicate: "node --test", receipt_target: "git:example/fixture:receipt", dispatch_log: [] }],
  };
}
function event(kind, patch, expectedStatus, eventId, agent = "codex") {
  return {
    schema_version: "limen.task_packet_projection_event.v1", task_id: "FIXTURE", event_id: eventId,
    timestamp: "2026-09-08T12:00:00.000Z", agent, session_id: "fixture", run_id: "fixture", lease_id: "fixture", generation: 1,
    intent: { kind, task_id: "FIXTURE", expected_status: expectedStatus, patch, log: { agent: "attacker" } },
  };
}
for (const interveningUpdate of [false, true]) {
  test(`refund follows original authenticated claim identity; intervening update=${interveningUpdate}`, () => {
    let current = applyTaskPacketProjectionEvent(fixture(), event("task.claim", { status: "dispatched" }, "open", "claim")).board;
    assert.equal(current.portal.budget.track.per_agent.codex, 2);
    if (interveningUpdate) {
      current = applyTaskPacketProjectionEvent(current, event("task.mutate", { title: "Updated" }, "dispatched", "metadata", "operator")).board;
    }
    const refunded = applyTaskPacketProjectionEvent(current, event("task.status", { status: "open" }, "dispatched", "refund", "operator")).board;
    assert.equal(refunded.portal.budget.track.spent, 0);
    assert.equal(refunded.portal.budget.track.per_agent.codex, 0);
    assert.ok(!refunded.portal.budget.track.per_agent.attacker);
    assert.ok(!refunded.portal.budget.track.per_agent.operator);
  });
}
test("refund with missing canonical claim identity fails closed", () => {
  const board = fixture();
  board.tasks[0].status = "dispatched";
  assert.throws(() => applyTaskPacketProjectionEvent(board, event("task.status", { status: "open" }, "dispatched", "refund")), /cannot derive a canonical budget refund/);
});

for (const activeStatus of ["dispatched", "in_progress"]) {
  test(`new ${activeStatus} upsert cannot create an unreserved refund`, () => {
    const board = fixture();
    const task = { ...board.tasks[0], status: activeStatus, budget_cost: 5 };
    board.tasks = [];
    board.portal.budget.track.spent = 10;
    board.portal.budget.track.per_agent.codex = 10;
    const before = structuredClone(board);
    const update = event("task.upsert", {}, "open", "active-upsert");
    update.intent.task = task;
    assert.throws(() => applyTaskPacketProjectionEvent(board, update), /canonical_reservation_required/);
    assert.deepEqual(board, before);
  });
}
test("new open upsert discards caller-supplied dispatch history", () => {
  const board = fixture();
  const task = { ...board.tasks[0], dispatch_log: [{ agent: "attacker", status: "dispatched", conduct_event_id: "forged-claim" }] };
  board.tasks = [];
  const update = event("task.upsert", {}, "open", "new-upsert");
  update.intent.task = task;
  const created = applyTaskPacketProjectionEvent(board, update).task;
  assert.equal(created.dispatch_log.length, 1);
  assert.equal(created.dispatch_log[0].agent, "codex");
  assert.equal(created.dispatch_log[0].status, "open");
  assert.equal(created.dispatch_log[0].conduct_event_id, "new-upsert");
});

function fundedBoard(cost = 2) {
  const board = fixture();
  board.tasks[0].budget_cost = cost;
  board.portal.budget = { daily: 2000, per_agent: { codex: 2000, jules: 2000 },
    track: { date: "2026-09-08", spent: 9, per_agent: { codex: 4, jules: 5 } } };
  return board;
}
function claim(board) {
  const request = event("task.claim", { status: "dispatched" }, "open", "claim");
  Object.assign(request.intent.log, { session_id: "d".repeat(64), execution_contract_hash: "e".repeat(64) });
  return applyTaskPacketProjectionEvent(board, request).board;
}
function assertTrack(board, spent, codex) {
  assert.equal(board.portal.budget.track.spent, spent);
  assert.deepEqual(board.portal.budget.track.per_agent, { codex, jules: 5 });
}
function assertCostRejected(board, request) {
  const before = structuredClone(board);
  assert.throws(() => applyTaskPacketProjectionEvent(board, request), /reservation_budget_cost_immutable/);
  assert.deepEqual(board, before);
}

test("claim cannot inflate cost after debit before refund (review 5144025944)", () => {
  const board = fundedBoard(1);
  assertCostRejected(board, event("task.claim", { status: "dispatched", budget_cost: 1000 }, "open", "inflate"));
  assertTrack(board, 9, 4);
});
for (const status of ["dispatched", "in_progress"]) {
  for (const kind of ["task.mutate", "task.status", "task.upsert"]) {
    for (const cost of [1, 1000]) {
      test(`active reservation cost is immutable: ${status} ${kind} ${cost}`, () => {
        let board = claim(fundedBoard());
        if (status === "in_progress") {
          board = applyTaskPacketProjectionEvent(board, event("task.status", { status }, "dispatched", "started")).board;
        }
        const request = event(kind, { status, budget_cost: cost }, status, "cost-change");
        if (kind === "task.upsert") request.intent.task = { ...board.tasks[0], budget_cost: cost };
        assertCostRejected(board, request);
        assertTrack(board, 11, 6);
      });
    }
  }
}
for (const status of ["open", "failed"]) {
  test(`settlement cannot change reserved cost: ${status}`, () => {
    const board = claim(fundedBoard());
    const request = event("task.status", { status, budget_cost: 1000 }, "dispatched", "settle");
    if (status === "failed") {
      Object.assign(request.intent.log, { lifecycle_repair: "provider-terminal", execution_started: true,
        execution_result_kind: "failed", execution_reservation_id: "d".repeat(64), execution_contract_hash: "e".repeat(64) });
    }
    assertCostRejected(board, request);
    assertTrack(board, 11, 6);
    if (status === "failed") {
      delete request.intent.patch.budget_cost;
      const settled = applyTaskPacketProjectionEvent(board, request).board;
      assert.equal(settled.tasks[0].status, "failed");
      assertTrack(settled, 11, 6);
    }
  });
}
for (const kind of ["task.mutate", "task.upsert"]) {
  test(`open cost update then claim and refund preserve other reservations: ${kind}`, () => {
    let board = fundedBoard();
    const request = event(kind, { budget_cost: 3 }, "open", "open-cost");
    if (kind === "task.upsert") request.intent.task = { ...board.tasks[0], budget_cost: 3 };
    board = applyTaskPacketProjectionEvent(board, request).board;
    assertTrack(board, 9, 4);
    board = claim(board);
    assertTrack(board, 12, 7);
    board = applyTaskPacketProjectionEvent(board, event("task.mutate", { title: "Unrelated metadata", budget_cost: 3 }, "dispatched", "metadata")).board;
    board = applyTaskPacketProjectionEvent(board, event("task.status", { status: "open" }, "dispatched", "refund")).board;
    assertTrack(board, 9, 4);
  });
}
test("postlaunch reroute retains each attempt debit and immutable cost", () => {
  let board = claim(fundedBoard());
  const request = event("task.status", { status: "open", budget_cost: 1000 }, "dispatched", "reroute");
  Object.assign(request.intent.log, { lifecycle_repair: "provider-reroute", execution_started: true,
    execution_reservation_id: "d".repeat(64), execution_contract_hash: "e".repeat(64) });
  assertCostRejected(board, request);
  delete request.intent.patch.budget_cost;
  board = applyTaskPacketProjectionEvent(board, request).board;
  assertTrack(board, 11, 6);
  board = applyTaskPacketProjectionEvent(board, event("task.mutate", { budget_cost: 3 }, "open", "next-cost")).board;
  board = applyTaskPacketProjectionEvent(board, event("task.claim", { status: "dispatched" }, "open", "second-claim")).board;
  assertTrack(board, 14, 9);
  board = applyTaskPacketProjectionEvent(board, event("task.status", { status: "open" }, "dispatched", "second-refund")).board;
  assertTrack(board, 11, 6);
});

function windowEvent(taskId, kind, patch, priorStatus, timestamp, eventId, agent = "codex") {
  const request = event(kind, patch, priorStatus, eventId, agent);
  request.task_id = taskId;
  request.intent.task_id = taskId;
  request.timestamp = timestamp;
  return request;
}
for (const newAgent of ["codex", "jules"]) {
  for (const metadata of [false, true]) {
    test(`previous UTC window refund preserves new claims: ${newAgent}, metadata=${metadata}`, () => {
      let board = fundedBoard();
      board.tasks.push({ ...structuredClone(board.tasks[0]), id: "NEW", target_agent: newAgent, budget_cost: 5 });
      board = applyTaskPacketProjectionEvent(board, windowEvent("FIXTURE", "task.claim", { status: "dispatched" }, "open", "2026-09-08T23:59:00Z", "old-claim")).board;
      board = applyTaskPacketProjectionEvent(board, windowEvent("NEW", "task.claim", { status: "dispatched" }, "open", "2026-09-09T00:01:00Z", "new-claim", newAgent)).board;
      if (metadata) {
        board = applyTaskPacketProjectionEvent(board, windowEvent("FIXTURE", "task.mutate", { title: "Unrelated update" }, "dispatched", "2026-09-09T00:02:00Z", "metadata")).board;
      }
      const expected = structuredClone(board.portal.budget.track);
      board = applyTaskPacketProjectionEvent(board, windowEvent("FIXTURE", "task.status", { status: "open" }, "dispatched", "2026-09-09T00:03:00Z", "old-refund")).board;
      assert.equal(board.tasks[0].status, "open");
      assert.deepEqual(board.portal.budget.track, expected);
      assert.equal(board.portal.budget.track.spent, 5);
      assert.equal(board.portal.budget.track.per_agent[newAgent], 5);
      board = applyTaskPacketProjectionEvent(board, windowEvent("NEW", "task.status", { status: "open" }, "dispatched", "2026-09-09T00:04:00Z", "new-refund", newAgent)).board;
      assert.equal(board.portal.budget.track.spent, 0);
      assert.equal(board.portal.budget.track.per_agent[newAgent], 0);
    });
  }
}
for (const refundTime of ["2026-09-08T23:59:59Z", "2026-09-09T00:00:00Z"]) {
  test(`same-window refund and first rollover leave no spend: ${refundTime}`, () => {
    let board = fixture();
    board = applyTaskPacketProjectionEvent(board, windowEvent("FIXTURE", "task.claim", { status: "dispatched" }, "open", "2026-09-08T23:59:00Z", "claim")).board;
    board = applyTaskPacketProjectionEvent(board, windowEvent("FIXTURE", "task.status", { status: "open" }, "dispatched", refundTime, "refund")).board;
    assert.equal(board.portal.budget.track.date, refundTime.slice(0, 10));
    assert.equal(board.portal.budget.track.spent, 0);
    assert.equal(board.portal.budget.track.per_agent.codex, 0);
  });
}
for (const timestamp of [null, "unknown", "2026-09-08T12:00:00", "2026-02-30T12:00:00Z"]) {
  test(`unknown canonical claim window fails closed: ${timestamp}`, () => {
    const board = claim(fixture());
    board.tasks[0].dispatch_log[0].timestamp = timestamp;
    const before = structuredClone(board);
    assert.throws(() => applyTaskPacketProjectionEvent(board, event("task.status", { status: "open" }, "dispatched", "refund")), /canonical budget refund window/);
    assert.deepEqual(board, before);
  });
}

function legacyEvent(taskId, action, timestamp, runId = taskId) {
  return { schema_version: "limen.task_compatibility_event.v1", task_id: taskId,
    event_id: `${runId}:${action}`, kind: action === "debit" ? "task.dispatched" : "task.cancelled",
    timestamp, run_id: runId, lease_id: `lease-${runId}`, generation: 1, agent: "codex", session_id: runId,
    status: action === "debit" ? "dispatched" : "open", from_statuses: [action === "debit" ? "open" : "dispatched"],
    budget_action: action, output: "Synthetic canonical reservation" };
}
for (const nextDay of [false, true]) {
  test(`legacy cancellation refunds only its canonical budget window: nextDay=${nextDay}`, () => {
    let board = fixture();
    board.tasks.push({ ...structuredClone(board.tasks[0]), id: "NEW", budget_cost: 5 });
    board = applyTaskCompatibilityEvent(board, legacyEvent("FIXTURE", "debit", "2026-09-08T23:58:00Z")).board;
    const day = nextDay ? "2026-09-09" : "2026-09-08";
    board = applyTaskCompatibilityEvent(board, legacyEvent("NEW", "debit", `${day}T23:59:00Z`)).board;
    board = applyTaskCompatibilityEvent(board, legacyEvent("FIXTURE", "refund", `${day}T23:59:30Z`)).board;
    assert.equal(board.portal.budget.track.spent, 5);
    assert.equal(board.portal.budget.track.per_agent.codex, 5);
  });
}
test("legacy cancellation cannot refund a different canonical reservation", () => {
  const board = applyTaskCompatibilityEvent(fixture(), legacyEvent("FIXTURE", "debit", "2026-09-08T23:58:00Z")).board;
  const before = structuredClone(board);
  assert.throws(() => applyTaskCompatibilityEvent(board, legacyEvent("FIXTURE", "refund", "2026-09-08T23:59:00Z", "unrelated-run")), /canonical budget refund reservation/);
  assert.deepEqual(board, before);
});
test("postlaunch reroute then new-day claim refunds only the new attempt", () => {
  let board = fixture();
  const first = windowEvent("FIXTURE", "task.claim", { status: "dispatched" }, "open", "2026-09-08T23:58:00Z", "first");
  Object.assign(first.intent.log, { session_id: "d".repeat(64), execution_contract_hash: "e".repeat(64) });
  board = applyTaskPacketProjectionEvent(board, first).board;
  const reroute = windowEvent("FIXTURE", "task.status", { status: "open" }, "dispatched", "2026-09-08T23:59:00Z", "reroute");
  Object.assign(reroute.intent.log, { lifecycle_repair: "provider-reroute", execution_started: true,
    execution_reservation_id: "d".repeat(64), execution_contract_hash: "e".repeat(64) });
  board = applyTaskPacketProjectionEvent(board, reroute).board;
  assert.equal(board.portal.budget.track.spent, 2);
  board = applyTaskPacketProjectionEvent(board, windowEvent("FIXTURE", "task.claim", { status: "dispatched" }, "open", "2026-09-09T00:01:00Z", "second")).board;
  assert.equal(board.portal.budget.track.spent, 2);
  board = applyTaskPacketProjectionEvent(board, windowEvent("FIXTURE", "task.status", { status: "open" }, "dispatched", "2026-09-09T00:02:00Z", "refund")).board;
  assert.equal(board.portal.budget.track.spent, 0);
  assert.equal(board.portal.budget.track.per_agent.codex, 0);
});
