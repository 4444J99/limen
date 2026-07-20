#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/limen-runtime-probe.XXXXXX")"
# shellcheck disable=SC2329  # invoked by EXIT trap
early_cleanup() {
  rm -rf -- "$TMP_DIR"
}
trap early_cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
chmod 700 "$TMP_DIR"

TASKS_PATH="$TMP_DIR/tasks.yaml"
SERVER_LOG="$TMP_DIR/uvicorn.log"
PROBE_LOG="$TMP_DIR/probe.log"
OWNER_TOKEN="${LIMEN_PROBE_OWNER_TOKEN:-owner-probe-token}"
CLIENT_TOKEN="${LIMEN_PROBE_CLIENT_TOKEN:-client-probe-token}"
ATTEMPTS="${LIMEN_PROBE_ATTEMPTS:-40}"
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

if [[ -n "${LIMEN_PROBE_PORT:-}" ]]; then
  PORT="$LIMEN_PROBE_PORT"
  if ! port_available "$PORT"; then
    printf 'LIMEN_PROBE_PORT=%s is already in use; refusing to probe an unrelated process\n' "$PORT" >&2
    exit 1
  fi
else
  PORT="$(choose_port)"
fi

cat > "$TASKS_PATH" <<'YAML' # task-writer-audit: allow-derived-sandbox
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

LIMEN_TASKS="$TASKS_PATH" \
  LIMEN_API_TOKEN="$OWNER_TOKEN" \
  LIMEN_CLIENT_TOKEN="$CLIENT_TOKEN" \
  PYTHONPATH="${PYTHONPATH:-}" \
  python3 -c \
    'import os, sys; os.chdir(sys.argv[1]); os.setsid(); os.execvpe(sys.argv[2], sys.argv[2:], os.environ)' \
    "$ROOT/web/api" \
    python3 -m uvicorn main:app --host 127.0.0.1 --port "$PORT" >"$SERVER_LOG" 2>&1 &
SERVER_PID="$!"

for ((attempt = 0; attempt < ATTEMPTS; attempt++)); do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    cat "$SERVER_LOG" >&2 || true
    printf 'uvicorn exited before the runtime probe became ready\n' >&2
    exit 1
  fi
  if "$ROOT/scripts/probe-runtime-adapter.py" \
    --api-url "http://127.0.0.1:$PORT" \
    --owner-token "$OWNER_TOKEN" \
    --client-token "$CLIENT_TOKEN" \
    --task-id PROBE-001 \
    --verify-task-id PROBE-VERIFY \
    --assign-task-id PROBE-ASSIGN \
    --archive-task-id PROBE-ARCHIVE \
    --expect-mutations-unavailable >"$PROBE_LOG" 2>&1; then
    cat "$PROBE_LOG"
    exit 0
  fi
  sleep "$RETRY_DELAY"
done

cat "$SERVER_LOG" >&2 || true
cat "$PROBE_LOG" >&2 || true
exit 1
