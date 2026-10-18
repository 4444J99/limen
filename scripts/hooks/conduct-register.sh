#!/usr/bin/env bash
# conduct-register.sh — register a background Claude job with the conduct broker.
#
# A background job is a direct session nobody launched through start-worktree-session.sh, so
# it never got the `--conduct` registration that launcher performs. Without a broker binding the
# session-release predicate (scripts/no-tasks-on-me.sh) exits 2 "no broker binding or exact
# native-session witness" and the session can never prove release. This hook performs the SAME
# registration through the SAME function (workstream_register_conduct_session), so the values
# (surface, origin, human-protected, concurrency, lane capabilities) are the launcher's, not copies.
#
# Wired from the project's .claude/settings.json on SessionStart and PostToolUse. A job starts in
# the shared checkout and only later isolates into a worktree (EnterWorktree), and the broker
# refuses a second healthy session on one worktree path. So the hook:
#   * registers only once the session's cwd is inside .claude/worktrees/<name> — never the shared
#     checkout, which no single job owns;
#   * re-registers on a worktree change, and refreshes the heartbeat at most once per interval
#     (LIMEN_CONDUCT_REGISTER_INTERVAL_SECS, default 120; the broker session TTL is 5 minutes);
#   * is a clean no-op outside a background job (CLAUDE_JOB_DIR unset) and outside this project.
#
# FAIL-OPEN BY CONSTRUCTION: a hook cannot be allowed to wedge a session. Every failure is logged to
# $CLAUDE_JOB_DIR/tmp/conduct-register.log and the script exits 0. It writes NOTHING to stdout
# (SessionStart stdout is injected as model context).
#
# IDENTITY IS THE BEARER, NOT THE FLAG. The broker overwrites a session's agent/surface with those of
# the bearer's principal (_bind_session_identity), and a session id is pinned to its FIRST identity
# (re-registering under another is a 409, and there is no deregister). So this hook registers only
# with the lane's own bearer (LIMEN_CONDUCT_TOKEN_CLAUDE -> principal claude-direct) and refuses,
# loudly in the log, rather than fall back to the default LIMEN_CONDUCT_TOKEN (the legacy
# codex-direct-legacy principal), which would label a Claude job "codex" irreversibly. Credentials
# are read from the user-owned mode-600 cache (or the environment), consumed by the CLI, and never
# printed, logged, or written to the stamp.
#
# NEVER probe this against the real broker with a real session id: a wrong first registration is
# permanent. Drive it with a throwaway session id and read the broker's record back first.
set -uo pipefail

[ -n "${CLAUDE_JOB_DIR:-}" ] || exit 0                      # background jobs only

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
[ -f "$ROOT/scripts/lib/workstream-capsule.sh" ] || exit 0   # not a limen checkout -> no-op

payload=""
[ -t 0 ] || payload="$(cat)"

json_field() {  # $1 = key; first string value of that key in the flat hook payload
  printf '%s' "$payload" | sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" | head -n 1
}
sid="$(json_field session_id)"
cwd="$(json_field cwd)"
[ -n "$sid" ] && [ -n "$cwd" ] || exit 0

case "$cwd" in
  */.claude/worktrees/*)
    rest="${cwd#*/.claude/worktrees/}"
    name="${rest%%/*}"
    [ -n "$name" ] || exit 0
    wt="${cwd%%/.claude/worktrees/*}/.claude/worktrees/$name"
    ;;
  *) exit 0 ;;                                               # shared checkout: claim nothing
esac

state_dir="$CLAUDE_JOB_DIR/tmp"
stamp="$state_dir/conduct-register.stamp"
log="$state_dir/conduct-register.log"
interval="${LIMEN_CONDUCT_REGISTER_INTERVAL_SECS:-120}"
now="$(date +%s)"

# Stamp: <session-id> <worktree> <attempt-epoch> <hold-until-epoch>. The 4th field is 0 unless the
# broker answered the last attempt with a spent write quota (Cloudflare free tier, resets 00:00 UTC;
# owner 4444J99/limen#2054): until that epoch no attempt can succeed, so none is made — no python,
# no limen process, nothing appended to the log. Registration resumes by itself at the reset.
if [ -f "$stamp" ]; then
  read -r s_sid s_wt s_epoch s_hold < "$stamp" 2>/dev/null || true
  if [ "${s_sid:-}" = "$sid" ] && [ "${s_wt:-}" = "$wt" ]; then
    if [ -n "${s_hold:-}" ] && [ "$s_hold" -gt "$now" ] 2>/dev/null; then
      exit 0                                                 # broker write quota spent: holding
    fi
    if [ -n "${s_epoch:-}" ] && [ $((now - s_epoch)) -lt "$interval" ] 2>/dev/null; then
      exit 0                                                 # fresh registration for this worktree
    fi
  fi
fi

