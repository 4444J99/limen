#!/usr/bin/env bash
# Clear Claude Code's benign "install_failed" update marker.
#
# The native updater can write .last-update-result.json with status=install_failed,
# version_to=null, and error_code=null when it checks while already current. That is
# "nothing to install", not a real failed update. Clear only that exact signature; leave
# actual update failures visible.
#
# The marker path is DERIVED, never composed here. CLAUDE_CONFIG_DIR relocates Claude Code's
# entire config root, and this script used to hardcode "$HOME/.claude/" — so on 2026-08-12 it
# was measured clearing a file abandoned on 2026-07-24, while the LIVE marker sat untouched
# carrying exactly the benign signature this script exists to clear, and `claude doctor` kept
# reporting `Last update attempt: failed (install_failed)`. Reading a stale copy is silent:
# the file parses, the signature check runs, and the healer reports success about nothing.
# scripts/agent_config_paths.py owns which file each agent CLI actually reads.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MARKER="$(python3 "$ROOT/scripts/agent_config_paths.py" claude-update-marker 2>/dev/null)"

if [ -z "$MARKER" ]; then
  # Fail CLOSED on an unresolvable path instead of falling back to a literal. A literal fallback
  # is precisely how the wrong file got healed for 19 days, and clearing the wrong marker is
  # worse than clearing none: it reports a cure while the real marker keeps surfacing in doctor.
  echo "claude-marker-heal: could not resolve the marker path — inapplicable"
  exit 0
fi

if [ ! -f "$MARKER" ]; then
  echo "claude-marker-heal: clean (no marker at $MARKER)"
  exit 0
fi

if grep -Eq '"status"[[:space:]]*:[[:space:]]*"install_failed"' "$MARKER" \
   && grep -Eq '"version_to"[[:space:]]*:[[:space:]]*null' "$MARKER" \
   && grep -Eq '"error_code"[[:space:]]*:[[:space:]]*null' "$MARKER"; then
  rm -f "$MARKER" && echo "claude-marker-heal: cleared benign install_failed marker at $MARKER"
else
  echo "claude-marker-heal: marker present but not benign; left visible ($MARKER)"
fi
