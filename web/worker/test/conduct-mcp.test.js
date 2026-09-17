import assert from "node:assert/strict";
import test from "node:test";
import worker from "../src/index.js";
import { ConductKeeperDurableObject } from "../src/conduct/durable-object.js";
import { MemoryConductStore, SerializedConductService } from "../src/conduct/keeper.js";

// Test-only credentials. They are never installation values or runtime identities.
const TOKEN = "mcp-fixture-only-bearer-at-least-24-characters";
function fixture(roles = ["observer", "conductor", "executor"]) {
  const env = {
    LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
      schema_version: "limen.conduct_principal_registry.v1",
      principals: [{ principal_id: "mcp-fixture", agent: "codex", surface: "direct", roles, bearer: TOKEN }],
    }),
    LIMEN_CONDUCT_KEEPER_NAME: "mcp-existing-keeper",
  };
  const keeper = Object.create(ConductKeeperDurableObject.prototype);
  keeper.env = env;
  keeper.service = new SerializedConductService(new MemoryConductStore(), { capabilitySecret: "test-only-capability-secret-24-characters" });
  const calls = [];
  env.CONDUCT_KEEPER = {
    idFromName(name) { assert.equal(name, "mcp-existing-keeper"); return name; },
    get() { return { fetch: async (request) => {
      calls.push({ path: new URL(request.url).pathname, method: request.method,
        authorization: request.headers.get("authorization"),
        body: request.body ? await request.clone().json() : undefined });
      return keeper.fetch(request);
    } }; },
  };
  return { env, calls, keeper };
}

function request(message, { token = TOKEN, method = "POST", headers = {}, body } = {}) {
  return new Request("https://limen.example/mcp", {
    method,
    headers: {
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      "content-type": "application/json", accept: "application/json, text/event-stream", ...headers,
    },
    ...(method === "POST" ? { body: body ?? JSON.stringify(message) } : {}),
  });
}
const message = (method, params, id = 0) => ({ jsonrpc: "2.0", id, method, ...(params === undefined ? {} : { params }) });
const invoke = (name, args = {}, id = "correlation/1") => message("tools/call", { name, arguments: args }, id);

test("authentication precedes every MCP method and all keeper access", async () => {
  const { env, calls } = fixture();
  for (const method of ["POST", "GET", "OPTIONS", "DELETE"]) {
    for (const token of [null, "invalid"]) {
      const response = await worker.fetch(request(message("tools/list"), { method, token }), env);
      assert.equal(response.status, 401);
      assert.equal(response.headers.get("www-authenticate"), 'Bearer realm="limen-conduct"');
    }
  }
  assert.deepEqual(calls, []);
  delete env.LIMEN_CONDUCT_PRINCIPAL_REGISTRY;
  assert.equal((await worker.fetch(request(message("initialize")), env)).status, 503);
});

test("stateless initialize negotiates versions, notification is empty 202, GET is 405", async () => {
  const { env, calls } = fixture();
  for (const version of ["2025-03-26", "2025-06-18", "2025-11-25", "unknown-version"]) {
    const response = await worker.fetch(request(message("initialize", {
      protocolVersion: version, capabilities: {}, clientInfo: { name: "fixture", version: "1" },
    })), env);
    const payload = await response.json();
    assert.equal(payload.id, 0);
    assert.equal(payload.result.protocolVersion, version === "unknown-version" ? "2025-11-25" : version);
    assert.deepEqual(payload.result.capabilities, { tools: { listChanged: false } });
    assert.equal(response.headers.get("mcp-session-id"), null);
    assert.equal(response.headers.get("cache-control"), "no-store");
  }
  const notification = await worker.fetch(request({ jsonrpc: "2.0", method: "notifications/initialized" }), env);
  assert.equal(notification.status, 202);
  assert.equal(await notification.text(), "");
  assert.equal((await worker.fetch(request(null, { method: "GET" }), env)).status, 405);
  assert.deepEqual(calls, []);
});

