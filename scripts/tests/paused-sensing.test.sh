#!/usr/bin/env bash
# A pause withdraws the authority to ACT. It must never withdraw the ability to SENSE.
#
# The defect this pins: heartbeat-loop.sh's `paused` branch used to `continue` ~80 lines above the
# monitoring block, so arming ANY marker silently switched off the scheduled sensor pass, the drift
# monitors, and the inbox sweep. An agent-armed marker on 2026-07-27 blinded the fleet for four
# days — the live checkout reached 27 commits behind origin/main with check-live-checkout.py at
# exit 1 and nothing asking it. A 2026-07-21 PR had fixed the identical shape one split down
# (observe), which is exactly why this read as already-fixed and was not.
#
# Structural checks are the point here: the bug was an ORDERING bug, invisible to any test that
# only exercises run_monitoring in isolation. Hermetic — no daemon, no network, no launchd.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
LOOP="$ROOT/scripts/heartbeat-loop.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fails=0
pass() { printf '  ok   %s\n' "$1"; }
fail() { printf '  FAIL %s\n' "$1"; fails=$((fails + 1)); }

echo "paused-sensing matrix"

# ── 0. the file is valid shell at all ────────────────────────────────────────────────────────
bash -n "$LOOP" 2>/dev/null && pass "heartbeat-loop.sh parses" || fail "heartbeat-loop.sh does not parse"

# ── 1. run_monitoring is defined exactly once (one implementation, two call sites) ────────────
defs="$(grep -cE '^run_monitoring\(\) \{' "$LOOP")"
[ "$defs" = "1" ] && pass "run_monitoring defined exactly once" \
  || fail "run_monitoring defined $defs time(s) — must be 1 (shared substrate, not a copy)"

# ── 2. THE INVARIANT — the paused branch senses before it continues ──────────────────────────
# Slice the paused branch: from `if [ "$MODE" = "paused" ]` to its `continue`.
python3 - "$LOOP" > "$TMP/slice" <<'PY'
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
if [ -s "$TMP/slice" ]; then
  grep -q 'run_monitoring' "$TMP/slice" \
    && pass "the paused branch runs monitoring BEFORE it continues" \
    || fail "paused branch continues without sensing — THE 2026-07-27 DEFECT"
else
  fail "could not locate the paused branch (structure changed — update this test deliberately)"
fi

# ── 3. the live body still calls it too (we did not simply move the blindness) ────────────────
calls="$(grep -cE '^[[:space:]]*run_monitoring[[:space:]]*$' "$LOOP")"
[ "$calls" -ge 2 ] && pass "run_monitoring called from both the paused branch and the live body" \
  || fail "run_monitoring has $calls call site(s) — expected >= 2"

# ── 4. paused sensing is network-gated (every sensor in it talks to a remote) ─────────────────
grep -q 'net_up' "$TMP/slice" \
  && pass "paused sensing is gated on network reach" \
  || fail "paused sensing is not net_up-gated — offline paused beats would stall on remotes"

# ── 5. the escape hatch is declared (check-params.py contract) ────────────────────────────────
grep -q 'LIMEN_PAUSED_SENSING' "$ROOT/institutio/governance/parameters.yaml" \
  && pass "LIMEN_PAUSED_SENSING declared in the parameter panel" \
  || fail "LIMEN_PAUSED_SENSING is NOT declared in parameters.yaml"

# ── 6. FUNCTIONAL — run_monitoring actually invokes the sensor pass ───────────────────────────
# Extract just the function and run it against stubs. Proves the body does what the name claims.
python3 - "$LOOP" > "$TMP/fn.sh" <<'PY'
import sys
src = open(sys.argv[1]).read().splitlines()
start = next(i for i, l in enumerate(src) if l.startswith("run_monitoring() {"))
depth = 0
for j in range(start, len(src)):
    depth += src[j].count("{") - src[j].count("}")
    if depth == 0:
        print("\n".join(src[start:j + 1])); break
PY
mkdir -p "$TMP/root/scripts"
cat > "$TMP/bin_python3" <<EOF
#!/usr/bin/env bash
printf 'SENSORS_RAN %s\n' "\$*" >> "$TMP/calls"
EOF
mkdir -p "$TMP/bin" && mv "$TMP/bin_python3" "$TMP/bin/python3" && chmod +x "$TMP/bin/python3"
(
  PATH="$TMP/bin:$PATH"
  LIMEN_ROOT="$TMP/root"; c=0; MAX=60; VOICED="$TMP/voice"; C_MAIL=1
  mkdir -p "$VOICED"
  play() { [ $(( c % $1 )) -eq 0 ]; }
  stamp() { :; }
  # shellcheck disable=SC1090
  . "$TMP/fn.sh"
  run_monitoring >/dev/null 2>&1
)
grep -q 'SENSORS_RAN.*beat-sensors' "$TMP/calls" 2>/dev/null \
  && pass "run_monitoring invokes the scheduled sensor pass" \
  || fail "run_monitoring did not invoke beat-sensors.py"

echo
if [ "$fails" -eq 0 ]; then
  echo "paused-sensing: all checks passed"
  exit 0
fi
echo "paused-sensing: $fails check(s) FAILED"
exit 1
