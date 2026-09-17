// Optional OAuth resource boundary for /mcp only. The issuer owns login, consent,
// refresh and client registration; existing conduct principals still own authority.
import { createRemoteJWKSet, customFetch, jwtVerify } from "jose";
import { authorizeConductRequest, configuredConductPrincipals } from "./auth.js";

const CONFIG = "LIMEN_CONDUCT_MCP_OAUTH";
const METADATA_PATH = "/.well-known/oauth-protected-resource/mcp";
const MAX_JWKS_BYTES = 128 * 1024;
const ALGORITHMS = ["RS256", "ES256"];
const resolvers = new Map();
class OAuthKeysUnavailable extends Error {}

function object(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
function text(value, maximum = 1024) { return typeof value === "string" && value.length > 0 && value.length <= maximum; }
function httpsUrl(value) {
  if (!text(value, 2048)) throw new Error("invalid URL");
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash) throw new Error("invalid URL");
  return url;
}

export function configuredMcpOAuth(env) {
  const raw = String(env[CONFIG] || "").trim();
  if (!raw) return null;
  const config = JSON.parse(raw);
  if (!object(config) || config.schema_version !== "limen.conduct_mcp_oauth.v1"
      || Object.keys(config).some(key => !["schema_version", "resource", "issuer", "jwks_uri", "scopes", "client_id_claim", "bindings"].includes(key))) {
    throw new Error("invalid OAuth configuration");
  }
  const resource = httpsUrl(config.resource);
  httpsUrl(config.issuer);
  httpsUrl(config.jwks_uri);
  if (resource.pathname !== "/mcp" || resource.href !== config.resource
      || !["client_id", "azp"].includes(config.client_id_claim)
      || !Array.isArray(config.scopes) || !config.scopes.length || config.scopes.length > 16
      || config.scopes.some(scope => !text(scope, 128) || !/^[\x21\x23-\x5B\x5D-\x7E]+$/.test(scope))
      || new Set(config.scopes).size !== config.scopes.length
      || !Array.isArray(config.bindings) || !config.bindings.length || config.bindings.length > 128) {
    throw new Error("invalid OAuth configuration");
  }
  const principals = configuredConductPrincipals(env);
  const seen = new Set();
  const bindings = config.bindings.map(binding => {
    if (!object(binding) || Object.keys(binding).length !== 3
        || !text(binding.subject) || !text(binding.client_id) || !text(binding.principal_id, 256)) {
      throw new Error("invalid OAuth binding");
    }
    const entry = principals.find(item => item.principal.principal_id === binding.principal_id);
    // Never expose compatibility-owner or collector authority through a login.
    if (!entry || entry.principal.roles.some(role => !["observer", "conductor", "executor"].includes(role))) {
      throw new Error("invalid OAuth principal");
    }
    const key = JSON.stringify([binding.subject, binding.client_id]);
    if (seen.has(key)) throw new Error("duplicate OAuth binding");
    seen.add(key);
    return { ...binding, entry };
  });
  return { ...config, bindings, metadataUrl: `${resource.origin}${METADATA_PATH}` };
}

function json(body, status, headers = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", "cache-control": "no-store", ...headers } });
}

export function mcpOAuthMetadata(request, env) {
  let config;
  try { config = configuredMcpOAuth(env); }
  catch { return json({ error: "OAuth resource configuration unavailable" }, 503); }
  if (!config || new URL(request.url).origin !== new URL(config.resource).origin) return json({ error: "Not found" }, 404);
  if (request.method !== "GET") return json({ error: "Only GET is supported" }, 405, { allow: "GET" });
  return json({ resource: config.resource, authorization_servers: [config.issuer],
    scopes_supported: config.scopes, bearer_methods_supported: ["header"] }, 200);
}

export function isMcpOAuthMetadataPath(path) {
  return path === METADATA_PATH || path === "/.well-known/oauth-protected-resource";
}

function challenge(config, error) {
  return `Bearer realm="limen-conduct", resource_metadata="${config.metadataUrl}", scope="${config.scopes.join(" ")}"`
    + (error ? `, error="${error}"` : "");
}

