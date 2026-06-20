#!/usr/bin/env bash
# gen-gemini-settings.sh — render .gemini/settings.json with a DERIVED repo path, never a
# hardcoded home dir. The mcp dir is always <repo>/mcp, so LIMEN_ROOT is resolved from this
# script's own location. Names are outputs, not inputs.
#
#   scripts/gen-gemini-settings.sh            # print to stdout (default, safe)
#   scripts/gen-gemini-settings.sh --write    # write .gemini/settings.json
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${LIMEN_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
TMPL="$ROOT/.gemini/settings.json.tmpl"
[ -f "$TMPL" ] || { echo "template not found: $TMPL" >&2; exit 1; }
render() { sed -e "s|@@LIMEN_ROOT@@|$ROOT|g" "$TMPL"; }
case "${1:-}" in
  --write) render > "$ROOT/.gemini/settings.json"; echo "wrote $ROOT/.gemini/settings.json" >&2 ;;
  ""|--stdout) render ;;
  *) echo "usage: $0 [--stdout | --write]" >&2; exit 2 ;;
esac
