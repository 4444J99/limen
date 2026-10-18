import assert from "node:assert/strict";
import test from "node:test";
import { gzipSync } from "node:zlib";
import { createHash } from "node:crypto";
import { ConductKeeperDurableObject } from "../src/conduct/durable-object.js";
import { canonicalHash } from "../src/conduct/schemas.js";

const bearer = "storage-owner-bearer-at-least-24-characters";
const policy = {mode: "recovery", dispatch_enabled: false, execution_limits: {attempt_seconds: 1800,
  verification_seconds: 600, cumulative_seconds: 7200}, approved_priorities: Array.from({length: 8}, (_, i) => ({
    outcome_id: `storage-fixture-${i}`, work_keys: [`fixture-${i}`], enabled: true, recovery: true,
    owner: "https://example.test/" + "preserved-policy-data/".repeat(40), deadline_policy: "hard_deadline",
    resource_limits: {issue: 0, branch: 3, worktree: 1}}))};
function envelope(value, bytes = Buffer.from(JSON.stringify(value))) {
  return {schema_version: "limen.execution_policy_storage.v1", encoding: "gzip+base64",
    sha256: createHash("sha256").update(bytes).digest("hex"), uncompressed_bytes: bytes.length,
    data: gzipSync(bytes).toString("base64")};
}
function worker(binding) {
  const storage = new Map();
  return new ConductKeeperDurableObject({storage: {
    get: async key => storage.get(key), put: async (key, value) => storage.set(key, value),
    delete: async key => storage.delete(key), list: async () => new Map(storage),
  }}, {LIMEN_EXECUTION_POLICY: binding, LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
    schema_version: "limen.conduct_principal_registry.v1", principals: [{principal_id: "owner", agent: "codex",
      surface: "cli", roles: ["conductor"], bearer}]}),
    LIMEN_CONDUCT_RUNTIME_GIT_SHA: "a".repeat(40), CF_VERSION_METADATA: {id: "storage-fixture"}});
}
async function read(instance, custody = false) {
  return instance.fetch(new Request("https://limen.test/api/conduct/execution/policy", {headers: {
    authorization: `Bearer ${bearer}`, ...(custody ? {"x-limen-policy-custody": "recover"} : {})}}));
}

test("oversize complete policy round trips through bounded compressed binding and private readback", async () => {
  assert.ok(Buffer.byteLength(JSON.stringify(policy)) > 5120);
  const binding = JSON.stringify(envelope(policy));
  assert.ok(Buffer.byteLength(binding) < 5000);
  const instance = worker(binding);
  const response = await read(instance);
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.configuration_fingerprint, await canonicalHash(policy));
  assert.deepEqual(body.supported_storage_encodings, ["json", "gzip+base64"]);
  assert.ok(!JSON.stringify(body).includes("preserved-policy-data"));
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual((await (await read(instance, true)).json()).policy, policy);
});

test("legacy JSON policy readback retains its original semantic fingerprint", async () => {
  const value = {mode: "recovery", dispatch_enabled: false, approved_priorities: []};
  const response = await read(worker(JSON.stringify(value)), true);
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.configuration_fingerprint, await canonicalHash(value));
  assert.deepEqual(body.policy, value);
});

test("invalid compressed policy never falls back to its envelope as an execution policy", async t => {
  const good = envelope(policy);
  const cases = {
    digest: {...good, sha256: "0".repeat(64)},
    truncated: {...good, data: good.data.slice(0, -8)},
    encoding: {...good, encoding: "unknown"},
    version: {...good, schema_version: "limen.execution_policy_storage.v2"},
    length: {...good, uncompressed_bytes: good.uncompressed_bytes - 1},
    limit: {...good, uncompressed_bytes: 65537},
    expansion: {...envelope({}, Buffer.from(" ".repeat(65537))), uncompressed_bytes: 1024},
    utf8: envelope({}, Buffer.from([0xff])),
    json: envelope({}, Buffer.from("{")),
    array: envelope([]),
    missing: {...good, data: undefined},
    extra: {...good, unexpected: true},
  };
  for (const [name, value] of Object.entries(cases)) await t.test(name, async () => {
    const instance = worker(JSON.stringify(value));
    const response = await read(instance, true);
    assert.equal(response.status, 409);
    assert.deepEqual(await response.json(), {detail: "execution_policy_invalid"});
    // The constructor must retain a fail-closed policy for every admission call.
    const allowance = await instance.fetch(new Request("https://limen.test/api/conduct/execution/allowance", {
      method: "POST", headers: {authorization: `Bearer ${bearer}`, "content-type": "application/json"},
      body: JSON.stringify({work_key: "fixture-0"})}));
    assert.equal(allowance.status, 409);
    assert.deepEqual(await allowance.json(), {detail: "execution_priority_not_approved"});
  });
});