next_utc_midnight() {  # epoch of the next 00:00 UTC (the daily reset); 0 when no date flavour parses
  local today base
  today="$(date -u +%Y-%m-%d)"
  base="$(date -u -j -f '%Y-%m-%d %H:%M:%S' "$today 00:00:00" +%s 2>/dev/null)" \
    || base="$(date -u -d "$today 00:00:00" +%s 2>/dev/null)" \
    || base=""
  case "$base" in ''|*[!0-9]*) echo 0 ;; *) echo $((base + 86400)) ;; esac
}

mkdir -p "$state_dir" 2>/dev/null || exit 0
# Record the attempt first so a failing broker costs at most one attempt per interval.
printf '%s %s %s %s\n' "$sid" "$wt" "$now" 0 > "$stamp" 2>/dev/null || true

# shellcheck source=scripts/lib/workstream-capsule.sh
source "$ROOT/scripts/lib/workstream-capsule.sh" >>"$log" 2>&1 || exit 0

# IDENTITY: the broker binds a session's agent/surface to the principal of the bearer, whatever
# --agent says. The default LIMEN_CONDUCT_TOKEN is the legacy codex-direct-legacy bearer, so
# registering with it labels this Claude job "codex" (observed 2026-10-18). Unset it BEFORE hydrating
# so hydrate always validates the cache (user-owned, mode 600), then use the lane's own bearer
# (claude-direct) and never fall back: no lane bearer means no registration, not a mislabeled one.
unset LIMEN_CONDUCT_TOKEN
cache="${LIMEN_CONDUCT_ENV_FILE:-$HOME/.limen.env}"
workstream_hydrate_conduct_environment >>"$log" 2>&1 || {
  printf '%s NOT registered session=%s: conduct credential cache unusable\n' "$(date -u +%FT%TZ)" "$sid" >>"$log"
  exit 0
}
lane_token="${LIMEN_CONDUCT_TOKEN_CLAUDE:-}"
if [ -z "$lane_token" ] && [ -e "$cache" ]; then
  lane_token="$(bash -c 'set -a; . "$1" >/dev/null 2>&1; set +a; printf "%s" "${LIMEN_CONDUCT_TOKEN_CLAUDE:-}"' _ "$cache" 2>/dev/null)" || lane_token=""
fi
if [ -z "$lane_token" ]; then
  printf '%s NOT registered session=%s: no LIMEN_CONDUCT_TOKEN_CLAUDE; refusing the default bearer (it would label this job codex)\n' \
    "$(date -u +%FT%TZ)" "$sid" >>"$log"
  exit 0
fi
export LIMEN_CONDUCT_TOKEN="$lane_token"
unset lane_token

if [ -z "${LIMEN_CLI_BIN:-}" ] && ! command -v limen >/dev/null 2>&1 && [ -x "$HOME/.local/bin/limen" ]; then
  export LIMEN_CLI_BIN="$HOME/.local/bin/limen"
fi

caps="$(PYTHONPATH="$ROOT/cli/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c '
from limen.census import by_name
print(" ".join(sorted(by_name("claude").execution.capabilities)))' 2>/dev/null)" || caps=""
[ -n "$caps" ] || caps="code conduct review"                 # the launcher's own fallback set

# The function sets workstream_protected_registration in THIS shell, so its output goes to a file
# (a command substitution would run it in a subshell and lose the flag). The file holds the same
# text the log already receives — broker error text, never the bearer — and is read once for the
# quota verdict, then appended and removed.
attempt="$state_dir/conduct-register.attempt"
workstream_protected_registration=0
LIMEN_SESSION_ID="$sid" workstream_register_conduct_session claude "$wt" "$caps" >"$attempt" 2>&1
rc=$?
cat "$attempt" >>"$log" 2>/dev/null
if [ "$rc" -eq 0 ] && [ "${workstream_protected_registration:-0}" = 1 ]; then
  printf '%s registered session=%s worktree=%s\n' "$(date -u +%FT%TZ)" "$sid" "$wt" >>"$log"
elif grep -qE 'BrokerQuotaExhausted|Exceeded allowed rows written' "$attempt" 2>/dev/null; then
  hold="$(next_utc_midnight)"
  printf '%s %s %s %s\n' "$sid" "$wt" "$now" "$hold" > "$stamp" 2>/dev/null || true
  printf '%s NOT registered session=%s worktree=%s rc=%s: broker write quota spent; holding registration until %s (owner 4444J99/limen#2054)\n' \
    "$(date -u +%FT%TZ)" "$sid" "$wt" "$rc" "$(date -u -r "$hold" +%FT%TZ 2>/dev/null || date -u -d "@$hold" +%FT%TZ 2>/dev/null || echo "epoch $hold")" >>"$log"
else
  printf '%s NOT registered session=%s worktree=%s rc=%s\n' "$(date -u +%FT%TZ)" "$sid" "$wt" "$rc" >>"$log"
fi
rm -f "$attempt" 2>/dev/null
exit 0
