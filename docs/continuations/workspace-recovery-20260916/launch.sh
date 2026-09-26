#!/usr/bin/env bash
set -euo pipefail
capsule_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(git -C "$capsule_dir" rev-parse --show-toplevel)"
if [[ "${1:-}" == "--check" ]]; then
  # Read-only inspection of the current session's context. Session-scoped:
  # resolves the live branch/HEAD, reports retained concurrent work, and
  # never binds the session to the historical capsule branch or whole-
  # checkout cleanliness. Passes extra args (e.g. --owned <path>) through.
  exec python3 "$capsule_dir/verify-closeout.py" --check "${@:2}"
fi
# Delegate to the existing capsule: its original expired deadline must refuse
# automatic continuation. Explicit future authority is required to renew it.
exec bash "$root/.limen-workstream/kickstart.sh"
