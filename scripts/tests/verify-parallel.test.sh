#!/usr/bin/env bash
set -euo pipefail

# Parallel-wave contract for scripts/verify.py.
#
# Independent gates must overlap inside each bounded resource wave. Gates
# carrying serialize:true remain ordered; every gate has a finite process-group
# deadline and output cap.

unset LIMEN_VERIFY_GATE_OUTPUT_BYTES LIMEN_VERIFY_GATE_TIMEOUT_SECONDS
unset LIMEN_VERIFY_JOBS LIMEN_VERIFY_LOCK_FILE

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fails=0

pass() { printf 'ok %s\n' "$1"; }
flunk() { printf 'FAIL %s\n  %s\n' "$1" "$2"; fails=$((fails + 1)); }

make_sandbox() {
  local dir
  dir="$(mktemp -d "${TMPDIR:-/tmp}/verify-parallel.XXXXXX")"
  mkdir -p "$dir/scripts" "$dir/institutio/governance"
  mkdir -p "$dir/parallel" "$dir/heavy" "$dir/serialized"
  mkdir -p "$dir/timeout" "$dir/interrupt" "$dir/noisy" "$dir/invalid"
  cp "$ROOT/scripts/verify.py" "$dir/scripts/verify.py"
  cat >"$dir/scripts/parallel-fixture.py" <<'PY'
from pathlib import Path
import sys
import time

namespace = sys.argv[1]
label = sys.argv[2]
other = "right" if label == "left" else "left"
Path(f"{namespace}-ready-{label}").write_text(label, encoding="utf-8")
deadline = time.monotonic() + 3
while not Path(f"{namespace}-ready-{other}").exists():
    if time.monotonic() >= deadline:
        raise SystemExit(19)
    time.sleep(0.01)
with Path(f"{namespace}-order").open("a", encoding="utf-8") as handle:
    handle.write(f"{label}\n")
PY
  cat >"$dir/scripts/serialized-fixture.py" <<'PY'
from pathlib import Path
import sys
import time

label = sys.argv[1]
active = Path("serialized-active")
if active.exists():
    raise SystemExit(23)
active.write_text(label, encoding="utf-8")
time.sleep(0.1)
with Path("serialized-order").open("a", encoding="utf-8") as handle:
    handle.write(f"{label}\n")
active.unlink()
PY
  cat >"$dir/scripts/timeout-fixture.py" <<'PY'
from pathlib import Path
import signal
import subprocess
import sys
import time

child = subprocess.Popen(
    [
        sys.executable,
        "-c",
        "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
    ]
)
Path("timeout-child-pid").write_text(str(child.pid), encoding="utf-8")
signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(30)
PY
  cat >"$dir/scripts/noisy-fixture.py" <<'PY'
import sys

sys.stdout.write("x" * 8192)
sys.stdout.flush()
PY
  cat >"$dir/scripts/invalid-fixture.py" <<'PY'
import os

os.write(1, b"\xff" * 8192)
PY
  cat >"$dir/scripts/completed-before-timeout.py" <<'PY'
from pathlib import Path
import importlib.util
import os
import tempfile
import threading

module_path = Path(__file__).with_name("verify.py")
spec = importlib.util.spec_from_file_location("verify_deadline_fixture", module_path)
assert spec and spec.loader
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

read_descriptor, write_descriptor = os.pipe()
os.close(write_descriptor)


class CompletedProcess:
    pid = 999_999_999

    def __init__(self) -> None:
        self.stdout = os.fdopen(read_descriptor, "rb", buffering=0)

    @staticmethod
    def poll() -> int:
        return 0

    @staticmethod
    def wait(timeout: float | None = None) -> int:
        return 0


process = CompletedProcess()
verify.subprocess.Popen = lambda *args, **kwargs: process
verify.os.killpg = lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError())
times = iter([0.0, 2.0])
verify.time.monotonic = lambda: next(times, 2.0)
with tempfile.TemporaryFile() as output:
    result = verify.run_command(
        ":",
        output=output,
        deadline=1.0,
        output_limit_bytes=1024,
        cancel_event=threading.Event(),
    )
if result != 0:
    raise SystemExit(f"completed gate was misclassified: {result}")
print("completed-before-timeout-ok")
PY
  cat >"$dir/scripts/zombie-group-fixture.py" <<'PY'
from pathlib import Path
from types import SimpleNamespace
import importlib.util

module_path = Path(__file__).with_name("verify.py")
spec = importlib.util.spec_from_file_location("verify_zombie_fixture", module_path)
assert spec and spec.loader
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

