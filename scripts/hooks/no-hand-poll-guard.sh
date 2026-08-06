#!/usr/bin/env bash
# PreToolUse(Bash) hook: no-hand-poll-guard — deny hand-rolled PR/CI poll loops.
#
# WHY: the charter (CLAUDE.md § Merge & Branch Protocol) bans `for … gh pr … sleep … done`
# watchers — the 2026-07-15 endless-watcher incident: bespoke pollers, silent on FAIL,
# outliving their sessions — but the ban was prose-only. The sanctioned waiter's own
# single-instance lock protects await-pr.sh from duplication; it does nothing about the
# hand-rolled loop that bypasses it entirely. This closes that side door mechanically,
# the same move worktree-commit-guard.sh made for live-checkout commits (censor precedent
# PREC-2026-07-09-worktree-isolation-hook).
#
# SCOPE — the deny is deliberately narrow (never false-positive-block a legitimate lane):
#   DENY only: ONE command string carrying all three of
#     (1) a repetition construct at command position (while/until/for…do, or a trailing
#         `&` backgrounding a compound), AND
#     (2) a GitHub state probe (`gh pr …`, `gh run …`, `gh api …pulls/…`), AND
#     (3) a `sleep` invocation at command position.
#   PASS silently everything else: `scripts/await-pr.sh 1872 --merge` (its internals poll,
#   but a hook sees only the command string), bare `sleep`, bare `gh pr view`, loops
#   without sleep (bounded retries), sleeps without gh (build waits), and EVERY parse
#   failure. Legitimate multi-PR iteration (`for pr in 1 2 3; do gh pr view $pr; done`)
#   carries no sleep and passes.
#
# Fail-open by construction: uncertainty (missing python3, undecodable payload) exits 0
# with no output. The hook never emits "allow", so it cannot widen the permission surface.
# Escape hatch: LIMEN_ALLOW_PR_POLL=1 (mirrors LIMEN_ALLOW_LIVE_COMMIT).
set -u

# Consume stdin FIRST, unconditionally — an early exit that leaves the payload
# writer facing a closed pipe turns into a BrokenPipeError upstream.
input="$(cat)"

[ "${LIMEN_ALLOW_PR_POLL:-0}" = "1" ] && exit 0

# Cheap prefilter: almost every Bash call carries no sleep token — bail in O(1), no fork.
case "$input" in
  *sleep*) : ;;
  *) exit 0 ;;
esac

command -v python3 >/dev/null 2>&1 || exit 0

verdict="$(printf '%s' "$input" | python3 -c '
import json, re, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
cmd = (d.get("tool_input") or {}).get("command") or ""

# Command position: start, a separator, a loop/branch keyword (a probe can be the
# loop CONDITION — `until gh pr view …` — or its body — `do gh pr checks …`), or a bang.
POS = r"(?:^|[;&|(`]\s*|\b(?:do|then|else|while|until)\s+|!\s+)\s*"

# (1) repetition construct at command position
LOOP = re.compile(r"(?:^|[;&|(]\s*)\s*(?:while|until)\s|(?:^|[;&|(]\s*)\s*for\s+\S+\s+in\s.*?;\s*do\s")
# a compound ( … sleep … ) & or { …; } & backgrounded is a poller too
BG_COMPOUND = re.compile(r"[)}]\s*&\s*$")

# (2) GitHub state probe at command position
GH_PROBE = re.compile(POS + r"gh\s+(?:pr|run)\s|" + POS + r"gh\s+api\s+\S*pulls")

# (3) sleep at command position
SLEEP = re.compile(POS + r"sleep\s+\S")

looping = bool(LOOP.search(cmd)) or bool(BG_COMPOUND.search(cmd))
if looping and GH_PROBE.search(cmd) and SLEEP.search(cmd):
    print("deny")
' 2>/dev/null)"

[ "$verdict" = "deny" ] || exit 0

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"hand-rolled PR poll loops are banned (CLAUDE.md § Merge & Branch Protocol; 2026-07-15 endless-watcher incident: bespoke pollers, silent on FAIL, outliving their sessions). The one sanctioned synchronous waiter is scripts/await-pr.sh <PR#> [--merge] — hard deadline, loud verdicts, single instance. Anything longer than its deadline belongs to the beat'"'"'s merge rung (scripts/merge-drain.py via scripts/drain.sh) — hand off and end. Escape hatch for a genuinely non-PR loop misread: LIMEN_ALLOW_PR_POLL=1."}}\n'
exit 0
