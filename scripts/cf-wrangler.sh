#!/usr/bin/env bash
# cf-wrangler.sh — the ONE headless entry to `wrangler`. Never prompts `wrangler login`.
#
# Why this exists (the durable fix, 2026-07-01): wrangler falls back to an interactive
# `wrangler login` OAuth prompt the moment it cannot find CLOUDFLARE_API_TOKEN in the
# environment. Every worktree and every dispatched Cloudflare lane hit that prompt because
# (a) the token was never materialized into ~/.limen.env and (b) the call sites (web/worker's
# `npm run deploy`, ad-hoc agent runs) never sourced that file. So the credit organ's ONE
# spot (1Password -> ~/.limen.env, see scripts/creds-hydrate.py DEFAULT_MAP `cloudflare` lane)
# was bypassed on every invocation. That is the recurring "log into wrangler again" disease.
#
# This wrapper closes it structurally, so a login prompt is UNREACHABLE from this repo:
#   1. Source ~/.limen.env — the ONE credential home — so CLOUDFLARE_API_TOKEN is present
#      exactly where wrangler already looks for it. No login, no per-worktree re-auth.
#   2. Export CI=1 — wrangler NEVER opens an interactive prompt under CI; it fails with a
#      clear error instead. So a missing/dead token yields a one-line failure pointing at
#      1Password, never a `wrangler login` nag.
#   3. If the token is absent, fail LOUDLY with the single irreducible human action:
#      re-mint the API token ONCE and paste it into op://Personal/Cloudflare API Token.
#      That is a paste into the ONE spot — never a login command, never per-worktree.
#
# Usage (drop-in for `wrangler`):
#   bash scripts/cf-wrangler.sh deploy
#   bash scripts/cf-wrangler.sh pages deploy ./out
#   bash scripts/cf-wrangler.sh --which   # report token source + validity intent (no value printed)
#
# The token itself is NEVER printed (behind the same discipline as creds-hydrate's _scrub()).
set -uo pipefail

log() { echo "cf-wrangler: $*" >&2; }
ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"

find_local_wrangler() {
  local dir candidate
  dir="$PWD"
  while [ -n "$dir" ] && [ "$dir" != "/" ]; do
    candidate="$dir/node_modules/.bin/wrangler"
    if [ -x "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  case "$PWD/" in
    "$ROOT/"*)
      for dir in "$ROOT/web/worker" "$ROOT"; do
        candidate="$dir/node_modules/.bin/wrangler"
        if [ -x "$candidate" ]; then
          printf '%s\n' "$candidate"
          return 0
        fi
      done
      ;;
  esac
  return 1
}

# 1. Load the ONE credential home the same way the rest of the fleet does (chmod 600, never a shell rc).
#    This reads a FILE — it NEVER pings 1Password. op is touched exactly once, by an explicit
#    `creds-hydrate --apply` (or at login), which materializes the token here; from then on every
#    deploy reads this file and 1Password is never prompted again. That is the "once, then never"
#    contract — so this wrapper deliberately has NO `op read` fallback (a per-deploy op read would
#    re-ping 1Password on every run, which is exactly the disease we are curing).
ENV_FILE="${LIMEN_ENV:-$HOME/.limen.env}"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a

# 2. wrangler must never drop to an interactive login from this repo.
export CI="${CI:-1}"
export WRANGLER_SEND_METRICS="${WRANGLER_SEND_METRICS:-false}"

# --which: report the credential state without running wrangler and without printing the value.
if [ "${1:-}" = "--which" ]; then
  if [ -n "${CLOUDFLARE_API_TOKEN:-}" ]; then
    log "CLOUDFLARE_API_TOKEN present (len ${#CLOUDFLARE_API_TOKEN}) — wrangler runs headless."
    log "validity is NOT checked here; run: python3 scripts/creds-hydrate.py --verify"
    exit 0
  fi
  log "CLOUDFLARE_API_TOKEN ABSENT."
  exit 3
fi

# 3. No token in the env home -> materialize it once. NOT a login prompt, NOT a per-deploy op read.
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
  log "CLOUDFLARE_API_TOKEN not in ${ENV_FILE}."
  log "Run ONCE (the single op touch — never per deploy, never 'wrangler login'):"
  log "  python3 scripts/creds-hydrate.py --apply --op"
  log "That materializes the token from 1Password into ${ENV_FILE}; every wrangler call is headless"
  log "thereafter. (For ZERO 1Password prompts even on that one run, install a service-account token"
  log "at ~/.config/op/service-account-token — then op authenticates non-interactively.)"
  exit 3
fi

# Prefer the nearest repo-local wrangler, then Limen's worker-local wrangler, then global/npx.
LOCAL_WRANGLER="$(find_local_wrangler || true)"
if [ -n "$LOCAL_WRANGLER" ]; then
  exec "$LOCAL_WRANGLER" "$@"
fi
if command -v wrangler >/dev/null 2>&1; then
  exec wrangler "$@"
fi
exec npx --yes wrangler "$@"