process = SimpleNamespace(pid=424242)
verify.os.killpg = lambda pid, sig: None
verify.subprocess.run = lambda *args, **kwargs: SimpleNamespace(
    returncode=0,
    stdout="Z\nZ+\n",
)
if verify.process_group_alive(process):
    raise SystemExit("zombie-only process group was treated as live")
verify.subprocess.run = lambda *args, **kwargs: SimpleNamespace(
    returncode=0,
    stdout="Z\nS+\n",
)
if not verify.process_group_alive(process):
    raise SystemExit("live process-group member was ignored")
print("zombie-group-ok")
PY
  cat >"$dir/scripts/lock-holder.py" <<'PY'
from pathlib import Path
import fcntl
import sys
import time

lock_path = Path(sys.argv[1])
ready_path = Path(sys.argv[2])
with lock_path.open("w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    ready_path.write_text("ready\n", encoding="utf-8")
    time.sleep(30)
PY
  cat >"$dir/scripts/interrupt-supervisor.py" <<'PY'
from pathlib import Path
import os
import signal
import subprocess
import sys
import time

root = Path(sys.argv[1])
base = sys.argv[2]
marker = root / "timeout-child-pid"
process = subprocess.Popen(
    [
        sys.executable,
        str(root / "scripts" / "verify.py"),
        "--changed",
        "--base",
        base,
        "--require-base",
        "--gate-timeout-seconds",
        "30",
    ],
    cwd=root,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
deadline = time.monotonic() + 3
while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
    time.sleep(0.02)
if not marker.exists():
    process.kill()
    output, _ = process.communicate()
    raise SystemExit(f"fixture child never started: {output.decode(errors='replace')}")

child_pid = int(marker.read_text(encoding="utf-8"))
process.terminate()
try:
    output, _ = process.communicate(timeout=6)
except subprocess.TimeoutExpired:
    process.kill()
    output, _ = process.communicate()
    try:
        os.kill(child_pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    raise SystemExit(f"verifier ignored parent SIGTERM: {output.decode(errors='replace')}")

child_alive = True
for _ in range(20):
    try:
        os.kill(child_pid, 0)
    except ProcessLookupError:
        child_alive = False
        break
    state = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(child_pid)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if state.startswith("Z"):
        child_alive = False
        break
    time.sleep(0.05)
if child_alive:
    try:
        os.kill(child_pid, signal.SIGKILL)
    except ProcessLookupError:
        child_alive = False
if process.returncode != 143 or child_alive:
    raise SystemExit(
        f"unsafe interruption returncode={process.returncode} child_alive={child_alive}: "
        f"{output.decode(errors='replace')}"
    )
print("interruption-ok")
PY
  cat >"$dir/institutio/governance/gates.yaml" <<'YAML'
schema_version: 0.1
gates:
  parallel-left:
    command: "python3 scripts/parallel-fixture.py parallel left"
    paths: ["parallel/**"]
    owner: verify
    note: "left half of the independent overlap fixture"
  parallel-right:
    command: "python3 scripts/parallel-fixture.py parallel right"
    paths: ["parallel/**"]
    owner: verify
    note: "right half of the independent overlap fixture"
  heavy-left:
    command: "python3 scripts/parallel-fixture.py heavy left"
    paths: ["heavy/**"]
    tier: heavy
    owner: verify
    note: "left half of the admission-gated overlap fixture"
  heavy-right:
    command: "python3 scripts/parallel-fixture.py heavy right"
    paths: ["heavy/**"]
    tier: heavy
    owner: verify
    note: "right half of the admission-gated overlap fixture"
  serialized-first:
    command: "python3 scripts/serialized-fixture.py first"
    paths: ["serialized/**"]
    tier: heavy
    serialize: true
    owner: verify
    note: "first explicitly serialized fixture"
  serialized-second:
    command: "python3 scripts/serialized-fixture.py second"
    paths: ["serialized/**"]
    tier: heavy
    serialize: true
    owner: verify
    note: "second explicitly serialized fixture"
  timeout-gate:
    command: "python3 scripts/timeout-fixture.py"
    paths: ["timeout/**"]
    owner: verify
    note: "deadline terminates the entire fixture process group"
  interrupt-gate:
    command: "python3 scripts/timeout-fixture.py"
    paths: ["interrupt/**"]
    owner: verify
    note: "parent interruption cancels and reaps the active fixture process group"
  noisy-gate:
    command: "python3 scripts/noisy-fixture.py"
    paths: ["noisy/**"]
    owner: verify
    note: "output ceiling terminates a noisy fixture"
  invalid-byte-gate:
    command: "python3 scripts/invalid-fixture.py"
    paths: ["invalid/**"]
    owner: verify
    note: "raw invalid UTF-8 bytes cannot expand the retained-byte ceiling"
YAML
  touch "$dir/parallel/.keep" "$dir/heavy/.keep" "$dir/serialized/.keep"
  touch "$dir/timeout/.keep" "$dir/interrupt/.keep" "$dir/noisy/.keep" "$dir/invalid/.keep"
  git -C "$dir" init -q -b main
  git -C "$dir" -c user.email=t@t -c user.name=t add -A
  git -C "$dir" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm base
  echo "$dir"
}

commit_touch() {
  local dir="$1" path="$2"
  printf 'changed\n' >"$dir/$path"
  git -C "$dir" -c user.email=t@t -c user.name=t add "$path"
  git -C "$dir" -c user.email=t@t -c user.name=t -c commit.gpgsign=false commit -qm "touch $path"
}

effectively_alive() {
  local pid="$1" state
  kill -0 "$pid" 2>/dev/null || return 1
  state="$(ps -o stat= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
  [[ -n "$state" && "$state" != Z* ]]
}

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" parallel/input
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base --jobs 2 2>&1)" \
  || flunk parallel-wave "independent gates did not overlap: $out"
[[ -f "$sb/parallel-ready-left" && -f "$sb/parallel-ready-right" ]] \
  && [[ "$(sort "$sb/parallel-order")" == $'left\nright' ]] \
  && grep -q "WAVE cheap: START" <<<"$out" \
  && grep -q "WAVE cheap: START gate=parallel-left" <<<"$out" \
  && grep -q "WAVE cheap: START gate=parallel-right" <<<"$out" \
  && grep -q "WAVE cheap: FINISH gate=parallel-left" <<<"$out" \
  && grep -q "WAVE cheap: FINISH gate=parallel-right" <<<"$out" \
  && pass parallel-wave \
  || flunk parallel-wave "both overlap markers were not produced: $out"

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" heavy/input
out="$(LIMEN_VERIFY_LOCK_FILE="$sb/verify.lock" \
       python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base --jobs 2 2>&1)" \
  || flunk heavy-wave "independent heavy gates did not overlap: $out"
[[ -f "$sb/heavy-ready-left" && -f "$sb/heavy-ready-right" ]] \
  && [[ "$(sort "$sb/heavy-order")" == $'left\nright' ]] \
  && grep -q "WAVE heavy: START gate=heavy-left" <<<"$out" \
  && grep -q "WAVE heavy: START gate=heavy-right" <<<"$out" \
  && pass heavy-wave \
  || flunk heavy-wave "both heavy overlap markers were not produced: $out"

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" serialized/input
out="$(LIMEN_VERIFY_LOCK_FILE="$sb/verify.lock" \
       python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base --jobs 8 2>&1)" \
  || flunk serialized-tail "explicitly serialized gates failed: $out"
[[ "$(cat "$sb/serialized-order")" == $'first\nsecond' && ! -e "$sb/serialized-active" ]] \
  && pass serialized-tail \
  || flunk serialized-tail "serialize:true gates overlapped or reordered: $out"

out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --jobs 0 2>&1)" \
  && flunk invalid-jobs "--jobs 0 unexpectedly passed" \
  || { grep -q "jobs must be between 1 and 32" <<<"$out" \
         && pass invalid-jobs \
         || flunk invalid-jobs "missing bounded-jobs refusal: $out"; }

