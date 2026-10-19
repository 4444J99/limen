#!/usr/bin/env bash
# Stop-hook wrapper for scripts/stop-governor.py (Claude and Codex share it).
#
# Fail-open: a missing script, missing python3, a crash or a timeout yields empty stdout and exit 0, so an
# unarmed or broken governor is a silent no-op, never a stalled session. The governor itself prints nothing
# or exactly one {"decision":"block","reason":...} object; this wrapper only adds the time ceiling and the
# always-exit-0 guarantee. The hook payload arrives on stdin and is passed through untouched.
#
# A failing interpreter (an old python3 that cannot import the governor, a crash) leaves ONE line in
# logs/stop-governor/wrapper-errors.log beside the governor's own ledger, so "armed but dead" is findable.
set -uo pipefail

HOOK_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)"
ROOT="$(CDPATH= cd -- "$HOOK_DIR/../.." 2>/dev/null && pwd -P)"
GOVERNOR="$ROOT/scripts/stop-governor.py"
[ -f "$GOVERNOR" ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0

breadcrumb() {
  mkdir -p "$ROOT/logs/stop-governor" 2>/dev/null || return 0
  printf '%s rc=%s python=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "$(command -v python3)" \
    >> "$ROOT/logs/stop-governor/wrapper-errors.log" 2>/dev/null || true
}

# The settings-level timeout is ten seconds; the governor's own alarm is six. This ceiling covers a hung
# interpreter start so the hook still returns inside the budget.
TIMEOUT_BIN="$(command -v timeout 2>/dev/null || command -v gtimeout 2>/dev/null || true)"
if [ -n "$TIMEOUT_BIN" ]; then
  out="$("$TIMEOUT_BIN" 8 python3 "$GOVERNOR" "$@" 2>/dev/null)"
else
  out="$(python3 "$GOVERNOR" "$@" 2>/dev/null)"
fi
rc=$?
if [ "$rc" -ne 0 ]; then
  breadcrumb "$rc"
  exit 0
fi
[ -n "$out" ] && printf '%s' "$out"
exit 0