test("tools/list exposes a closed typed catalog including canonical executor claim", async () => {
  const { env, calls } = fixture();
  const payload = await (await worker.fetch(request(message("tools/list")), env)).json();
  assert.equal(payload.result.tools.length, 14);
  const claim = payload.result.tools.find((tool) => tool.name === "conduct_claim");
  assert.deepEqual(claim.inputSchema.required, ["lease", "generation"]);
  assert.equal(claim.inputSchema.additionalProperties, false);
  assert.deepEqual(calls, []);
});

test("Origin, protocol, media, and bounded input validation deny before delegation", async () => {
  const { env, calls } = fixture();
  const cases = [
    [{ origin: "https://untrusted.example" }, 403], [{ origin: "null" }, 403],
    [{ "mcp-protocol-version": "2020-01-01" }, 400], [{ accept: "application/json" }, 406],
    [{ "content-type": "text/plain" }, 415], [{ "content-length": "1048577" }, 413],
  ];
  for (const [headers, status] of cases) {
    assert.equal((await worker.fetch(request(message("tools/list"), { headers }), env)).status, status);
  }
  env.LIMEN_MCP_ALLOWED_ORIGINS = "https://approved.example";
  assert.equal((await worker.fetch(request(message("ping"), { headers: { origin: "https://approved.example" } }), env)).status, 200);
  assert.equal((await worker.fetch(request(message("ping"), { body: " ".repeat(1048577) }), env)).status, 413);
  assert.equal((await worker.fetch(request(message("ping"), { body: "{invalid" }), env)).status, 400);
  assert.deepEqual(calls, []);
});

test("invalid IDs, batches, responses, methods, notifications and arguments never execute", async () => {
  const { env, calls } = fixture();
  for (const value of [
    [message("ping")], message("ping", {}, null), message("ping", {}, {}),
    { jsonrpc: "2.0", id: 1, result: {} },
    { jsonrpc: "2.0", method: "tools/call", params: { name: "conduct_submit", arguments: { packet: {} } } },
  ]) assert.equal((await worker.fetch(request(value), env)).status, 400);
  for (const value of [
    message("arbitrary/method"), invoke("arbitrary_tool"), invoke("conduct_capabilities", { url: "https://attacker.example" }),
    invoke("conduct_capabilities", { toString: "prototype" }), invoke("conduct_capabilities", null),
    invoke("conduct_claim", { lease: "lease", generation: 0 }), invoke("conduct_claim", { lease: "../escape", generation: 1 }),
    invoke("conduct_claim", { lease: "lease", generation: 1, principal: {} }),
  ]) assert.ok((await (await worker.fetch(request(value), env)).json()).error);
  assert.deepEqual(calls, []);
});

test("authenticated capabilities delegate the original bearer to the configured keeper", async () => {
  const { env, calls } = fixture();
  const payload = await (await worker.fetch(request(invoke("conduct_capabilities")), env)).json();
  assert.equal(payload.id, "correlation/1");
  assert.equal(payload.result.isError, false);
  assert.equal(payload.result.structuredContent.schema_version, "limen.conduct_capabilities.v1");
  assert.deepEqual(calls, [{ path: "/api/conduct/capabilities", method: "GET", authorization: `Bearer ${TOKEN}`, body: undefined }]);
  assert.equal(JSON.stringify(payload).includes(TOKEN), false);
});

test("deeply nested valid JSON fails with correlation before keeper admission", async () => {
  const { env, calls } = fixture();
  const body = '{"jsonrpc":"2.0","id":"nested/1","method":"tools/call","params":{"name":"conduct_submit","arguments":{"packet":'
    + '{"x":'.repeat(10000) + '{}' + '}'.repeat(10000) + '}}}';
  const response = await worker.fetch(request(null, { body }), env);
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { jsonrpc: "2.0", id: "nested/1", error: { code: -32602, message: "Invalid tool arguments" } });
  assert.deepEqual(calls, []);
});

