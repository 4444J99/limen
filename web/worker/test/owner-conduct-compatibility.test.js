import assert from "node:assert/strict";
import test from "node:test";

import worker from "../src/index.js";
import { ConductKeeperDurableObject } from "../src/conduct/durable-object.js";
import { readInlineProjectionForTest } from "../src/conduct/projection.js";

class FakeStorage {
  constructor() {
    this.values = new Map();
  }

  async get(key) {
    return structuredClone(this.values.get(key));
  }

  async put(key, value) {
    this.values.set(key, structuredClone(value));
  }
}

function ownerEnvironment() {
  const bearer = "compatibility-secret-at-least-24-characters";
  const env = {
    LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
      schema_version: "limen.conduct_principal_registry.v1",
      principals: [{
        principal_id: "worker-compatibility",
        agent: "api",
        surface: "worker",
        roles: ["observer", "conductor", "executor", "compatibility"],
        bearer,
      }],
    }),
    LIMEN_CONDUCT_CAPABILITY_SECRET: "compatibility-capability-secret-24-plus",
    LIMEN_CONDUCT_KEEPER_NAME: "tabularius-conduct-v2",
    LIMEN_INLINE_TASKS_YAML: `
portal:
  budget:
    daily: 10
    per_agent:
      api: 10
    track:
      spent: 0
      per_agent:
        api: 0
tasks:
  - id: TASK-OWNER
    title: Owner mutation
    repo: organvm/limen
    target_agent: codex
    priority: high
    budget_cost: 1
    status: in_progress
    predicate: pytest -q
    receipt_target: git:organvm/limen:tasks.yaml#TASK-OWNER
    origin: human_prompt
    horizon: present
    value_case: Verify one bounded owner mutation
    owner_surface: organvm/limen
    created: 2026-07-01
    updated: 2026-07-01T00:00:00.000Z
    dispatch_log: []
`,
  };
  const keeper = new ConductKeeperDurableObject({ storage: new FakeStorage() }, env);
  env.selectedKeeperNames = [];
  env.CONDUCT_KEEPER = {
    idFromName: (name) => {
      env.selectedKeeperNames.push(name);
      return name;
    },
    get: () => ({ fetch: (request) => keeper.fetch(request) }),
  };
  return env;
}

test("owner task mutations traverse the authenticated keeper and return projection receipts", async () => {
  const env = ownerEnvironment();
  const response = await worker.fetch(new Request(
    "https://limen.example/api/tasks/TASK-OWNER/verify",
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        status: "done",
        note: "exact-head evidence passed",
        session_id: "qa-owner",
        predicate_exit_code: 0,
        receipt_target: "git:organvm/limen:tasks.yaml#TASK-OWNER",
        receipt_verified: true,
        verification_context_digest: "a".repeat(64),
      }),
    },
  ), env);
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.status, "verified");
  assert.equal(payload.task.status, "done");
  assert.equal(payload.task.receipt_verified, true);
  assert.equal(payload.task.dispatch_log.at(-1).agent, "api");
  assert.equal(payload.task.dispatch_log.at(-1).session_id, "worker-owner-compatibility");
  assert.equal(payload.broker_receipt.status, "committed");
  assert.match(payload.broker_receipt.run_id, /^run-/);
  assert.ok(env.selectedKeeperNames.length >= 2);
  assert.ok(env.selectedKeeperNames.every((name) => name === "tabularius-conduct-v2"));
  assert.equal(readInlineProjectionForTest(env).tasks[0].status, "done");
});

test("owner mutation routes fail closed when the conduct keeper is unavailable", async () => {
  const env = ownerEnvironment();
  delete env.CONDUCT_KEEPER;
  const before = structuredClone(readInlineProjectionForTest(env));
  const response = await worker.fetch(new Request(
    "https://limen.example/api/tasks/TASK-OWNER/verify",
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        status: "done",
        predicate_exit_code: 0,
        receipt_target: "git:organvm/limen:tasks.yaml#TASK-OWNER",
        receipt_verified: true,
        verification_context_digest: "a".repeat(64),
      }),
    },
  ), env);
  assert.equal(response.status, 503);
  assert.match((await response.json()).detail, /conduct keeper binding is not configured/);
  assert.deepEqual(readInlineProjectionForTest(env), before);
});
