# Authenticated conduct MCP transport

The runtime Worker exposes `/mcp` as a stateless JSON-response Streamable HTTP
adapter over its existing `/api/conduct/*` routes. It does not create another
keeper, queue, credential registry, session database, or task projection writer.
Every operation uses the caller's existing principal-bound Authorization header.
The canonical HTTP router still decides roles, identity, schema validity,
authority, claims, budget, lease generation, receipts, and protected-session rules.

This source implementation is not a deployment or a connected-client receipt.
The current ChatGPT GitHub connection cannot acquire a conduct lease merely by
reading or writing a GitHub issue. A remote MCP client must actually connect to
the deployed endpoint with its separately provisioned native principal.

## Protocol and boundary

Supported protocol revisions are `2025-11-25`, `2025-06-18`, and `2025-03-26`.
The implementation follows the official MCP
[Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports),
[initialization lifecycle](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle),
and [tool messages](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
Clients initialize, send `notifications/initialized`, then list or call tools.
Initialization negotiates the protocol version; subsequent requests carry the
`MCP-Protocol-Version` header. A missing header uses the compatible March 2025
message subset. No server-side MCP session identifier is issued or required.

- All HTTP methods require an existing conduct principal, including initialization,
  tool discovery, GET, and OPTIONS. A missing/invalid bearer returns 401; an
  unavailable credential registry returns 503. The adapter never falls back to
  owner compatibility credentials or the local SQLite test adapter.
- POST requires JSON and Accept support for both JSON and event streams. Each
  POST contains one JSON-RPC message. Replies preserve the bounded request ID.
  The initialized notification returns an empty 202. GET returns 405 because
  this adapter does not offer an SSE stream. Browser preflight is not enabled;
  the intended client is a credential-owning server, not browser JavaScript.
- Present Origin values must equal the Worker origin or one exact comma-separated
  entry in `LIMEN_MCP_ALLOWED_ORIGINS`. Wildcards and `null` are not supported.
  Server clients may omit Origin. No origin list is needed for that normal path.
- Requests are bounded to 1 MiB while streaming; keeper responses are bounded to
  4 MiB. Invalid UTF-8, batches, invalid IDs, unsolicited responses, unsupported
  notifications/methods, unknown tools, extra arguments, and invalid generations
  fail closed. No tool accepts a URL, shell command, alternate keeper, principal,
  credential, or arbitrary HTTP method as a transport control.
- Canonical 4xx tool rejection returns `isError: true` with `conduct_rejected` and
  the HTTP status. Internal error prose is not reflected. A 5xx or failed observation of
  a potentially accepted mutation returns `conduct_outcome_unobserved`; inspect
  the same canonical work/run identity before retrying. Never infer rejection,
  resubmit with a new work identity, or manufacture a success receipt.
- A successful executor claim returns the canonical executor-only capability.
  Its custody rules are unchanged: keep it inside the authenticated executor
  interaction; do not publish it in issues, logs, source, or durable receipts.

The closed tool catalog is `conduct_capabilities`, `conduct_register`,
`conduct_submit`, `conduct_split`, `conduct_graph`, `conduct_claim`,
`conduct_heartbeat`, `conduct_report`, `conduct_harvest`, `conduct_adopt`,
`conduct_cancel`, and `conduct_request_stop`. There are no credential-management,
arbitrary HTTP, compatibility-owner, inventory-write, or private-board tools.

## Deployment and client installation

| Setting | Existing owner / required value |
| --- | --- |
| Worker | `limen-runtime`, declared by `web/worker/wrangler.toml` |
| MCP URL | The actual deployed Worker origin plus `/mcp` |
| Server principal registry | Existing `LIMEN_CONDUCT_PRINCIPAL_REGISTRY` Worker secret; owner #320 |
| Keeper | Existing `CONDUCT_KEEPER` binding and `LIMEN_CONDUCT_KEEPER_NAME` |
| Client authentication | Existing lane-specific bearer, hydrated by the credential organ into the managed connector's Authorization header |
| Deployment credential | Existing repository-secret cache `CLOUDFLARE_API_TOKEN` |
| Optional Origin allowlist | `LIMEN_MCP_ALLOWED_ORIGINS`; exact origins only |
| Deployment workflow | `deploy-worker.yml`, `ref=main`, input `expected_sha` equal to the captured accepted-main SHA |

Use the exact-head workflow documented in [Deployment](../deployment.md). It
verifies the Worker before deploying and records runtime Git identity. Register
the MCP URL in a client that supports a managed bearer header, such as the
existing Ianva/Copilot configuration shape. Keep all values in the credential
organ and managed connector settings, never in the repository or a prompt.

This adapter does not implement OAuth authorization-server discovery, dynamic
client registration, or a login flow. A client that requires OAuth cannot use
this bearer-only endpoint directly: its sanctioned OAuth/managed-credential
gateway must map the authenticated native lane to the existing conduct principal.
Do not advertise this URL as an OAuth server or remove authentication to connect it.
Source deployment and client installation must be independently verified; neither
can be inferred from a successful GitHub connector call or a saved permission setting.

## Operational acceptance

After deployment and connection, use the actual exposed tool surface:

1. Prove an unauthenticated initialization and tool-list request returns 401.
2. Initialize with the managed native-lane credential; read capabilities and
   confirm the expected installed runtime and real lane identity.
3. Register the native session. Direct human sessions retain `human_protected`.
4. Submit one bounded read-only WorkPacketV1 with a stable work ID and real predicate.
5. Have its assigned native executor claim the returned lease/generation,
   heartbeat, execute the predicate, and report its actual RunReceiptV1.
6. Harvest that same run; verify the accepted terminal receipt. Replay the same
   work ID and prove no duplicate claim or budget debit.
7. Independently repeat through the configured scheduled producer and consumer;
   retain both trigger/run identities and the same handoff lineage. A direct-session
   canary is not proof that a scheduled trigger or unattended continuation ran.

Local source verification is `node --test test/conduct-mcp.test.js`, followed by
`npm run check` from `web/worker`. Tests use explicitly synthetic credentials and
the real canonical HTTP/keeper validation path; they are not live authorization,
deployment, or unattended-execution evidence.
