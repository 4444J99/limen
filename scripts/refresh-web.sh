#!/usr/bin/env bash
# refresh-web.sh — regenerate the web dashboard from LIVE tasks.yaml and keep it served.
# Called as a slow voice by heartbeat-loop.sh so the browser view stays current without a
# human rebuild. READ-only w.r.t. the conductor (only rebuilds web/app/out + serves it).
set -uo pipefail
ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
APP="$ROOT/web/app"
PORT="${LIMEN_WEB_PORT:-8788}"
[ -d "$APP/node_modules" ] || { echo "  web: node_modules missing — skip"; exit 0; }
cd "$APP" || exit 0

with_timeout() {
  local seconds="$1"; shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "$seconds" "$@"
  elif command -v gtimeout >/dev/null 2>&1; then
    gtimeout "$seconds" "$@"
  else
    perl -e 'alarm shift; exec @ARGV' "$seconds" "$@"
  fi
}

# re-export static site from live tasks.yaml (prebuild regenerates data, postbuild validates).
# Skip the TS typecheck (next.config.js honours LIMEN_WEB_SKIP_TYPECHECK): the beat only needs a
# fast data re-export, and the typecheck is the slow phase that overran the timeout. CI still types.
if LIMEN_TASKS="$ROOT/tasks.yaml" LIMEN_WEB_SKIP_TYPECHECK=1 with_timeout "${LIMEN_WEB_BUILD_TIMEOUT:-90}" \
    npm run build >"$ROOT/logs/web-refresh.log" 2>&1; then
  echo "  web: rebuilt from live tasks.yaml"
else
  echo "  web: build failed/timed out (logs/web-refresh.log) — keeping previous export"
fi

# Assemble the static-first bounded projection from one shared policy. Full task history remains in
# the private canonical board/API; done tasks stay lazy-fetched from done-tasks.json.
python3 "$ROOT/scripts/assemble-dashboard-data.py" \
  --app "$APP" --repo-root "$ROOT" --write-public \
  || echo "  web: dashboard.json assemble skipped"

# ensure the static server is up (idempotent)
# Harden: if something else holds PORT (e.g. another http.server or a stray process), detect it
# via lsof and only launch ours if the port is free OR already owned by python (our server).
_port_owner_cmd() {
  lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $1}' | head -1
}
_port_owner_cmd_result="$(_port_owner_cmd)"
_our_server_running=false
if [ -z "$_port_owner_cmd_result" ]; then
  _our_server_running=false  # port free — (re)start ours
elif echo "$_port_owner_cmd_result" | grep -qi "python"; then
  _our_server_running=true   # already our python server
else
  echo "  web: WARNING — port $PORT held by foreign process ($_port_owner_cmd_result); dashboard not (re)started"
  _our_server_running=true   # treat as occupied; skip launch
fi
if ! "$_our_server_running"; then
  # </dev/null detaches stdin and, with the >file 2>&1 redirects, keeps the backgrounded server from
  # inheriting a caller's pipe write-end (defense-in-depth for the tail-EOF wedge fixed at the call sites).
  ( cd "$APP/out" && nohup python3 -m http.server "$PORT" --bind 127.0.0.1 >"$ROOT/logs/portal-web.log" 2>&1 </dev/null & )
  echo "  web: server (re)started → http://127.0.0.1:$PORT/internal.html"
fi
