#!/usr/bin/env bash
# gh-app-token.sh — mint one exact-repository GitHub App installation token.
#
# Why this exists (the durable architecture fix, concluded 2026-06-18, see
# memory github-structure-app-not-orgs): the fleet authenticated to GitHub through a personal
# Personal Access Token (GITHUB_TOKEN). A PAT *acts as the human* and shares that account's
# authorization and rate-limit surface. A GitHub App is a first-class machine identity with
# short-lived, repository-scoped installation tokens. This script is that identity, executable.
#
# Credential selection:
#   1. GitHub App  — if GITHUB_APP_ID + GITHUB_APP_PRIVATE_KEY are set, require one exact
#                    OWNER/REPO, resolve only that repository's installation, and mint a token
#                    restricted to its numeric repository ID. Any App targeting failure is final:
#                    it must never broaden silently into a PAT or gh-auth credential.
#   2. PAT         — else if GITHUB_TOKEN is set, emit it unchanged (today's bootstrap path).
#   3. gh auth     — else if `gh auth token` works, emit that.
# PAT/gh fallback exists only when App credentials are absent.
#
# Usage:
#   GITHUB_TOKEN=$(bash scripts/gh-app-token.sh --repo OWNER/REPO)
#   GITHUB_TOKEN=$(bash scripts/gh-app-token.sh --repo OWNER/REPO --app-only) # mutation/finalizer path
#   bash scripts/gh-app-token.sh --repo OWNER/REPO --which
#   bash scripts/gh-app-token.sh --repo OWNER/REPO --verify-app
#
# Credentials (set via scripts/set-credential.sh — never on a command line / in history):
#   GITHUB_APP_ID                — the App's numeric id (Settings → Developer settings → GitHub Apps)
#   GITHUB_APP_PRIVATE_KEY       — the App's PEM private key, EITHER inline (full PEM) OR a path to the .pem
#   GITHUB_APP_INSTALLATION_ID   — optional assertion; when set it must equal the installation
#                                   resolved from the exact repository endpoint
#   LIMEN_GITHUB_TARGET_REPO     — optional alternative to --repo, exact OWNER/REPO
set -uo pipefail

# Load the conductor's secret file the same way the rest of the fleet does (chmod 600, never a shell rc).
ENV_FILE="${LIMEN_ENV:-$HOME/.limen.env}"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

API="${GITHUB_API:-https://api.github.com}"
MODE=""
APP_ONLY=0
TARGET_REPO="${LIMEN_GITHUB_TARGET_REPO:-}"
TARGET_REPO_SOURCE="${TARGET_REPO:+environment}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --repo)
      [ "$#" -ge 2 ] || { echo "gh-app-token: --repo requires OWNER/REPO" >&2; exit 2; } # allow-secret: diagnostic label only
      if [ -n "$TARGET_REPO_SOURCE" ] && [ "$TARGET_REPO" != "$2" ]; then
        echo "gh-app-token: ambiguous exact target from $TARGET_REPO_SOURCE and --repo" >&2 # allow-secret: diagnostic label only
        exit 2
      fi
      TARGET_REPO="$2"
      TARGET_REPO_SOURCE="--repo"
      shift 2
      ;;
    --which|--verify-app)
      [ -z "$MODE" ] || { echo "gh-app-token: choose only one mode" >&2; exit 2; } # allow-secret: diagnostic label only
      MODE="$1"
      shift
      ;;
    --app-only)
      [ "$APP_ONLY" = "0" ] || { echo "gh-app-token: --app-only may be passed only once" >&2; exit 2; } # allow-secret: diagnostic label only
      APP_ONLY=1
      shift
      ;;
    *)
      echo "gh-app-token: unknown argument: $1" >&2 # allow-secret: diagnostic label only
      exit 2
      ;;
  esac
done

log() { echo "gh-app-token: $*" >&2; }

# --- path 1: GitHub App installation token -------------------------------------------------
app_creds_present() { [ -n "${GITHUB_APP_ID:-}" ] && [ -n "${GITHUB_APP_PRIVATE_KEY:-}" ]; }
app_creds_configured() { [ -n "${GITHUB_APP_ID:-}" ] || [ -n "${GITHUB_APP_PRIVATE_KEY:-}" ]; }

