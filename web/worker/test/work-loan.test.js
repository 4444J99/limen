import assert from "node:assert/strict";
import test from "node:test";

import fixtures from "../../../spec/contracts/work-loan-v1-fixtures.json" with { type: "json" };
import { validateWorkPacket } from "../src/conduct/schemas.js";
import {
  durableReceiptTarget,
  executablePredicate,
  packetIsNonCapacityProjection,
  packetWorkLoanMissingFields,
  taskWorkLoanMissingFields,
  workLoanDenial,
} from "../src/conduct/work-loan.js";

const identity = {
  agent: "codex",
  surface: "test",
  session_id: "work-loan-test",
};

function schemaPacket(workLoan) {
  return validateWorkPacket({
    work_id: "work-loan-schema-test",
    work_key: "work-loan-schema-test",
    intent: { objective: "verify work loan schema" },
    execution: { command: "pytest -q" },
    initiator: identity,
    conductor: identity,
    required_capabilities: ["code"],
    resource_claims: [{ key: "task/work-loan-schema-test", mode: "exclusive" }],
    predicate: "pytest -q",
    receipt_target: "github:organvm/limen:pull-request:WL-SCHEMA",
    work_loan: workLoan,
    authority: {
      actions: ["code"],
      repositories: ["organvm/limen"],
      path_prefixes: ["cli"],
      external_effects: [],
      may_delegate: false,
    },
    deadline: "2026-08-01T12:00:00Z",
    spend: { unit: "runs", limit: 1, reserve: 0 },
    effect: "write",
  });
}

test("task work-loan denials use stable field order", () => {
  const missing = taskWorkLoanMissingFields({
    id: "RAW",
    title: "Human asks for valuable urgent work",
    repo: "organvm/limen",
    budget_cost: 0,
    status: "open",
    predicate: "should pass",
    receipt_target: "receipt.txt",
  });

  assert.deepEqual(missing, [
    "source_origin",
    "horizon",
    "value_case",
    "budget_cost",
    "predicate",
    "receipt_target",
  ]);
  assert.equal(
    workLoanDenial(missing),
    "task-not-underwritten:source_origin,horizon,value_case,budget_cost,predicate,receipt_target",
  );
  assert.deepEqual(taskWorkLoanMissingFields({
    repo: "organvm/limen",
    origin: "human_prompt",
    horizon: "present",
    budget_cost: 1,
    value_case: "\0",
    predicate: "pytest -q",
    receipt_target: "git:organvm/limen:logs/receipt.json",
  }), ["value_case"]);
  assert.equal(
    workLoanDenial(["value_case", "source_origin"]),
    "task-not-underwritten:source_origin,value_case",
  );
});

test("packet work loans bind their positive cost to the spend envelope", () => {
  const packet = {
    predicate: "pytest -q",
    receipt_target: "github:organvm/limen:pull-request:WL-1",
    spend: { limit: 2 },
    work_loan: {
      source_origin: "human_prompt",
      horizon: "present",
      value_case: "Deliver one bounded outcome",
      budget_cost: 3,
      owner_surface: "organvm/limen",
    },
  };

  assert.deepEqual(packetWorkLoanMissingFields(packet), ["budget_cost"]);
  packet.work_loan.budget_cost = 2;
  assert.deepEqual(packetWorkLoanMissingFields(packet), []);

  packet.work_loan.source_origin = "urgent";
  packet.work_loan.horizon = "soon";
  assert.deepEqual(packetWorkLoanMissingFields(packet), ["source_origin", "horizon"]);
});

test("due_at is required only for declared external deadlines", () => {
  const task = {
    repo: "organvm/limen",
    budget_cost: 1,
    origin: "obligation",
    horizon: "present",
    value_case: "Meet the real deadline",
    predicate: "pytest -q",
    receipt_target: "git:organvm/limen:logs/deadline.json",
  };

  assert.deepEqual(taskWorkLoanMissingFields(task), []);
  assert.deepEqual(taskWorkLoanMissingFields({ ...task, external_deadline: true }), ["due_at"]);
  assert.deepEqual(
    taskWorkLoanMissingFields({ ...task, external_deadline: true, due_at: "2026-08-01" }),
    [],
  );

  for (const fixture of fixtures.due_at_cases) {
    assert.equal(
      taskWorkLoanMissingFields({ ...task, external_deadline: true, due_at: fixture.value }).length === 0,
      fixture.valid,
      fixture.value,
    );
  }
});

test("predicate and receipt fixtures match canonical intake behavior", () => {
  for (const fixture of fixtures.predicate_cases) {
    assert.equal(executablePredicate(fixture.value), fixture.valid, fixture.value);
  }
  for (const fixture of fixtures.receipt_target_cases) {
    assert.equal(durableReceiptTarget(fixture.value), fixture.valid, fixture.value);
  }
});

test("only an exact zero-cost task projection bypasses capacity underwriting", () => {
  const taskId = "LIMEN-PROJECTION-1";
  const packet = {
    intent: { kind: "task.status", task_id: taskId },
    execution: { adapter: "tabularius", projection: "tasks.yaml" },
    preferred_agent: "tabularius",
    required_capabilities: ["board-write"],
    resource_claims: [{ key: `task/${taskId}`, mode: "exclusive" }],
    predicate: "python3 scripts/validate-task-board.py --tasks tasks.yaml",
    receipt_target: `git:organvm/limen:tasks.yaml#${taskId}`,
    authority: {
      actions: ["task.status"],
      path_prefixes: ["tasks.yaml"],
      external_effects: [],
      may_delegate: false,
    },
    effect: "write",
    spend: { unit: "runs", limit: 0, reserve: 0 },
    task_id: taskId,
  };

  assert.equal(packetIsNonCapacityProjection(packet), true);
  assert.deepEqual(packetWorkLoanMissingFields(packet), []);
  packet.spend.limit = 1;
  assert.equal(packetIsNonCapacityProjection(packet), false);
  assert.deepEqual(packetWorkLoanMissingFields(packet), [
    "source_origin",
    "horizon",
    "value_case",
    "budget_cost",
    "owner_surface",
  ]);
});

test("portable schema enforces bounded collateral and external deadline semantics", async () => {
  const valid = {
    source_origin: "human_prompt",
    horizon: "present",
    value_case: "Deliver the bounded schema seam",
    budget_cost: 1,
    owner_surface: "organvm/limen",
  };
  assert.equal((await schemaPacket(valid)).work_loan.value_case, valid.value_case);
  await assert.rejects(() => schemaPacket({ ...valid, value_case: "" }), /packet schema rejected/);
  await assert.rejects(() => schemaPacket({ ...valid, value_case: "\0" }), /packet schema rejected/);
  await assert.rejects(() => schemaPacket({ ...valid, owner_surface: "" }), /packet schema rejected/);
  await assert.rejects(
    () => schemaPacket({ ...valid, external_deadline: true }),
    /packet schema rejected/,
  );
});
