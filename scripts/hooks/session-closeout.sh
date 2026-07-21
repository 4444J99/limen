#!/usr/bin/env bash
# Constant-time SessionEnd hook. Slow closeout work belongs to heartbeat's
# consume-session-end-breadcrumbs.py rung, never to Claude's lifecycle budget.
set -u

HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
SCRIPT_ROOT="$(CDPATH= cd -- "$HOOK_DIR/../.." 2>/dev/null && pwd -P)"
ROOT="${LIMEN_ROOT:-$SCRIPT_ROOT}"
PRODUCER="$ROOT/scripts/session-end-breadcrumb.py"
if [ ! -f "$PRODUCER" ]; then
  PRODUCER="$SCRIPT_ROOT/scripts/session-end-breadcrumb.py"
  ROOT="$SCRIPT_ROOT"
fi
[ -f "$PRODUCER" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
STATE_ROOT="${XDG_STATE_HOME:-${HOME:-/tmp}/.local/state}"
QUEUE="${LIMEN_SESSION_END_BREADCRUMBS:-$STATE_ROOT/limen/session-end-breadcrumbs.jsonl}"

# The settings-level timeout is five seconds. This inner four-second ceiling
# leaves room for the hook runner itself to return cleanly.
TIMEOUT_BIN="$(command -v timeout 2>/dev/null || command -v gtimeout 2>/dev/null || true)"
if [ -n "$TIMEOUT_BIN" ]; then
  exec "$TIMEOUT_BIN" 4 python3 "$PRODUCER" --root "$ROOT" --source project --output "$QUEUE" >/dev/null 2>&1
fi
exec python3 "$PRODUCER" --root "$ROOT" --source project --output "$QUEUE" >/dev/null 2>&1
