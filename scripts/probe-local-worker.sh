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
TMP_DIR="${TMPDIR:-/tmp}/limen-worker-probe"
ENV_FILE="$TMP_DIR/.dev.vars"
BOARD_FILE="$TMP_DIR/tasks.yaml"
OWNER_TOKEN="${LIMEN_PROBE_OWNER_TOKEN:-owner-probe-token}"
CLIENT_TOKEN="${LIMEN_PROBE_CLIENT_TOKEN:-client-probe-token}"

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

mkdir -p "$TMP_DIR"
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
LIMEN_CORS_ORIGINS=http://127.0.0.1:$PORT
EOF

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ ! -d "$ROOT/web/worker/node_modules/yaml" ]]; then
  (
    cd "$ROOT/web/worker"
    npm install --silent
  )
fi

(
  cd "$ROOT/web/worker"
  npx wrangler dev --local --ip 127.0.0.1 --port "$PORT" --env-file "$ENV_FILE" --log-level error >/tmp/limen-worker-probe-wrangler.log 2>&1
) &
SERVER_PID="$!"

for _ in {1..80}; do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    cat /tmp/limen-worker-probe-wrangler.log >&2 || true
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
    --archive-task-id PROBE-ARCHIVE >/tmp/limen-worker-probe.log 2>&1; then
    cat /tmp/limen-worker-probe.log
    exit 0
  fi
  sleep 0.25
done

cat /tmp/limen-worker-probe-wrangler.log >&2 || true
cat /tmp/limen-worker-probe.log >&2 || true
exit 1
