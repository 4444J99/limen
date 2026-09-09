import assert from "node:assert/strict";
import test from "node:test";
import emittedCensus from "./fixtures/inventory-collector-census.json" with { type: "json" };
import { configuredConductPrincipals } from "../src/conduct/auth.js";
import { ConductKeeperDurableObject } from "../src/conduct/durable-object.js";
import { DurableConductStore, MemoryConductStore, SerializedConductService } from "../src/conduct/keeper.js";
import { applyTaskCompatibilityEvent } from "../src/conduct/projection.js";
import { publicBoardProjection } from "../src/conduct/private-board.js";
import { canonicalHash, validateSession, validateWorkPacket } from "../src/conduct/schemas.js";
import {
  acceptInventoryObservation, configuredInventoryAuthority, inventoryCount,
  inventoryProjectionContext, requireInventoryCapacity, recordInventoryTransition,
} from "../src/conduct/inventory-admission.js";

const NOW = new Date("2026-09-09T12:00:00.000Z");
const authority = configuredInventoryAuthority({ LIMEN_INVENTORY_AUTHORITY: JSON.stringify({
  schema_version: "limen.inventory_authority.v1", principal_id: "estate-collector",
  repository_ids: ["42"], source_generation: "a".repeat(64),
}) });
const collector = { principal_id: authority.principal_id, roles: ["inventory_collector"] };

test("Worker consumes actual Python collector emission with its canonical hashes", async () => {
  // Produced by the real collect(inventory_authority=...) path with only remote
  // transport replaced by test_inventory_census_integration._emit's fixture.
  const at = new Date(emittedCensus.source_report.generated_at);
  assert.equal(await inventoryCount(emittedCensus, authority, at), 1);
  assert.equal((await acceptInventoryObservation(authority, collector, emittedCensus, null, at)).count, 1);
});

async function census(count = 249, now = NOW) {
  const leaves = Array.from({ length: count }, (_, index) => ({ kind: "pull_request",
    repository: "example/private-repo", number: index + 1, author_login: "4444J99", title: "private-synthetic-title" }));
  const cursors = ["pull_requests", "issues", "branches", "checks"].map((kind) => ({
    repository: "example/private-repo", kind, expected_total: kind === "pull_requests" ? count : 0,
    known_count: kind === "pull_requests" ? count : 0, page_count: kind === "pull_requests" && count ? 1 : 0,
    page_cursor: null, complete: true, exhaustive: true, reused: false, source_generation: "b".repeat(64),
  }));
  return { schema: "limen.github-estate-census.v1", failures: [], leaves, cursors,
    repositories: [{ repository_id: "42", name_with_owner: "example/private-repo" }],
    repository_receipts: [{ repository: "example/private-repo", repository_id: "42", complete: true,
      source_generation: authority.source_generation, connection_receipt_digest: await canonicalHash(cursors) }],
    inventory_collection: { started_at: now.toISOString() },
    source_report: { exhaustive: true, generated_at: now.toISOString(), source_generation: authority.source_generation,
      normalized_leaf_count: count, content_sha256: await canonicalHash(leaves),
      cursor: { leaf_count_complete: true, known_leaf_count: count,
        repository: { expected_total: 1, known_count: 1, page_count: 1, exhaustive: true } } },
  };
}

function task(id) {
  return { id, title: "Routine task", status: "open", labels: [], target_agent: "codex", budget_cost: 2,
    repo: "example/private-repo", origin: "human_prompt", horizon: "present", value_case: "Verify admission",
    owner_surface: "example/private-repo", predicate: "node --test", receipt_target: "git:example/private-repo:receipt" };
}

test("collector role is dedicated and ingestion ignores ordinary principal/request claims", async () => {
  const registry = (roles) => ({ LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
    schema_version: "limen.conduct_principal_registry.v1", principals: [{ principal_id: "estate-collector",
      agent: "codex", surface: "collector", bearer: "synthetic-collector-bearer-at-least-24", roles }],
  }) });
  assert.equal(configuredConductPrincipals(registry(["inventory_collector"])).length, 1);
  for (const role of ["observer", "conductor", "executor", "compatibility"]) {
    assert.throws(() => configuredConductPrincipals(registry(["inventory_collector", role])), /invalid/);
    await assert.rejects(acceptInventoryObservation(authority, { ...collector, roles: [role] }, await census(), null, NOW),
      /inventory_collector_unauthorized/);
  }
  const durable = new ConductKeeperDurableObject({ storage: {} }, registry(["inventory_collector"]));
  for (const [path, method] of [["/api/conduct/sessions", "POST"], ["/api/conduct/runs", "POST"],
    ["/api/board/private", "GET"], ["/api/board/initialize", "POST"]]) {
    const response = await durable.fetch(new Request(`https://example.invalid${path}`, { method,
      headers: { authorization: "Bearer synthetic-collector-bearer-at-least-24" } }));
    assert.equal(response.status, 403, path);
  }
});