test("canonical role enforcement rejects conductor claim and observer registration", async () => {
  for (const [roles, call] of [
    [["observer", "conductor"], invoke("conduct_claim", { lease: "lease/scope", generation: 3 })],
    [["observer"], invoke("conduct_register", { session: {} })],
  ]) {
    const { env, calls } = fixture(roles);
    const payload = await (await worker.fetch(request(call), env)).json();
    assert.equal(payload.result.isError, true);
    assert.deepEqual(payload.result.structuredContent, { code: "conduct_rejected", status: 403 });
    assert.equal(calls.length, 1);
  }
});

test("register crosses canonical schema and principal binding before creating session", async () => {
  const { env, calls } = fixture();
  const session = { session_id: "native-session", identity: { agent: "claude", surface: "fake", session_id: "native-session" },
    origin: "direct", human_protected: true };
  const payload = await (await worker.fetch(request(invoke("conduct_register", { session })), env)).json();
  assert.equal(payload.result.isError, false);
  const registered = payload.result.structuredContent;
  assert.equal(registered.identity.agent, "codex");
  assert.equal(registered.identity.surface, "direct");
  assert.equal(registered.human_protected, true);
  assert.deepEqual(calls[0].body, session);
});

test("canonical packet validation rejects malformed submission without synthetic admission", async () => {
  const { env } = fixture();
  const payload = await (await worker.fetch(request(invoke("conduct_submit", { packet: {} })), env)).json();
  assert.equal(payload.result.isError, true);
  assert.equal(payload.result.structuredContent.status, 422);
});

test("executor claim forwards exact generation and encoded lease, with no fallback", async () => {
  const { env, calls } = fixture();
  const payload = await (await worker.fetch(request(invoke("conduct_claim", { lease: "lease/scope", generation: 7 })), env)).json();
  assert.equal(payload.result.isError, true); // A nonexistent lease is never manufactured.
  assert.equal(payload.result.structuredContent.status, 404);
  assert.deepEqual(calls[0].body, { generation: 7 });
  assert.equal(calls[0].path, "/api/conduct/leases/lease%2Fscope/claim");
});

test("missing keeper and internal failures are bounded, confidential, and never success", async () => {
  const { env } = fixture();
  delete env.CONDUCT_KEEPER;
  let payload = await (await worker.fetch(request(invoke("conduct_capabilities")), env)).json();
  assert.deepEqual(payload.result.structuredContent, { code: "conduct_outcome_unobserved", status: 503 });
  env.CONDUCT_KEEPER = { idFromName: () => "keeper", get: () => ({ fetch: () => { throw Error(TOKEN); } }) };
  payload = await (await worker.fetch(request(invoke("conduct_capabilities")), env)).json();
  assert.deepEqual(payload.result.structuredContent, { code: "conduct_outcome_unobserved" });
  assert.equal(JSON.stringify(payload).includes(TOKEN), false);
  env.CONDUCT_KEEPER.get = () => ({ fetch: () => new Response(JSON.stringify({ detail: TOKEN }), { status: 500 }) });
  payload = await (await worker.fetch(request(invoke("conduct_capabilities")), env)).json();
  assert.equal(JSON.stringify(payload).includes(TOKEN), false);
  assert.deepEqual(payload.result.structuredContent, { code: "conduct_outcome_unobserved", status: 500 });
});

test("oversized and nonobject keeper responses fail without false success", async () => {
  const { env } = fixture();
  for (const raw of [JSON.stringify({ value: "x".repeat(4 * 1024 * 1024) }), "[]", "invalid"] ) {
    env.CONDUCT_KEEPER.get = () => ({ fetch: () => new Response(raw) });
    const payload = await (await worker.fetch(request(invoke("conduct_capabilities")), env)).json();
    assert.equal(payload.result.isError, true);
    assert.deepEqual(payload.result.structuredContent, { code: "conduct_outcome_unobserved" });
  }
});
