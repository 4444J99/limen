const encoder = new TextEncoder();
const IDENTIFIER_RE = /^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$/;
const ROLES = new Set(["observer", "conductor", "executor", "compatibility"]);

function invalidRegistry(detail = "conduct principal registry is invalid") {
  return { ok: false, status: 503, detail };
}

export function configuredConductPrincipals(env) {
  const raw = String(env.LIMEN_CONDUCT_PRINCIPAL_REGISTRY || "").trim();
  if (!raw) throw new Error("conduct principal registry is not configured");
  let document;
  try {
    document = JSON.parse(raw);
  } catch {
    throw new Error("conduct principal registry is invalid JSON");
  }
  if (
    document?.schema_version !== "limen.conduct_principal_registry.v1"
    || !Array.isArray(document.principals)
    || !document.principals.length
  ) {
    throw new Error("conduct principal registry must contain principals");
  }
  const principalIds = new Set();
  const bearers = new Set();
  return document.principals.map((entry) => {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
      throw new Error("conduct principal registry entries must be objects");
    }
    const {
      principal_id: principalId,
      agent,
      surface,
      roles,
      bearer,
    } = entry;
    if (
      !IDENTIFIER_RE.test(principalId || "")
      || !IDENTIFIER_RE.test(agent || "")
      || !IDENTIFIER_RE.test(surface || "")
      || !Array.isArray(roles)
      || !roles.length
      || roles.some((role) => !ROLES.has(role))
      || typeof bearer !== "string"
      || bearer.length < 24
      || bearer.length > 4096
    ) {
      throw new Error("conduct principal registry entry is invalid");
    }
    if (principalIds.has(principalId) || bearers.has(bearer)) {
      throw new Error("conduct principal registry contains a duplicate");
    }
    principalIds.add(principalId);
    bearers.add(bearer);
    return {
      principal: {
        schema_version: "limen.conduct_principal.v1",
        principal_id: principalId,
        agent,
        surface,
        roles: [...new Set(roles)].sort(),
      },
      bearer,
    };
  });
}

async function digest(value) {
  const raw = await crypto.subtle.digest("SHA-256", encoder.encode(value));
  return new Uint8Array(raw);
}

function equalBytes(left, right) {
  if (left.length !== right.length) return false;
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) mismatch |= left[index] ^ right[index];
  return mismatch === 0;
}

export async function authorizeConductRequest(request, env) {
  let entries;
  try {
    entries = configuredConductPrincipals(env);
  } catch (error) {
    return invalidRegistry(error instanceof Error ? error.message : undefined);
  }
  const authorization = request.headers.get("authorization") || "";
  const match = authorization.match(/^Bearer\s+(.+)$/i);
  if (!match) {
    return {
      ok: false,
      status: 401,
      detail: "missing or invalid Authorization header",
    };
  }
  const presented = await digest(match[1]);
  for (const entry of entries) {
    if (equalBytes(presented, await digest(entry.bearer))) {
      return { ok: true, principal: entry.principal };
    }
  }
  return {
    ok: false,
    status: 401,
    detail: "missing or invalid Authorization header",
  };
}

export function internalConductPrincipal(env) {
  const entry = configuredConductPrincipals(env)
    .find(({ principal }) => principal.roles.includes("compatibility"));
  if (!entry) throw new Error("conduct compatibility principal is not configured");
  return entry;
}
