#!/usr/bin/env bash
# Hermetic matrix for scripts/hooks/conduct-register.sh — the hook that gives a background Claude job
# the broker registration start-worktree-session.sh --conduct gives a launched one.
#
# A fake `limen` records its argv, so nothing talks to a real broker, reads a real credential cache,
# or touches the real $HOME. The negative rows are the deliverable: a registration hook that fires
# in the shared checkout, outside a background job, or on every tool call is worse than none.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$ROOT/scripts/hooks/conduct-register.sh"

FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT

export HOME="$FIX/home"
export LIMEN_CONDUCT_ENV_FILE="$FIX/absent.env"          # hydrate is a no-op: no cache to read
mkdir -p "$HOME" "$FIX/bin" "$FIX/repo/.claude/worktrees/wt1/sub" "$FIX/repo/.claude/worktrees/wt2"

export CALLS="$FIX/calls.txt"
export CALLS_ENV="$FIX/calls-env.txt"
cat > "$FIX/bin/limen" <<'FAKE'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$CALLS"
case "${LIMEN_CONDUCT_TOKEN:-}" in
  LANESECRET) label=lane ;; LEGACYSECRET) label=legacy ;; "") label=none ;; *) label=other ;;
esac
printf 'bearer:%s\n' "$label" >> "$CALLS_ENV"        # a label, never the value
exit "${FAKE_BROKER_EXIT:-0}"
FAKE
chmod +x "$FIX/bin/limen"
export LIMEN_CLI_BIN="$FIX/bin/limen"
# Default credentials for the registration rows: the lane's own bearer (identity rows override these).
export LIMEN_CONDUCT_URL=http://127.0.0.1:1 LIMEN_CONDUCT_TOKEN_CLAUDE=LANESECRET

pass=0 fail=0
check() {  # $1 = label, $2 = 0|1 (1 = the condition held)
  if [ "$2" = 1 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); printf 'FAIL: %s\n' "$1" >&2; fi
}
ok() { if "$@"; then echo 1; else echo 0; fi; }       # run a condition, print 1|0 for check
calls() { if [ -f "$CALLS" ]; then wc -l < "$CALLS" | tr -d ' '; else echo 0; fi; }
reset() { rm -rf "$FIX/job" "$CALLS" "$CALLS_ENV"; mkdir -p "$FIX/job/tmp"; export CLAUDE_JOB_DIR="$FIX/job"; }
payload() { python3 -c 'import json,sys; print(json.dumps({"session_id":sys.argv[1],"cwd":sys.argv[2],"hook_event_name":"PostToolUse"}))' "$1" "$2"; }
# run <session-id> <cwd>: current-shell call (no subshell) so OUT and RC survive for the checks.
# The payload goes in via a file, not a pipe: a hook that exits early without reading stdin would
# otherwise hand the writer a SIGPIPE, and pipefail would report the writer's failure as the hook's.
run() { payload "$1" "$2" > "$FIX/payload.json"; OUT="$("$HOOK" < "$FIX/payload.json" 2>/dev/null)"; RC=$?; }

is_zero() { [ "$1" = "$2" ]; }
silent() { [ -z "$OUT" ]; }
exited_ok() { [ "$RC" = 0 ]; }

WT1="$FIX/repo/.claude/worktrees/wt1"
WT2="$FIX/repo/.claude/worktrees/wt2"

# ── No-op rows ───────────────────────────────────────────────────────────────
reset; unset CLAUDE_JOB_DIR
run S1 "$WT1"
check "not a background job -> no registration" "$(ok is_zero "$(calls)" 0)"
check "not a background job -> exit 0" "$(ok exited_ok)"
check "not a background job -> silent stdout" "$(ok silent)"

reset
run S1 "$FIX/repo"
check "shared checkout (no worktree) -> claims nothing" "$(ok is_zero "$(calls)" 0)"
check "shared checkout -> exit 0" "$(ok exited_ok)"
check "shared checkout -> silent stdout (SessionStart stdout is model context)" "$(ok silent)"
check "shared checkout -> logs a 'skipped' line naming the session (issue 3102)" \
  "$(ok grep -q 'skipped session=S1' "$CLAUDE_JOB_DIR/tmp/conduct-register.log")"
run S1 "$FIX/repo"; run S1 "$FIX/repo"
check "shared checkout -> the skip is logged once per session, not once per tool call" \
  "$(ok is_zero "$(grep -c 'skipped session=S1' "$CLAUDE_JOB_DIR/tmp/conduct-register.log")" 1)"
