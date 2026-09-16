import assert from "node:assert/strict";
import test from "node:test";
import { submitCompletionHint, readCompletionHints } from "../src/conduct/dependency-completion.js";
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
