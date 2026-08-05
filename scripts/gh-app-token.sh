#!/usr/bin/env bash
# gh-app-token.sh — mint a GitHub App (limen[bot]) INSTALLATION token, with PAT fallback.
#
# Why this exists (the durable architecture fix, concluded 2026-06-18, see
# memory github-structure-app-not-orgs): the fleet authenticated to GitHub through a personal
# Personal Access Token (GITHUB_TOKEN). A PAT *acts as the human* — it shares their 5k/hr limit
# and DIES the moment the personal account is billing-locked. That is exactly what took CI down
# org-wide. A GitHub App is a first-class machine identity: its own actor (limen[bot]), per-repo
# least-privilege auto-expiring installation tokens, 15k/hr, surviving independent of any human
# account. This script is that identity, executable.
#
# Cascade (cascade-fallback-principle): try the BEST path first, fall back, never hard-fail
# while a path remains:
#   1. GitHub App  — if GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY are set, mint a short-lived
#                    installation token (the durable machine identity).
#   2. PAT         — else if GITHUB_TOKEN is set, emit it unchanged (today's bootstrap path).
#   3. gh auth     — else if `gh auth token` works, emit that.
# Exit 1 only when EVERY path is exhausted.
#
# Usage:
#   GITHUB_TOKEN=$(bash scripts/gh-app-token.sh)            # drop-in for any gh/api caller
#   bash scripts/gh-app-token.sh --which                    # report which path WOULD be used (no token printed)
#   bash scripts/gh-app-token.sh --verify-app               # require a real App token mint, no fallback
#
# Credentials (set via scripts/set-credential.sh — never on a command line / in history):
#   GITHUB_APP_ID                — the App's numeric id (Settings → Developer settings → GitHub Apps)
#   GITHUB_APP_PRIVATE_KEY       — the App's PEM private key, EITHER inline (full PEM) OR a path to the .pem
#   GITHUB_APP_INSTALLATION_ID   — optional; if unset, derived at run-time from the App's installations
#                                   ("names are outputs" — don't pin it; the first/only installation wins)
set -uo pipefail

# Load the conductor's secret file the same way the rest of the fleet does (chmod 600, never a shell rc).
ENV_FILE="${LIMEN_ENV:-$HOME/.limen.env}"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

API="${GITHUB_API:-https://api.github.com}"
MODE="${1:-}"

log() { echo "gh-app-token: $*" >&2; }

# --- path 1: GitHub App installation token -------------------------------------------------
app_creds_present() { [ -n "${GITHUB_APP_ID:-}" ] && [ -n "${GITHUB_APP_PRIVATE_KEY:-}" ]; }

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

mint_app_token() {
  command -v openssl >/dev/null 2>&1 || { log "openssl not found — cannot sign App JWT"; return 1; }
  command -v curl    >/dev/null 2>&1 || { log "curl not found — cannot reach the GitHub API"; return 1; }

  # Resolve the private key: inline PEM, or a path to a .pem file.
  local key_pem
  if printf '%s' "$GITHUB_APP_PRIVATE_KEY" | grep -q "BEGIN"; then
    key_pem="$GITHUB_APP_PRIVATE_KEY"
  elif [ -f "$GITHUB_APP_PRIVATE_KEY" ]; then
    key_pem="$(cat "$GITHUB_APP_PRIVATE_KEY")"
  else
    log "GITHUB_APP_PRIVATE_KEY is neither inline PEM nor a readable file path"; return 1
  fi

  # Build a 10-minute RS256 JWT, iat backdated 60s for clock skew (GitHub's documented recipe).
  # iat/exp are derived from the clock at run-time — never hardcoded.
  local now iat exp header payload signing_input sig jwt
  now=$(date +%s); iat=$((now - 60)); exp=$((now + 540))
  header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
  payload=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$iat" "$exp" "$GITHUB_APP_ID" | b64url)
  signing_input="${header}.${payload}"
  sig=$(printf '%s' "$signing_input" \
        | openssl dgst -sha256 -sign <(printf '%s' "$key_pem") -binary 2>/dev/null | b64url) || {
    log "JWT signing failed — is GITHUB_APP_PRIVATE_KEY a valid RSA PEM?"; return 1; }
  jwt="${signing_input}.${sig}"

  # Resolve the installation id if not pinned (derive, don't hardcode).
  local inst="${GITHUB_APP_INSTALLATION_ID:-}"
  if [ -z "$inst" ]; then
    inst=$(curl -fsS -H "Authorization: Bearer $jwt" -H "Accept: application/vnd.github+json" \
                "$API/app/installations" 2>/dev/null \
           | grep -m1 -oE '"id":[[:space:]]*[0-9]+' | grep -oE '[0-9]+' | head -1)
    [ -z "$inst" ] && { log "no App installations found — install limen[bot] on the load-bearing owners"; return 1; }
  fi

  # Exchange the JWT for a short-lived installation token.
  local resp tok
  resp=$(curl -fsS -X POST -H "Authorization: Bearer $jwt" -H "Accept: application/vnd.github+json" \
              "$API/app/installations/${inst}/access_tokens" 2>/dev/null) || {
    log "installation token request rejected (App id/key/installation mismatch?)"; return 1; }
  tok=$(printf '%s' "$resp" | grep -m1 -oE '"token":[[:space:]]*"[^"]+"' | sed -E 's/.*"token":[[:space:]]*"([^"]+)".*/\1/')
  [ -z "$tok" ] && { log "installation token missing from API response"; return 1; }
  printf '%s\n' "$tok"
}

# --- which path? (diagnostic, prints NO secret) --------------------------------------------
if [ "$MODE" = "--which" ]; then
  if app_creds_present; then echo "app (limen[bot] installation token)"
  elif [ -n "${GITHUB_TOKEN:-}" ]; then echo "pat (GITHUB_TOKEN fallback)"
  elif command -v gh >/dev/null 2>&1 && gh auth token >/dev/null 2>&1; then echo "gh (gh auth token fallback)"
  else echo "none (no credential available)"; fi
  exit 0
fi

if [ "$MODE" = "--verify-app" ]; then
  app_creds_present || { log "missing GITHUB_APP_ID or GITHUB_APP_PRIVATE_KEY"; exit 2; }
  mint_app_token >/dev/null || exit 1
  echo "app verified (limen[bot] installation token mint succeeds)"
  exit 0
fi

# --- cascade ------------------------------------------------------------------------------
if app_creds_present; then
  if tok=$(mint_app_token); then printf '%s\n' "$tok"; exit 0; fi
  log "App path failed — cascading to PAT/gh fallback"
fi
if [ -n "${GITHUB_TOKEN:-}" ]; then printf '%s\n' "$GITHUB_TOKEN"; exit 0; fi
if command -v gh >/dev/null 2>&1 && tok=$(gh auth token 2>/dev/null) && [ -n "$tok" ]; then
  printf '%s\n' "$tok"; exit 0
fi
log "no credential available: set GITHUB_APP_ID+GITHUB_APP_PRIVATE_KEY, or GITHUB_TOKEN, or run 'gh auth login'"
exit 1
