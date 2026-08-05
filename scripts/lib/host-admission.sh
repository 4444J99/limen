#!/usr/bin/env bash
# Shared shell custody for a heavy Limen entrypoint.
#
# Source this file, call host_admission_acquire after any older surface-specific
# lock has been acquired, and install host_admission_exit_trap. The refresher is
# this shell's own bounded child; cleanup never signals another workload.

HOST_ADMISSION_SCRIPT=""
HOST_ADMISSION_OWNER=""
HOST_ADMISSION_LEASE_ID=""
HOST_ADMISSION_INHERITED="0"
HOST_ADMISSION_REFRESH_PID=""

_host_admission_json_field() {
  local field="$1"
  python3 -c '
import json, sys
payload = json.load(sys.stdin)
value = payload
for part in sys.argv[1].split("."):
    value = value.get(part) if isinstance(value, dict) else None
print("" if value is None else ("1" if value is True else "0" if value is False else value))
' "$field"
}

_host_admission_reason() {
  python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except Exception:
    print("host admission returned unreadable state")
    raise SystemExit(0)
reasons = payload.get("reasons") or ["host-admission-denied"]
print(",".join(str(reason) for reason in reasons[:6]))
'
}

host_admission_acquire() {
  local surface="$1"
  local root="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
  local decision=""
  local rc=0
  HOST_ADMISSION_SCRIPT="$root/scripts/host-work-admission.py"
  HOST_ADMISSION_OWNER="limen-${surface//[^A-Za-z0-9_.-]/_}-$$"

  if decision="$(python3 "$HOST_ADMISSION_SCRIPT" acquire \
      --kind heavy \
      --owner "$HOST_ADMISSION_OWNER" \
      --surface "$surface" \
      --pid "$$")"; then
    :
  else
    rc=$?
    printf 'Host admission denied %s: %s\n' \
      "$surface" "$(printf '%s' "$decision" | _host_admission_reason)" >&2
    return "$rc"
  fi

  HOST_ADMISSION_INHERITED="$(printf '%s' "$decision" | _host_admission_json_field inherited)"
  HOST_ADMISSION_LEASE_ID="$(printf '%s' "$decision" | _host_admission_json_field lease.lease_id)"
  if [[ "$HOST_ADMISSION_INHERITED" == "1" ]]; then
    return 0
  fi
  if [[ -z "$HOST_ADMISSION_LEASE_ID" ]]; then
    printf 'Host admission allowed %s without a lease identity; refusing to proceed\n' "$surface" >&2
    return 3
  fi

  python3 "$HOST_ADMISSION_SCRIPT" refresh \
    --lease-id "$HOST_ADMISSION_LEASE_ID" \
    --owner "$HOST_ADMISSION_OWNER" \
    --pid "$$" \
    --watch \
    --interval-seconds 60 >/dev/null 2>&1 &
  HOST_ADMISSION_REFRESH_PID="$!"
}

host_admission_release() {
  if [[ -n "$HOST_ADMISSION_REFRESH_PID" ]]; then
    kill "$HOST_ADMISSION_REFRESH_PID" 2>/dev/null || true
    wait "$HOST_ADMISSION_REFRESH_PID" 2>/dev/null || true
    HOST_ADMISSION_REFRESH_PID=""
  fi
  if [[ "$HOST_ADMISSION_INHERITED" != "1" && -n "$HOST_ADMISSION_LEASE_ID" ]]; then
    python3 "$HOST_ADMISSION_SCRIPT" release \
      --lease-id "$HOST_ADMISSION_LEASE_ID" \
      --owner "$HOST_ADMISSION_OWNER" \
      --pid "$$" >/dev/null 2>&1 || true
  fi
}

host_admission_exit_trap() {
  local status=$?
  host_admission_release
  return "$status"
}