for (const [name, mutate, pattern] of [
  ["partial", (o) => { o.source_report.exhaustive = false; }, /partial/],
  ["scope", (o) => { o.repositories[0].repository_id = "43"; }, /scope/],
  ["generation", (o) => { o.source_report.source_generation = "f".repeat(64); }, /generation/],
  ["stale", (o) => { o.source_report.generated_at = "2026-09-09T11:44:59Z"; }, /stale/],
  ["future", (o) => { o.source_report.generated_at = "2026-09-09T12:00:01Z"; }, /stale/],
  ["content", (o) => { o.leaves[0].author_login = "someone-else"; }, /content_digest/],
  ["cursor", (o) => { o.cursors.pop(); }, /partition/],
  ["identity", (o) => { o.leaves[0].number = true; }, /content_digest/],
]) {
  test(`reject ${name} evidence before durable mutation`, async () => {
    const store = new MemoryConductStore();
    const service = new SerializedConductService(store, { inventoryAuthority: authority, clock: () => NOW });
    const observation = await census();
    mutate(observation);
    const before = store.snapshot();
    await assert.rejects(service.call("inventory_observation", { principal: collector, observation }), pattern);
    assert.deepEqual(store.snapshot(), before);
    assert.equal(store.saveCount, 0);
  });
}

test("same-time replay, reused scans and config rotation cannot mint freshness", async () => {
  const observation = await census();
  const accepted = await acceptInventoryObservation(authority, collector, observation, null, NOW);
  await assert.rejects(acceptInventoryObservation(authority, collector, observation, accepted, NOW), /replayed/);
  observation.cursors[0].reused = true;
  observation.repository_receipts[0].connection_receipt_digest = await canonicalHash(observation.cursors);
  await assert.rejects(acceptInventoryObservation(authority, collector, observation, null, NOW), /fresh_collection/);
  await assert.rejects(inventoryProjectionContext({ ...authority, source_generation: "f".repeat(64) }, accepted, NOW), /adapter_unavailable/);
  await assert.rejects(inventoryProjectionContext(authority, accepted, new Date(NOW.getTime() + 900001)), /stale/);
});

test("keeper stores private facts while responses and public projection exclude them", async () => {
  const store = new MemoryConductStore();
  const service = new SerializedConductService(store, { inventoryAuthority: authority, clock: () => NOW });
  const observation = await census();
  observation.local_git_census = { private_path: "private-local-source" };
  const result = await service.call("inventory_observation", { principal: collector, observation });
  assert.equal(result.status, "accepted");
  assert.equal(store.snapshot().inventory_observation.observation.local_git_census, undefined);
  const publicValues = [result, await service.call("capabilities"), publicBoardProjection({ tasks: [task("GEN-one")] })];
  for (const value of publicValues) {
    assert.doesNotMatch(JSON.stringify(value), /private-synthetic-title|example\/private-repo|private-local-source|content_sha256/);
  }
  assert.equal(store.snapshot().inventory_observation.observation.leaves.length, 249);
});

