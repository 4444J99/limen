#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/limen-worker-probe"
ENV_FILE="$TMP_DIR/.dev.vars"
BOARD_FILE="$TMP_DIR/tasks.yaml"
PORT="${LIMEN_WORKER_PROBE_PORT:-8787}"
OWNER_TOKEN="${LIMEN_PROBE_OWNER_TOKEN:-owner-probe-token}"
CLIENT_TOKEN="${LIMEN_PROBE_CLIENT_TOKEN:-client-probe-token}"

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
