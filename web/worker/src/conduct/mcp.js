// Stateless Streamable HTTP transport; the authenticated conduct HTTP router remains
// the only admission authority. No MCP session, credential cache, or task store is created.
import { authorizeMcpRequest } from "./mcp-oauth.js";
import { forwardConductRequest } from "./durable-object.js";

const VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26"];
const MAX_INPUT = 1024 * 1024;
const MAX_OUTPUT = 4 * 1024 * 1024;
const IDENTIFIER = { type: "string", pattern: "^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$" };
const GENERATION = { type: "integer", minimum: 1, maximum: Number.MAX_SAFE_INTEGER };
const OBJECT = { type: "object" };
const CAPABILITY = { type: "string", minLength: 1, maxLength: 1024 };
const object = (properties = {}, required = Object.keys(properties)) => ({
  type: "object", properties, required, additionalProperties: false,
});
const encoded = (value) => encodeURIComponent(value);

function tool(name, description, properties, route, { required, readOnly = false } = {}) {
  return {
    definition: {
      name, description, inputSchema: object(properties, required),
      annotations: { readOnlyHint: readOnly, destructiveHint: !readOnly, openWorldHint: false },
    },
    route,
  };
}

const TOOLS = new Map([
  tool("conduct_capabilities", "Read live keeper capabilities and authenticated lane availability.", {},
    () => ["GET", "/api/conduct/capabilities"], { readOnly: true }),
  tool("conduct_register", "Register a native session; the keeper binds identity to the authenticated principal.", { session: OBJECT },
    ({ session }) => ["POST", "/api/conduct/sessions", session]),
  tool("conduct_submit", "Submit one WorkPacketV1 for canonical admission, claims, and budget reservation.", { packet: OBJECT },
    ({ packet }) => ["POST", "/api/conduct/runs", packet]),
  tool("conduct_split", "Submit a bounded child; the keeper enforces parent authority and lineage.", { parent_run: IDENTIFIER, packet: OBJECT },
    ({ parent_run, packet }) => ["POST", `/api/conduct/runs/${encoded(parent_run)}/children`, packet]),
  tool("conduct_graph", "Read a canonical work graph.", { root_run: IDENTIFIER },
    ({ root_run }) => ["GET", `/api/conduct/runs/${encoded(root_run)}/graph`], { readOnly: true }),
  tool("conduct_claim", "Claim the exact lease generation as its authenticated native executor.", { lease: IDENTIFIER, generation: GENERATION },
    ({ lease, generation }) => ["POST", `/api/conduct/leases/${encoded(lease)}/claim`, { generation }]),
  tool("conduct_heartbeat", "Refresh an existing executor lease using its keeper-issued capability.",
    { lease: IDENTIFIER, generation: GENERATION, capability_token: CAPABILITY, observed_heads: OBJECT, attempt: OBJECT },
    ({ lease, ...body }) => ["POST", `/api/conduct/leases/${encoded(lease)}/heartbeat`, body],
    { required: ["lease", "generation", "capability_token"] }),
  tool("conduct_report", "Submit RunReceiptV1; the keeper validates executor, generation, and evidence.",
    { lease: IDENTIFIER, generation: GENERATION, capability_token: CAPABILITY, receipt: OBJECT },
    ({ lease, ...body }) => ["POST", `/api/conduct/leases/${encoded(lease)}/receipt`, body]),
  tool("conduct_harvest", "Read canonical terminal receipts for a work graph.", { root_run: IDENTIFIER },
    ({ root_run }) => ["GET", `/api/conduct/runs/${encoded(root_run)}/harvest`], { readOnly: true }),
  ...["adopt", "cancel", "request_stop"].map((action) => tool(`conduct_${action}`,
    `Request canonical ${action}; existing protection and ownership checks remain enforced.`,
    { run: IDENTIFIER, session_id: IDENTIFIER },
    ({ run, session_id }) => ["POST", `/api/conduct/runs/${encoded(run)}/${action.replace("_", "-")}`, { session_id }])),
].map((entry) => [entry.definition.name, entry]));