async function boundedJwksFetch(url, options) {
  let reader;
  let abort;
  const aborted = new Promise((resolve, reject) => {
    abort = () => {
      reader?.cancel().catch(() => {});
      reject(new OAuthKeysUnavailable());
    };
    options.signal.addEventListener("abort", abort, { once: true });
    if (options.signal.aborted) abort();
  });
  const read = async () => {
    // Only the configured URL reaches this function; JWT jku/x5u are never used.
    const response = await fetch(url, { ...options, redirect: "error" });
    if (response.status !== 200) { await response.body?.cancel(); throw new Error("JWKS unavailable"); }
    const length = response.headers.get("content-length");
    if (length && (!/^\d+$/.test(length) || Number(length) > MAX_JWKS_BYTES)) {
      await response.body?.cancel(); throw new Error("JWKS too large");
    }
    reader = response.body?.getReader();
    if (!reader) throw new Error("JWKS unavailable");
    const chunks = [];
    let size = 0;
    try {
      while (true) {
        options.signal.throwIfAborted();
        const { value, done } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_JWKS_BYTES) { await reader.cancel(); throw new Error("JWKS too large"); }
        chunks.push(value);
      }
    } finally { reader.releaseLock(); }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    return new Response(bytes, { headers: { "content-type": "application/json" } });
  };
  try { return await Promise.race([read(), aborted]); }
  finally { options.signal.removeEventListener("abort", abort); }
}

function keyResolver(config) {
  const key = JSON.stringify([config.issuer, config.jwks_uri]);
  if (!resolvers.has(key)) {
    if (resolvers.size >= 16) resolvers.delete(resolvers.keys().next().value);
    const remote = createRemoteJWKSet(new URL(config.jwks_uri), {
      timeoutDuration: 5000, cooldownDuration: 30000, cacheMaxAge: 300000,
      [customFetch]: boundedJwksFetch,
    });
    resolvers.set(key, async (...args) => {
      try { return await remote(...args); }
      catch (error) {
        if (error.code === "ERR_JWKS_NO_MATCHING_KEY") throw error;
        throw new OAuthKeysUnavailable();
      }
    });
  }
  return resolvers.get(key);
}

export async function authorizeMcpRequest(request, env) {
  const legacy = await authorizeConductRequest(request, env);
  // An OAuth outage or bad optional configuration must not disable existing lanes.
  if (legacy.ok) return { ...legacy, request };
  if (legacy.status !== 401) return legacy;
  let config;
  try { config = configuredMcpOAuth(env); }
  catch { return { ok: false, status: 503 }; }
  if (!config) return legacy;
  if (request.url !== config.resource) return { ok: false, status: 401 };
  const match = (request.headers.get("authorization") || "").match(/^Bearer\s+([^\s]+)$/i);
  if (!match || match[1].length > 16384) return { ok: false, status: 401, challenge: challenge(config) };
  let payload;
  try {
    ({ payload } = await jwtVerify(match[1], keyResolver(config), {
      issuer: config.issuer, audience: config.resource, algorithms: ALGORITHMS,
      requiredClaims: ["exp", "sub", "iss", "aud"], typ: "at+jwt",
    }));
  } catch (error) {
    if (error instanceof OAuthKeysUnavailable) return { ok: false, status: 503 };
    return { ok: false, status: 401, challenge: challenge(config, "invalid_token") };
  }
  const clientId = payload[config.client_id_claim];
  const binding = config.bindings.find(item => item.subject === payload.sub && item.client_id === clientId);
  if (!binding) return { ok: false, status: 401, challenge: challenge(config, "invalid_token") };
  const scopes = typeof payload.scope === "string" ? payload.scope.split(" ") : [];
  if (!config.scopes.every(scope => scopes.includes(scope))) {
    return { ok: false, status: 403, challenge: challenge(config, "insufficient_scope") };
  }
  // Convert only to the exact provisioned native principal's credential. This
  // remains in memory, is reauthenticated by the existing router and keeper,
  // and is never returned to the client. OAuth cannot authenticate /api/conduct.
  const headers = new Headers(request.headers);
  headers.set("authorization", `Bearer ${binding.entry.bearer}`);
  return { ok: true, principal: binding.entry.principal, request: new Request(request, { headers }), scopes: config.scopes };
}
