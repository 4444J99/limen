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
  mkdir -p "$dir/parallel" "$dir/heavy" "$dir/serialized" "$dir/timeout" "$dir/noisy"
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
  noisy-gate:
    command: "python3 scripts/noisy-fixture.py"
    paths: ["noisy/**"]
    owner: verify
    note: "output ceiling terminates a noisy fixture"
YAML
  touch "$dir/parallel/.keep" "$dir/heavy/.keep" "$dir/serialized/.keep"
  touch "$dir/timeout/.keep" "$dir/noisy/.keep"
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

sb="$(make_sandbox)"
base_sha="$(git -C "$sb" rev-parse HEAD)"
commit_touch "$sb" parallel/input
out="$(python3 "$sb/scripts/verify.py" --changed --base "$base_sha" --require-base --jobs 2 2>&1)" \
  || flunk parallel-wave "independent gates did not overlap: $out"
[[ -f "$sb/parallel-ready-left" && -f "$sb/parallel-ready-right" ]] \
  && [[ "$(sort "$sb/parallel-order")" == $'left\nright' ]] \
  && grep -q "WAVE cheap: START" <<<"$out" \
  && grep -q "WAVE cheap: FINISH gate=" <<<"$out" \
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
  && grep -q "WAVE heavy: START" <<<"$out" \
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
    if ! kill -0 "$child_pid" 2>/dev/null; then
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

if ((fails)); then
  printf '\nverify-parallel: %d case(s) FAILED\n' "$fails"
  exit 1
fi
printf '\nverify-parallel: all scheduling fixtures pass\n'
