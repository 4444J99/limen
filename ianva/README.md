# ianva — the fleet's single MCP doorway

> Latin *ianua*: the door. It sits at the *limen* (threshold). Every agent passes through this
> one doorway to reach every MCP server — and authenticates each server **once, forever**.

## The problem it kills

"Why the fuck do I keep authorizing MCP servers over and over?" — three separate diseases
(see [docs/THREE-DISEASES.md](docs/THREE-DISEASES.md)):

| # | disease | who it hits | ianva's cure |
|---|---|---|---|
| **A** | claude.ai connector prompts (Sentry, Gmail, …) expire server-side in Anthropic's cloud | the claude.ai desktop/web client | **cloud face** — expose ianva as one public self-authenticating connector that never returns 401 (replaces the per-service connectors) |
| **B** | every other agent (Codex/Gemini/agy/opencode/Copilot/Cline) authenticates each server independently | your local CLIs | **local face** — one config entry per agent → ianva; consent once per upstream, never again |
| **C** | ~30 concurrent `claude -p` share + rotate one Keychain token (40 stale forks found) | the limen daemon | **discipline** — single-writer refresh + `~/.limen.env`; ianva never recreates the flap |

The honest constraint: a *local* gateway cannot intercept disease A — claude.ai runs that OAuth
from its cloud, not your machine. Killing A requires the public **cloud face** (a tunnel + one
custom connector). B and C are solved entirely locally.

## Architecture (four faces, all built)

```
   Claude Code   Codex   Gemini   agy   opencode   Copilot   Cline       claude.ai (cloud)
        \          |       |       |       |          |       /                  |
         \         └───────┴───┬───┴───────┴──────────┘      /         public HTTPS (cloudflared)
          \  (http direct)     │   (stdio via mcp-proxy)    /                     │
           └────────────────►  ianva endpoint  ◄───────────┘  ◄───────────────────┘
                                   │  (http://127.0.0.1:7666/mcp)
                          ┌────────┴─────────┐
                          │  core: MCPHub    │   holds upstream OAuth 2.1 + auto-refresh,
                          │  (or Docker GW)  │   aggregates + namespaces all servers
                          └────────┬─────────┘
              ┌──────────┬─────────┼──────────┬───────────┐
           limen(stdio) github   notion(OAuth) sentry(OAuth)  … every MCP server, authed once
```

- **core** — wraps [MCPHub](https://github.com/samanhappy/mcphub) (`@samanhappy/mcphub`), the one
  surveyed aggregator that implements full upstream OAuth 2.1 (PKCE, DCR, resource indicators) **and
  persistent auto-refresh**. We wrap, not rebuild. `docker` backend is an alternate (see compose).
- **local face** — agents with first-class HTTP MCP point straight at the endpoint; the rest spawn
  [`mcp-proxy`](https://pypi.org/project/mcp-proxy/) as a thin stdio↔HTTP shim (carries no creds).
- **cloud face** — `scripts/ianva-tunnel.sh` publishes the endpoint (bearer-enforced) so claude.ai connects once.
- **discipline** — MCPHub, being one long-lived process, is the *single* OAuth refresher (no
  cross-process refresh race by construction). `src/ianva/creds.py` keeps the backend off the
  Keychain (`CLAUDE_CODE_OAUTH_TOKEN` never propagated — #37512 — fleet auth precedence applied,
  one-shot auth-blip retry) and flock-serializes ianva's own credential writes; `preflight.py`
  gates unreachable upstreams.

## Quickstart

```bash
export PYTHONPATH="$PWD/src"                 # or: uv pip install -e .
python3 -m ianva.cli doctor                  # verify deps, paths, endpoint (no secrets printed)
python3 -m ianva.cli gen-configs             # write per-agent entries to ./generated (review only)
python3 -m ianva.cli up                      # materialize settings + start the MCPHub backend
python3 -m ianva.cli install-configs         # DRY RUN — show what would change in real configs
python3 -m ianva.cli install-configs --apply # write them in (backs up every file first)
```

Upstreams come from `~/.agents/mcp/servers.json` (the fleet's `build-mcp-registry.py` output —
ianva is finally its consumer) merged with `~/.config/ianva/upstreams.json` (see
`upstreams.example.json`). The exact MCPHub/mcp-proxy invocations are config knobs in `ianva.toml`,
verified by `ianva doctor` — never pinned literals.

## What's gated (his-hand)

Building + staging is done. The irreversible flips are yours — see [docs/HIS-HAND.md](docs/HIS-HAND.md):
writing into global agent configs (`install-configs --apply`), the public connector tunnel, the
launchd keepalive, and merging the branch. Nothing here touches your machine until you run it.
