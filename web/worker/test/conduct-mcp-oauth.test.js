import assert from "node:assert/strict";
import test from "node:test";
import { exportJWK, generateKeyPair, SignJWT } from "jose";
import worker from "../src/index.js";
import { ConductKeeperDurableObject } from "../src/conduct/durable-object.js";
import { MemoryConductStore, SerializedConductService } from "../src/conduct/keeper.js";

const TOKEN = "oauth-fixture-only-existing-principal-bearer";
const RESOURCE = "https://limen.example/mcp";
const SUBJECT = "fixture-user-only";
const CLIENT = "fixture-chat-client-only";
const keys = await generateKeyPair("RS256");
const wrongKeys = await generateKeyPair("RS256");
const jwk = { ...await exportJWK(keys.publicKey), kid: "fixture-rsa", alg: "RS256", use: "sig" };
let sequence = 0;

function fixture() {
  const config = {
    schema_version: "limen.conduct_mcp_oauth.v1", resource: RESOURCE,
    issuer: `https://issuer-${++sequence}.example`, jwks_uri: `https://issuer-${sequence}.example/jwks`,
    scopes: ["limen:conduct"], client_id_claim: "client_id",
    bindings: [{ subject: SUBJECT, client_id: CLIENT, principal_id: "chat-fixture" }],
  };
  const env = {
    LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
      schema_version: "limen.conduct_principal_registry.v1",
      principals: [{ principal_id: "chat-fixture", agent: "chatgpt", surface: "chat",
        roles: ["observer", "conductor"], bearer: TOKEN }],
    }),
    LIMEN_CONDUCT_MCP_OAUTH: JSON.stringify(config),
  };
  const keeper = Object.create(ConductKeeperDurableObject.prototype);
  keeper.env = env;
  keeper.service = new SerializedConductService(new MemoryConductStore(), { capabilitySecret: "oauth-test-only-capability-secret-24-characters" });
  const calls = [];
  const principals = [];
  const route = keeper.route.bind(keeper);
  keeper.route = (request, principal) => { principals.push(principal); return route(request, principal); };
  env.CONDUCT_KEEPER = {
    idFromName(name) { return name; },
    get() { return { fetch: async request => {
      calls.push({ path: new URL(request.url).pathname, authorization: request.headers.get("authorization") });
      return keeper.fetch(request);
    } }; },
  };
  return { env, config, calls, keeper, principals };
}

async function token(config, changes = {}, key = keys.privateKey, header = {}) {
  const payload = { iss: config.issuer, sub: SUBJECT, aud: RESOURCE, client_id: CLIENT,
    exp: Math.floor(Date.now() / 1000) + 300, scope: "limen:conduct", ...changes };
  for (const [name, value] of Object.entries(payload)) if (value === undefined) delete payload[name];
  return new SignJWT(payload).setProtectedHeader({ alg: "RS256", kid: "fixture-rsa", typ: "at+jwt", ...header }).sign(key);
}

function request(bearer, message = { jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "conduct_capabilities", arguments: {} } }, url = RESOURCE) {
  return new Request(url, { method: "POST", headers: {
    ...(bearer ? { authorization: `Bearer ${bearer}` } : {}),
    accept: "application/json, text/event-stream", "content-type": "application/json",
  }, body: JSON.stringify(message) });
}

function mockJwks(t, config, implementation) {
  const calls = [];
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls.push({ url, options });
    assert.equal(url, config.jwks_uri);
    assert.equal(options.redirect, "error");
    assert.ok(options.signal instanceof AbortSignal);
    return implementation ? implementation(url, options) : Response.json({ keys: [jwk] });
  });
  return calls;
}

test("OAuth uses the exact native principal through the unchanged keeper; tokens stay private", async t => {
  const { env, config, calls, principals } = fixture();
  const fetches = mockJwks(t, config);
  const bearer = await token(config);
  const response = await worker.fetch(request(bearer), env);
  assert.equal(response.status, 200);
  const body = await response.json();
  assert.equal(body.result.isError, false);
  assert.deepEqual(principals[0], {
    schema_version: "limen.conduct_principal.v1", principal_id: "chat-fixture", agent: "chatgpt",
    surface: "chat", roles: ["conductor", "observer"],
  });
  assert.deepEqual(calls, [{ path: "/api/conduct/capabilities", authorization: `Bearer ${TOKEN}` }]);
  assert.equal(JSON.stringify(body).includes(TOKEN), false);
  assert.equal(JSON.stringify(body).includes(bearer), false);
  const listed = await (await worker.fetch(request(bearer, { jsonrpc: "2.0", id: 2, method: "tools/list" }), env)).json();
  assert.equal(listed.result.tools.length, 12);
  assert.ok(listed.result.tools.every(tool => tool.securitySchemes[0].type === "oauth2"));
  assert.equal(fetches.length, 1, "JWKS is cached across calls");
});

