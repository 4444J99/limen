#!/usr/bin/env bash
# mail-beat.sh — the C_MAIL organ: the inbound mail lane, autonomic + fail-open.
#
# Each C_MAIL beat:
#   1. SWEEP every Apple Mail account, keylessly + reversibly — flag the fires (a status
#      bit Gmail respects) and archive folder-store noise (iCloud/Outlook, reliable). The
#      futile/blocked Gmail bulk-archive is SKIPPED (--flag-only-gmail) so the beat stays
#      bounded; the Gmail-archive leg lights up automatically once a write door opens
#      (L-MCP / L-OAUTH / L-IMAP-APP-PW — surfaced as owned levers in the ledger).
#   2. BUILD the obligations ledger from the fresh receipts (derived, no LLM, no network).
#   3. RENDER the pervasive faces (obligations.html → 127.0.0.1:8787/obligations.html).
#
# Reversible-only (flag/archive-to-mailbox; never delete, never send). Every step is
# wrapped so one failure never aborts the beat or the daemon ([[no-never-happens-again]]).
# Opt out of the mutating sweep with LIMEN_MAIL_SWEEP=0 (still rebuilds the ledger/face).
set -uo pipefail
export HOME="${HOME:-/Users/4jp}"
LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
UMA_ROOT="${UMA_ROOT:-$HOME/Workspace/universal-mail--automation}"
LEDGER="${LIMEN_OBLIGATIONS_LEDGER:-$LIMEN_ROOT/obligations-ledger.json}"
PY="${LIMEN_PY:-python3}"

# DAEMON-SAFETY: never let a hung/slow Mail AppleScript block the heartbeat beat. Two
# structural bounds: (1) the sweep reads only the most-recent N messages (new arrivals —
# the full backlog was already swept), so each account is a couple of paged reads, not the
# whole inbox; (2) every step runs under `timeout` when available (homebrew coreutils on the
# daemon PATH), so even an unresponsive Mail.app can't stall the beat. Without `timeout`,
# the small --limit + the provider's per-call 30s AppleScript cap keep it bounded anyway.
SWEEP_LIMIT="${LIMEN_MAIL_SWEEP_LIMIT:-80}"
TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
bounded() {  # bounded <secs> <cmd...>  — time-box if a timeout binary exists, else run plain
  if [ -n "$TIMEOUT_BIN" ]; then "$TIMEOUT_BIN" "$@"; else shift; "$@"; fi
}
run_tmp() {  # run_tmp <secs> <cmd...>  — run with cwd=/tmp (avoids the platform/ shadow), bounded, fail-open
  local secs="$1"; shift
  bounded "$secs" bash -c 'cd /tmp && exec "$@"' _ "$@" 2>&1 | tail -1 || true
}

# 1) SWEEP — reversible flag+archive per account. Account names come straight from Mail
#    (no creds, no python import). The futile Gmail archive is skipped; iCloud/Outlook
#    (folder stores) archive reliably; fires flag everywhere. Heavy AppleScript reads, so
#    this runs on the C_MAIL cadence, not every beat.
if [ "${LIMEN_MAIL_SWEEP:-1}" = "1" ]; then
  accts="$(osascript -e 'tell application "Mail" to get name of every account' 2>/dev/null || true)"
  if [ -n "$accts" ]; then
    OLDIFS="$IFS"; IFS=','
    for a in $accts; do
      a="${a#"${a%%[![:space:]]*}"}"; a="${a%"${a##*[![:space:]]}"}"   # trim
      [ -z "$a" ] && continue
      run_tmp 240 "$PY" "$UMA_ROOT/inbox_sweep.py" --account "$a" --apply --flag-only-gmail --limit "$SWEEP_LIMIT"
    done
    IFS="$OLDIFS"
  else
    echo "mail-beat: no Mail accounts enumerated (Automation permission? skipping sweep)"
  fi
fi

# 2) BUILD the ledger from the receipts (keyless, derived, fail-open) — includes the
#    propose-mode unsubscribe noise-killers.
run_tmp 120 "$PY" "$UMA_ROOT/obligations_build.py" --out "$LEDGER"

# 2b) DRAFT — enrich reply-owed obligations with a voice-matched draft (NEVER sent).
#     Persist to Drafts only when LIMEN_MAIL_DRAFTS=1 (idempotent); else enrich-only so the
#     ready draft is visible in the ledger/face without touching the mailbox.
DRAFT_SAVE=""; [ "${LIMEN_MAIL_DRAFTS:-0}" = "1" ] && DRAFT_SAVE="--save"
run_tmp 180 "$PY" "$UMA_ROOT/draft_writer.py" --ledger "$LEDGER" $DRAFT_SAVE

# 3) RENDER the pervasive faces (pure stdlib, no Mail I/O — short bound).
bounded 60 "$PY" "$LIMEN_ROOT/scripts/obligations-view.py" 2>&1 | tail -1 || true
