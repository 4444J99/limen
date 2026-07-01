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
#   • install ALSO wires ~/.zshenv to export the token, so op is promptless in EVERY shell too —
#     your interactive `op read`, scripts, and ~/.config/op/secrets.zsh's cache refresh all read the
#     SAME one file. (The token file alone silences only the fleet; the ~/.zshenv export silences you.)
# One control point, touched once, controlling all of it.
#
# The token VALUE is NEVER printed, never placed in argv (so it can't land in shell history or `ps`),
# and never enters an agent's context — it is read from STDIN and written straight to the chmod-600 file.
#
# Usage:
#   scripts/op-service-account.sh install        # paste the token (TTY, hidden) → writes file + wires ~/.zshenv
#   pbpaste | scripts/op-service-account.sh install
#   op read "op://Personal/limen-fleet SA/token" | scripts/op-service-account.sh install   # if you saved it in 1Password
#   scripts/op-service-account.sh status         # promptless right now? fleet + login-shell wiring (no value)
#   scripts/op-service-account.sh remove         # delete the token file AND unwire ~/.zshenv (revert to biometric)
set -uo pipefail

SA_FILE="${LIMEN_OP_SA_TOKEN_FILE:-$HOME/.config/op/service-account-token}"
ZSHENV="$HOME/.zshenv"                    # universal home: sourced by EVERY zsh → op promptless everywhere
SENTINEL_BEGIN="# >>> limen:op-sa-token >>>"
SENTINEL_END="# <<< limen:op-sa-token <<<"
ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)"
log() { echo "op-service-account: $*" >&2; }

promptless_ok() {
  # True iff `op` can authenticate with NO interactive prompt using the token in the file.
  # Runs op in a child with ONLY the token exported; never prints the value.
  [ -s "$SA_FILE" ] || return 1
  OP_SERVICE_ACCOUNT_TOKEN="$(cat "$SA_FILE")" op whoami >/dev/null 2>&1
}

# ── Login-shell wiring ────────────────────────────────────────────────────────────────────────────
# Materializing the token FILE makes only the limen fleet promptless — it reads the file directly. For
# op to be promptless in the human's OWN shells too (interactive `op read`, scripts, and secrets.zsh's
# cache refresh), the login environment must export OP_SERVICE_ACCOUNT_TOKEN from that same file. ~/.zshenv
# is sourced by EVERY zsh, so a guarded export block there covers every context. No token value is ever
# read or printed by any function here — only the path is handled.
shell_block() {
  # The exact managed block, bracketed by sentinels so it can be detected + removed idempotently.
  cat <<'BLOCK'
# >>> limen:op-sa-token >>>  (managed by scripts/op-service-account.sh — do not edit between sentinels)
# THE one control point. Install the token once with scripts/op-service-account.sh; from then on every
# `op read` in any shell — interactive, script, GUI-spawned, launchd — runs with ZERO Touch-ID, because
# op authenticates via this env var instead of the biometric desktop-app integration. This is what makes
# ~/.config/op/secrets.zsh's cache refresh and any interactive `op` promptless, reading the SAME file the
# limen fleet reads. Guarded: a pure no-op until the token file exists, so behaviour with no token
# installed is unchanged (op falls back to the desktop-app integration exactly as before).
if [[ -z "${OP_SERVICE_ACCOUNT_TOKEN:-}" && -r "$HOME/.config/op/service-account-token" ]]; then
  export OP_SERVICE_ACCOUNT_TOKEN="$(<"$HOME/.config/op/service-account-token")"
fi
# <<< limen:op-sa-token <<<
BLOCK
}

shell_wired() {
  # True iff the login-shell export block is present in ~/.zshenv.
  [ -f "$ZSHENV" ] && grep -qF "$SENTINEL_BEGIN" "$ZSHENV"
}

ensure_shell_wired() {
  # Idempotently append the export block to ~/.zshenv so op is promptless in EVERY shell, not just limen.
  if shell_wired; then
    log "login shell already wired ($ZSHENV exports the token) — op is promptless in every shell."
    return 0
  fi
  { [ -s "$ZSHENV" ] && printf '\n'; shell_block; } >> "$ZSHENV"
  log "wired the login shell: appended the op-sa-token export block to $ZSHENV."
  log "new shells + secrets.zsh's cache refresh now read the token from the same file — promptless."
}

unwire_shell() {
  # Strip the sentinel-bracketed block (inclusive) from ~/.zshenv, plus the single separator blank line
  # ensure_shell_wired added right before it — so remove is a byte-clean reverse of install's wiring.
  # index() = literal substring match (regex-safe against the '>' chars in the sentinels).
  shell_wired || return 0
  local tmp; tmp="$(mktemp)"
  awk -v b="$SENTINEL_BEGIN" -v e="$SENTINEL_END" '
    index($0, b) { skip = 1; held = 0; next }         # entering block: drop the held separator blank + BEGIN
    index($0, e) { skip = 0; next }                   # END line: drop
    skip == 1    { next }                             # block body: drop
    {
      if (held)                    { print held_line; held = 0 }
      if ($0 ~ /^[[:space:]]*$/)   { held = 1; held_line = $0; next }
      print
    }
    END { if (held) print held_line }
  ' "$ZSHENV" > "$tmp" && mv "$tmp" "$ZSHENV"
  log "removed the op-sa-token export block from $ZSHENV — shells revert to biometric op."
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
      # Make op promptless in the human's OWN shells too (not just the fleet), reading the same file.
      ensure_shell_wired
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
    if shell_wired; then
      log "login shell WIRED: $ZSHENV exports the token for EVERY shell (interactive/script/GUI/launchd). ✓"
    else
      log "login shell NOT wired: $ZSHENV has no op-sa-token block → interactive op + secrets.zsh still prompt."
      log "  → run 'install' to wire it (it self-wires on install once the token verifies)."
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
    unwire_shell   # also strip the ~/.zshenv export block so the revert is complete
    exit 0
    ;;
  -h|--help|help)
    sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
    ;;
  *)
    log "unknown mode '${1:-}'. Use: install | status | remove | help"
    exit 2
    ;;
esac
