#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$HOME/Workspace}"
PORTVS_ROOT="${PORTVS_ROOT:-$WORKSPACE_ROOT/library/engine/organvm/portvs}"
LIMEN_ROOT="${LIMEN_ROOT:-$WORKSPACE_ROOT/library/engine/organvm/limen}"
DOMUS_ROOT="${DOMUS_ROOT:-$WORKSPACE_ROOT/library/engine/organvm/domus-genoma}"

for path in "$WORKSPACE_ROOT" "$PORTVS_ROOT" "$LIMEN_ROOT" "$DOMUS_ROOT"; do
  [[ -d "$path" && ! -L "$path" ]] || {
    printf 'completion: canonical directory unavailable or symlinked: %s\n' "$path" >&2
    exit 1
  }
done

bash "$PORTVS_ROOT/jack.sh" --verify --json >/dev/null
python3 "$DOMUS_ROOT/dot_local/bin/executable_domus-home-guard.tmpl" --check --json >/dev/null
python3 "$LIMEN_ROOT/scripts/substrate-convergence.py" \
  --manifest "$PORTVS_ROOT/governance/workspace-manifest.yaml" \
  --workspace-root "$WORKSPACE_ROOT" --json >/dev/null
python3 "$ROOT/scripts/overnight-watch.py" --check-trial --omega-strict --json >/dev/null
bash "$ROOT/scripts/omega.sh" --strict --quiet
