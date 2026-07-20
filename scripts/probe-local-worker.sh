#!/usr/bin/env bash
set -euo pipefail

# Headless guard: this probe runs unattended (CI, git hooks, the metabolize beat), and it shells out
# to `npm install` + `npx wrangler dev` below. CI=1 makes wrangler ERROR instead of opening an
# interactive OAuth login if a token is ever missing — the exact guard scripts/cf-wrangler.sh applies.
# A wrangler login *prompt* is a distribution gap, never a dead token (the #518 wrangler-login disease).
# `wrangler dev --local` needs no remote auth, so this is belt-and-suspenders that makes the invariant
# "no wrangler call in this repo can ever drop to an interactive login" structurally true, not merely
# probable — the last straggler outside cf-wrangler.sh.
export CI=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/limen-worker-probe.XXXXXX")"
# shellcheck disable=SC2329  # invoked by EXIT trap
early_cleanup() {
  rm -rf -- "$TMP_DIR"
}
trap early_cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
chmod 700 "$TMP_DIR"

ENV_FILE="$TMP_DIR/.dev.vars"
BOARD_FILE="$TMP_DIR/tasks.yaml"
SERVER_LOG="$TMP_DIR/wrangler.log"
PROBE_LOG="$TMP_DIR/probe.log"
OWNER_TOKEN="${LIMEN_PROBE_OWNER_TOKEN:-owner-probe-token-at-least-24-chars}"
CLIENT_TOKEN="${LIMEN_PROBE_CLIENT_TOKEN:-client-probe-token}"
CAPABILITY_SECRET="${LIMEN_PROBE_CAPABILITY_SECRET:-probe-capability-secret-at-least-24-chars}"
WRANGLER_CLI="$ROOT/web/worker/node_modules/wrangler/wrangler-dist/cli.js"
ATTEMPTS="${LIMEN_PROBE_ATTEMPTS:-80}"
RETRY_DELAY="${LIMEN_PROBE_RETRY_DELAY:-0.25}"
TERM_GRACE="${LIMEN_PROBE_TERM_GRACE:-2}"

port_available() {
  python3 - "$1" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        raise SystemExit(1)
PY
}

choose_port() {
  python3 - <<'PY'
import socket

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    print(sock.getsockname()[1])
PY
}

if [[ -n "${LIMEN_WORKER_PROBE_PORT:-}" ]]; then
  PORT="$LIMEN_WORKER_PROBE_PORT"
  if ! port_available "$PORT"; then
    printf 'LIMEN_WORKER_PROBE_PORT=%s is already in use; refusing to probe an unrelated process\n' "$PORT" >&2
    exit 1
  fi
else
  PORT="$(choose_port)"
fi

cat > "$BOARD_FILE" <<'YAML'
version: '1.0'
portal:
  name: Worker Runtime Probe
  description: temporary worker runtime adapter board
  budget:
    daily: 100
    unit: runs
    per_agent:
      jules: 100
    track:
      date: ''
      spent: 0
      per_agent: {}
tasks:
  - id: PROBE-001
    title: Worker probe active task
    repo: 4444J99/limen
    target_agent: jules
    priority: high
    budget_cost: 1
    status: in_progress
    created: '2026-06-03'
    urls:
      - https://github.com/4444J99/limen/pull/1
    context: private probe context
    dispatch_log:
      - timestamp: '2099-06-03T00:00:00+00:00'
        agent: jules
        session_id: private-session
        status: in_progress
  - id: PROBE-VERIFY
    title: Worker probe verify mutation
    repo: 4444J99/limen
    target_agent: jules
    priority: medium
    budget_cost: 1
    status: in_progress
    created: '2026-06-03'
    urls:
      - https://github.com/4444J99/limen/pull/2
    dispatch_log: []
  - id: PROBE-ASSIGN
    title: Worker probe assign mutation
    repo: 4444J99/limen
    target_agent: any
    priority: low
    budget_cost: 1
    status: needs_human
    created: '2026-06-03'
    dispatch_log: []
  - id: PROBE-ARCHIVE
    title: Worker probe archive mutation
    repo: 4444J99/limen
    target_agent: jules
    priority: low
    budget_cost: 1
    status: done
    created: '2026-06-03'
    dispatch_log: []
YAML