class TransportError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

function response(body, status = 200, extraHeaders = {}) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...extraHeaders },
  });
}

function rpcError(id, code, message, status = 200) {
  return response({ jsonrpc: "2.0", id, error: { code, message } }, status);
}

function result(id, value) {
  return response({ jsonrpc: "2.0", id, result: value });
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validArguments(value, schema) {
  if (!isObject(value) || schema.required.some((key) => !Object.hasOwn(value, key))) return false;
  return Object.entries(value).every(([key, item]) => {
    if (!Object.hasOwn(schema.properties, key)) return false;
    const rule = schema.properties[key];
    if (!rule) return false;
    if (rule.type === "object") return isObject(item);
    if (rule.type === "integer") return Number.isSafeInteger(item) && item >= rule.minimum && item <= rule.maximum;
    return typeof item === "string" && item.length >= (rule.minLength ?? 0)
      && item.length <= (rule.maxLength ?? 256) && (!rule.pattern || new RegExp(rule.pattern).test(item));
  });
}

async function boundedJson(message, maximum) {
  const length = message.headers.get("content-length");
  if (length && (!/^\d+$/.test(length) || Number(length) > maximum)) {
    throw new TransportError(413, "Message exceeds the transport limit");
  }
  const reader = message.body?.getReader();
  if (!reader) throw new TransportError(400, "Invalid JSON message");
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > maximum) {
        await reader.cancel();
        throw new TransportError(413, "Message exceeds the transport limit");
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try { return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
  catch { throw new TransportError(400, "Invalid UTF-8 JSON message"); }
}

function originAllowed(request, env) {
  const origin = request.headers.get("origin");
  if (!origin) return true; // Server-to-server clients do not send Origin.
  const allowed = String(env.LIMEN_MCP_ALLOWED_ORIGINS || "").split(",").map((item) => item.trim());
  return origin === new URL(request.url).origin || (origin !== "null" && allowed.includes(origin));
}

async function callTool(request, env, id, params) {
  if (!isObject(params) || typeof params.name !== "string"
      || Object.keys(params).some((key) => !["name", "arguments", "_meta"].includes(key))) {
    return rpcError(id, -32602, "Invalid tool call parameters");
  }
  const entry = TOOLS.get(params.name);
  if (!entry) return rpcError(id, -32602, "Unknown tool");
  const args = params.arguments === undefined ? {} : params.arguments;
  if (!validArguments(args, entry.definition.inputSchema)) return rpcError(id, -32602, "Invalid tool arguments");
  const [method, path, body] = entry.route(args);
  let delegated;
  try {
    delegated = new Request(new URL(path, request.url), {
      method,
      headers: {
        authorization: request.headers.get("authorization"),
        accept: "application/json",
        ...(body ? { "content-type": "application/json" } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
  } catch {
    // JSON.parse can accept deeper nesting than JSON.stringify. Serialization
    // failure is a pre-admission input failure, not an unobserved keeper write.
    return rpcError(id, -32602, "Invalid tool arguments");
  }
  try {
    // Never use a service principal, local store, or direct keeper call here.
    const upstream = await forwardConductRequest(delegated, env);
    if (!upstream.ok) {
      // Keeper error prose can contain submitted data. Return a bounded status,
      // never echo credentials, supplied text, or an internal exception message.
      await upstream.body?.cancel();
      const error = { code: upstream.status >= 500 ? "conduct_outcome_unobserved" : "conduct_rejected", status: upstream.status };
      return result(id, { content: [{ type: "text", text: JSON.stringify(error) }], structuredContent: error, isError: true });
    }
    const payload = await boundedJson(upstream, MAX_OUTPUT);
    if (!isObject(payload)) throw new Error("Invalid keeper response");
    return result(id, { content: [{ type: "text", text: JSON.stringify(payload) }], structuredContent: payload, isError: false });
  } catch {
    // A transport failure does not prove the keeper rejected a mutation. Callers
    // must inspect the same work/run identity before any retry.
    const error = { code: "conduct_outcome_unobserved" };
    return result(id, { content: [{ type: "text", text: JSON.stringify(error) }], structuredContent: error, isError: true });
  }
}

export async function handleConductMcp(request, env) {
  // Authenticate every method, including initialize, tools/list, GET and OPTIONS.
  const auth = await authorizeMcpRequest(request, env);
  if (!auth.ok) return response({ error: "Conduct authentication unavailable or rejected" }, auth.status,
    auth.challenge ? { "www-authenticate": auth.challenge }
      : auth.status === 401 ? { "www-authenticate": 'Bearer realm="limen-conduct"' } : {});
  request = auth.request;
  if (!originAllowed(request, env)) return response({ error: "Origin not allowed" }, 403);
  if (request.method !== "POST") return response({ error: "Only POST is supported; no SSE stream or session storage" }, 405, { allow: "POST" });
  const version = request.headers.get("mcp-protocol-version");
  if (version && !VERSIONS.includes(version)) return response({ error: "Unsupported MCP protocol version" }, 400);
  const accept = (request.headers.get("accept") || "").split(",").map((item) => item.trim().split(";")[0]);
  if (!accept.includes("application/json") || !accept.includes("text/event-stream")) {
    return response({ error: "Accept must include application/json and text/event-stream" }, 406);
  }
  if (request.headers.get("content-type")?.split(";")[0].trim() !== "application/json") {
    return response({ error: "Content-Type must be application/json" }, 415);
  }
  let message;
  try { message = await boundedJson(request, MAX_INPUT); }
  catch (error) { return rpcError(null, -32700, "Invalid or oversized JSON message", error.status || 400); }
  if (!isObject(message) || message.jsonrpc !== "2.0" || typeof message.method !== "string"
      || Object.keys(message).some((key) => !["jsonrpc", "id", "method", "params"].includes(key))
      || (message.params !== undefined && !isObject(message.params))) {
    return rpcError(null, -32600, "Invalid JSON-RPC request", 400);
  }
  if (!Object.hasOwn(message, "id")) {
    // No notification can cause a keeper mutation. Unknown notifications and
    // unsolicited client responses are refused without being dispatched.
    return message.method === "notifications/initialized"
      ? response(null, 202) : response({ error: "Unsupported notification" }, 400);
  }
  const { id, method, params = {} } = message;
  if (!(Number.isSafeInteger(id) || (typeof id === "string" && id.length <= 256))) {
    return rpcError(null, -32600, "Invalid request id", 400);
  }
  if (method === "initialize") {
    if (typeof params.protocolVersion !== "string" || !isObject(params.capabilities)
        || !isObject(params.clientInfo) || typeof params.clientInfo.name !== "string" || typeof params.clientInfo.version !== "string") {
      return rpcError(id, -32602, "Invalid initialization parameters");
    }
    return result(id, {
      protocolVersion: VERSIONS.includes(params.protocolVersion) ? params.protocolVersion : VERSIONS[0],
      capabilities: { tools: { listChanged: false } },
      serverInfo: { name: "limen-conduct", version: "0.1.0" },
    });
  }
  if (method === "ping") return result(id, {});
  if (method === "tools/list") {
    if (Object.keys(params).some((key) => key !== "_meta")) return rpcError(id, -32602, "Pagination is not supported");
    return result(id, { tools: [...TOOLS.values()].map((entry) => ({ ...entry.definition,
      ...(auth.scopes ? { securitySchemes: [{ type: "oauth2", scopes: auth.scopes }] } : {}),
    })) });
  }
  if (method === "tools/call") return callTool(request, env, id, params);
  return rpcError(id, -32601, "Method not found");
}
