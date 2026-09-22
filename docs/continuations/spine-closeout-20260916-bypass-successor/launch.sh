#!/usr/bin/env bash
set -euo pipefail
capsule_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$capsule_dir/../../.." && pwd)"
if [[ "${1:-}" == "--check" && "$#" -eq 1 ]]; then
  exec python3 "$capsule_dir/check.py"
fi
if [[ "$#" -ne 0 ]]; then
  echo "usage: bash launch.sh [--check]" >&2
  exit 2
fi
python3 "$capsule_dir/check.py"
exec bash "$repo_root/.limen-workstream/kickstart.sh"