test("authenticated HTTP ingestion survives private chunk-store reload without a facts endpoint", async () => {
  class Storage {
    values = new Map();
    async get(key) { return Array.isArray(key) ? new Map(key.map((name) => [name, structuredClone(this.values.get(name))]))
      : structuredClone(this.values.get(key)); }
    async put(key, value) { this.values.set(key, structuredClone(value)); }
    async delete(keys) { for (const key of Array.isArray(keys) ? keys : [keys]) this.values.delete(key); }
    async list({ prefix } = {}) { return new Map([...this.values].filter(([key]) => !prefix || key.startsWith(prefix))); }
  }
  const storage = new Storage();
  const bearer = "synthetic-collector-bearer-at-least-24";
  const env = { LIMEN_INVENTORY_AUTHORITY: JSON.stringify(authority), LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
    schema_version: "limen.conduct_principal_registry.v1", principals: [{ principal_id: authority.principal_id,
      agent: "codex", surface: "collector", roles: ["inventory_collector"], bearer }],
  }) };
  const durable = new ConductKeeperDurableObject({ storage }, env);
  durable.service.clock = () => NOW;
  const request = (path, method = "GET", body) => new Request(`https://example.invalid/api/conduct/inventory/${path}`,
    { method, headers: { authorization: `Bearer ${bearer}` }, ...(body ? { body: JSON.stringify(body) } : {}) });
  assert.deepEqual(await (await durable.fetch(request("authority"))).json(), authority);
  const result = await durable.fetch(request("observations", "POST", { observation: await census(2) }));
  assert.equal(result.status, 200);
  assert.doesNotMatch(await result.text(), /private-synthetic-title|private-repo|content_sha256/);
  const restored = await new DurableConductStore(storage).load();
  assert.equal(restored.inventory_observation.observation.leaves.length, 2);
  const before = structuredClone([...storage.values]);
  assert.equal((await durable.fetch(request("observations", "POST", { observation: await census(2) }))).status, 409);
  assert.deepEqual([...storage.values], before);
  assert.equal((await durable.fetch(request("observations"))).status, 404);
});

test("two concurrent final-slot claims persist exactly one reservation, task change and debit", async () => {
  let board = { portal: { budget: { daily: 10, per_agent: { codex: 10 }, track: { date: "2026-09-09", spent: 0, per_agent: {} } } },
    tasks: [task("GEN-one"), task("GEN-two")] };
  const store = new MemoryConductStore();
  const service = new SerializedConductService(store, { inventoryAuthority: authority, clock: () => NOW,
    projectTaskEvent: async (event, context) => {
      const admission = await inventoryProjectionContext(context.inventoryAuthority, context.inventoryObservation, context.now);
      const applied = applyTaskCompatibilityEvent(board, event, admission);
      board = applied.board;
      return { status: "committed", task: applied.task };
    } });
  await service.call("inventory_observation", { principal: collector, observation: await census() });
  const identity = { schema_version: "limen.agent_identity.v1", agent: "codex", surface: "cli", session_id: "inventory-test-session",
    native_run_id: null, provider_identity: null };
  await service.call("register", { session: validateSession({ session_id: identity.session_id, identity, origin: "direct",
    capabilities: ["code", "board-write", "task-submit"], concurrency: 2, worktree: null, registered_at: NOW.toISOString(),
    heartbeat_at: NOW.toISOString(), human_protected: true, supersedes: null }, NOW) });
  const packets = await Promise.all(board.tasks.map((row) => validateWorkPacket({
    work_id: row.id, work_key: row.id, intent: { kind: "task.claim", task_id: row.id, expected_status: "open", patch: { status: "dispatched" } },
    execution: { adapter: "tabularius", projection: "tasks.yaml", observed_heads: {} }, initiator: identity, conductor: identity,
    preferred_agent: "tabularius", required_capabilities: ["board-write"], resource_claims: [{ key: `task/${row.id}`, mode: "exclusive" }],
    predicate: "python3 scripts/validate-task-board.py --tasks tasks.yaml",
    receipt_target: `git:example/private-repo:tasks.yaml#${row.id}`, authority: { actions: ["task.claim"],
      repositories: ["example/private-repo"], path_prefixes: ["tasks.yaml"], external_effects: [], may_delegate: false },
    deadline: new Date(NOW.getTime() + 60000).toISOString(), spend: { unit: "runs", limit: 0, reserve: 0 },
    retry: { max_attempts: 1, transient_only: true }, fanout: { max_children: 0, max_depth: 0 }, effect: "write", task_id: row.id,
  })));
  const results = await Promise.allSettled(packets.map((packet) => service.call("submit", { packet })));
  assert.equal(results.filter((row) => row.status === "fulfilled").length, 1,
    JSON.stringify(results.map((row) => row.reason?.message || row.value)));
  assert.match(results.find((row) => row.status === "rejected").reason.message, /inventory_growth_ceiling/);
  assert.equal(board.tasks.filter((row) => row.status === "dispatched").length, 1);
  assert.equal(board.portal.budget.track.spent, 2);
  assert.equal(Object.keys(board.inventory_growth_reservations).length, 1);
  assert.equal(Object.keys(store.snapshot().runs).length, 1);
  assert.equal(Object.keys(store.snapshot().leases).length, 1);
});

