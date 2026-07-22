import {
  authorizeConductRequest,
  internalConductPrincipal,
} from "./auth.js";
import {
  ConductError,
  DurableConductStore,
  SerializedConductService,
} from "./keeper.js";
import {
  ConductProjectionError,
  commitTaskCompatibilityEvent,
} from "./projection.js";
import {
  ConductValidationError,
  validateExecutorAttempt,
  validateReceipt,
  validateSession,
  validateWorkPacket,
} from "./schemas.js";

const IDENTIFIER_RE = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$/;

function corsHeaders(env) {
  const origin = String(env.LIMEN_CORS_ORIGINS || "*").split(",")[0].trim() || "*";
  return {
    "access-control-allow-origin": origin,
    "access-control-allow-methods": "GET,POST,OPTIONS",
    "access-control-allow-headers": "authorization,content-type",
  };
}

function json(payload, status, env) {
  return new Response(JSON.stringify(payload, null, 2), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      ...corsHeaders(env),
    },
  });
}

function errorResponse(detail, status, env) {
  return json({ detail }, status, env);
}

function duration(env, name, fallback) {
  const parsed = Number(env[name]);
  return Number.isFinite(parsed) && parsed > 0 ? parsed * 1000 : fallback;
}

async function parseBody(request) {
  const length = Number(request.headers.get("content-length") || 0);
  if (Number.isFinite(length) && length > 1024 * 1024) {
    throw new ConductValidationError("conduct request body exceeds 1 MiB");
  }
  let value;
  try {
    value = await request.json();
  } catch {
    throw new ConductValidationError("invalid JSON body");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ConductValidationError("conduct request body must be an object");
  }
  return value;
}

function decodeIdentifier(value, field) {
  let decoded;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    throw new ConductValidationError(`${field} is not valid URL encoding`);
  }
  if (!IDENTIFIER_RE.test(decoded)) {
    throw new ConductValidationError(`${field} must be a bounded protocol identifier`);
  }
  return decoded;
}

function bodyIdentifier(body, field) {
  const value = body[field];
  if (typeof value !== "string" || !IDENTIFIER_RE.test(value)) {
    throw new ConductValidationError(`${field} must be a bounded protocol identifier`);
  }
  return value;
}

function bodyGeneration(body) {
  const value = body.generation;
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new ConductValidationError("generation must be a positive integer");
  }
  return value;
}

function requireRole(principal, ...roles) {
  if (!principal || !roles.some((role) => principal.roles.includes(role))) {
    throw new ConductError(`authenticated principal lacks required ${roles.join("/")} role`, 403);
  }
}

function capabilityToken(body) {
  if (typeof body.capability_token !== "string" || !body.capability_token || body.capability_token.length > 1024) {
    throw new ConductValidationError("capability_token must be a non-empty bounded string");
  }
  return body.capability_token;
}

function observedHeads(body) {
  const raw = body.observed_heads ?? {};
  if (!raw || typeof raw !== "object" || Array.isArray(raw) || Object.keys(raw).length > 1024) {
    throw new ConductValidationError("observed_heads must be a bounded object");
  }
  const heads = {};
  for (const [key, value] of Object.entries(raw)) {
    if (!key || key.length > 1024 || typeof value !== "string" || !value || value.length > 512) {
      throw new ConductValidationError("observed_heads keys and values must be bounded strings");
    }
    heads[key] = value;
  }
  return heads;
}

function executorAttempt(body) {
  if (body.attempt === undefined) return null;
  if (!body.attempt || typeof body.attempt !== "object" || Array.isArray(body.attempt)) {
    throw new ConductValidationError("attempt must be an object");
  }
  return validateExecutorAttempt(body.attempt);
}

export class ConductKeeperDurableObject {
  constructor(ctx, env) {
    this.ctx = ctx;
    this.env = env;
    this.service = new SerializedConductService(
      new DurableConductStore(ctx.storage),
      {
        projectTaskEvent: (event) => commitTaskCompatibilityEvent(env, event),
        sessionTtlMs: duration(env, "LIMEN_CONDUCT_SESSION_TTL_SECONDS", 5 * 60 * 1000),
        adoptionAfterMs: duration(env, "LIMEN_CONDUCT_ADOPTION_AFTER_SECONDS", 10 * 60 * 1000),
        leaseTtlMs: duration(env, "LIMEN_CONDUCT_LEASE_TTL_SECONDS", 15 * 60 * 1000),
        capabilitySecret: String(env.LIMEN_CONDUCT_CAPABILITY_SECRET || ""),
      },
    );
  }

  async fetch(request) {
    if (request.method === "OPTIONS") return new Response(null, { headers: corsHeaders(this.env) });
    const auth = await authorizeConductRequest(request, this.env);
    if (!auth.ok) return errorResponse(auth.detail, auth.status, this.env);
    try {
      return await this.route(request, auth.principal);
    } catch (err) {
      if (err instanceof ConductValidationError || err instanceof ConductError || err instanceof ConductProjectionError) {
        return errorResponse(err.message, err.status || 500, this.env);
      }
      return errorResponse(err instanceof Error ? err.message : "conduct keeper error", 500, this.env);
    }
  }

