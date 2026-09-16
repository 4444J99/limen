import assert from "node:assert/strict";
import test from "node:test";
import { submitCompletionHint, readCompletionHints, completionWorkKey, reconcileCompletionAssessment } from "../src/conduct/dependency-completion.js";
import { configuredConductPrincipals } from "../src/conduct/auth.js";
import { ConductKeeperDurableObject } from "../src/conduct/durable-object.js";
const policy = { schema: "limen.dependency_completion_policy.v1", installed: true,
  principal_id: "completion-test", max_records: 2,
  repositories: { "1154799938": { coordinate: "organvm/.github", default_branch: "main" } } };
const principal = { principal_id: "completion-test", roles: ["dependency_observer"] };
const conductor = { principal_id: "conductor-test", roles: ["conductor"] };
const hint = { repository_id: 1154799938, run_id: 10, run_attempt: 1, head_sha: "a".repeat(40) };
function storage() {
  let value;
  let tail = Promise.resolve();
  const store = { get: async () => structuredClone(value),
    put: async (_key, next) => { value = structuredClone(next); },
    transaction: operation => {
      const result = tail.then(() => operation(store));
      tail = result.catch(() => {});
      return result;
    } };
  return store;
}
test("concurrent duplicate deliveries persist one hint and survive a new reader", async () => {
  const store = storage();
  const results = await Promise.all(Array.from({ length: 5 }, () => submitCompletionHint(store, principal, hint, policy)));
  assert.equal(results.filter(row => !row.duplicate).length, 1);
  const readback = await readCompletionHints(store, conductor, policy);
  assert.equal(readback.hints.length, 1);
  assert.equal(readback.hints[0].assessment, "unmeasured");
  assert.equal(readback.automatic_acceptance, false);
  assert.equal(readback.hints[0].automatic_acceptance, false);
});
test("replayed changed head is rejected without changing stored evidence", async () => {
  const store = storage();
  await submitCompletionHint(store, principal, hint, policy);
  await assert.rejects(submitCompletionHint(store, principal, { ...hint, head_sha: "b".repeat(40) }, policy), /replay_conflict/);
  assert.equal((await readCompletionHints(store, conductor, policy)).hints[0].head_sha, hint.head_sha);
});
test("competing final slots admit exactly one record; duplicates need no new slot", async () => {
  const store = storage();
  await submitCompletionHint(store, principal, hint, policy);
  const result = await Promise.allSettled([11, 12].map(run_id => submitCompletionHint(store, principal, { ...hint, run_id }, policy)));
  assert.equal(result.filter(row => row.status === "fulfilled").length, 1);
  assert.equal(result.filter(row => row.status === "rejected").length, 1);
  assert.equal((await submitCompletionHint(store, principal, hint, policy)).duplicate, true);
});
test("ordinary principals, role combinations and wrong identities cannot write", async () => {
  for (const caller of [conductor, { ...principal, roles: ["observer"] },
    { ...principal, roles: ["dependency_observer", "conductor"] },
    { ...principal, principal_id: "another-observer" }]) {
    await assert.rejects(submitCompletionHint(storage(), caller, hint, policy), /unauthorized/);
  }
  await assert.rejects(readCompletionHints(storage(), principal, policy), /unauthorized/);
});
test("unknown repository, malformed hints and disabled policy fail before persistence", async () => {
  const store = { transaction() { throw Error("unexpected write"); } };
  for (const input of [{ ...hint, run_attempt: true }, { ...hint, run_id: 0 },
    { ...hint, head_sha: "bad" }, { ...hint, private_body: "not allowed" }]) {
    await assert.rejects(submitCompletionHint(store, principal, input, policy), /invalid/);
  }
  await assert.rejects(submitCompletionHint(store, principal, { ...hint, repository_id: 42 }, policy), /scope_unconfigured/);
  await assert.rejects(submitCompletionHint(store, principal, hint, { ...policy, installed: false }), /not_installed/);
});
test("corrupt durable evidence remains unmeasured", async () => {
  const store = storage();
  await store.put("unused", { corrupt: true });
  await assert.rejects(readCompletionHints(store, conductor, policy), /storage_unmeasured/);
  await assert.rejects(submitCompletionHint(store, principal, hint, policy), /storage_unmeasured/);
});
test("transport authenticates and dedicated roles cannot mix; production policy stays disabled", async () => {
  const bearer = "test-only-completion-bearer-0001";
  const env = { LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
    schema_version: "limen.conduct_principal_registry.v1", principals: [{
      principal_id: "dependency-completion-observer", agent: "github_actions", surface: "completion",
      roles: ["dependency_observer"], bearer }] }) };
  assert.equal(configuredConductPrincipals(env).length, 1);
  const keeper = new ConductKeeperDurableObject({ storage: {} }, env);
  const request = headers => new Request("https://keeper.test/api/conduct/dependencies/completions", {
    method: "POST", headers, body: JSON.stringify(hint) });
  assert.equal((await keeper.fetch(request({}))).status, 401);
  assert.equal((await keeper.fetch(request({ Authorization: `Bearer ${bearer}` }))).status, 503);
  const document = JSON.parse(env.LIMEN_CONDUCT_PRINCIPAL_REGISTRY);
  document.principals[0].roles.push("observer");
  assert.throws(() => configuredConductPrincipals({ ...env,
    LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify(document) }), /invalid/);
});
function graphFor(hintRow) {
  return { schema_version: "limen.conduct_graph.v1", root_run_id: "assessment-1", nodes: [{
    run_id: "assessment-1", lease_id: "lease-1", lease: { generation: 1 }, status: "succeeded",
    packet: { work_key: completionWorkKey(hintRow), effect: "read", predicate: "trusted-assessor",
      authority: { may_delegate: false, external_effects: [], repositories: ["organvm/.github"] },
      intent: { dependency_completion: { ...hint } }, execution: { observed_heads: { dependency_head: hint.head_sha } } },
    receipts: [{ receipt_id: "receipt-1", run_id: "assessment-1", lease_id: "lease-1", lease_generation: 1,
      mutation_authorized: true, accepted_at: "2026-09-16T00:00:00Z", outcome: "succeeded",
      predicate: { command: "trusted-assessor", exit_code: 0 },
      observed_heads_before: { dependency_head: hint.head_sha }, observed_heads_after: { dependency_head: hint.head_sha } }],
  }] };
}
test("only a bound keeper receipt records assessment, never automatic acceptance", async () => {
  const store = storage();
  const row = await submitCompletionHint(store, principal, hint, policy);
  const graph = graphFor(row);
  const result = await reconcileCompletionAssessment(store, conductor, row.key, "assessment-1", async id => {
    assert.equal(id, "assessment-1"); return graph;
  }, policy);
  assert.equal(result.status, "reported");
  assert.equal(result.receipt_id, "receipt-1");
  assert.equal(result.automatic_acceptance, false);
  assert.deepEqual((await readCompletionHints(store, conductor, policy)).hints[0].broker_assessment, result);
  assert.deepEqual(await reconcileCompletionAssessment(store, conductor, row.key, "assessment-1", async () => graph, policy), result);
});
test("stale, unauthorized, failed predicate and wrong-head receipts remain unmeasured", async () => {
  for (const patch of [{ mutation_authorized: false }, { lease_generation: 2 },
    { predicate: { command: "wrong", exit_code: 0 } }, { predicate: { command: "trusted-assessor", exit_code: 1 } },
    { observed_heads_before: { dependency_head: "b".repeat(40) } }]) {
    const store = storage();
    const row = await submitCompletionHint(store, principal, hint, policy);
    const graph = graphFor(row); Object.assign(graph.nodes[0].receipts[0], patch);
    const result = await reconcileCompletionAssessment(store, conductor, row.key, "assessment-1", async () => graph, policy);
    assert.equal(result.status, "unmeasured");
    assert.equal(result.automatic_acceptance, false);
  }
});
test("changed packet scope and duplicate receipts fail closed", async () => {
  for (const mutate of [graph => { graph.nodes[0].packet.effect = "write"; },
    graph => { graph.nodes[0].packet.work_key = "unrelated"; },
    graph => { graph.nodes[0].packet.intent.dependency_completion.run_attempt = 2; },
    graph => { graph.nodes[0].packet.authority.external_effects = ["send"]; },
    graph => { graph.nodes[0].receipts.push({ ...graph.nodes[0].receipts[0] }); }]) {
    const store = storage(); const row = await submitCompletionHint(store, principal, hint, policy);
    const graph = graphFor(row); mutate(graph);
    await assert.rejects(reconcileCompletionAssessment(store, conductor, row.key, "assessment-1", async () => graph, policy), /scope_mismatch|receipts_ambiguous/);
    assert.equal((await readCompletionHints(store, conductor, policy)).hints[0].broker_assessment, undefined);
  }
});
test("broker outages and unauthorized callers cannot file assessment", async () => {
  const store = storage(); const row = await submitCompletionHint(store, principal, hint, policy);
  await assert.rejects(reconcileCompletionAssessment(store, conductor, row.key, "assessment-1", async () => { throw Error("private diagnostic"); }, policy), /dependency_assessment_unmeasured/);
  await assert.rejects(reconcileCompletionAssessment(store, principal, row.key, "assessment-1", async () => { throw Error("must not read"); }, policy), /unauthorized/);
});
