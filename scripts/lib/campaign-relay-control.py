#!/usr/bin/env python3
"""Transform one ordinary capsule kickstart into the strict relay control protocol."""

import os
import sys
from pathlib import Path

kickstart = Path(sys.argv[1])
relay_id = sys.argv[2]
marker = f"# limen-campaign-relay:{relay_id}"
try:
    source = kickstart.read_text(encoding="utf-8")
except OSError as exc:
    raise SystemExit(f"campaign relay kickstart is unreadable: {exc}") from exc
foreign_markers = [line for line in source.splitlines() if line.startswith("# limen-campaign-relay:")]
if foreign_markers:
    if foreign_markers != [marker]:
        raise SystemExit("campaign relay kickstart belongs to a different relay")
    raise SystemExit(0)

early = f'''{marker}
if [[ "${{LIMEN_CAMPAIGN_RELAY_FINAL_EXEC:-}}" == "1" ]]; then
  exec python3 -c '
import json
import os
import sys
import ctypes
from pathlib import Path

control_fd = int(sys.argv[1])
exec_fd = int(sys.argv[2])
relay_id = sys.argv[3]
agent = sys.argv[4]
session_id = sys.argv[5]
real_binary = sys.argv[6]
arguments = sys.argv[7:]
if (
    control_fd == exec_fd
    or control_fd < 3
    or exec_fd < 3
    or control_fd > 255
    or exec_fd > 255
):
    raise SystemExit(125)
pid = os.getpid()
started = ""
proc_stat = Path(f"/proc/{{pid}}/stat")
if proc_stat.is_file():
    try:
        raw = proc_stat.read_text(encoding="ascii")
        fields = raw[raw.rindex(")") + 2:].split()
        started = f"linux-clock-ticks:{{fields[19]}}"
    except (OSError, UnicodeError, ValueError, IndexError):
        started = ""
elif sys.platform == "darwin":
    class ProcBSDInfo(ctypes.Structure):
        _fields_ = [
            ("flags", ctypes.c_uint32),
            ("status", ctypes.c_uint32),
            ("xstatus", ctypes.c_uint32),
            ("pid", ctypes.c_uint32),
            ("ppid", ctypes.c_uint32),
            ("uid", ctypes.c_uint32),
            ("gid", ctypes.c_uint32),
            ("ruid", ctypes.c_uint32),
            ("rgid", ctypes.c_uint32),
            ("svuid", ctypes.c_uint32),
            ("svgid", ctypes.c_uint32),
            ("rfu_1", ctypes.c_uint32),
            ("comm", ctypes.c_char * 16),
            ("name", ctypes.c_char * 32),
            ("nfiles", ctypes.c_uint32),
            ("pgid", ctypes.c_uint32),
            ("pjobc", ctypes.c_uint32),
            ("e_tdev", ctypes.c_uint32),
            ("e_tpgid", ctypes.c_uint32),
            ("nice", ctypes.c_int32),
            ("start_tvsec", ctypes.c_uint64),
            ("start_tvusec", ctypes.c_uint64),
        ]
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib")
        value = ProcBSDInfo()
        size = library.proc_pidinfo(
            pid, 3, 0, ctypes.byref(value), ctypes.sizeof(value)
        )
        if size == ctypes.sizeof(value):
            started = f"darwin-timeval:{{value.start_tvsec}}:{{value.start_tvusec}}"
    except (OSError, AttributeError):
        started = ""
if not started or len(started) > 256:
    raise SystemExit(125)
event = {{
    "agent": agent,
    "pid": pid,
    "process_started": started,
    "relay_id": relay_id,
    "schema": "limen.campaign_relay_control.v1",
    "session_id": session_id,
    "stage": "exec_pending",
}}
payload = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\\n").encode()
while payload:
    written = os.write(control_fd, payload)
    payload = payload[written:]
os.set_inheritable(control_fd, False)
os.set_inheritable(exec_fd, False)
for key in (
    "LIMEN_CAMPAIGN_RELAY_BASE",
    "LIMEN_CAMPAIGN_RELAY_ACK_FD",
    "LIMEN_CAMPAIGN_RELAY_CONTROL_FD",
    "LIMEN_CAMPAIGN_RELAY_ELIGIBLE_LANES",
    "LIMEN_CAMPAIGN_RELAY_EXEC_FD",
    "LIMEN_CAMPAIGN_RELAY_FINAL_EXEC",
    "LIMEN_CAMPAIGN_RELAY_ID",
    "LIMEN_CAMPAIGN_RELAY_REAL_BINARY",
    "LIMEN_HUMAN_PROTECTED",
    "LIMEN_NATIVE_RUN_ID",
    "LIMEN_NATIVE_SESSION_ID",
    "LIMEN_PROVIDER_IDENTITY",
    "LIMEN_RUN_ID",
):
    os.environ.pop(key, None)
os.environ.pop(f"LIMEN_{{agent.upper().replace(chr(45), chr(95))}}_BIN", None)
devnull = os.open(os.devnull, os.O_WRONLY)
os.dup2(devnull, 1)
os.dup2(devnull, 2)
if devnull > 2:
    os.close(devnull)
try:
    os.execvpe(real_binary, [real_binary, *arguments], os.environ)
except OSError as exc:
    failure = {{
        "errno": int(exc.errno or 0),
        "relay_id": relay_id,
        "schema": "limen.campaign_relay_control.v1",
        "stage": "exec_failed",
    }}
    failed = (json.dumps(failure, sort_keys=True, separators=(",", ":")) + "\\n").encode()
    while failed:
        written = os.write(exec_fd, failed)
        failed = failed[written:]
    raise SystemExit(126)
' "${{LIMEN_CAMPAIGN_RELAY_CONTROL_FD}}" \
    "${{LIMEN_CAMPAIGN_RELAY_EXEC_FD}}" "{relay_id}" \
    "${{LIMEN_AGENT}}" "${{LIMEN_SESSION_ID}}" \
    "${{LIMEN_CAMPAIGN_RELAY_REAL_BINARY}}" "$@"
fi
'''