out="$(LIMEN_VERIFY_JOBS=0 python3 "$sb/scripts/verify.py" --changed --base "$base_sha" 2>&1)" \
  && flunk invalid-env-jobs "LIMEN_VERIFY_JOBS=0 unexpectedly passed" \
  || { grep -q "jobs must be between 1 and 32" <<<"$out" \
         && pass invalid-env-jobs \
         || flunk invalid-env-jobs "missing bounded env refusal: $out"; }

out="$(LIMEN_VERIFY_GATE_TIMEOUT_SECONDS=0 \
       python3 "$sb/scripts/verify.py" --changed --base "$base_sha" 2>&1)" \
  && flunk invalid-env-timeout "zero gate timeout unexpectedly passed" \
  || { grep -q "gate timeout must be between" <<<"$out" \
         && pass invalid-env-timeout \
         || flunk invalid-env-timeout "missing timeout-bound refusal: $out"; }

out="$(LIMEN_VERIFY_GATE_OUTPUT_BYTES=1 \
       python3 "$sb/scripts/verify.py" --changed --base "$base_sha" 2>&1)" \
  && flunk invalid-env-output "one-byte output limit unexpectedly passed" \
  || { grep -q "gate output limit must be between" <<<"$out" \
         && pass invalid-env-output \
         || flunk invalid-env-output "missing output-bound refusal: $out"; }

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" timeout/input
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base \
       --gate-timeout-seconds 0.2 2>&1)" \
  && flunk gate-timeout "hung process group unexpectedly passed" \
  || { grep -q "gate-command-timeout" <<<"$out" \
         && pass gate-timeout \
         || flunk gate-timeout "missing finite timeout receipt: $out"; }