test("resource metadata is public, minimal, canonical, and never derived from a hostile host", async () => {
  const { env, config } = fixture();
  for (const path of ["/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"]) {
    const response = await worker.fetch(new Request(`https://limen.example${path}`), env);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { resource: RESOURCE, authorization_servers: [config.issuer],
      scopes_supported: config.scopes, bearer_methods_supported: ["header"] });
    assert.equal((await worker.fetch(new Request(`https://hostile.example${path}`), env)).status, 404);
    assert.equal((await worker.fetch(new Request(`https://limen.example${path}`, { method: "POST" }), env)).status, 405);
  }
  const rejected = await worker.fetch(request(null), env);
  assert.equal(rejected.status, 401);
  assert.match(rejected.headers.get("www-authenticate"), /resource_metadata="https:\/\/limen\.example\/.well-known\/oauth-protected-resource\/mcp"/);
  assert.equal((await rejected.text()).includes(SUBJECT), false);
});

test("optional invalid OAuth configuration cannot disable existing bearer clients", async () => {
  const { env, config } = fixture();
  for (const raw of [undefined, "{invalid", JSON.stringify({ ...config, resource: "http://limen.example/mcp" })]) {
    env.LIMEN_CONDUCT_MCP_OAUTH = raw;
    assert.equal((await worker.fetch(request(TOKEN), env)).status, 200);
    assert.equal((await worker.fetch(request("unrecognized"), env)).status, raw ? 503 : 401);
    assert.equal((await worker.fetch(new Request("https://limen.example/.well-known/oauth-protected-resource/mcp"), env)).status, raw ? 503 : 404);
  }
});

test("OAuth rejects invalid principal mappings, ambiguous bindings, and unsafe discovery config", async () => {
  const { env, config, calls } = fixture();
  const badConfigs = [
    { ...config, bindings: [{ ...config.bindings[0], principal_id: "absent" }] },
    { ...config, bindings: [config.bindings[0], config.bindings[0]] },
    { ...config, scopes: [] }, { ...config, scopes: ['bad"scope'] },
    { ...config, client_id_claim: "sub" }, { ...config, jwks_uri: "http://issuer.example/jwks" },
    { ...config, issuer: "https://user:password@issuer.example" },
    { ...config, resource: "https://limen.example/mcp?alternate" },
    { ...config, unknown: true },
  ];
  for (const bad of badConfigs) {
    env.LIMEN_CONDUCT_MCP_OAUTH = JSON.stringify(bad);
    assert.equal((await worker.fetch(request("invalid"), env)).status, 503);
  }
  env.LIMEN_CONDUCT_MCP_OAUTH = JSON.stringify(config);
  const registry = JSON.parse(env.LIMEN_CONDUCT_PRINCIPAL_REGISTRY);
  registry.principals[0].roles = ["compatibility"];
  env.LIMEN_CONDUCT_PRINCIPAL_REGISTRY = JSON.stringify(registry);
  assert.equal((await worker.fetch(request("invalid"), env)).status, 503);
  assert.deepEqual(calls, []);
});

test("issuer, resource, expiry, subject, client and scopes all bind OAuth authority", async t => {
  const { env, config, calls } = fixture();
  mockJwks(t, config);
  const invalid = [
    [{ iss: "https://other.example" }, 401], [{ aud: "https://another.example/mcp" }, 401],
    [{ exp: Math.floor(Date.now() / 1000) - 1 }, 401], [{ nbf: Math.floor(Date.now() / 1000) + 60 }, 401],
    [{ exp: undefined }, 401], [{ sub: "another-user" }, 401], [{ sub: undefined }, 401],
    [{ client_id: "another-client" }, 401], [{ client_id: undefined }, 401],
    [{ client_id: [CLIENT] }, 401], [{ client_id: { value: CLIENT } }, 401],
    [{ scope: undefined }, 403], [{ scope: "limen:conduct-extra" }, 403], [{ scope: ["limen:conduct"] }, 403],
  ];
  for (const [claims, status] of invalid) {
    const response = await worker.fetch(request(await token(config, claims)), env);
    assert.equal(response.status, status, JSON.stringify(claims));
    assert.match(response.headers.get("www-authenticate"), /resource_metadata=/);
  }
  assert.equal((await worker.fetch(request(await token(config, {}, wrongKeys.privateKey)), env)).status, 401);
  assert.equal((await worker.fetch(request("x".repeat(16385)), env)).status, 401);
  assert.deepEqual(calls, []);
});

