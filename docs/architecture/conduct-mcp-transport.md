# Authenticated conduct MCP transport

The runtime Worker exposes `/mcp` as a stateless JSON-response Streamable HTTP
adapter over its existing `/api/conduct/*` routes. It does not create another
keeper, queue, credential registry, session database, or task projection writer.
Managed-bearer operations use the caller's existing principal-bound Authorization
header. An optional OAuth resource boundary authenticates `/mcp` access tokens
and maps them to one explicitly provisioned native principal before entering the
same canonical bearer-authenticated path.
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
| Client authentication | Existing lane-specific bearer, or the optional OAuth resource configuration below |
| Optional OAuth configuration | `LIMEN_CONDUCT_MCP_OAUTH`, a Worker secret under the existing credential owner; absent means disabled |
| Deployment credential | Existing repository-secret cache `CLOUDFLARE_API_TOKEN` |
| Optional Origin allowlist | `LIMEN_MCP_ALLOWED_ORIGINS`; exact origins only |
| Deployment workflow | `deploy-worker.yml`, `ref=main`, input `expected_sha` equal to the captured accepted-main SHA |

Use the exact-head workflow documented in [Deployment](../deployment.md). It
verifies the Worker before deploying and records runtime Git identity. Register
the MCP URL in a client that supports a managed bearer header, such as the
existing Ianva/Copilot configuration shape. Keep all values in the credential
organ and managed connector settings, never in the repository or a prompt.

The Worker is an OAuth **resource server**, never an authorization server. It does
not implement login, consent, client registration, token issuance, or refresh.
Ianva holds upstream OAuth grants as a client and does not supply this missing
authorization-server function. Source deployment and client installation must be
independently verified; neither can be inferred from a successful GitHub connector
call or a saved permission setting.

### Optional OAuth connection for ChatGPT

The opt-in boundary follows the official
[OpenAI authentication contract](https://developers.openai.com/plugins/build/auth)
and [MCP authorization specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization).
Provision an established OAuth issuer with authorization-code + S256 PKCE,
discovery metadata, resource indicators, and a supported ChatGPT client
registration method. Register the exact redirect URI shown by the connection UI.
No deployed issuer, user grant, or client registration is assumed by this source.

The issuer must mint signed JWT **access tokens** with `typ: at+jwt`, `alg: RS256`
or `ES256`, exact `iss`, audience `https://<canonical-worker-origin>/mcp`, required
`exp` and `sub`, and a space-separated `scope` claim. `nbf`, when present, is
enforced. The configured `client_id` or `azp` claim must identify the authenticated
OAuth client. An ID token, GitHub installation token, or a token for another
resource is not accepted. This strict access-token profile is a provisioning
requirement, not a claim that any arbitrary OAuth provider works unchanged.

Example configuration shape (all identifiers below are synthetic):

```json
{
  "schema_version": "limen.conduct_mcp_oauth.v1",
  "resource": "https://limen.example/mcp",
  "issuer": "https://identity.example",
  "jwks_uri": "https://identity.example/.well-known/jwks.json",
  "scopes": ["limen:conduct"],
  "client_id_claim": "client_id",
  "bindings": [
    {
      "subject": "issuer-owned-user-id",
      "client_id": "registered-chatgpt-client-id",
      "principal_id": "existing-chat-principal"
    }
  ]
}
```

Store this JSON only through the existing credential-management/deployment path
as `LIMEN_CONDUCT_MCP_OAUTH`. It contains private user and principal bindings.
The referenced principal must already exist in `LIMEN_CONDUCT_PRINCIPAL_REGISTRY`
with its real native agent and surface. This adapter never creates principals,
assigns roles, infers Chat/Work/Codex identity from `clientInfo`, or substitutes
Codex for Chat. Only observer, conductor, and executor roles may be mapped;
compatibility-owner and collector principals cannot be exposed through OAuth.
An OAuth client ID alone does not establish the actual execution experience or
usage allowance; the execution receipt must independently identify those facts.

With valid configuration, public `GET /.well-known/oauth-protected-resource/mcp`
and `GET /.well-known/oauth-protected-resource` return only the canonical resource,
issuer, scopes, and header bearer method. Requests to another origin return 404.
Unauthenticated `/mcp` responses advertise the canonical metadata URL in
`WWW-Authenticate`. Unknown or invalid tokens return 401, insufficient scopes 403,
and invalid configuration or an unavailable JWKS verifier 503. Existing valid
managed-bearer clients remain usable even when optional OAuth configuration or the
issuer is unavailable. OAuth tokens never authenticate `/api/conduct/*` directly.

The resource boundary verifies issuer, audience, algorithm, signature, token
class, validity period, subject, client, and scopes before replacing the header
in memory with that exact existing principal's bearer. The original canonical
router and keeper reauthenticate it and retain role, session, lease, and protected
human-session checks. Neither credential is returned in metadata, tool responses,
or errors. No OAuth token is passed to another resource server.

JWKS requests use only the fixed configured HTTPS URL, forbid redirects, have a
five-second deadline including the body, and accept at most 128 KiB. JOSE caches
keys for at most five minutes and applies a thirty-second unknown-key refresh
cooldown. Tokens cannot supply `jku` or `x5u` destinations. Access-token expiry
still applies on every request. Removing a binding or disabling this optional
configuration stops OAuth admission; issuer key removal may take up to the cache
window to take effect. User consent, refresh/revocation behavior, and key rotation
remain the issuer's responsibility.

Installing this source is **not** an activated Chat connection. Activation still
requires a provisioned issuer and binding, exact-head Worker deployment, an
actual ChatGPT connection, and accepted live execution receipts. A source test
executed from Work proves none of those additional states.

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

For the optional OAuth path, additionally verify public metadata and 401 discovery,
complete authorization in the actual Chat interface, and prove the bound native
principal reaches the same keeper. Wrong-user, wrong-client, expired, wrong-audience,
and ID tokens must not cause keeper access. Confirm direct `/api/conduct` calls
with the OAuth token remain rejected. Finally, execute one bounded authorized
code change through verification, PR, exact-head merge, and readback while
recording the actual executor and allowance owner. The broker handshake alone
does not prove engineering completion or Chat-first usage savings.

Local source verification is `node --test test/conduct-mcp.test.js test/conduct-mcp-oauth.test.js`, followed by
`npm run check` from `web/worker`. Tests use explicitly synthetic credentials and
the real canonical HTTP/keeper validation path; they are not live authorization,
deployment, or unattended-execution evidence.
