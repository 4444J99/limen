#!/usr/bin/env bash
set -euo pipefail

# Thin wrapper — the scoped push gate's selection and execution live in scripts/verify.py,
# which derives them from institutio/governance/gates.yaml (the GATES registry). This file
# survives for callers and muscle memory only; check-gates.py ratchet `verify_scoped_wrapper`
# holds it to wrapper form. --full defers to the whole-system predicate unchanged.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "${1:-}" == "--full" ]]; then
  shift
  exec "$ROOT/scripts/verify-whole.sh" "$@"
fi
exec python3 "$ROOT/scripts/verify.py" --changed "$@"
