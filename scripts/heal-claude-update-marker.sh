#!/usr/bin/env bash
# Clear Claude Code's benign "install_failed" update marker.
#
# The native updater can write ~/.claude/.last-update-result.json with
# status=install_failed, version_to=null, and error_code=null when it checks while
# already current. That is "nothing to install", not a real failed update. Clear
# only that exact signature; leave actual update failures visible.
set -uo pipefail

MARKER="${HOME:-/Users/4jp}/.claude/.last-update-result.json"

if [ ! -f "$MARKER" ]; then
  echo "claude-marker-heal: clean (no marker)"
  exit 0
fi

if grep -Eq '"status"[[:space:]]*:[[:space:]]*"install_failed"' "$MARKER" \
   && grep -Eq '"version_to"[[:space:]]*:[[:space:]]*null' "$MARKER" \
   && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*null' "$MARKER"; then
  rm -f "$MARKER" && echo "claude-marker-heal: cleared benign install_failed marker"
else
  echo "claude-marker-heal: marker present but not benign; left visible"
fi
