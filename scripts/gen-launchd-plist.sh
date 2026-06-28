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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${LIMEN_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"        # repo root = parent of scripts/
HOME_DIR="${HOME:?HOME is unset}"
WORKDIR="${LIMEN_WORKDIR:-$(cd "$ROOT/.." && pwd)}"        # parent of the repo
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
LANES="${LIMEN_LANES:-codex,opencode,agy,claude,gemini}"
LOCAL_LIMIT="${LIMEN_LOCAL_LIMIT:-3}"
DISPATCH_ASYNC="${LIMEN_DISPATCH_ASYNC:-0}"

render() {
  sed -e "s|@@HOME@@|$HOME_DIR|g" \
      -e "s|@@LIMEN_ROOT@@|$ROOT|g" \
      -e "s|@@LIMEN_WORKDIR@@|$WORKDIR|g" \
      -e "s|@@LIMEN_PYTHON@@|$PY|g" \
      -e "s|@@LIMEN_LANES@@|$LANES|g" \
      -e "s|@@LIMEN_LOCAL_LIMIT@@|$LOCAL_LIMIT|g" \
      -e "s|@@LIMEN_DISPATCH_ASYNC@@|$DISPATCH_ASYNC|g" \
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