helpers = f'''
workstream_campaign_relay_process_identity() {{
  python3 - "$1" <<'RELAY_PROCESS_IDENTITY_PY'
import ctypes
import sys
from pathlib import Path

pid = int(sys.argv[1])
identity = ""
proc_stat = Path(f"/proc/{{pid}}/stat")
if proc_stat.is_file():
    try:
        raw = proc_stat.read_text(encoding="ascii")
        fields = raw[raw.rindex(")") + 2:].split()
        identity = f"linux-clock-ticks:{{fields[19]}}"
    except (OSError, UnicodeError, ValueError, IndexError):
        identity = ""
elif sys.platform == "darwin":
    class ProcBSDInfo(ctypes.Structure):
        _fields_ = [
            ("flags", ctypes.c_uint32),
            ("status", ctypes.c_uint32),
            ("xstatus", ctypes.c_uint32),
            ("pid", ctypes.c_uint32),
            ("ppid", ctypes.c_uint32),
            ("uid", ctypes.c_uint32),
            ("gid", ctypes.c_uint32),
            ("ruid", ctypes.c_uint32),
            ("rgid", ctypes.c_uint32),
            ("svuid", ctypes.c_uint32),
            ("svgid", ctypes.c_uint32),
            ("rfu_1", ctypes.c_uint32),
            ("comm", ctypes.c_char * 16),
            ("name", ctypes.c_char * 32),
            ("nfiles", ctypes.c_uint32),
            ("pgid", ctypes.c_uint32),
            ("pjobc", ctypes.c_uint32),
            ("e_tdev", ctypes.c_uint32),
            ("e_tpgid", ctypes.c_uint32),
            ("nice", ctypes.c_int32),
            ("start_tvsec", ctypes.c_uint64),
            ("start_tvusec", ctypes.c_uint64),
        ]
    try:
        library = ctypes.CDLL("/usr/lib/libproc.dylib")
        value = ProcBSDInfo()
        size = library.proc_pidinfo(
            pid, 3, 0, ctypes.byref(value), ctypes.sizeof(value)
        )
        if size == ctypes.sizeof(value):
            identity = f"darwin-timeval:{{value.start_tvsec}}:{{value.start_tvusec}}"
    except (OSError, AttributeError):
        identity = ""
if not identity or len(identity) > 256:
    raise SystemExit(1)
print(identity)
RELAY_PROCESS_IDENTITY_PY
}}

workstream_conduct_target_is_live() {{
  local target_pid="$1"
  local target_started="$2"
  local observed_started=""

  if ! kill -0 "$target_pid" 2>/dev/null; then
    return 1
  fi
  observed_started="$(workstream_campaign_relay_process_identity "$target_pid" 2>/dev/null || true)"
  [[ -n "$observed_started" && "$observed_started" == "$target_started" ]]
}}

workstream_campaign_relay_emit_selected() {{
  local selected_agent="$1"
  local selected_capabilities="$2"
  local ack_fd="${{LIMEN_CAMPAIGN_RELAY_ACK_FD}}"
  local emit_rc=0
  python3 -c '
import json
import os
import sys

capabilities = sorted(set(sys.argv[5].split()))
if not capabilities or any(not value or len(value) > 128 for value in capabilities):
    raise SystemExit(2)
event = {{
    "agent": sys.argv[2],
    "capabilities": capabilities,
    "relay_id": sys.argv[3],
    "schema": "limen.campaign_relay_control.v1",
    "session_id": sys.argv[4],
    "stage": "selected",
}}
payload = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\\n").encode()
fd = int(sys.argv[1])
while payload:
    written = os.write(fd, payload)
    payload = payload[written:]
ack = b""
ack_fd = int(sys.argv[6])
while len(ack) < 11:
    chunk = os.read(ack_fd, 11 - len(ack))
    if not chunk:
        break
    ack += chunk
if ack != b"registered\\n":
    raise SystemExit(2)
' "${{LIMEN_CAMPAIGN_RELAY_CONTROL_FD}}" "$selected_agent" "{relay_id}" \
    "$LIMEN_SESSION_ID" "$selected_capabilities" "$ack_fd" || emit_rc=$?
  case "$ack_fd" in
    ""|*[!0-9]*) return 2 ;;
  esac
  if (( ack_fd < 3 || ack_fd > 255 )); then
    return 2
  fi
  return "$emit_rc"
}}

workstream_campaign_relay_emit_published() {{
  local receipt_path="$1"
  local ack_fd="${{LIMEN_CAMPAIGN_RELAY_ACK_FD}}"
  local emit_rc=0
  local contract_helper="${{LIMEN_CAPSULE_DIR:-}}/workstream-contract.py"
  local timeout_seconds="${{LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS:-120}}"
  local receipt_rel=""
  local commit="" parent="" receipt_blob="" receipt_ref="" remote_row=""

  receipt_rel="${{receipt_path#"$LIMEN_WORKTREE/"}}"
  commit="$(git rev-parse HEAD 2>/dev/null || true)"
  parent="$(git rev-parse HEAD^ 2>/dev/null || true)"
  receipt_blob="$(git rev-parse "HEAD:$receipt_rel" 2>/dev/null || true)"
  receipt_ref="refs/heads/limen-relay/capsule/$commit"
  if ! GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
    --timeout-seconds "$timeout_seconds" -- \
    git push origin "$commit:$receipt_ref" >/dev/null 2>&1; then
    if ! remote_row="$(GIT_TERMINAL_PROMPT=0 python3 "$contract_helper" run-bounded \
      --timeout-seconds "$timeout_seconds" -- \
      git ls-remote --refs origin "$receipt_ref" 2>/dev/null)"; then
      printf 'campaign relay immutable receipt-ref publication failed\\n' >&2
      return 2
    fi
    if [[ "$remote_row" != "$commit"$'\\t'"$receipt_ref" ]]; then
      printf 'campaign relay immutable receipt-ref publication failed\\n' >&2
      return 2
    fi
  fi
  python3 -c '
import json
import os
import re
import sys

git_object = re.compile(r"^(?:[0-9a-f]{{40}}|[0-9a-f]{{64}})$")
commit, parent, blob = sys.argv[4:7]
if not all(git_object.fullmatch(value) for value in (commit, parent, blob)):
    raise SystemExit(2)
event = {{
    "branch": sys.argv[2],
    "commit": commit,
    "parent": parent,
    "receipt_blob": blob,
    "receipt_path": sys.argv[3],
    "receipt_ref": sys.argv[7],
    "relay_id": "{relay_id}",
    "schema": "limen.campaign_relay_control.v1",
    "stage": "published",
}}
payload = (json.dumps(event, sort_keys=True, separators=(",", ":")) + "\\n").encode()
fd = int(sys.argv[1])
while payload:
    written = os.write(fd, payload)
    payload = payload[written:]
ack = b""
ack_fd = int(sys.argv[8])
while len(ack) < 7:
    chunk = os.read(ack_fd, 7 - len(ack))
    if not chunk:
        break
    ack += chunk
if ack != b"launch\\n":
    raise SystemExit(2)
' "${{LIMEN_CAMPAIGN_RELAY_CONTROL_FD}}" "$expected_branch" \
    "$receipt_rel" "$commit" "$parent" "$receipt_blob" "$receipt_ref" "$ack_fd" || emit_rc=$?
  case "$ack_fd" in
    ""|*[!0-9]*) return 2 ;;
  esac
  if (( ack_fd < 3 || ack_fd > 255 )); then
    return 2
  fi
  eval "exec ${{ack_fd}}>&-"
  unset LIMEN_CAMPAIGN_RELAY_ACK_FD
  return "$emit_rc"
}}

workstream_register_conduct_session() {{
  local agent="$1"
  local wt="$2"
  local capabilities="$3"

  workstream_conduct_token="${{LIMEN_CONDUCT_TOKEN:-}}"
  unset LIMEN_CONDUCT_TOKEN
  workstream_campaign_relay_emit_selected "$agent" "$capabilities"
  printf 'selected dormant relay conduct session: %s (%s)\\n' "$LIMEN_SESSION_ID" "$agent"
}}

workstream_campaign_relay_refresh_registration() {{
  local lock_path="$1"
  local limen_binary="$2"
  local conduct_token="$3"
  local agent="$4"
  local wt="$5"
  local session_id="$6"
  local activation_marker="$7"
  local relay_id="$8"
  local capabilities="$9"
  local capability
  local capability_args=()

  for capability in $capabilities; do
    capability_args+=(--capability "$capability")
  done
  LIMEN_CONDUCT_TOKEN="$conduct_token" python3 - \
    "$lock_path" "$limen_binary" "$agent" "$wt" "$session_id" \
    "$activation_marker" "$relay_id" \
    "${{capability_args[@]}}" <<'RELAY_LOCKED_REGISTRATION_PY'
import fcntl
import os
import signal
import stat
import subprocess
import sys
import time

lock_path, binary, agent, worktree, session_id, activation_marker, relay_id = sys.argv[1:8]
capability_args = sys.argv[8:]
flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
try:
    descriptor = os.open(lock_path, flags, 0o600)
except OSError:
    raise SystemExit(125)
locked = False
try:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o077:
        raise SystemExit(125)
    deadline = time.monotonic() + 21
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise SystemExit(124)
            time.sleep(0.05)
    accepting = "--not-accepting-work"
    marker_descriptor = -1
    try:
        marker_descriptor = os.open(
            activation_marker,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
    except FileNotFoundError:
        pass
    except OSError:
        raise SystemExit(125)
    if marker_descriptor >= 0:
        marker_metadata = os.fstat(marker_descriptor)
        marker_value = os.read(marker_descriptor, 66)
        os.close(marker_descriptor)
        if (
            not stat.S_ISREG(marker_metadata.st_mode)
            or stat.S_IMODE(marker_metadata.st_mode) & 0o077
            or marker_value != (relay_id + "\\n").encode()
        ):
            raise SystemExit(125)
        accepting = "--accepting-work"
    command = [
        binary,
        "conduct",
        "register",
        "--agent",
        agent,
        "--surface",
        "workstream",
        "--session-id",
        session_id,
        "--origin",
        "relay",
        *capability_args,
        "--worktree",
        worktree,
        "--concurrency",
        "1",
        accepting,
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        raise SystemExit(125)
    try:
        return_code = process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except OSError:
                pass
            process.wait()
        raise SystemExit(124)
    raise SystemExit(return_code)
finally:
    if locked:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    os.close(descriptor)
RELAY_LOCKED_REGISTRATION_PY
}}

workstream_conduct_keepalive_loop() {{
  local agent="$1"
  local wt="$2"
  local capabilities="$3"
  local target_pid="$4"
  local target_started="$5"
  local deadline_epoch="$6"
  local status_path="$7"
  local capsule_dir="$8"
  local interval_seconds="$9"
  local retry_seconds="${{10}}"
  local poll_seconds="${{11}}"
  local limen_binary="${{12}}"
  local conduct_token="${{13}}"
  local activation_marker="${{14}}"
  local relay_id="${{15}}"
  local registration_lock="${{capsule_dir}}/relay-registration.lock"
  local accepting_flag="--not-accepting-work"
  local activation_value=""
  local keepalive_pid
  local now_epoch next_refresh refresh_count=1
  local last_success_epoch last_failure_epoch=""
  local register_rc=0 detail="relay session remains dormant pending exec proof"

  trap 'exit 0' HUP INT TERM
  keepalive_pid="$(/bin/sh -c 'printf "%s\\n" "$PPID"')"
  case "$keepalive_pid" in
    ""|*[!0-9]*) return 2 ;;
  esac
  now_epoch="$(date +%s)"
  last_success_epoch="$now_epoch"
  next_refresh=$((now_epoch + interval_seconds))
  workstream_write_conduct_keepalive_status \
    "$status_path" "$capsule_dir" "$LIMEN_SESSION_ID" active "$target_pid" "$keepalive_pid" \
    "$deadline_epoch" "$refresh_count" "$last_success_epoch" "$last_failure_epoch" "$detail"
  while workstream_conduct_target_is_live "$target_pid" "$target_started"; do
    now_epoch="$(date +%s)"
    if (( now_epoch >= deadline_epoch )); then
      detail="capsule deadline reached"
      break
    fi
    if (( now_epoch < next_refresh )); then
      sleep "$poll_seconds"
      continue
    fi
    register_rc=0
    workstream_campaign_relay_refresh_registration \
      "$registration_lock" "$limen_binary" "$conduct_token" "$agent" "$wt" \
      "$LIMEN_SESSION_ID" "$activation_marker" "$relay_id" "$capabilities" \
      >/dev/null 2>&1 || register_rc=$?
    now_epoch="$(date +%s)"
    if [[ "$register_rc" -eq 0 ]]; then
      refresh_count=$((refresh_count + 1))
      last_success_epoch="$now_epoch"
      accepting_flag="--not-accepting-work"
      activation_value=""
      if [[ -f "$activation_marker" && ! -L "$activation_marker" ]]; then
        IFS= read -r activation_value < "$activation_marker" || activation_value=""
        if [[ "$activation_value" == "$relay_id" ]]; then
          accepting_flag="--accepting-work"
        fi
      fi
      if [[ "$accepting_flag" == "--accepting-work" ]]; then
        detail="active relay session refreshed"
      else
        detail="dormant relay session refreshed"
      fi
      next_refresh=$((now_epoch + interval_seconds))
      workstream_write_conduct_keepalive_status \
        "$status_path" "$capsule_dir" "$LIMEN_SESSION_ID" active "$target_pid" "$keepalive_pid" \
        "$deadline_epoch" "$refresh_count" "$last_success_epoch" "$last_failure_epoch" "$detail"
    else
      last_failure_epoch="$now_epoch"
      detail="relay registration refresh failed with exit $register_rc"
      next_refresh=$((now_epoch + retry_seconds))
      workstream_write_conduct_keepalive_status \
        "$status_path" "$capsule_dir" "$LIMEN_SESSION_ID" refresh_failed "$target_pid" "$keepalive_pid" \
        "$deadline_epoch" "$refresh_count" "$last_success_epoch" "$last_failure_epoch" "$detail"
    fi
  done
  if [[ "$detail" != "capsule deadline reached" ]]; then
    detail="provider process exited or changed identity"
  fi
  workstream_write_conduct_keepalive_status \
    "$status_path" "$capsule_dir" "$LIMEN_SESSION_ID" stopped "$target_pid" "$keepalive_pid" \
    "$deadline_epoch" "$refresh_count" "$last_success_epoch" "$last_failure_epoch" "$detail"
}}

workstream_start_conduct_keepalive() {{
  local agent="$1"
  local wt="$2"
  local capabilities="$3"
  local target_pid="$4"
  local deadline_epoch="$5"
  local capsule_dir="$6"
  local limen_binary="${{LIMEN_CLI_BIN:-limen}}"
  local interval_seconds="${{LIMEN_CONDUCT_KEEPALIVE_SECONDS:-180}}"
  local retry_seconds="${{LIMEN_CONDUCT_KEEPALIVE_RETRY_SECONDS:-30}}"
  local poll_seconds="${{LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS:-5}}"
  local status_path="$capsule_dir/conduct-keepalive.json"
  local activation_marker="$capsule_dir/relay-activated"
  local target_started="" launched_epoch="" ready=0 attempt value

  for value in "$target_pid" "$deadline_epoch" "$interval_seconds" "$retry_seconds" "$poll_seconds"; do
    case "$value" in
      ""|*[!0-9]*)
        printf 'invalid relay conduct keepalive numeric contract\\n' >&2
        return 2
        ;;
    esac
  done
  if (( interval_seconds < 1 || interval_seconds > 240
    || retry_seconds < 1 || retry_seconds > 60
    || poll_seconds < 1 || poll_seconds > 30
    || deadline_epoch <= $(date +%s) )); then
    printf 'relay conduct keepalive interval, retry, poll, or deadline is out of bounds\\n' >&2
    return 2
  fi
  target_started="$(workstream_campaign_relay_process_identity "$target_pid" 2>/dev/null || true)"
  if [[ -z "$target_started" ]]; then
    printf 'relay conduct keepalive could not bind the provider process identity\\n' >&2
    return 2
  fi
  launched_epoch="$(date +%s)"
  (
    case "${{LIMEN_CAMPAIGN_RELAY_CONTROL_FD:-}}" in
      ""|*[!0-9]*) exit 2 ;;
    esac
    case "${{LIMEN_CAMPAIGN_RELAY_EXEC_FD:-}}" in
      ""|*[!0-9]*) exit 2 ;;
    esac
    if (( LIMEN_CAMPAIGN_RELAY_CONTROL_FD < 3
      || LIMEN_CAMPAIGN_RELAY_CONTROL_FD > 255
      || LIMEN_CAMPAIGN_RELAY_EXEC_FD < 3
      || LIMEN_CAMPAIGN_RELAY_EXEC_FD > 255
      || LIMEN_CAMPAIGN_RELAY_CONTROL_FD == LIMEN_CAMPAIGN_RELAY_EXEC_FD )); then
      exit 2
    fi
    eval "exec ${{LIMEN_CAMPAIGN_RELAY_CONTROL_FD}}>&-"
    eval "exec ${{LIMEN_CAMPAIGN_RELAY_EXEC_FD}}>&-"
    unset LIMEN_CAMPAIGN_RELAY_CONTROL_FD LIMEN_CAMPAIGN_RELAY_EXEC_FD
    exec 9>&-
    workstream_conduct_keepalive_loop \
      "$agent" "$wt" "$capabilities" "$target_pid" "$target_started" "$deadline_epoch" \
      "$status_path" "$capsule_dir" "$interval_seconds" "$retry_seconds" "$poll_seconds" \
      "$limen_binary" "${{workstream_conduct_token:-}}" "$activation_marker" "{relay_id}"
  ) </dev/null >/dev/null 2>&1 &
  workstream_conduct_keepalive_pid=$!
  unset workstream_conduct_token
  for ((attempt = 0; attempt < 50; attempt++)); do
    if ! kill -0 "$workstream_conduct_keepalive_pid" 2>/dev/null; then
      break
    fi
    if workstream_conduct_keepalive_is_ready \
      "$status_path" "$LIMEN_SESSION_ID" "$target_pid" \
      "$workstream_conduct_keepalive_pid" "$launched_epoch"; then
      ready=1
      break
    fi
    sleep 0.1
  done
  if [[ "$ready" -ne 1 ]]; then
    kill "$workstream_conduct_keepalive_pid" 2>/dev/null || true
    wait "$workstream_conduct_keepalive_pid" 2>/dev/null || true
    printf 'relay conduct keepalive did not acknowledge its live session channel\\n' >&2
    return 2
  fi
  export LIMEN_CONDUCT_KEEPALIVE_PID="$workstream_conduct_keepalive_pid"
  printf 'started relay conduct keepalive: %s\\n' "$workstream_conduct_keepalive_pid"
}}
'''