run S2 "$FIX/repo"
check "shared checkout -> a different session logs its own skip" \
  "$(ok grep -q 'skipped session=S2' "$CLAUDE_JOB_DIR/tmp/conduct-register.log")"
check "shared checkout -> the skip line says how to become claimable" \
  "$(ok grep -q 'EnterWorktree' "$CLAUDE_JOB_DIR/tmp/conduct-register.log")"
check "shared checkout -> still claims nothing after the skips" "$(ok is_zero "$(calls)" 0)"

reset; unset CLAUDE_JOB_DIR
run S1 "$FIX/repo"
check "shared checkout outside a background job -> writes no log" "$(ok test ! -e "$FIX/job/tmp/conduct-register.log")"

reset
printf 'not json' > "$FIX/payload.json"; OUT="$("$HOOK" < "$FIX/payload.json" 2>/dev/null)"; RC=$?
check "malformed payload -> no call" "$(ok is_zero "$(calls)" 0)"
check "malformed payload -> exit 0" "$(ok exited_ok)"
check "malformed payload -> silent stdout" "$(ok silent)"

reset
printf '{"cwd":"%s"}' "$WT1" > "$FIX/payload.json"; OUT="$("$HOOK" < "$FIX/payload.json" 2>/dev/null)"; RC=$?
check "payload without session_id -> no call" "$(ok is_zero "$(calls)" 0)"

# ── The registration itself ──────────────────────────────────────────────────
reset
run S1 "$WT1/sub"
check "worktree subdirectory -> exactly one registration" "$(ok is_zero "$(calls)" 1)"
check "registration -> exit 0" "$(ok exited_ok)"
check "registration prints nothing to stdout" "$(ok silent)"
line="$(head -n 1 "$CALLS" 2>/dev/null || true)"
for want in "conduct register" "--agent claude" "--surface workstream" "--session-id S1" "--origin direct" \
            "--human-protected" "--concurrency 1" "--capability code" "--capability conduct" "--worktree $WT1"; do
  case "$line" in *"$want"*) check "argv carries '$want'" 1 ;; *) check "argv carries '$want' (got: $line)" 0 ;; esac
done
case "$line" in *"--worktree $WT1/sub"*) check "worktree normalised to the worktree root" 0 ;; *) check "worktree normalised to the worktree root" 1 ;; esac

# ── Throttle and re-registration ─────────────────────────────────────────────
run S1 "$WT1"
check "same session + worktree within the interval -> throttled" "$(ok is_zero "$(calls)" 1)"
run S1 "$WT2"
check "worktree change -> re-registers" "$(ok is_zero "$(calls)" 2)"
run S2 "$WT2"
check "different session id -> registers" "$(ok is_zero "$(calls)" 3)"
export LIMEN_CONDUCT_REGISTER_INTERVAL_SECS=0
run S2 "$WT2"
unset LIMEN_CONDUCT_REGISTER_INTERVAL_SECS
check "interval 0 disables the throttle" "$(ok is_zero "$(calls)" 4)"

# ── Fail-open and credential hygiene ─────────────────────────────────────────
reset
export FAKE_BROKER_EXIT=7
run S3 "$WT1"
check "broker failure -> hook still exits 0" "$(ok exited_ok)"
check "broker failure -> silent stdout" "$(ok silent)"
check "broker failure -> logged as NOT registered" "$(ok grep -q 'NOT registered session=S3' "$CLAUDE_JOB_DIR/tmp/conduct-register.log")"
run S3 "$WT1"
unset FAKE_BROKER_EXIT
check "failed attempt is also throttled (no retry storm)" "$(ok is_zero "$(calls)" 1)"

# ── Identity: the broker labels a session by its BEARER's principal, whatever --agent says ──
# The default LIMEN_CONDUCT_TOKEN is the legacy codex-direct-legacy bearer; registering a Claude job
# with it produced a session labelled "codex" (2026-10-18). Only the lane bearer may register.
tokens_used() { sort -u "$CALLS_ENV" 2>/dev/null | tr '\n' ' '; }
cache_file() {  # $1 = mode, rest = lines; writes a credential-cache fixture and points hydrate at it
  local mode="$1"; shift
  printf '%s\n' "$@" > "$FIX/cache.env"; chmod "$mode" "$FIX/cache.env"
  export LIMEN_CONDUCT_ENV_FILE="$FIX/cache.env"
}
reset_creds() { unset LIMEN_CONDUCT_URL LIMEN_CONDUCT_TOKEN LIMEN_CONDUCT_TOKEN_CLAUDE; export LIMEN_CONDUCT_ENV_FILE="$FIX/absent.env"; }

