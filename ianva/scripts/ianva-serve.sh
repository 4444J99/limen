#!/usr/bin/env bash
# ianva-serve.sh — FOREGROUND supervisor for launchd/keepalive.
#
# `ianva up` spawns the backend detached (good for an interactive shell). launchd instead
# wants to supervise a foreground process, so this script: (1) materializes mcp_settings.json
# from the current upstream set, (2) derives the backend argv from ianva.toml (never hardcoded),
# (3) execs it in the foreground so launchd can KeepAlive it.
set -euo pipefail

IANVA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="$IANVA_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

# Load fleet secrets the same way the daemon does (upstream creds / fleet auth live here).
[ -f "$HOME/.limen.env" ] && set -a && . "$HOME/.limen.env" && set +a

PORT="$(python3 - <<'PY'
from ianva.config import load_config
print(load_config().port)
PY
)"
export PORT
export CLAUDE_CODE_OAUTH_TOKEN=""   # never let the backend inherit it (#37512); unset below
unset CLAUDE_CODE_OAUTH_TOKEN

# Materialize settings and derive the exact backend command from config.
# launchd runs this under macOS /bin/bash 3.2; keep this read loop Bash-3-safe.
ARGV=()
while IFS= read -r arg; do
  ARGV[${#ARGV[@]}]="$arg"
done < <(python3 - <<'PY'
from ianva.config import load_config
from ianva.upstreams import load_upstreams
from ianva.mcphub import materialize_settings
cfg = load_config()
sp = materialize_settings(load_upstreams())
for a in cfg.backend_argv(sp):
    print(a)
PY
)
if [ "${#ARGV[@]}" -eq 0 ]; then
  echo "ianva-serve: backend command resolved empty" >&2
  exit 127
fi

IANVA_RUNTIME_HOME="${IANVA_HOME:-$HOME/.config/ianva}"
mkdir -p "$IANVA_RUNTIME_HOME/run"
printf '%s\n' "$$" > "$IANVA_RUNTIME_HOME/run/backend.pid"
cd "$IANVA_RUNTIME_HOME"
echo "ianva-serve: exec ${ARGV[*]} (PORT=$PORT, cwd=$PWD)"
exec "${ARGV[@]}"
