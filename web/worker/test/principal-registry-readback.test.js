import assert from "node:assert/strict";
import test from "node:test";
import { conductPrincipalRegistryReadback } from "../src/conduct/auth.js";
import { ConductKeeperDurableObject } from "../src/conduct/durable-object.js";

function fixture() {
  const principals = ["conductor", "observer", "executor", "compatibility", "inventory_collector", "dependency_observer"]
    .map(role => ({ principal_id: role, agent: "codex", surface: "test", roles: [role],
      bearer: `nonfunctional-test-bearer-for-${role}` }));
  const env = { LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
    schema_version: "limen.conduct_principal_registry.v1", principals,
  }) };
  const keeper = Object.create(ConductKeeperDurableObject.prototype);
  keeper.env = env;
  keeper.service = { call() { throw new Error("readback must not mutate keeper state"); } };
  return { env, principals, keeper };
}

test("only authenticated conductors can inspect complete redacted registry", async () => {
  const { keeper, principals } = fixture();
  for (const row of principals) {
    const response = await keeper.fetch(new Request("https://keeper.test/api/conduct/principal-registry", {
      headers: { authorization: `Bearer ${row.bearer}` },
    }));
    assert.equal(response.status, row.roles[0] === "conductor" ? 200 : 403);
    const body = await response.text();
    for (const principal of principals) assert.equal(body.includes(principal.bearer), false);
    if (response.status === 200) {
      assert.equal(response.headers.get("cache-control"), "no-store");
      const doc = JSON.parse(body);
      assert.equal(doc.principals.length, principals.length);
      assert.match(doc.configuration_fingerprint, /^[a-f0-9]{64}$/);
      assert.ok(doc.principals.every(p => !Object.hasOwn(p, "bearer")));
    }
  }
  const missing = await keeper.fetch(new Request("https://keeper.test/api/conduct/principal-registry"));
  assert.equal(missing.status, 401);
});

test("fingerprint detects every credential or authority change and ignores serialization order", async () => {
  const { env, principals } = fixture();
  const baseline = await conductPrincipalRegistryReadback(env);
  const read = async rows => conductPrincipalRegistryReadback({ LIMEN_CONDUCT_PRINCIPAL_REGISTRY:
    JSON.stringify({ schema_version: "limen.conduct_principal_registry.v1", principals: rows }, null, 2) });
  assert.deepEqual(await read([...principals].reverse()), baseline);
  for (const key of ["bearer", "principal_id", "agent", "surface", "roles"]) {
    const changed = structuredClone(principals);
    changed[1][key] = key === "roles" ? ["observer", "conductor"] : changed[1][key] + "-changed";
    assert.notEqual((await read(changed)).configuration_fingerprint, baseline.configuration_fingerprint);
  }
  assert.notEqual((await read(principals.slice(1))).configuration_fingerprint, baseline.configuration_fingerprint);
  const duplicate = [...principals, principals[0]];
  await assert.rejects(read(duplicate), /duplicate/);
});

test("malformed registry fails closed before readback", async () => {
  const { keeper, env } = fixture();
  env.LIMEN_CONDUCT_PRINCIPAL_REGISTRY = "invalid";
  const response = await keeper.fetch(new Request("https://keeper.test/api/conduct/principal-registry", {
    headers: { authorization: "Bearer nonfunctional-test-bearer-for-conductor" },
  }));
  assert.equal(response.status, 503);
});
