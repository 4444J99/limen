#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"

cd "$repo_root"
if git diff --quiet origin/main...HEAD --; then
  bash "$script_dir/verify-local.sh"
else
  scripts/verify-scoped.sh --base origin/main --require-base
fi
test -z "$(git -C "$repo_root" status --porcelain)"

printf 'charles-cotton-preview closeout: PASS\n'