test("settled reservations need post-settlement scan coverage; same-task retries retain old custody", async () => {
  const observation = await census(248);
  const context = await inventoryProjectionContext(authority, await acceptInventoryObservation(authority, collector, observation, null, NOW), NOW);
  const prior = task("GEN-new");
  const candidate = { ...prior, status: "dispatched" };
  const board = { tasks: [{ ...task("GEN-old"), status: "in_progress" }], inventory_growth_reservations: {
    old: { task_id: "GEN-old", repository: "example/private-repo", settled_at: NOW.toISOString() },
  } };
  assert.throws(() => requireInventoryCapacity(board, prior, candidate, context), /growth_ceiling/);
  assert.throws(() => requireInventoryCapacity(board, prior, candidate, { count: 0 }), /adapter_unavailable/);
  const fresh = new Date(NOW.getTime() + 1000);
  const freshContext = await inventoryProjectionContext(authority,
    await acceptInventoryObservation(authority, collector, await census(248, fresh), null, fresh), fresh);
  requireInventoryCapacity(board, prior, candidate, freshContext);
  board.inventory_growth_reservations.old.repository = "outside/coverage";
  assert.throws(() => requireInventoryCapacity(board, prior, candidate, freshContext), /growth_ceiling/);
});

test("only canonical prelaunch refund clears a reservation before fresh coverage", () => {
  const original = task("GEN-one");
  const board = { tasks: [] };
  const event = { lease_id: "lease-one", timestamp: NOW.toISOString(), intent: { kind: "task.claim" } };
  const reserved = { ...original, status: "dispatched" };
  recordInventoryTransition(board, original, reserved, event);
  recordInventoryTransition(board, reserved, original, { ...event, intent: { kind: "task.status" } });
  assert.equal(Object.keys(board.inventory_growth_reservations).length, 0);
  recordInventoryTransition(board, original, reserved, event);
  recordInventoryTransition(board, reserved, { ...reserved, status: "in_progress" }, event);
  recordInventoryTransition(board, { ...reserved, status: "in_progress" }, { ...reserved, status: "failed" }, event);
  assert.equal(board.inventory_growth_reservations["lease-one"].settled_at, NOW.toISOString());
});

test("claim-time repository change binds the resulting reservation to the execution repository", () => {
  const original = task("GEN-repository-change");
  const board = { tasks: [] };
  const candidate = { ...original, repo: "example/another-scoped-repo", status: "dispatched" };
  const event = { lease_id: "lease-moved", timestamp: NOW.toISOString(), intent: { kind: "task.claim" } };
  recordInventoryTransition(board, original, candidate, event);
  assert.equal(board.inventory_growth_reservations["lease-moved"].repository, candidate.repo);
});

test("out-of-scope routine claims cannot debit and active reservations cannot move repositories", async () => {
  const context = await inventoryProjectionContext(authority,
    await acceptInventoryObservation(authority, collector, await census(0), null, NOW), NOW);
  const original = { ...task("GEN-one"), repo: "outside/scope" };
  const board = { tasks: [original], portal: { budget: { daily: 10, track: { spent: 0 } } } };
  const event = { schema_version: "limen.task_packet_projection_event.v1", event_id: "scope-test",
    timestamp: NOW.toISOString(), task_id: original.id, agent: "codex", session_id: "session-test",
    run_id: "run-test", lease_id: "lease-test", generation: 1,
    intent: { kind: "task.claim", task_id: original.id, expected_status: "open", patch: { status: "dispatched" } } };
  const before = structuredClone(board);
  assert.throws(() => applyTaskCompatibilityEvent(board, event, context), /inventory_task_scope_changed/);
  assert.deepEqual(board, before);
  board.tasks[0] = { ...task("GEN-one"), status: "in_progress" };
  event.intent = { kind: "task.mutate", task_id: original.id, expected_status: "in_progress", patch: { repo: "outside/scope" } };
  const reserved = structuredClone(board);
  assert.throws(() => applyTaskCompatibilityEvent(board, event), /inventory_reservation_repository_immutable/);
  assert.deepEqual(board, reserved);
});