if [[ -f "$sb/timeout-child-pid" ]]; then
  child_pid="$(<"$sb/timeout-child-pid")"
  child_alive=1
  for _ in 1 2 3 4 5; do
    if ! effectively_alive "$child_pid"; then
      child_alive=0
      break
    fi
    sleep 0.05
  done
  ((child_alive == 0)) \
    && pass timeout-process-group \
    || flunk timeout-process-group "deadline left fixture descendant $child_pid alive"
else
  flunk timeout-process-group "timeout fixture never recorded its descendant"
fi

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" noisy/input
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base \
       --gate-output-bytes 1024 2>&1)" \
  && flunk gate-output-limit "noisy gate unexpectedly passed" \
  || { grep -q "gate-command-output-limit" <<<"$out" \
         && pass gate-output-limit \
         || flunk gate-output-limit "missing finite output-limit receipt: $out"; }
(( ${#out} < 4096 )) \
  && pass bounded-output-replay \
  || flunk bounded-output-replay "output-limit receipt replayed ${#out} bytes"

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" invalid/input
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base \
       --gate-output-bytes 1024 2>&1)" \
  && flunk invalid-byte-limit "invalid-byte flood unexpectedly passed" \
  || { grep -q "gate-command-output-limit" <<<"$out" \
         && pass invalid-byte-limit \
         || flunk invalid-byte-limit "missing raw-byte output-limit receipt"; }
(( ${#out} < 4096 )) \
  && pass invalid-byte-replay \
  || flunk invalid-byte-replay "invalid bytes expanded replay to ${#out} characters"

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" interrupt/input
out="$(python3 "$sb/scripts/interrupt-supervisor.py" "$sb" "$base_sha" 2>&1)" \
  && [[ "$out" == "interruption-ok" ]] \
  && pass parent-interruption \
  || flunk parent-interruption "parent interruption did not reap its gate group: $out"

out="$(python3 "$sb/scripts/completed-before-timeout.py" 2>&1)" \
  && [[ "$out" == "completed-before-timeout-ok" ]] \
  && pass completed-before-timeout \
  || flunk completed-before-timeout "completed gate lost the deadline race: $out"

out="$(python3 "$sb/scripts/zombie-group-fixture.py" 2>&1)" \
  && [[ "$out" == "zombie-group-ok" ]] \
  && pass zombie-group \
  || flunk zombie-group "zombie process-group handling regressed: $out"

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" serialized/input
python3 "$sb/scripts/lock-holder.py" "$sb/verify.lock" "$sb/lock-ready" &
holder_pid=$!
for _ in 1 2 3 4 5 6 7 8 9 10; do
  [[ -f "$sb/lock-ready" ]] && break
  sleep 0.02
done
if [[ -f "$sb/lock-ready" ]]; then
  out="$(LIMEN_VERIFY_LOCK_FILE="$sb/verify.lock" \
         python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base \
         --gate-timeout-seconds 0.2 2>&1)" \
    && flunk serialized-lock-timeout "held serialized lock unexpectedly passed" \
    || { grep -q "serialized-lock-timeout" <<<"$out" \
           && pass serialized-lock-timeout \
           || flunk serialized-lock-timeout "missing bounded lock receipt: $out"; }
else
  flunk serialized-lock-timeout "lock-holder fixture did not become ready"
fi
kill "$holder_pid" 2>/dev/null || true
wait "$holder_pid" 2>/dev/null || true

if ((fails)); then
  printf '\nverify-parallel: %d case(s) FAILED\n' "$fails"
  exit 1
fi
printf '\nverify-parallel: all scheduling fixtures pass\n'
