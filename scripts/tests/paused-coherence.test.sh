#!/usr/bin/env bash
# A pause withdraws acting on the WORLD. It must never stop the machine keeping its own body coherent.
#
# The defect this pins: heartbeat-loop.sh called sync-release.sh — the rung that fast-forwards the
# live checkout to origin/main — only from the live body, ~55 lines BELOW the paused branch's
# `continue`. That produced a deadlock which ate its own tail: the 2026-07-21 maintenance blocker's
# resume_predicate requires "live root exact origin/main and clean", and the only rung that produces
# that state ran solely when NOT paused. The halt could never self-clear.
#
# Measured 2026-07-31: a hand-run sync brought the tree to exact-origin at 12:04; twenty-five minutes
# later origin had moved and check-live-checkout.py was back at exit 1, naming sync-release.sh as its
# owner. Sibling of paused-sensing.test.sh (#1713) — same shape, one category over.
#
# Structural checks are the point: an ordering bug is invisible to any test that exercises
# run_release_sync in isolation. Hermetic — no daemon, no network, no launchd, no git remote.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
LOOP="$ROOT/scripts/heartbeat-loop.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fails=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

echo "paused-coherence matrix"

# Slice the paused branch out of an arbitrary copy of the loop: from the `paused` test to its
# `continue`. Shared by the live check and the negative control below.
slice_paused() {
  python3 - "$1" <<'PY'
import re, sys
src = open(sys.argv[1]).read().splitlines()
start = next((i for i, l in enumerate(src) if re.search(r'if \[ "\$MODE" = "paused" \]', l)), None)
if start is None:
    sys.exit("NO_PAUSED_BRANCH")
end = next((j for j in range(start, len(src)) if src[j].strip() == "continue"), None)
if end is None:
    sys.exit("NO_CONTINUE")
print("\n".join(src[start:end + 1]))
PY
}

# ── 0. the file is valid shell at all ────────────────────────────────────────────────────────
bash -n "$LOOP" 2>/dev/null && pass "heartbeat-loop.sh parses" || fail "heartbeat-loop.sh does not parse"

# ── 1. one implementation, two call sites (not a copy-paste) ──────────────────────────────────
defs="$(grep -cE '^run_release_sync\(\) \{' "$LOOP")"
[ "$defs" = "1" ] && pass "run_release_sync defined exactly once" \
  || fail "run_release_sync defined $defs time(s) — must be 1 (shared substrate, not a copy)"

# ── 2. THE INVARIANT — the paused branch re-converges before it continues ─────────────────────
slice_paused "$LOOP" > "$TMP/slice" 2>"$TMP/slice.err"
if [ -s "$TMP/slice" ]; then
  grep -q 'run_release_sync' "$TMP/slice" \
    && pass "the paused branch re-converges the checkout BEFORE it continues" \
    || fail "paused branch continues without re-converging — THE RESUME DEADLOCK"
else
  fail "could not locate the paused branch ($(cat "$TMP/slice.err")) — update this test deliberately"
fi

# ── 3. the live body still calls it too (we did not simply move the rung) ─────────────────────
calls="$(grep -cE '^[[:space:]]*(\[ "\$\{LIMEN_PAUSED_SYNC:-1\}" = "1" \] &&[[:space:]]*)?run_release_sync[[:space:]]*$' "$LOOP")"
[ "$calls" -ge 2 ] && pass "run_release_sync called from both the paused branch and the live body" \
  || fail "run_release_sync has $calls call site(s) — expected >= 2"

# ── 4. the paused call has its own escape hatch ───────────────────────────────────────────────
grep -q 'LIMEN_PAUSED_SYNC' "$TMP/slice" \
  && pass "paused re-convergence is gated on LIMEN_PAUSED_SYNC" \
  || fail "paused re-convergence has no escape hatch — a bad-trunk pause could not freeze code"

# ── 5. the gate is declared (check-params.py contract) ────────────────────────────────────────
grep -q 'LIMEN_PAUSED_SYNC' "$ROOT/institutio/governance/parameters.yaml" \
  && pass "LIMEN_PAUSED_SYNC declared in the parameter panel" \
  || fail "LIMEN_PAUSED_SYNC is NOT declared in parameters.yaml"

# ── 6. FUNCTIONAL — run_release_sync actually invokes sync-release.sh ─────────────────────────
# Extract just the function and run it against a fake `bash` on PATH, so we prove the body does what
# the name claims rather than trusting the name.
python3 - "$LOOP" > "$TMP/fn.sh" <<'PY'
import sys
src = open(sys.argv[1]).read().splitlines()
start = next(i for i, l in enumerate(src) if l.startswith("run_release_sync() {"))
depth = 0
for j in range(start, len(src)):
    depth += src[j].count("{") - src[j].count("}")
    if depth == 0:
        print("\n".join(src[start:j + 1])); break
PY
mkdir -p "$TMP/bin"
cat > "$TMP/bin/bash" <<EOF
#!/bin/sh
printf 'SYNC_RAN %s\n' "\$*" >> "$TMP/calls"
EOF
chmod +x "$TMP/bin/bash"
(
  PATH="$TMP/bin:$PATH"
  LIMEN_ROOT="$TMP/root"; c=0; C_SYNC=1
  play() { [ $(( c % $1 )) -eq 0 ]; }
  # shellcheck disable=SC1090
  . "$TMP/fn.sh"
  run_release_sync >/dev/null 2>&1
)
grep -q 'SYNC_RAN.*sync-release' "$TMP/calls" 2>/dev/null \
  && pass "run_release_sync invokes sync-release.sh" \
  || fail "run_release_sync did not invoke sync-release.sh"

# ── 7. NEGATIVE CONTROL — the invariant must FAIL against the pre-fix loop ────────────────────
# A guard test that passes on the buggy code proves nothing. Skips (not passes) when the base ref is
# unavailable, so an offline runner never reports a false green here.
if git -C "$ROOT" cat-file -e origin/main:scripts/heartbeat-loop.sh 2>/dev/null; then
  git -C "$ROOT" show origin/main:scripts/heartbeat-loop.sh > "$TMP/base.sh" 2>/dev/null
  if slice_paused "$TMP/base.sh" > "$TMP/base.slice" 2>/dev/null && [ -s "$TMP/base.slice" ]; then
    if grep -q 'run_release_sync\|sync-release' "$TMP/base.slice"; then
      pass "base ref already re-converges while paused (fix landed upstream — expected after merge)"
    else
      pass "negative control: the pre-fix paused branch does NOT re-converge (defect reproduced)"
    fi
  else
    printf '  skip negative control — could not slice the base ref\n'
  fi
else
  printf '  skip negative control — origin/main not fetched\n'
fi

echo
if [ "$fails" -eq 0 ]; then
  echo "paused-coherence: all checks passed"
  exit 0
fi
echo "paused-coherence: $fails check(s) FAILED"
exit 1
