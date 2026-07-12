import assert from "node:assert/strict";
import test from "node:test";

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
