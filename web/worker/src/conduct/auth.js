const encoder = new TextEncoder();

function configuredConductTokens(env) {
  const singular = String(env.LIMEN_CONDUCT_TOKEN || "").trim();
  const rotated = String(env.LIMEN_CONDUCT_TOKENS || "")
    .split(",")
    .map((token) => token.trim())
    .filter(Boolean);
  return [...new Set([singular, ...rotated].filter(Boolean))];
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
  const tokens = configuredConductTokens(env);
  if (!tokens.length) {
    return {
      ok: false,
      status: 503,
      detail: "conduct authentication is not configured",
    };
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
  const configured = await Promise.all(tokens.map(digest));
  if (!configured.some((candidate) => equalBytes(presented, candidate))) {
    return {
      ok: false,
      status: 401,
      detail: "missing or invalid Authorization header",
    };
  }
  return { ok: true };
}

export { configuredConductTokens };
