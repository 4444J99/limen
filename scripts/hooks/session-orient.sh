#!/usr/bin/env bash
# session-orient.sh — SessionStart context-injection hook.
#
# Emits a compact, PII-free orientation digest (north star, open his-hand levers,
# organ liveness, the board, git state, "read first" pointers) to stdout, which the
# Claude Code harness injects as session context. This is the auto-version of the
# orienting context that otherwise gets hand-pasted at the top of every session.
#
# FAIL-OPEN BY CONSTRUCTION: any error -> emit nothing -> exit 0. A SessionStart hook
# cannot block a session even on a non-zero exit (per the Claude Code hooks contract),
# and this one is read-only. Activated by a SessionStart entry in the project's
# committed .claude/settings.json (limen-scoped); a clean no-op in any other project.
set -uo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-}"
[ -z "$ROOT" ] && ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)"
[ -z "$ROOT" ] && exit 0                        # not in a project -> no-op
GEN="$ROOT/scripts/session-orient.py"
DIGEST="$ROOT/logs/session-orientation.md"

# Primary: regenerate fresh (lean + read-only) under a hard timeout; the generator
# prints the digest to stdout AND refreshes $DIGEST. No-op cleanly outside limen
# (no generator present -> fall through). `timeout` is absent on stock macOS, so
# guard for it and run the generator directly if it is missing.
if command -v python3 >/dev/null 2>&1 && [ -f "$GEN" ]; then
  if command -v timeout >/dev/null 2>&1; then
    timeout 5 python3 "$GEN" 2>/dev/null && exit 0
  else
    python3 "$GEN" 2>/dev/null && exit 0
  fi
fi

# Fallback: emit the last-good digest the daemon/previous run left behind.
[ -f "$DIGEST" ] && cat "$DIGEST"
exit 0