reset; reset_creds
export LIMEN_CONDUCT_URL=http://127.0.0.1:1 LIMEN_CONDUCT_TOKEN=LEGACYSECRET LIMEN_CONDUCT_TOKEN_CLAUDE=LANESECRET
run S4 "$WT1"
check "env: lane bearer is used, the legacy bearer is not" "$([ "$(tokens_used)" = 'bearer:lane ' ] && echo 1 || echo 0)"
check "env: registers exactly once" "$(ok is_zero "$(calls)" 1)"
check "env: lane bearer never reaches stdout" "$(ok silent)"
check "env: no bearer value in the job dir (log/stamp)" "$(ok sh -c "! grep -rqE 'LANESECRET|LEGACYSECRET' '$CLAUDE_JOB_DIR'")"
check "env: no bearer value in the argv record" "$(ok sh -c "! grep -qE 'LANESECRET|LEGACYSECRET' '$CALLS'")"

reset; reset_creds
export LIMEN_CONDUCT_URL=http://127.0.0.1:1 LIMEN_CONDUCT_TOKEN=LEGACYSECRET
run S5 "$WT1"
check "env: only the legacy bearer present -> refuses to register" "$(ok is_zero "$(calls)" 0)"
check "env: refusal exits 0 and says why" "$(ok sh -c "[ '$RC' = 0 ] && grep -q 'refusing the default bearer' '$CLAUDE_JOB_DIR/tmp/conduct-register.log'")"

reset; reset_creds
cache_file 600 "LIMEN_CONDUCT_URL=http://127.0.0.1:1" "LIMEN_CONDUCT_TOKEN=LEGACYSECRET" "LIMEN_CONDUCT_TOKEN_CLAUDE=LANESECRET"
run S6 "$WT1"
check "cache: lane bearer is used, the legacy bearer is not" "$([ "$(tokens_used)" = 'bearer:lane ' ] && echo 1 || echo 0)"
check "cache: no bearer value in the job dir (log/stamp)" "$(ok sh -c "! grep -rqE 'LANESECRET|LEGACYSECRET' '$CLAUDE_JOB_DIR'")"

reset; reset_creds
cache_file 600 "LIMEN_CONDUCT_URL=http://127.0.0.1:1" "LIMEN_CONDUCT_TOKEN=LEGACYSECRET"
run S7 "$WT1"
check "cache: no lane bearer -> refuses, never falls back to legacy" "$(ok is_zero "$(calls)" 0)"

reset; reset_creds
cache_file 644 "LIMEN_CONDUCT_URL=http://127.0.0.1:1" "LIMEN_CONDUCT_TOKEN=LEGACYSECRET" "LIMEN_CONDUCT_TOKEN_CLAUDE=LANESECRET"
run S8 "$WT1"
check "cache: group/world-readable cache is not trusted -> no registration" "$(ok is_zero "$(calls)" 0)"
check "cache: unusable cache is logged, exit 0" "$(ok sh -c "[ '$RC' = 0 ] && grep -q 'credential cache unusable' '$CLAUDE_JOB_DIR/tmp/conduct-register.log'")"

reset_creds

# ── Wiring: the script surviving while its settings entry is removed turns the feature off silently ──
wired() {  # $1 = event; the hook must be present, executable-guarded, and carry a timeout
  python3 - "$ROOT/.claude/settings.json" "$1" <<'PY'
import json, sys
settings, event = sys.argv[1], sys.argv[2]
groups = json.load(open(settings))["hooks"].get(event, [])
hits = [h for g in groups for h in g.get("hooks", []) if "scripts/hooks/conduct-register.sh" in h.get("command", "")]
sys.exit(0 if hits and all(h.get("timeout") for h in hits) and all(h["command"].rstrip().endswith("|| true") for h in hits) else 1)
PY
}
check "SessionStart wires conduct-register.sh (timeout set, fail-open)" "$(ok wired SessionStart)"
check "PostToolUse wires conduct-register.sh (timeout set, fail-open)" "$(ok wired PostToolUse)"
check "hook script is executable" "$(ok test -x "$HOOK")"

printf 'conduct-register hook: %s passed, %s failed\n' "$pass" "$fail"
[ "$fail" = 0 ]