valid_target_repo() {
  local owner repo
  [[ "$TARGET_REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || return 1
  owner="${TARGET_REPO%%/*}"
  repo="${TARGET_REPO#*/}"
  [ "$owner" != "." ] && [ "$owner" != ".." ] && [ "$repo" != "." ] && [ "$repo" != ".." ]
}

require_target_repo() {
  valid_target_repo || { log "exact target required: pass --repo OWNER/REPO"; return 1; }
}

json_field() {
  local field="$1"
  python3 -c 'import json, sys
row = json.load(sys.stdin)
if not isinstance(row, dict) or sys.argv[1] not in row:
    raise SystemExit(1)
value = row[sys.argv[1]]
if isinstance(value, bool) or not isinstance(value, (str, int)):
    raise SystemExit(1)
print(value)' "$field"
}

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

mint_app_token() {
  require_target_repo || return 1
  command -v openssl >/dev/null 2>&1 || { log "openssl not found — cannot sign App JWT"; return 1; }
  command -v curl    >/dev/null 2>&1 || { log "curl not found — cannot reach the GitHub API"; return 1; }
  command -v python3 >/dev/null 2>&1 || { log "python3 not found — cannot validate GitHub responses"; return 1; }

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

  # Resolve exactly the target repository's installation. Never list installations and pick one.
  local installation_resp inst pinned repo_resp repo_id full_name repo_name request_body
  installation_resp=$(curl -fsS -H "Authorization: Bearer $jwt" -H "Accept: application/vnd.github+json" \
                           "$API/repos/$TARGET_REPO/installation" 2>/dev/null) || {
    log "no GitHub App installation resolves for exact target $TARGET_REPO"; return 1; }
  inst=$(printf '%s' "$installation_resp" | json_field id) || {
    log "exact target installation response is missing one numeric id"; return 1; }
  [[ "$inst" =~ ^[0-9]+$ ]] || { log "exact target installation id is invalid"; return 1; }
  pinned="${GITHUB_APP_INSTALLATION_ID:-}"
  if [ -n "$pinned" ] && { [[ ! "$pinned" =~ ^[0-9]+$ ]] || [ "$pinned" != "$inst" ]; }; then
    log "pinned installation id does not match exact target $TARGET_REPO"; return 1
  fi

  # Bind the scoped token body to GitHub's numeric repository identity and verify the coordinate.
  repo_resp=$(curl -fsS -H "Authorization: Bearer $jwt" -H "Accept: application/vnd.github+json" \
                   "$API/repos/$TARGET_REPO" 2>/dev/null) || {
    log "exact target repository identity is unavailable"; return 1; }
  repo_id=$(printf '%s' "$repo_resp" | json_field id) || {
    log "exact target repository response is missing one numeric id"; return 1; }
  full_name=$(printf '%s' "$repo_resp" | json_field full_name) || {
    log "exact target repository response is missing full_name"; return 1; }
  [[ "$repo_id" =~ ^[0-9]+$ ]] || { log "exact target repository id is invalid"; return 1; }
  [ "$full_name" = "$TARGET_REPO" ] || {
    log "repository identity mismatch: requested $TARGET_REPO"; return 1; }
  repo_name="${TARGET_REPO#*/}"
  [ -n "$repo_name" ] || { log "exact target repository name is empty"; return 1; }
  request_body=$(printf '{"repository_ids":[%s]}' "$repo_id")

  # Exchange the JWT for a short-lived token restricted to that one numeric repository ID.
  local resp tok
  resp=$(curl -fsS -X POST -H "Authorization: Bearer $jwt" -H "Accept: application/vnd.github+json" \
              -H "Content-Type: application/json" --data "$request_body" \
              "$API/app/installations/${inst}/access_tokens" 2>/dev/null) || {
    log "installation token request rejected (App id/key/installation mismatch?)"; return 1; }
  tok=$(printf '%s' "$resp" | json_field token) || {
    log "installation token missing from API response"; return 1; }
  [ -z "$tok" ] && { log "installation token missing from API response"; return 1; }
  printf '%s\n' "$tok"
}

# Every credential path is target-bound, including the temporary PAT/gh bootstrap fallback.
require_target_repo || exit 1

# --- which path? (diagnostic, prints NO secret) --------------------------------------------
if [ "$MODE" = "--which" ]; then
  if app_creds_present && require_target_repo && mint_app_token >/dev/null; then
    echo "app (limen[bot] exact-repository installation token)"
  elif app_creds_present; then echo "blocked (exact-repository App token unavailable)"; exit 1
  elif app_creds_configured; then echo "blocked (GitHub App credentials are incomplete)"; exit 1
  elif [ "$APP_ONLY" = "1" ]; then echo "blocked (App-only mode requires GitHub App credentials)"; exit 1
  elif [ -n "${GITHUB_TOKEN:-}" ]; then echo "pat (GITHUB_TOKEN fallback)"
  elif command -v gh >/dev/null 2>&1 && gh auth token >/dev/null 2>&1; then echo "gh (gh auth token fallback)"
  else echo "none (no credential available)"; fi
  exit 0
fi

if [ "$MODE" = "--verify-app" ]; then
  app_creds_present || { log "missing GITHUB_APP_ID or GITHUB_APP_PRIVATE_KEY"; exit 2; }
  mint_app_token >/dev/null || exit 1
  echo "app verified (limen[bot] exact-repository installation token mint succeeds)"
  exit 0
fi

# --- cascade ------------------------------------------------------------------------------
if [ "$APP_ONLY" = "1" ]; then
  app_creds_present || { log "App-only mode requires complete GitHub App credentials"; exit 1; }
  if tok=$(mint_app_token); then printf '%s\n' "$tok"; exit 0; fi
  log "App-only exact target mint failed — refusing every broader credential"
  exit 1
fi
if app_creds_configured && ! app_creds_present; then
  log "GitHub App credentials are incomplete — refusing PAT/gh credential broadening"
  exit 1
fi
if app_creds_present; then
  if tok=$(mint_app_token); then printf '%s\n' "$tok"; exit 0; fi
  log "App path failed for exact target — refusing PAT/gh credential broadening"
  exit 1
fi
if [ -n "${GITHUB_TOKEN:-}" ]; then printf '%s\n' "$GITHUB_TOKEN"; exit 0; fi
if command -v gh >/dev/null 2>&1 && tok=$(gh auth token 2>/dev/null) && [ -n "$tok" ]; then
  printf '%s\n' "$tok"; exit 0
fi
log "no credential available: set GITHUB_APP_ID+GITHUB_APP_PRIVATE_KEY, or GITHUB_TOKEN, or run 'gh auth login'"
exit 1
