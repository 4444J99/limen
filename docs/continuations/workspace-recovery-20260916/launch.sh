#!/usr/bin/env bash
set -euo pipefail
capsule_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(git -C "$capsule_dir" rev-parse --show-toplevel)"
python3 "$capsule_dir/verify-closeout.py"
if [[ "${1:-}" == "--check" ]]; then exit 0; fi
# Delegate to the existing capsule: its original expired deadline must refuse
# automatic continuation. Explicit future authority is required to renew it.
exec bash "$root/.limen-workstream/kickstart.sh"
