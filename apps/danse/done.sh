#!/usr/bin/env bash
# Idempotent Danse delivery predicate. Reads the staged package and exercises
# the live browser seams; it never calls render.py or changes an artifact.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
package=""
phase="package"

usage() {
  echo "usage: apps/danse/done.sh --package <path> [--phase package|uploaded|submitted]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --package)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      package="$2"
      shift 2
      ;;
    --phase)
      [[ $# -ge 2 ]] || { usage; exit 2; }
      phase="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

[[ -n "$package" ]] || { usage; exit 2; }
case "$phase" in
  package|uploaded|submitted) ;;
  *) usage; exit 2 ;;
esac

python3 "$ROOT/scripts/check-danse.py"
python3 "$HERE/render/browser.py" --check --verify --arrival --probe
python3 "$HERE/submission/check.py" --package "$package" --phase "$phase"

echo
phase_upper="$(printf '%s' "$phase" | tr '[:lower:]' '[:upper:]')"
echo "DANSE ${phase_upper} DONE — invariant, Metal, reproduction, arrival, continuity, and package predicates hold"
