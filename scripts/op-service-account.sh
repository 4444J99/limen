#!/usr/bin/env bash
# op-service-account.sh — install the 1Password SERVICE-ACCOUNT TOKEN once, and op is promptless FOREVER.
#
# THE ONE SPOT. A 1Password service-account token is the ONLY `op` auth mode that reads secrets with
# ZERO interactive prompt — no Touch-ID, no GUI dialog, ever. Every other mode (the desktop-app
# integration / op-daemon.sock) re-locks on each read and pops a fingerprint. Install the token once at
#   ~/.config/op/service-account-token   (override: LIMEN_OP_SA_TOKEN_FILE)
# and from that instant:
#   • `scripts/creds-hydrate.py --apply` sweeps every op:// lane into ~/.limen.env with no prompt,
#   • `--sweep-all` materializes EVERY credential in the automation vaults (full-scope sweep),
#   • the metabolize beat re-hydrates them forever, unattended,
#   • your dotfiles op-refresh (~/.config/op/secrets.zsh) ALSO goes promptless — same env token.
# One control point, touched once, controlling all of it.
#
# The token VALUE is NEVER printed, never placed in argv (so it can't land in shell history or `ps`),
# and never enters an agent's context — it is read from STDIN and written straight to the chmod-600 file.
#
# Usage:
#   scripts/op-service-account.sh install        # paste the token at the silent prompt (TTY), or:
#   pbpaste | scripts/op-service-account.sh install
#   op read "op://Personal/limen-fleet SA/token" | scripts/op-service-account.sh install   # if you saved it in 1Password
#   scripts/op-service-account.sh status         # is op promptless right now? (no value shown)
#   scripts/op-service-account.sh remove         # delete the token file (revert to biometric op)
set -uo pipefail

SA_FILE="${LIMEN_OP_SA_TOKEN_FILE:-$HOME/.config/op/service-account-token}"
ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
log() { echo "op-service-account: $*" >&2; }

promptless_ok() {
  # True iff `op` can authenticate with NO interactive prompt using the token in the file.
  # Runs op in a child with ONLY the token exported; never prints the value.
  [ -s "$SA_FILE" ] || return 1
  OP_SERVICE_ACCOUNT_TOKEN="$(cat "$SA_FILE")" op whoami >/dev/null 2>&1
}

case "${1:-status}" in
  install)
    umask 077
    mkdir -p "$(dirname "$SA_FILE")"
    if [ -t 0 ]; then
      # Interactive: read silently so the token never appears on screen or in history.
      printf 'Paste the 1Password service-account token (input hidden), then Enter: ' >&2
      IFS= read -rs TOKEN; echo >&2
    else
      # Piped: take the first non-empty line from stdin.
      IFS= read -r TOKEN || true
    fi
    if [ -z "${TOKEN:-}" ]; then
      log "no token on stdin — nothing written. (Pipe it, or run at a terminal and paste.)"
      exit 2
    fi
    # Shape check WITHOUT echoing the value: service-account tokens are prefixed 'ops_'.
    case "$TOKEN" in
      ops_*) : ;;
      *) log "warning: token does not start with 'ops_' — that is the 1Password service-account prefix."
         log "proceeding anyway (a Connect token or future format may differ), but double-check if op fails." ;;
    esac
    # Write atomically, chmod 600, value never echoed.
    TMP="$(mktemp "$(dirname "$SA_FILE")/.sa.XXXXXX")"
    printf '%s' "$TOKEN" > "$TMP"; unset TOKEN
    chmod 600 "$TMP"; mv -f "$TMP" "$SA_FILE"
    log "wrote token to $SA_FILE (chmod 600, value not shown)."
    if promptless_ok; then
      log "VERIFIED: op authenticates with ZERO prompt. 1Password will never ask for a fingerprint on a"
      log "fleet read again. Sweeping all credentials into ~/.limen.env now…"
      python3 "$ROOT/scripts/creds-hydrate.py" --apply || true
      python3 "$ROOT/scripts/creds-hydrate.py" --sweep-all --apply || true
      log "done. The metabolize beat keeps them fresh forever. Run 'creds-hydrate --verify' to confirm validity."
      exit 0
    fi
    log "token written but 'op whoami' still failed. Likely causes: the token is revoked, or this account"
    log "has no service account (Business/Teams feature). Fix the token, re-run install. (File left in place.)"
    exit 1
    ;;
  status)
    if [ -n "${OP_SERVICE_ACCOUNT_TOKEN:-}" ]; then
      log "OP_SERVICE_ACCOUNT_TOKEN is set in THIS env → op reads are promptless here."
    fi
    if [ -s "$SA_FILE" ]; then
      if promptless_ok; then
        log "PROMPTLESS: $SA_FILE present and op authenticates with no prompt. Full-access, zero-fingerprint. ✓"
        exit 0
      fi
      log "token file present at $SA_FILE but 'op whoami' failed — token may be revoked/invalid. ✗"
      exit 1
    fi
    log "NO service-account token at $SA_FILE → op falls back to the desktop-app integration (Touch-ID per read)."
    log "Install it once to go promptless forever:  scripts/op-service-account.sh install"
    exit 1
    ;;
  remove)
    if [ -f "$SA_FILE" ]; then
      rm -f "$SA_FILE"; log "removed $SA_FILE — op reverts to biometric (desktop-app) auth."
    else
      log "nothing to remove ($SA_FILE absent)."
    fi
    exit 0
    ;;
  -h|--help|help)
    sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *)
    log "unknown mode '${1:-}'. Use: install | status | remove | help"
    exit 2
    ;;
esac
