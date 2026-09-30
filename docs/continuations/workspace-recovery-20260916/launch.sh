#!/usr/bin/env bash
set -euo pipefail
capsule_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(git -C "$capsule_dir" rev-parse --show-toplevel)"
if [[ "${1:-}" == "--check" ]]; then
  # Explicit session identity and owner receipt; historical custody is a separate mode.
  exec python3 "$root/scripts/session-closeout.py" "${@:2}"
fi
# Delegate to the existing capsule: its original expired deadline must refuse
# automatic continuation. Explicit future authority is required to renew it.
exec bash "$root/.limen-workstream/kickstart.sh"