test("configured azp binding works without accepting a conflicting client_id claim as authority", async t => {
  const { env, config } = fixture();
  config.client_id_claim = "azp";
  env.LIMEN_CONDUCT_MCP_OAUTH = JSON.stringify(config);
  mockJwks(t, config);
  assert.equal((await worker.fetch(request(await token(config, { azp: CLIENT, client_id: undefined })), env)).status, 200);
  assert.equal((await worker.fetch(request(await token(config, { azp: "wrong", client_id: CLIENT })), env)).status, 401);
});

test("OAuth tokens cannot authenticate the direct conduct API or another MCP origin", async t => {
  const { env, config, calls } = fixture();
  const fetches = mockJwks(t, config);
  const bearer = await token(config);
  for (const url of ["https://limen.example/api/conduct/capabilities", "https://wrong.example/mcp", `${RESOURCE}?alternate`]) {
    assert.equal((await worker.fetch(request(bearer, undefined, url), env)).status, 401);
  }
  assert.deepEqual(calls, []);
  assert.deepEqual(fetches, []);
});

test("OAuth preserves canonical role rejection instead of widening the bound principal", async t => {
  const { env, config, calls } = fixture();
  mockJwks(t, config);
  const response = await worker.fetch(request(await token(config), { jsonrpc: "2.0", id: 4, method: "tools/call",
    params: { name: "conduct_claim", arguments: { lease: "fixture-lease", generation: 1 } } }), env);
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.result.isError, true);
  assert.deepEqual(payload.result.structuredContent, { code: "conduct_rejected", status: 403 });
  assert.equal(calls.length, 1);
});

test("JWKS fetch is bounded, has no redirects, and never follows a token-provided key URL", async t => {
  for (const implementation of [
    () => new Response(null, { status: 302, headers: { location: "https://attacker.example/jwks" } }),
    () => new Response("{}", { headers: { "content-length": "131073" } }),
    () => new Response(" ".repeat(131073)),
    () => new Response("not-json"),
    () => { throw new Error("network unavailable"); },
  ]) {
    const { env, config, calls } = fixture();
    const fetches = mockJwks(t, config, implementation);
    const response = await worker.fetch(request(await token(config, {}, keys.privateKey, { jku: "https://attacker.example/jwks" })), env);
    assert.equal(response.status, 503);
    assert.equal(fetches.length, 1);
    assert.deepEqual(calls, []);
    t.mock.restoreAll();
  }
});

test("JWKS response body deadline cancels a stalled stream and returns unavailability", async t => {
  const { env, config, calls } = fixture();
  let cancelled = false;
  t.mock.method(AbortSignal, "timeout", milliseconds => {
    assert.equal(milliseconds, 5000);
    const controller = new AbortController();
    setTimeout(() => controller.abort(), 10);
    return controller.signal;
  });
  mockJwks(t, config, () => new Response(new ReadableStream({ cancel() { cancelled = true; } })));
  const response = await worker.fetch(request(await token(config)), env);
  assert.equal(response.status, 503);
  assert.equal(cancelled, true);
  assert.deepEqual(calls, []);
});

test("JWT token-class separation rejects ID tokens while accepting only access tokens", async t => {
  const { env, config, calls } = fixture();
  mockJwks(t, config);
  for (const typ of ["JWT", "id+jwt", undefined]) {
    assert.equal((await worker.fetch(request(await token(config, {}, keys.privateKey, { typ })), env)).status, 401);
  }
  assert.deepEqual(calls, []);
});

test("unsecured or symmetric JWTs cannot use the configured asymmetric trust root", async t => {
  const { env, config, calls } = fixture();
  const fetches = mockJwks(t, config);
  const payload = { iss: config.issuer, aud: RESOURCE, sub: SUBJECT, client_id: CLIENT, scope: "limen:conduct",
    exp: Math.floor(Date.now() / 1000) + 300 };
  const symmetric = await new SignJWT(payload).setProtectedHeader({ alg: "HS256" }).sign(new TextEncoder().encode("test-only-key-32-characters-long!!"));
  const unsecured = `${Buffer.from(JSON.stringify({ alg: "none" })).toString("base64url")}.${Buffer.from(JSON.stringify(payload)).toString("base64url")}.`;
  for (const bearer of [symmetric, unsecured]) assert.equal((await worker.fetch(request(bearer), env)).status, 401);
  assert.deepEqual(calls, []);
  assert.deepEqual(fetches, []);
});
