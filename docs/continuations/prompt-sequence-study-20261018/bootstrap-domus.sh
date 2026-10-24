#!/usr/bin/env bash
# Run from this owned Limen checkout; never changes execution policy.
set -euo pipefail
mode="${1:---dry-run}"
if [[ "$mode" != "--dry-run" && "$mode" != "--apply" ]]; then
  echo "usage: bootstrap-domus.sh --dry-run|--apply APPROVED_WORK_KEY DESTINATION" >&2
  exit 64
fi
if [[ "$#" != 3 ]]; then
  echo "An approved work key and a new destination are required; no policy is changed." >&2
  exit 64
fi
test -f scripts/lib/workstream-capsule.sh
runtime="${LIMEN_RUNTIME_ROOT:-$HOME/.local/share/limen/current}"
export PATH="$runtime/venv/bin:$PATH"
export LIMEN_WORK_KEY="$2"
source scripts/lib/workstream-capsule.sh
workstream_hydrate_conduct_environment
if [[ "$mode" == "--dry-run" ]]; then
  printf 'Bootstrap ready; no reservation or checkout created. Canonical apply still requires approved execution admission.\n'
  exit 0
fi
exec limen workstream domus process-ownership-01a14e66 --destination "$3" --no-readme
