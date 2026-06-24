# ianva architecture

ianva is an **orchestrator**, deliberately dependency-free (stdlib only). It does not re-implement
OAuth — it supervises a credential-holding backend, generates each agent's config, and enforces the
fleet's credential discipline. Four faces, one endpoint.

## Modules (`src/ianva/`)
| module | role |
|---|---|
| `paths.py` | derived layout; `~/.limen.env` loader (never logs values) |
| `config.py` | `ianva.toml` → `GatewayConfig`; backend command is a knob, not a literal |
| `upstreams.py` | merge `servers.json` (build-mcp-registry) + `upstreams.json`; defensive normalize |
| `creds.py` | keeps backend off the Keychain (`CLAUDE_CODE_OAUTH_TOKEN` guard #37512 + fleet auth precedence); flock for ianva-side writes; auth-blip retry; bearer helpers |
| `preflight.py` | per-upstream DNS+TCP:443 reachability (the agy login-flap lesson) |
| `agents.py` | the 7 agent targets: path, format, transport (ground-truthed on this machine) |
| `gen.py` | render the one entry per agent in its native format; golden files to `generated/` |
| `mcphub.py` | materialize `mcp_settings.json`; start/stop/status the backend |
| `cli.py` | `up · down · status · doctor · gen-configs · install-configs · add-upstream · probe` |

## The core (credential authority)
**MCPHub** (`@samanhappy/mcphub`, verified on npm) is the wrapped core: it implements the full
upstream OAuth 2.1 client flow (Authorization-Code + PKCE, WWW-Authenticate/RFC8414 discovery,
DCR/RFC7591, resource indicators/RFC8707) **and persistent auto-refresh** — tokens cached and renewed
before expiry, written back so they survive restarts. That silent-renewal property (OAuth 2.1 §4.3:
a refresh token mints new access tokens with no user interaction) is what makes "authenticate once,
forever" true. ianva owns the settings file and supervises the process; it runs MCPHub in
`~/.config/ianva` so MCPHub finds `mcp_settings.json` in its CWD.

**Alternate backend (docker face):** the fleet's 2026-03-25 decision picked the Docker MCP gateway.
`deploy/docker-compose.yml` keeps it live as an option (MCPHub-in-container, or `docker mcp gateway
run` for Docker-managed OAuth + interceptors). Not required — `docker` isn't installed here.

## Transports down to agents
- **HTTP-direct** (Claude Code, Codex, Gemini, opencode): the agent's native remote-MCP support
  points straight at the endpoint. No extra process.
- **stdio-via-mcp-proxy** (agy, Copilot, Cline): the agent spawns `uvx mcp-proxy --transport
  streamablehttp <endpoint>`, a pure-transport shim (verified: `--help` exit 0). It carries no
  credentials; all auth stays in the core.

## Verification status
Built + verified locally: package imports, all modules compile, `doctor` resolves every dependency,
`gen-configs` emits 7 correct entries, installer dry-run touches nothing, MCPHub package + mcp-proxy
flags confirmed empirically. **Not yet run live:** the MCPHub backend boot (`ianva up` downloads it
on first run) and the cloud-face tunnel — both are his-hand flips (see [HIS-HAND.md](HIS-HAND.md)).
