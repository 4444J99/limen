import assert from "node:assert/strict";
import test from "node:test";
import { applyTaskPacketProjectionEvent } from "../src/conduct/projection.js";

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

function spentFixture() {
  const board = fixture();
  board.portal.budget.track.spent = 5;
  board.portal.budget.track.per_agent.codex = 5;
  return board;
}

for (const cost of [1, 1000]) {
  test(`claim cannot reprice its debit or refund to ${cost}`, () => {
    const board = spentFixture();
    const before = structuredClone(board);
    assert.throws(() => applyTaskPacketProjectionEvent(board,
      event("task.claim", { status: "dispatched", budget_cost: cost }, "open", "reprice")),
    /reserved budget_cost cannot change/);
    assert.deepEqual(board, before);
    const claimed = applyTaskPacketProjectionEvent(board, event("task.claim", { status: "dispatched" }, "open", "claim")).board;
    assert.equal(claimed.portal.budget.track.spent, 7);
    const refunded = applyTaskPacketProjectionEvent(claimed, event("task.status", { status: "open" }, "dispatched", "refund")).board;
    assert.equal(refunded.portal.budget.track.spent, 5);
    assert.deepEqual(refunded.portal.budget.track.per_agent, { codex: 5 });
  });
}

for (const kind of ["task.mutate", "task.status", "task.upsert"]) {
  for (const activeStatus of ["dispatched", "in_progress"]) {
    test(`${kind} cannot inflate ${activeStatus} reservation cost`, () => {
      let claimed = applyTaskPacketProjectionEvent(spentFixture(), event("task.claim", { status: "dispatched" }, "open", "claim")).board;
      if (activeStatus === "in_progress") {
        claimed = applyTaskPacketProjectionEvent(claimed, event("task.status", { status: "in_progress" }, "dispatched", "start")).board;
      }
      const before = structuredClone(claimed);
      const update = event(kind, { status: activeStatus, budget_cost: 1000 }, activeStatus, "inflate");
      if (kind === "task.upsert") update.intent.task = { ...claimed.tasks[0], budget_cost: 1000 };
      assert.throws(() => applyTaskPacketProjectionEvent(claimed, update), /reserved budget_cost cannot change/);
      assert.deepEqual(claimed, before);
      assert.equal(claimed.portal.budget.track.spent, 7);
      if (activeStatus === "dispatched") {
        const refunded = applyTaskPacketProjectionEvent(claimed, event("task.status", { status: "open" }, "dispatched", "refund")).board;
        assert.equal(refunded.portal.budget.track.spent, 5);
        assert.deepEqual(refunded.portal.budget.track.per_agent, { codex: 5 });
      }
    });
  }
}

test("cancellation cannot change cost as it releases reservation", () => {
  const claimed = applyTaskPacketProjectionEvent(spentFixture(), event("task.claim", { status: "dispatched" }, "open", "claim")).board;
  assert.throws(() => applyTaskPacketProjectionEvent(claimed,
    event("task.status", { status: "open", budget_cost: 1000 }, "dispatched", "refund")),
  /reserved budget_cost cannot change/);
});

test("unreserved task can change cost before admission", () => {
  const updated = applyTaskPacketProjectionEvent(spentFixture(), event("task.mutate", { budget_cost: 3 }, "open", "update")).board;
  const claimed = applyTaskPacketProjectionEvent(updated, event("task.claim", { status: "dispatched" }, "open", "claim")).board;
  assert.equal(claimed.portal.budget.track.spent, 8);
});