  async route(request, principal) {
    const path = new URL(request.url).pathname;
    if (path === "/api/conduct/capabilities" && request.method === "GET") {
      requireRole(principal, "observer");
      return json(await this.service.call("capabilities"), 200, this.env);
    }
    if (path === "/api/conduct/sessions" && request.method === "POST") {
      requireRole(principal, "conductor", "executor");
      const body = await parseBody(request);
      return json(await this.service.call("register", {
        session: validateSession(body),
        principal,
      }), 200, this.env);
    }
    if (path === "/api/conduct/runs" && request.method === "POST") {
      requireRole(principal, "conductor", "compatibility");
      const body = await parseBody(request);
      return json(await this.service.call("submit", {
        packet: await validateWorkPacket(body),
        principal,
      }), 200, this.env);
    }
    if (path === "/api/conduct/graphs" && request.method === "POST") {
      requireRole(principal, "conductor");
      const body = await parseBody(request);
      if (!Array.isArray(body.packets) || !body.packets.length || body.packets.length > 10000) {
        throw new ConductValidationError("packets must be a bounded non-empty array");
      }
      const packets = [];
      for (const packet of body.packets) packets.push(await validateWorkPacket(packet));
      return json(await this.service.call("submit_graph", { packets, principal }), 200, this.env);
    }

    let match = path.match(/^\/api\/conduct\/runs\/([^/]+)\/children$/);
    if (match && request.method === "POST") {
      requireRole(principal, "conductor");
      const parentRunId = decodeIdentifier(match[1], "parent_run_id");
      const body = await parseBody(request);
      return json(await this.service.call("split", {
        parent_run_id: parentRunId,
        packet: await validateWorkPacket(body),
        principal,
      }), 200, this.env);
    }
    match = path.match(/^\/api\/conduct\/runs\/([^/]+)\/graph$/);
    if (match && request.method === "GET") {
      requireRole(principal, "observer");
      return json(await this.service.call("graph", {
        run_id: decodeIdentifier(match[1], "root_run_id"),
      }), 200, this.env);
    }
    match = path.match(/^\/api\/conduct\/leases\/([^/]+)\/claim$/);
    if (match && request.method === "POST") {
      requireRole(principal, "executor", "compatibility");
      const body = await parseBody(request);
      return json(await this.service.call("claim", {
        lease_id: decodeIdentifier(match[1], "lease_id"),
        generation: bodyGeneration(body),
        principal,
      }), 200, this.env);
    }
    match = path.match(/^\/api\/conduct\/leases\/([^/]+)\/heartbeat$/);
    if (match && request.method === "POST") {
      requireRole(principal, "executor", "compatibility");
      const body = await parseBody(request);
      return json(await this.service.call("heartbeat", {
        lease_id: decodeIdentifier(match[1], "lease_id"),
        capability_token: capabilityToken(body),
        generation: bodyGeneration(body),
        principal,
        observed_heads: observedHeads(body),
        attempt: executorAttempt(body),
      }), 200, this.env);
    }
    match = path.match(/^\/api\/conduct\/leases\/([^/]+)\/receipt$/);
    if (match && request.method === "POST") {
      requireRole(principal, "executor", "compatibility");
      const body = await parseBody(request);
      if (!body.receipt || typeof body.receipt !== "object" || Array.isArray(body.receipt)) {
        throw new ConductValidationError("receipt must be an object");
      }
      return json(await this.service.call("report", {
        lease_id: decodeIdentifier(match[1], "lease_id"),
        capability_token: capabilityToken(body),
        generation: bodyGeneration(body),
        principal,
        receipt: validateReceipt(body.receipt),
      }), 200, this.env);
    }
    match = path.match(/^\/api\/conduct\/runs\/([^/]+)\/harvest$/);
    if (match && request.method === "GET") {
      requireRole(principal, "observer");
      return json(await this.service.call("harvest", {
        run_id: decodeIdentifier(match[1], "root_run_id"),
      }), 200, this.env);
    }
    match = path.match(/^\/api\/conduct\/runs\/([^/]+)\/(adopt|cancel|request-stop)$/);
    if (match && request.method === "POST") {
      requireRole(principal, "conductor");
      const body = await parseBody(request);
      const operation = {
        adopt: "adopt",
        cancel: "cancel",
        "request-stop": "request_stop",
      }[match[2]];
      return json(await this.service.call(operation, {
        run_id: decodeIdentifier(match[1], "run_id"),
        session_id: bodyIdentifier(body, "session_id"),
        principal,
      }), 200, this.env);
    }
    return errorResponse("not found", 404, this.env);
  }
}

export async function forwardConductRequest(request, env) {
  const auth = await authorizeConductRequest(request, env);
  if (!auth.ok) return errorResponse(auth.detail, auth.status, env);
  if (!env.CONDUCT_KEEPER) {
    return errorResponse("conduct keeper binding is not configured", 503, env);
  }
  const id = env.CONDUCT_KEEPER.idFromName(
    String(env.LIMEN_CONDUCT_KEEPER_NAME || "tabularius-conduct-v1"),
  );
  return env.CONDUCT_KEEPER.get(id).fetch(request);
}

async function internalConductRequest(env, path, payload) {
  if (!env.CONDUCT_KEEPER) {
    throw new ConductError("conduct keeper binding is not configured", 503);
  }
  let token;
  try {
    token = internalConductPrincipal(env).bearer;
  } catch (error) {
    throw new ConductError(
      error instanceof Error ? error.message : "conduct compatibility principal is not configured",
      503,
    );
  }
  const id = env.CONDUCT_KEEPER.idFromName(
    String(env.LIMEN_CONDUCT_KEEPER_NAME || "tabularius-conduct-v1"),
  );
  const response = await env.CONDUCT_KEEPER.get(id).fetch(new Request(
    `https://limen.internal${path}`,
    {
      method: "POST",
      headers: {
        authorization: `Bearer ${token}`,
        "content-type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  ));
  const body = await response.json();
  if (!response.ok) {
    throw new ConductError(
      typeof body?.detail === "string" ? body.detail : "conduct keeper request failed",
      response.status,
    );
  }
  return body;
}

export async function forwardCompatibilityPacket(env, session, packet) {
  await internalConductRequest(env, "/api/conduct/sessions", session);
  return internalConductRequest(env, "/api/conduct/runs", packet);
}
