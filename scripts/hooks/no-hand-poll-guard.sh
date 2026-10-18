#!/usr/bin/env bash
# PreToolUse(Bash) hook: no-hand-poll-guard — deny hand-rolled PR/CI poll loops.
#
# WHY: the charter (CLAUDE.md § Merge & Branch Protocol) bans `for … gh pr … sleep … done`
# watchers — the 2026-07-15 endless-watcher incident: bespoke pollers, silent on FAIL,
# outliving their sessions — but the ban was prose-only. Synchronous waiters are now retired;
# this rejects both a direct await-pr invocation and a hand-rolled loop mechanically,
# the same move worktree-commit-guard.sh made for live-checkout commits (censor precedent
# PREC-2026-07-09-worktree-isolation-hook).
#
# SCOPE — the deny is deliberately narrow (never false-positive-block a legitimate lane):
#   DENY only: ONE command string carrying all three of
#     (1) a repetition construct at command position (while/until/for…do, or a trailing
#         `&` backgrounding a compound), AND
#     (2) a GitHub state probe (`gh pr …`, `gh run …`, `gh api …pulls/…`), AND
#     (3) a `sleep` invocation at command position.
#   PASS silently everything else: bare `sleep`, bare `gh pr view`, loops
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

# Cheap prefilter: almost every Bash call carries neither token — bail in O(1), no fork.
case "$input" in
  *sleep*|*await-pr.sh*) : ;;
  *) exit 0 ;;
esac

command -v python3 >/dev/null 2>&1 || exit 0

verdict="$(printf '%s' "$input" | python3 -c '
import json, os, re, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
cmd = (d.get("tool_input") or {}).get("command") or ""

# The retired waiter is denied as an INVOCATION, best-effort: the filename at a command position
# (start, newline, ; & | ( {, or after do/then/else/elif/if/while/until/!), optionally behind VAR=val,
# env/nohup/exec/eval/time/nice/sudo/xargs/timeout-style wrappers (with their options) and a
# bash/sh/source runner (incl. `bash -c` + a quoted body). A mention (ls, grep, git log, commit or PR
# text, a quoted or backticked name) is not an invocation and passes. The script exits 64 on its own, so a
# miss costs one refused call while a false deny blocks real work: the grammar errs permissive. The name
# must end at whitespace, end of string or ; & | (so a closing quote, paren or backtick means a mention),
# and `--help`/`-h` and `bash -n` (syntax check) pass. Known misses: ssh/docker/tmux/find -exec/flock/
# parallel launchers, pipes into a shell, and a quoted VAR=value containing a space. Known false denies:
# a heredoc or quoted prose line that STARTS with the script path after a separator. Every class is a
# single [ \t] run or a separator-free path class: linear time (a nested \s* once hung this hook on 200 KB).
POS = r"(?:^|[;&|(\n{][ \t]*|\b(?:do|then|else|elif|if|while|until)[ \t]+|![ \t]+)"
WORD = r"[^\s;&|()`\x27\"]"
WRAP = r"env|nohup|exec|eval|command|time|nice|ionice|setsid|stdbuf|sudo|xargs|watch|caffeinate|unbuffer"
SHELL = r"bash|sh|zsh|dash|ksh|source|\."
OPT = (
    r"(?:-[^\s;&|()`]+(?:[ \t]+(?!(?:" + WRAP + r"|timeout|" + SHELL + r")[ \t])"
    r"[A-Za-z0-9_.][^\s;&|()`=]*)?[ \t]+)*"
)
PRE = (
    r"(?:[A-Za-z_][A-Za-z0-9_]*=[^\s;&|()`]*[ \t]+"
    r"|(?:" + WORD + r"*/)?(?:" + WRAP + r")[ \t]+" + OPT +
    r"|timeout[ \t]+" + OPT + r"[0-9][0-9.]*[smhd]?[ \t]+)*"
)
RUN = (
    r"(?:(?:" + WORD + r"*/)?(?:" + SHELL + r")[ \t]+"
    r"(?:(?!-n[ \t])(?:-[oO][ \t]+[^\s-]\S*|-\S+)[ \t]+)*[\x27\"]?" + PRE + r")?"
)
FILE = (
    r"[\x27\"]?(?:" + WORD + r"*/)?await-pr\.sh(?=[ \t\n;&|]|$)"
    r"(?![ \t]+(?:-h|--help)(?:[ \t]|$))"
)
WAITER = re.compile(POS + PRE + RUN + FILE)
if WAITER.search(cmd):
    print("deny")
    sys.exit(0)

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
if os.environ.get("LIMEN_ALLOW_PR_POLL") != "1" and looping and GH_PROBE.search(cmd) and SLEEP.search(cmd):
    print("deny")
' 2>/dev/null)"

[ "$verdict" = "deny" ] || exit 0

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"agent/provider PR waiting is forbidden (CLAUDE.md § Merge & Branch Protocol). scripts/await-pr.sh is retired, and hand-rolled PR poll loops are banned. Submit one exact head once with scripts/merge-drain.py --repo OWNER/NAME --pr NUMBER --expected-head SHA, then return control. LIMEN_ALLOW_PR_POLL=1 applies only to a genuinely non-PR loop misread; it never revives await-pr.sh. If the command only NAMES the retired script (docs, commit or PR text) it was read as an invocation because the name starts a line or follows ; & | and ends at whitespace: put it mid-sentence, quote it, or build the name from parts."}}\n'
exit 0
