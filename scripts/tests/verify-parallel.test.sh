#!/usr/bin/env bash
set -euo pipefail

# Parallel-wave contract for scripts/verify.py.
#
# Independent cheap gates must overlap inside one bounded wave. Gates carrying
# serialize:true must remain ordered even when the caller grants many workers.

unset LIMEN_VERIFY_JOBS LIMEN_VERIFY_LOCK_FILE

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
fails=0

pass() { printf 'ok %s\n' "$1"; }
flunk() { printf 'FAIL %s\n  %s\n' "$1" "$2"; fails=$((fails + 1)); }

make_sandbox() {
  local dir
  dir="$(mktemp -d "${TMPDIR:-/tmp}/verify-parallel.XXXXXX")"
  mkdir -p "$dir/scripts" "$dir/institutio/governance" "$dir/parallel" "$dir/serialized"
  cp "$ROOT/scripts/verify.py" "$dir/scripts/verify.py"
  cat >"$dir/scripts/parallel-fixture.py" <<'PY'
from pathlib import Path
import sys
import time

label = sys.argv[1]
other = "right" if label == "left" else "left"
Path(f"ready-{label}").write_text(label, encoding="utf-8")
deadline = time.monotonic() + 3
while not Path(f"ready-{other}").exists():
    if time.monotonic() >= deadline:
        raise SystemExit(19)
    time.sleep(0.01)
with Path("parallel-order").open("a", encoding="utf-8") as handle:
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
  cat >"$dir/institutio/governance/gates.yaml" <<'YAML'
schema_version: 0.1
gates:
  parallel-left:
    command: "python3 scripts/parallel-fixture.py left"
    paths: ["parallel/**"]
    owner: verify
    note: "left half of the independent overlap fixture"
  parallel-right:
    command: "python3 scripts/parallel-fixture.py right"
    paths: ["parallel/**"]
    owner: verify
    note: "right half of the independent overlap fixture"
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
YAML
  touch "$dir/parallel/.keep" "$dir/serialized/.keep"
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
[[ -f "$sb/ready-left" && -f "$sb/ready-right" ]] \
  && [[ "$(sort "$sb/parallel-order")" == $'left\nright' ]] \
  && pass parallel-wave \
  || flunk parallel-wave "both overlap markers were not produced: $out"

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

if ((fails)); then
  printf '\nverify-parallel: %d case(s) FAILED\n' "$fails"
  exit 1
fi
printf '\nverify-parallel: all scheduling fixtures pass\n'
