import assert from "node:assert/strict";
import test from "node:test";
import { ConductKeeperDurableObject } from "../src/conduct/durable-object.js";

function fixture(roles = ["observer"]) {
  const keeper = Object.create(ConductKeeperDurableObject.prototype);
  keeper.env = {
    LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
      schema_version: "limen.conduct_principal_registry.v1",
      principals: [{ principal_id: "audit-reader", agent: "codex", surface: "direct",
        roles, bearer: "audit-fixture-bearer-at-least-24-characters" }],
    }),
  };
  keeper.calls = [];
  keeper.service = { call: async (operation, payload) => {
    keeper.calls.push({ operation, payload });
    return { schema_version: "limen.conduct_session_audit.v1", session_id: payload.session_id };
  } };
  return keeper;
}

function request({ method = "GET", authenticated = true, identity = "session%2Fscope" } = {}) {
  return new Request(`https://limen.example/api/conduct/sessions/${identity}/audit`, {
    method,
    headers: authenticated ? { authorization: "Bearer audit-fixture-bearer-at-least-24-characters" } : {},
  });
}

test("session audit requires authentication and the observer role before touching keeper state", async () => {
  const anonymous = fixture();
  assert.equal((await anonymous.fetch(request({ authenticated: false }))).status, 401);
  assert.equal(anonymous.calls.length, 0);
  const conductor = fixture(["conductor"]);
  assert.equal((await conductor.fetch(request())).status, 403);
  assert.equal(conductor.calls.length, 0);
});

test("session audit GET only dispatches its bounded read operation", async () => {
  const keeper = fixture();
  const response = await keeper.fetch(request());
  assert.equal(response.status, 200);
  assert.deepEqual(keeper.calls, [{ operation: "session_audit", payload: { session_id: "session/scope" } }]);
  assert.equal((await response.json()).session_id, "session/scope");
  assert.equal((await keeper.fetch(request({ method: "POST" }))).status, 404);
  assert.equal(keeper.calls.length, 1);
});

test("malformed native identity fails before the audit operation", async () => {
  const keeper = fixture();
  assert.equal((await keeper.fetch(request({ identity: "%00invalid" }))).status, 422);
  assert.equal(keeper.calls.length, 0);
});
