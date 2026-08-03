#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"

cd "$repo_root"
scripts/verify-scoped.sh --base origin/main --require-base
test -z "$(git -C "$repo_root" status --porcelain)"

printf 'charles-cotton-preview closeout: PASS\n'
