#!/usr/bin/env bash
# ianva-tunnel.sh — the CLOUD face. Expose the local ianva endpoint over public HTTPS so the
# claude.ai connectors (which run OAuth from Anthropic's cloud, not your machine) can reach it.
#
# Why this is the ONLY way to stop the claude.ai connector prompts: claude.ai is itself the MCP
# client; a local gateway can't intercept it. But a public, self-authenticating gateway that
# holds all upstream creds behind it and never returns 401 connects with no prompt — forever.
#
#   bash ianva-tunnel.sh            # quick (ephemeral *.trycloudflare.com) tunnel — for testing
#   bash ianva-tunnel.sh --named ianva   # stable named tunnel (needs a Cloudflare account + DNS)
#
# After it prints the public URL:
#   1) set gateway.public_url in ianva.toml to "<url>/mcp"
#   2) add ONE custom connector in claude.ai pointing at that URL (replaces the per-service connectors)
set -euo pipefail

PORT="${IANVA_PORT:-7666}"
LOCAL="http://127.0.0.1:${PORT}"

command -v cloudflared >/dev/null || { echo "cloudflared not found (brew install cloudflared)"; exit 1; }

# Health + AUTH gate. A public unauthenticated /mcp is an open proxy to every upstream's creds, so
# we refuse to expose unless the endpoint rejects an un-credentialed request. Set IANVA_TUNNEL_FORCE=1
# only if you have other auth in front (and you know what you're doing).
CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "${LOCAL}/mcp" 2>/dev/null || echo 000)"
if [ "$CODE" = "000" ]; then
  echo "error: ${LOCAL}/mcp not responding — start it first with \`ianva up\`."; exit 1
fi
if [ "$CODE" != "401" ] && [ "$CODE" != "403" ] && [ "${IANVA_TUNNEL_FORCE:-0}" != "1" ]; then
  echo "REFUSING to expose: ${LOCAL}/mcp answered HTTP ${CODE} to an UNAUTHENTICATED request."
  echo "That would publish an open proxy to all your upstream credentials. Add a bearer first:"
  echo "  ianva bearer --new  →  store IANVA_BEARER_TOKEN  →  ianva up   (re-enables enforcement)"
  echo "(override with IANVA_TUNNEL_FORCE=1 only if you front it with your own auth.)"
  exit 1
fi
echo "auth gate OK: ${LOCAL}/mcp requires auth (HTTP ${CODE}). Safe to expose."

if [ "${1:-}" = "--named" ]; then
  NAME="${2:-ianva}"
  echo "Named tunnel '${NAME}' → ${LOCAL}"
  echo "Requires: \`cloudflared tunnel login\` (his-hand, one time) + a DNS route. See docs/HIS-HAND.md."
  exec cloudflared tunnel --url "${LOCAL}" run "${NAME}"
fi

echo "Quick tunnel → ${LOCAL} (ephemeral URL; for a stable one use --named)."
exec cloudflared tunnel --url "${LOCAL}"
