#!/usr/bin/env bash
# gen-launchd-plist.sh — render the launchd plist with DERIVED values, never hardcoded.
#
# "Names are outputs, not inputs": HOME, the repo root, the interpreter, and PATH are all
# resolved here at generation time from the environment + this script's own location —
# no home-dir paths and no pinned python version are typed into the source template.
#
#   scripts/gen-launchd-plist.sh              # print the derived plist to stdout (default, safe)
#   scripts/gen-launchd-plist.sh -o FILE      # write to FILE
#   scripts/gen-launchd-plist.sh --install    # write to ~/Library/LaunchAgents/ (does NOT load)
#
# It NEVER loads/bootstraps/restarts the daemon — that is a separate, supervised step:
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.limen.heartbeat.plist
set -euo pipefail

# --- resolve a symlink chain in pure bash (no python → no TCC prompt, no GNU readlink dep)
resolve() {
  local p="$1" t
  while [ -L "$p" ]; do
    t="$(readlink "$p")"
    case "$t" in
      /*) p="$t" ;;
      *)  p="$(cd "$(dirname "$p")" && cd "$(dirname "$t")" && pwd)/$(basename "$t")" ;;
    esac
  done
  printf '%s' "$p"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# repo root = parent of scripts/. Canonicalize (resolve symlinks, physical pwd) so a session
# that reached the repo via a symlink (e.g. ~/limen -> ~/Workspace/limen) cannot render a
# plist whose paths drift from the committed copy.
ROOT="$(cd "$(resolve "${LIMEN_ROOT:-$SCRIPT_DIR/..}")" && pwd -P)"
HOME_DIR="${HOME:?HOME is unset}"
AGENT_HOST="${LIMEN_AGENT_HOST_BIN:-${DOMUS_AGENT_HOST_BIN:-$HOME_DIR/Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost}}"
case "$AGENT_HOST" in
  \~) AGENT_HOST="$HOME_DIR" ;;
  \~/*) AGENT_HOST="$HOME_DIR/${AGENT_HOST#\~/}" ;;
esac
AGENT_HOST="$(resolve "$AGENT_HOST")"
WORKDIR="${LIMEN_WORKDIR:-$(cd "$ROOT/.." && pwd)}"        # parent of the repo
SCRATCH_ROOT="${LIMEN_SCRATCH_ROOT:-/Volumes/Scratch}"
if [ -n "${LIMEN_WORKTREES:-}" ]; then
  WORKTREES="$LIMEN_WORKTREES"
elif [ -d "$SCRATCH_ROOT" ] && [ -w "$SCRATCH_ROOT" ]; then
  WORKTREES="$SCRATCH_ROOT/limen-worktrees"
else
  WORKTREES="$WORKDIR/.limen-worktrees"
fi
WORKTREE_ROOT="${LIMEN_WORKTREE_ROOT:-$WORKTREES}"
TMPL="$ROOT/container/launchd/com.limen.heartbeat.plist.tmpl"
[ -f "$TMPL" ] || { echo "template not found: $TMPL" >&2; exit 1; }

# interpreter: pin to a CONCRETE absolute path (stable across PATH/brew drift) WITHOUT this
# file naming a version. Choose explicitly with LIMEN_PYTHON; else resolve whatever python3
# the current environment provides.
PY="${LIMEN_PYTHON:-$(command -v python3 || true)}"
[ -n "$PY" ] || { echo "no python3 on PATH; set LIMEN_PYTHON=/abs/path" >&2; exit 1; }
PY="$(resolve "$PY")"
PYDIR="$(dirname "$PY")"
PATH_VAL="$PYDIR:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
CAMPAIGN_WAKE_TIMEOUT="${LIMEN_CAMPAIGN_WAKE_TIMEOUT:-300}"
case "$CAMPAIGN_WAKE_TIMEOUT" in
  ''|*[!0-9]*) echo "LIMEN_CAMPAIGN_WAKE_TIMEOUT must be an integer from 300 to 7200" >&2; exit 2 ;;
esac
if [ "$CAMPAIGN_WAKE_TIMEOUT" -lt 300 ] || [ "$CAMPAIGN_WAKE_TIMEOUT" -gt 7200 ]; then
  echo "LIMEN_CAMPAIGN_WAKE_TIMEOUT must be an integer from 300 to 7200" >&2
  exit 2
fi
VIGILIA="${LIMEN_VIGILIA:-1}"

render() {
  sed -e "s|@@HOME@@|$HOME_DIR|g" \
      -e "s|@@DOMUS_AGENT_HOST_BIN@@|$AGENT_HOST|g" \
      -e "s|@@LIMEN_ROOT@@|$ROOT|g" \
      -e "s|@@LIMEN_WORKDIR@@|$WORKDIR|g" \
      -e "s|@@LIMEN_WORKTREES@@|$WORKTREES|g" \
      -e "s|@@LIMEN_WORKTREE_ROOT@@|$WORKTREE_ROOT|g" \
      -e "s|@@LIMEN_PYTHON@@|$PY|g" \
      -e "s|@@LIMEN_CAMPAIGN_WAKE_TIMEOUT@@|$CAMPAIGN_WAKE_TIMEOUT|g" \
      -e "s|@@LIMEN_VIGILIA@@|$VIGILIA|g" \
      -e "s|@@PATH@@|$PATH_VAL|g" \
      "$TMPL"
}

case "${1:-}" in
  --install)
    DEST="$HOME_DIR/Library/LaunchAgents/com.limen.heartbeat.plist"
    render > "$DEST"
    echo "wrote $DEST (NOT loaded — supervised step:" >&2
    echo "  launchctl bootout  gui/$(id -u)/com.limen.heartbeat 2>/dev/null; \\" >&2
    echo "  launchctl bootstrap gui/$(id -u) \"$DEST\")" >&2
    ;;
  -o) render > "${2:?-o needs a path}" ; echo "wrote ${2}" >&2 ;;
  ""|--stdout) render ;;
  *) echo "usage: $0 [--stdout | -o FILE | --install]" >&2; exit 2 ;;
esac