cat > "$ENV_FILE" <<EOF
LIMEN_INLINE_TASKS_YAML_B64=$(base64 < "$BOARD_FILE" | tr -d '\n')
LIMEN_API_TOKEN=$OWNER_TOKEN
LIMEN_CLIENT_TOKEN=$CLIENT_TOKEN
LIMEN_CONDUCT_PRINCIPAL_REGISTRY={"schema_version":"limen.conduct_principal_registry.v1","principals":[{"principal_id":"runtime-probe-owner","agent":"api","surface":"worker-probe","roles":["observer","conductor","executor","compatibility"],"bearer":"$OWNER_TOKEN"}]}
LIMEN_CONDUCT_CAPABILITY_SECRET=$CAPABILITY_SECRET
LIMEN_CORS_ORIGINS=http://127.0.0.1:$PORT
EOF

# shellcheck disable=SC2329  # invoked by EXIT trap
cleanup() {
  local exit_code="$?"
  local pid="${SERVER_PID:-}"
  local deadline
  local escalated=0
  local leader_reaped=0
  local leader_state
  trap - EXIT INT TERM HUP
  {
    if [[ -n "$pid" ]]; then
      if kill -0 "$pid" 2>/dev/null || kill -0 -- "-$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null || true
        deadline="$(python3 - "$TERM_GRACE" <<'PY'
import sys
import time

print(time.monotonic() + float(sys.argv[1]))
PY
)"
        while { kill -0 "$pid" 2>/dev/null || kill -0 -- "-$pid" 2>/dev/null; } && python3 - "$deadline" <<'PY'
import sys
import time

raise SystemExit(0 if time.monotonic() < float(sys.argv[1]) else 1)
PY
        do
          leader_state="$(ps -o state= -p "$pid" 2>/dev/null | tr -d '[:space:]' || true)"
          if [[ -z "$leader_state" || "$leader_state" == Z* ]]; then
            wait "$pid" 2>/dev/null || true
            leader_reaped=1
          fi
          if ! kill -0 "$pid" 2>/dev/null && ! kill -0 -- "-$pid" 2>/dev/null; then
            break
          fi
          sleep 0.05
        done
        if kill -0 "$pid" 2>/dev/null || kill -0 -- "-$pid" 2>/dev/null; then
          escalated=1
          if kill -0 -- "-$pid" 2>/dev/null; then
            kill -KILL -- "-$pid" 2>/dev/null || true
          else
            kill -KILL "$pid" 2>/dev/null || true
          fi
        fi
      fi
      if [[ "$leader_reaped" -eq 0 ]]; then
        wait "$pid" 2>/dev/null || true
      fi
    fi
  } 2>/dev/null
  if [[ "$escalated" -eq 1 ]]; then
    printf 'probe server group %s did not exit after TERM; sending KILL\n' "$pid" >&2
  fi
  rm -rf -- "$TMP_DIR"
  return "$exit_code"
}
trap cleanup EXIT

if [[ ! -d "$ROOT/web/worker/node_modules/yaml" || ! -f "$WRANGLER_CLI" ]]; then
  (
    cd "$ROOT/web/worker"
    npm install --silent
  )
fi

if [[ ! -f "$WRANGLER_CLI" ]]; then
  printf 'wrangler CLI not found after dependency install: %s\n' "$WRANGLER_CLI" >&2
  exit 1
fi

NODE_BIN="$(command -v node)"

python3 -c \
  'import os, sys; os.chdir(sys.argv[1]); os.setsid(); os.execvpe(sys.argv[2], sys.argv[2:], os.environ)' \
  "$ROOT/web/worker" \
  "$NODE_BIN" --no-warnings "$WRANGLER_CLI" \
    dev --local --ip 127.0.0.1 --port "$PORT" \
    --env-file "$ENV_FILE" --persist-to "$TMP_DIR/wrangler-state" \
    --log-level error >"$SERVER_LOG" 2>&1 &
SERVER_PID="$!"

for ((attempt = 0; attempt < ATTEMPTS; attempt++)); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    cat "$SERVER_LOG" >&2 || true
    printf 'wrangler dev exited before the worker probe became ready\n' >&2
    exit 1
  fi
  if "$ROOT/scripts/probe-runtime-adapter.py" \
    --api-url "http://127.0.0.1:$PORT" \
    --owner-token "$OWNER_TOKEN" \
    --client-token "$CLIENT_TOKEN" \
    --task-id PROBE-001 \
    --verify-task-id PROBE-VERIFY \
    --assign-task-id PROBE-ASSIGN \
    --archive-task-id PROBE-ARCHIVE >"$PROBE_LOG" 2>&1; then
    cat "$PROBE_LOG"
    exit 0
  fi
  sleep "$RETRY_DELAY"
done

cat "$SERVER_LOG" >&2 || true
cat "$PROBE_LOG" >&2 || true
exit 1