published_marker = '  workstream_publish_admitted_receipt "$receipt" "$expected_branch" "$expected_slug"\n  exec 9>&-\n'
published_replacement = (
    '  workstream_publish_admitted_receipt "$receipt" "$expected_branch" "$expected_slug"\n'
    '  workstream_campaign_relay_emit_published "$receipt"\n'
    "  exec 9>&-\n"
)
launch_marker = 'workstream_launch_native_agent   "$agent" "$registry_binary"'
launch_replacement = '''relay_env_suffix="$(printf '%s' "$agent" | tr '[:lower:]-' '[:upper:]_')"
export LIMEN_CAMPAIGN_RELAY_REAL_BINARY="$registry_binary"
export LIMEN_CAMPAIGN_RELAY_FINAL_EXEC=1
export "LIMEN_${relay_env_suffix}_BIN=$kickstart"
workstream_launch_native_agent   "$agent" "$registry_binary"'''
if source.count("set -euo pipefail\n") != 1:
    raise SystemExit("campaign relay kickstart preamble is ambiguous")
helper_anchor = "\n\nexpected_worktree="
legacy_helper_anchor = "\n\ncd "
if source.count(helper_anchor) == 1:
    pass
elif source.count(helper_anchor) == 0 and source.count(legacy_helper_anchor) == 1:
    helper_anchor = legacy_helper_anchor
else:
    raise SystemExit("campaign relay helper insertion point is ambiguous")
if source.count(published_marker) != 1:
    raise SystemExit("campaign relay publication insertion point is ambiguous")
if source.count(launch_marker) != 1:
    raise SystemExit("campaign relay exec insertion point is ambiguous")
source = source.replace("set -euo pipefail\n", "set -euo pipefail\n" + early, 1)
source = source.replace(helper_anchor, "\n" + helpers + helper_anchor[1:], 1)
source = source.replace(published_marker, published_replacement, 1)
source = source.replace(launch_marker, launch_replacement, 1)
temporary = kickstart.with_name(f".{kickstart.name}.relay.{os.getpid()}")
temporary.write_text(source, encoding="utf-8")
os.chmod(temporary, 0o755)
os.replace(temporary, kickstart)
