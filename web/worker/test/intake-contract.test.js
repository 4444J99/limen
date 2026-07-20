import assert from "node:assert/strict";
import test from "node:test";

import worker from "../src/index.js";
import {
  isDurableReceiptTarget,
  isExecutablePredicate,
  normalizeSelectedLegacyTask,
  validateIntakeContract,
} from "../src/index.js";

function typedTask(overrides = {}) {
  return {
    id: "WORKER-1",
    title: "One bounded worker task",
    repo: "organvm/limen",
    target_agent: "codex",
    status: "open",
    predicate: "pytest -q web/api/tests/test_main.py",
    receipt_target: "github:organvm/limen:pull-request:WORKER-1",
    ...overrides,
  };
}

test("active Worker tasks require executable predicates and durable receipts", () => {
  assert.throws(
    () => validateIntakeContract(typedTask({ predicate: undefined, receipt_target: undefined })),
    /predicate must be one executable command/,
  );
  assert.doesNotThrow(() => validateIntakeContract(typedTask()));
  assert.equal(isExecutablePredicate("tests should pass"), false);
  assert.equal(isDurableReceiptTarget("/tmp/result.json"), false);
});

test("Worker boundedness ignores ordinary uppercase AND prose", () => {
  assert.doesNotThrow(() => validateIntakeContract(typedTask({
    context: "Rebase AND preserve the unique diff AND verify the PR AND retain the owner receipt AND report the result.",
  })));
});

test("Worker normalizes only a selected owned legacy task and fails closed when unowned", () => {
  const selected = typedTask({ predicate: undefined, receipt_target: undefined });
  const contract = normalizeSelectedLegacyTask(selected);
  assert.match(contract.predicate, /^test "\$\(gh pr list/);
  assert.equal(contract.receipt_target, "github:organvm/limen:pull-request:WORKER-1");

  const unowned = typedTask({ repo: undefined, predicate: undefined, receipt_target: undefined });
  assert.throws(() => normalizeSelectedLegacyTask(unowned), /exact owner\/repo/);
});

test("GitHub-backed Worker mutations fail closed at the missing conduct keeper while reads stay live", async (t) => {
  const originalFetch = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = originalFetch;
  });
  const calls = [];
  const board = [
    "version: '1.0'",
    "portal: {}",
    "tasks:",
    "  - id: WORKER-1",
    "    title: Keeper-owned task",
    "    repo: organvm/limen",
    "    target_agent: codex",
    "    priority: high",
    "    budget_cost: 1",
    "    status: dispatched",
    "    predicate: pytest -q",
    "    receipt_target: git:organvm/limen:tasks.yaml#WORKER-1",
    "    created: '2026-07-01'",
    "    dispatch_log: []",
    "",
  ].join("\n");
  globalThis.fetch = async (url, options = {}) => {
    const method = options.method || "GET";
    calls.push({ method, url: String(url) });
    assert.equal(method, "GET", "the Worker must never issue a GitHub Contents mutation");
    return new Response(JSON.stringify({
      content: Buffer.from(board, "utf8").toString("base64"),
      sha: "fixture-board-sha",
    }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  const env = {
    LIMEN_GITHUB_REPO: "organvm/limen",
    LIMEN_GITHUB_BRANCH: "tabularius/board-projection",
    LIMEN_GITHUB_PATH: "tasks.yaml",
    LIMEN_GITHUB_TOKEN: "fixture-token",
  };

  const health = await worker.fetch(new Request("https://limen.test/health"), env);
  assert.equal(health.status, 200);
  const healthPayload = await health.json();
  assert.equal(healthPayload.storage.access, "read_only");
  assert.equal(healthPayload.storage.writable, false);
  assert.equal(healthPayload.storage.mutation_owner, "tabularius");
  assert.equal(healthPayload.storage.mutation_route, "tabularius_ticket");

  const readiness = await worker.fetch(new Request("https://limen.test/api/readiness?agent=codex"), env);
  assert.equal(readiness.status, 200);
  const readinessPayload = await readiness.json();
  assert.equal(readinessPayload.mutation.status, "deferred");
  assert.equal(readinessPayload.mutation.code, "board_mutation_deferred");
  assert.equal(readinessPayload.mutation.route, "tabularius_ticket");
  assert.ok(readinessPayload.next_actions.some((action) => action.includes("TABVLARIVS")));
  assert.ok(readinessPayload.next_actions.every((action) => !action.includes("release-stale")));
  assert.equal(readinessPayload.checks.find((check) => check.id === "storage").status, "warn");

  const read = await worker.fetch(new Request("https://limen.test/api/tasks"), env);
  assert.equal(read.status, 200);
  assert.equal((await read.json()).tasks[0].status, "dispatched");

  const mutations = [
    new Request("https://limen.test/api/release-stale?hours=0&dry_run=false", { method: "POST" }),
    new Request("https://limen.test/api/tasks/WORKER-1/verify", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: "done" }),
    }),
    new Request("https://limen.test/api/tasks/WORKER-1/assign", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ target_agent: "codex" }),
    }),
  ];
  for (const request of mutations) {
    const mutation = await worker.fetch(request, env);
    assert.equal(mutation.status, 503);
    const receipt = await mutation.json();
    assert.match(receipt.detail, /conduct keeper binding is not configured/);
  }
  assert.deepEqual(calls.map((call) => call.method), ["GET", "GET", "GET", "GET", "GET"]);
});
