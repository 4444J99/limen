#!/usr/bin/env bash
# Selection only: resolve Python without injecting --changed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
case "${1:-}" in
  --explain|--list|--help|-h) ;;
  *) printf 'Usage: bash scripts/verify-select.sh --explain PATH... | --list\n' >&2
     exit 64 ;;
esac
source "$ROOT/scripts/lib/gate-python.sh"
LIMEN_GATE_PYTHON="$(limen_gate_python)" || exit 1
export LIMEN_GATE_PYTHON
exec "$LIMEN_GATE_PYTHON" "$ROOT/scripts/verify.py" "$@"
