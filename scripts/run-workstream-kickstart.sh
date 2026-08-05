#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
source "$script_dir/lib/workstream-capsule.sh"

if [[ "$#" -ne 1 ]]; then
  printf 'usage: %s PATH/TO/.limen-workstream/kickstart.sh\n' "$0" >&2
  exit 2
fi
kickstart="$1"
if [[ -L "$kickstart" || ! -f "$kickstart" ]]; then
  printf 'workstream kickstart must be a real file: %s\n' "$kickstart" >&2
  exit 2
fi

capsule_dir="$(cd "$(dirname "$kickstart")" && pwd -P)"
if workstream_existing_active_session "$capsule_dir" >/dev/null; then
  printf 'This workstream is already running. Continue in its existing session; no second process was started.\n'
  exit 0
fi

workstream_hydrate_conduct_environment
exec bash "$kickstart"
