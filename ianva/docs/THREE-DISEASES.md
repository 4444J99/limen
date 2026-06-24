# The three re-auth diseases (and which ianva face cures each)

Recon (2026-06-24) overturned the simple "build one server and it all stops" framing. There are
**three** distinct causes of repeated authorization, with three different cures. This is the honest
map — including the one thing a local gateway physically cannot do.

## A — claude.ai connector prompts (the `/doctor` "Sentry needs authentication")

**Mechanism.** The `claude.ai <X>` servers (Sentry, Gmail, Notion, Figma, Drive, Vercel, …) are
**remote managed connectors hosted in Anthropic's cloud**. Recon confirmed their OAuth tokens are
**not on disk** — zero JWT/Bearer/sk-ant strings in `~/.claude.json`; only `claudeAiMcpEverConnected`
(which were ever linked) and `mcp-needs-auth-cache.json` (which need re-auth right now — it was
rewritten 2026-06-24 04:37 flagging Indeed/Cloudflare/Jam/Netlify/Candid/Sentry). claude.ai is
itself the MCP *client* and runs the OAuth handshake **from its cloud, not your device**. Tokens or
keys in a connector URL are unsupported.

**Therefore a local gateway cannot intercept these.** This is the hard truth.

**Cure = the cloud face.** Connector OAuth is *optional*: if a connector URL is reachable from
Anthropic's cloud over public HTTPS and never returns `401 / WWW-Authenticate`, claude.ai connects
with **no prompt**. So expose ianva publicly (`scripts/ianva-tunnel.sh`), have it hold every
upstream's credentials behind it (server-side, internal), and register **one** custom connector in
claude.ai pointing at it — replacing the dozen per-service connectors. One connector, never expires
from your side. Cost: a tunnel/deploy + a security pass (it's internet-reachable).

## B — every other agent authenticates independently

**Mechanism.** Codex, Gemini, antigravity (agy), opencode, Copilot, and Cline each hold their own
MCP connections and their own OAuth clients. The same upstream gets authorized once *per agent*, and
again whenever any token lapses. Recon mapped all six config files and formats (see
`src/ianva/agents.py`).

**Cure = the local face.** ianva connects to each upstream **once** and holds its refresh token
(MCPHub auto-renews silently — OAuth 2.1 refresh tokens renew access with no user interaction). Every
agent gets **one** entry pointing at ianva. Consent once per upstream, never again. Fully local, no
cloud. This is the clean, total win and the core of the original ask ("all agent config files point
at our own server").

## C — the fleet `claude -p` login flap (credential race)

**Mechanism.** ~30 concurrent `claude` processes share **one** macOS Keychain login credential
(no `CLAUDE_CONFIG_DIR` is set on any of them). Recon found **40 Keychain entries: 1 live + 39 stale
`Claude Code-credentials-<8hex>` forks**, accreting daily since Nov 2025. When a headless refresh
loses the race it logs "no token found… run claude auth login" and self-recovers — the flap in
`daemon.log` (06-16/17/18). Distinct from A and B.

**Cure = discipline (already staged on `fix/claude-credential-race`).** Give the fleet its own stable
credential via `~/.limen.env` (`LIMEN_CLAUDE_AUTH_TOKEN → ANTHROPIC_AUTH_TOKEN`), **never** export
`CLAUDE_CODE_OAUTH_TOKEN` (it deletes the Keychain item on exit — #37512), and never run two
refreshers at once. ianva inherits this in `src/ianva/creds.py`, and the precise guarantee is honest:
MCPHub — a single long-lived process — is the *only* refresher of each upstream token, so there is no
cross-process refresh race by construction; ianva's job is to keep `CLAUDE_CODE_OAUTH_TOKEN` out of the
backend, apply the fleet auth precedence, and flock-serialize its *own* credential writes (not MCPHub's
internal refresh, which it cannot reach). The 39 stale forks are safe to prune once the
fleet stops sharing the interactive token.

## Summary

| disease | on-disk? | local gateway fixes it? | ianva face |
|---|---|---|---|
| A claude.ai connectors | no (cloud) | **no** — needs public exposure | cloud (tunnel + 1 connector) |
| B other agents | yes | **yes, fully** | local (one entry per agent) |
| C fleet `claude -p` race | yes (Keychain) | n/a — credential discipline | discipline (`creds.py` + `~/.limen.env`) |
