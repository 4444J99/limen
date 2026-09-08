import assert from "node:assert/strict";
import test from "node:test";

import worker from "../src/index.js";

function assertBaseline(response) {
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  assert.equal(response.headers.get("referrer-policy"), "strict-origin-when-cross-origin");
  assert.equal(response.headers.get("x-xss-protection"), "0");
  for (const header of ["x-frame-options", "permissions-policy", "content-security-policy"]) {
    assert.equal(response.headers.has(header), false);
  }
}

test("Worker baseline covers normal, rejected, and preflight responses without changing CORS", async () => {
  const env = { LIMEN_CORS_ORIGINS: "https://dashboard.example" };
  for (const [path, method, status] of [
    ["/health", "GET", 200],
    ["/missing-route", "GET", 404],
    ["/api/tasks", "OPTIONS", 200],
  ]) {
    const response = await worker.fetch(new Request(`https://limen.example${path}`, { method }), env);
    assert.equal(response.status, status);
    assertBaseline(response);
    assert.equal(response.headers.get("access-control-allow-origin"), env.LIMEN_CORS_ORIGINS);
    assert.equal(response.headers.get("access-control-allow-methods"), "GET,POST,PATCH,OPTIONS");
    assert.equal(response.headers.get("access-control-allow-headers"), "authorization,content-type");
    if (method === "OPTIONS") assert.equal(await response.text(), "");
    else if (status === 200) assert.equal((await response.json()).status, "ok");
    else assert.deepEqual(await response.json(), { detail: "not found" });
  }
});

function keeperEnv(fetch) {
  const bearer = "test-header-principal-at-least-24-characters";
  return {
    bearer,
    LIMEN_CONDUCT_PRINCIPAL_REGISTRY: JSON.stringify({
      schema_version: "limen.conduct_principal_registry.v1",
      principals: [{ principal_id: "header-test", agent: "codex", surface: "test", roles: ["observer"], bearer }],
    }),
    CONDUCT_KEEPER: { idFromName: (name) => name, get: () => ({ fetch }) },
  };
}

test("Worker baseline covers forwarded immutable responses and preserves redirect status/location", async () => {
  const env = keeperEnv(() => Response.redirect("https://limen.example/health", 307));
  const response = await worker.fetch(new Request("https://limen.example/api/conduct/capabilities", {
    headers: { authorization: `Bearer ${env.bearer}` },
  }), env);
  assert.equal(response.status, 307);
  assert.equal(response.headers.get("location"), "https://limen.example/health");
  assertBaseline(response);
});

test("Worker baseline preserves forwarded response body, status, cache and CORS headers", async () => {
  const env = keeperEnv(() => new Response("keeper response", {
    status: 202,
    headers: { "cache-control": "no-store", "access-control-allow-origin": "https://owner.example" },
  }));
  const response = await worker.fetch(new Request("https://limen.example/api/conduct/capabilities", {
    headers: { authorization: `Bearer ${env.bearer}` },
  }), env);
  assert.equal(response.status, 202);
  assert.equal(await response.text(), "keeper response");
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("access-control-allow-origin"), "https://owner.example");
  assertBaseline(response);
});

for (const [name, thrown, status, payload] of [
  ["exception", new Error("keeper unavailable"), 500, { detail: "keeper unavailable" }],
  ["Response", new Response("missing task", { status: 404 }), 404, "missing task"],
]) {
  test(`Worker baseline covers thrown ${name}`, async () => {
    const env = keeperEnv(() => { throw thrown; });
    const response = await worker.fetch(new Request("https://limen.example/api/conduct/capabilities", {
      headers: { authorization: `Bearer ${env.bearer}` },
    }), env);
    assert.equal(response.status, status);
    assertBaseline(response);
    assert.deepEqual(typeof payload === "string" ? await response.text() : await response.json(), payload);
  });
}
