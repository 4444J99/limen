#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="${TMPDIR:-/tmp}/limen-runtime-probe"
TASKS_PATH="$TMP_DIR/tasks.yaml"
PORT="${LIMEN_PROBE_PORT:-8765}"
OWNER_TOKEN="${LIMEN_PROBE_OWNER_TOKEN:-owner-probe-token}"
CLIENT_TOKEN="${LIMEN_PROBE_CLIENT_TOKEN:-client-probe-token}"

mkdir -p "$TMP_DIR"
cat > "$TASKS_PATH" <<'YAML'
version: '1.0'
portal:
  name: Runtime Probe
  description: temporary runtime adapter board
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
    title: Runtime probe active task
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
    title: Runtime probe verify mutation
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
    title: Runtime probe assign mutation
    repo: 4444J99/limen
    target_agent: any
    priority: low
    budget_cost: 1
    status: needs_human
    created: '2026-06-03'
    dispatch_log: []
  - id: PROBE-ARCHIVE
    title: Runtime probe archive mutation
    repo: 4444J99/limen
    target_agent: jules
    priority: low
    budget_cost: 1
    status: done
    created: '2026-06-03'
    dispatch_log: []
YAML

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

(
  cd "$ROOT/web/api"
  LIMEN_TASKS="$TASKS_PATH" \
    LIMEN_API_TOKEN="$OWNER_TOKEN" \
    LIMEN_CLIENT_TOKEN="$CLIENT_TOKEN" \
    PYTHONPATH="${PYTHONPATH:-}" \
    python3 -m uvicorn main:app --host 127.0.0.1 --port "$PORT" >/tmp/limen-runtime-probe-uvicorn.log 2>&1
) &
SERVER_PID="$!"

for _ in {1..40}; do
  if "$ROOT/scripts/probe-runtime-adapter.py" \
    --api-url "http://127.0.0.1:$PORT" \
    --owner-token "$OWNER_TOKEN" \
    --client-token "$CLIENT_TOKEN" \
    --task-id PROBE-001 \
    --verify-task-id PROBE-VERIFY \
    --assign-task-id PROBE-ASSIGN \
    --archive-task-id PROBE-ARCHIVE >/tmp/limen-runtime-probe.log 2>&1; then
    cat /tmp/limen-runtime-probe.log
    exit 0
  fi
  sleep 0.25
done

cat /tmp/limen-runtime-probe-uvicorn.log >&2 || true
cat /tmp/limen-runtime-probe.log >&2 || true
exit 1
