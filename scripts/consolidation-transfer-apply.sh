#!/usr/bin/env bash
# Owner-authorized personal consolidation; preservation evidence is required.
set -euo pipefail
if [[ "$#" -lt 2 ]]; then
  echo "Usage: $0 PRIVATE_PREFLIGHT PRIVATE_RECEIPT [--allow-partial] [--resume]" >&2
  exit 2
fi
preflight="$1"
receipt="$2"
shift 2
here="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$here/consolidate-github.py" --apply --preflight "$preflight" --receipt "$receipt" "$@"
