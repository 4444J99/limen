#!/usr/bin/env bash
# session-lifecycle-pressure.sh — SessionEnd hook for local/remote lifecycle pressure.
#
# Refreshes ignored logs/session-lifecycle-pressure.{json,md} so the next session's
# orientation can show whether local disk pressure is returning to lean after work
# has been preserved remotely. Fail-open and non-blocking by construction.
set -u

ROOT="${CLAUDE_PROJECT_DIR:-}"
[ -z "$ROOT" ] && ROOT="$(git -C "$(dirname "${BASH_SOURCE[0]}")/../.." rev-parse --show-toplevel 2>/dev/null || true)"
[ -z "$ROOT" ] && exit 0
GEN="$ROOT/scripts/session-lifecycle-pressure.py"
[ -f "$GEN" ] || exit 0

(
  if command -v python3 >/dev/null 2>&1; then
    python3 "$GEN" --write >/dev/null 2>&1 || true
  fi
) &

exit 0
