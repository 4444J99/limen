#!/usr/bin/env bash
# PreToolUse(Bash) hook: worktree-commit-guard — deny `git commit` in the LIVE checkout on main.
#
# WHY: the charter (CLAUDE.md § Merge & Branch Protocol) forbids direct commits to main —
# every change rides a topic branch in an isolated worktree — but the rule was prose-only:
# the user-level allow-trusted-cd-git.sh even auto-approves `cd ~/Workspace/limen && git
# commit …` (commit is not in its danger-tail regex). This closes that side door mechanically
# (censor precedent PREC-2026-07-09-worktree-isolation-hook).
#
# SCOPE — the deny is deliberately narrow (never false-positive-block a legitimate lane):
#   DENY only: a Bash command containing a real `git … commit` invocation whose EFFECTIVE
#     directory (git -C target, else last `cd` clause before the commit, else session cwd)
#     resolves inside the LIVE limen checkout while that checkout sits on main.
#   PASS silently (no JSON) everything else: isolation worktrees (their git toplevel is the
#     worktree, not the live root), other repos, the live checkout parked on a topic branch
#     (scripts/sync-release.sh owns unparking), git add/status/log, scripts/ship-docs.sh
#     (its internal `git -C $tmp commit` is invisible to hooks), and EVERY parse failure.
#   Daemon lanes (heartbeat CAPTURE, the tasks.yaml keeper) run OUTSIDE Claude sessions —
#     PreToolUse hooks never see them.
#
# Fail-open by construction: uncertainty (missing python3, unresolvable cd target, detached
# HEAD, not a repo) exits 0 with no output. The hook never emits "allow", so it cannot widen
# the permission surface; Claude Code's deny-beats-allow precedence settles the one overlap
# with allow-trusted-cd-git.sh. Escape hatch: LIMEN_ALLOW_LIVE_COMMIT=1 (mirrors
# LIMEN_ALLOW_OPUS_FANOUT). LIMEN_LIVE_ROOT override exists for the hermetic test.
set -u

# Consume stdin FIRST, unconditionally — an early exit that leaves the payload
# writer facing a closed pipe turns into a BrokenPipeError upstream.
input="$(cat)"

[ "${LIMEN_ALLOW_LIVE_COMMIT:-0}" = "1" ] && exit 0

# Cheap prefilter: almost every Bash call carries no commit token — bail in O(1), no fork.
case "$input" in
  *git*commit*) : ;;
  *) exit 0 ;;
esac

command -v python3 >/dev/null 2>&1 || exit 0

# Precise parse: is there a `git … commit` at command position, and what directory does it
# effectively run in? Prints the resolved dir, or nothing (⇒ pass).
eff_dir="$(printf '%s' "$input" | python3 -c '
import json, os, re, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
cmd = (d.get("tool_input") or {}).get("command") or ""
cwd = d.get("cwd") or os.getcwd()

GIT_COMMIT = re.compile(
    r"(?:^|[;&|(]\s*|`\s*)\s*(?:command\s+)?git\s+"
    r"((?:-C\s+(?:\"[^\"]+\"|\x27[^\x27]+\x27|\S+)\s+|-c\s+\S+\s+|--no-pager\s+)*)"
    r"commit\b")
m = GIT_COMMIT.search(cmd)
if not m:
    sys.exit(0)          # "git commit" only inside a quoted string / not a command — pass

def unquote(s):
    return s[1:-1] if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"\x27" else s

target = None
mc = re.search(r"-C\s+(\"[^\"]+\"|\x27[^\x27]+\x27|\S+)", m.group(1) or "")
if mc:
    target = unquote(mc.group(1))                    # 1) git -C <path> pins the dir
else:
    head = cmd[: m.start()]                          # 2) last cd clause BEFORE the commit
    cds = re.findall(r"(?:^|[;&|]\s*)\s*cd\s+(\"[^\"]+\"|\x27[^\x27]+\x27|[^\s;&|]+)", head)
    if cds:
        target = unquote(cds[-1])

if target is None:
    eff = cwd                                        # 3) plain git commit → session cwd
else:
    target = os.path.expanduser(target)
    if "$" in target:
        sys.exit(0)                                  # unresolved variable — cannot place, pass
    eff = target if os.path.isabs(target) else os.path.join(cwd, target)

if not os.path.isdir(eff):
    sys.exit(0)                                      # cannot resolve — fail open
print(os.path.realpath(eff))
' 2>/dev/null)"

[ -n "$eff_dir" ] || exit 0

# Isolation worktrees and job dirs pass by shape, before any git call.
case "$eff_dir" in
  */.claude/worktrees/*|*/.worktrees/*|*/.limen-worktrees/*|*/.claude/jobs/*) exit 0 ;;
esac

LIVE="${LIMEN_LIVE_ROOT:-${LIMEN_ROOT:-$HOME/Workspace/limen}}"
LIVE="$(cd "$LIVE" 2>/dev/null && pwd -P)" || exit 0
[ -n "$LIVE" ] || exit 0

top="$(git -C "$eff_dir" rev-parse --show-toplevel 2>/dev/null)" || exit 0
[ -n "$top" ] || exit 0
top="$(cd "$top" 2>/dev/null && pwd -P)" || exit 0
[ "$top" = "$LIVE" ] || exit 0        # a worktree or another repo — not this guard's lane

branch="$(git -C "$eff_dir" symbolic-ref --short -q HEAD 2>/dev/null || true)"
[ "$branch" = "main" ] || exit 0      # parked topic branch / detached HEAD — pass (sync-release owns it)

printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"git commit in the LIVE checkout on main is blocked (CLAUDE.md § Merge & Branch Protocol: never commit to main; do session work in an isolated worktree). Cut a topic branch off origin/main in a worktree (EnterWorktree / git worktree add), or scripts/ship-docs.sh for docs-class files."}}\n'
exit 0
