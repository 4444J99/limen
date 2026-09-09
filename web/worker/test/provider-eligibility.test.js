import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { applyTaskPacketProjectionEvent, applyTaskCompatibilityEvent } from "../src/conduct/projection.js";
import { validateProviderEligibility } from "../src/conduct/provider-eligibility.js";

const cases = JSON.parse(readFileSync(new URL("./fixtures/provider-eligibility-policies.json", import.meta.url)));
for (const entry of cases) {
  test(`shared Python/Worker policy schema: ${entry.name}`, () => {
    if (entry.valid) assert.deepEqual(validateProviderEligibility(entry.policy), entry.normalized);
    else assert.throws(() => validateProviderEligibility(entry.policy), /provider_eligibility_invalid/);
  });
}

const policy = () => ({
  schema_version: "limen.provider_eligibility.v1",
  repository: "example/fixture",
  source_revision: "a".repeat(40),
  data_classification: "synthetic",
  max_retention_days: 0,
  tools: ["read"],
  destinations: ["https://example.test"],
});
const board = (eligibility) => ({
  portal: { budget: { daily: 10, per_agent: { codex: 10 }, track: { date: "2026-09-08", spent: 0, per_agent: {} } } },
  tasks: [{
    id: "POLICY-FIXTURE", title: "Policy admission", status: "open", repo: "example/fixture",
    target_agent: "codex", budget_cost: 2, priority: "high", origin: "system_debt", horizon: "present",
    value_case: "Verify canonical policy admission", owner_surface: "example/fixture", predicate: "node --test",
    receipt_target: "git:example/fixture:receipt.json", dispatch_log: [],
    ...(eligibility === undefined ? {} : { provider_eligibility: eligibility }),
  }],
});
const event = (patch = {}, kind = "task.mutate") => ({
  schema_version: "limen.task_packet_projection_event.v1", event_id: "fixture:event:1",
  task_id: "POLICY-FIXTURE", timestamp: "2026-09-08T12:00:00.000Z", agent: "codex",
  session_id: "fixture-session", run_id: "fixture-run", lease_id: "fixture-lease", generation: 1,
  intent: { kind, task_id: "POLICY-FIXTURE", expected_status: "open", patch },
});

for (const value of [{}, false, "", [], 0, { ...policy(), destinations: ["https://["] }]) {
  for (const kind of ["task.mutate", "task.upsert"]) {
    test(`canonical ${kind} rejects malformed policy ${JSON.stringify(value)}`, () => {
      const input = board();
      const before = structuredClone(input);
      const update = event({ provider_eligibility: value }, kind);
      if (kind === "task.upsert") update.intent.task = { ...input.tasks[0], provider_eligibility: value };
      assert.throws(() => applyTaskPacketProjectionEvent(input, update), /provider_eligibility_invalid/);
      assert.deepEqual(input, before);
    });
  }
}
for (const kind of ["task.mutate", "task.status", "task.upsert"]) {
  for (const replacement of [null, { ...policy(), max_retention_days: 30 }]) {
    test(`canonical ${kind} cannot remove or replace an existing policy`, () => {
      const input = board(policy());
      const before = structuredClone(input);
      const patch = { status: "open", provider_eligibility: replacement };
      const update = event(patch, kind);
      if (kind === "task.upsert") update.intent.task = { ...input.tasks[0], ...patch };
      assert.throws(() => applyTaskPacketProjectionEvent(input, update), /provider_eligibility_change_unauthorized/);
      assert.deepEqual(input, before);
      const claim = event({ status: "dispatched" }, "task.claim");
      assert.throws(() => applyTaskPacketProjectionEvent(input, claim), /provider_eligibility_adapter_unavailable/);
    });
  }
}

test("legacy conduct transition cannot launch an explicit policy", () => {
  const input = board(policy());
  const before = structuredClone(input);
  const legacy = { ...event(), schema_version: "limen.task_projection_event.v1", kind: "run.started",
    status: "dispatched", from_statuses: ["open"], budget_action: "debit", output: "reserved" };
  assert.throws(() => applyTaskCompatibilityEvent(input, legacy), /provider_eligibility_adapter_unavailable/);
  assert.deepEqual(input, before);
});

test("new upsert cannot install an already launched policy-bearing task", () => {
  const update = event({}, "task.upsert");
  update.intent.task = { ...board(policy()).tasks[0], status: "dispatched" };
  assert.throws(() => applyTaskPacketProjectionEvent({ portal: {}, tasks: [] }, update), /provider_eligibility_adapter_unavailable/);
});

test("repository mutations cannot move an existing policy out of its bound repository", () => {
  assert.throws(() => applyTaskPacketProjectionEvent(board(policy()), event({ repo: "example/other" })),
    /provider_eligibility_repository_mismatch/);
});

test("unrelated changes and semantically identical policies preserve normalized policy", () => {
  const input = board(policy());
  for (const patch of [{ title: "Updated title" }, { provider_eligibility: { ...policy(), repository: "EXAMPLE/Fixture" } }]) {
    const update = event(patch);
    const before = structuredClone(update);
    assert.deepEqual(applyTaskPacketProjectionEvent(input, update).task.provider_eligibility, policy());
    assert.deepEqual(update, before);
  }
});

test("legacy policy-free claims and explicit null intake remain compatible", () => {
  for (const value of [undefined, null]) {
    const claimed = applyTaskPacketProjectionEvent(board(value), event({ status: "dispatched" }, "task.claim"));
    assert.equal(claimed.task.status, "dispatched");
    assert.equal(claimed.board.portal.budget.track.spent, 2);
  }
});
