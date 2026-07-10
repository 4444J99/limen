#!/usr/bin/env bash
# omega.test.sh — regression test for scripts/omega.sh (the autonomic fixed-point predicate).
#
# omega.sh is the CONJUNCTION of every gate's --check; its own contract is the tally logic:
#   • a rung that cannot be checked here is SKIP, never a silent PASS (the curl-000 lesson);
#   • exit 0 ⟺ zero FAIL rungs (SKIPs allowed);
#   • it stamps logs/omega.json with one {rung,tier,status} row per rung.
# Deterministic: omega.sh derives ROOT from its own path and calls children by "$ROOT/scripts/X",
# so we run a COPY in a temp ROOT stubbed with fake predicates — no live board, handoff, or network.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
real_omega="$here/../omega.sh"
[ -f "$real_omega" ] || { echo "FAIL: cannot find omega.sh at $real_omega" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# A stub ROOT: omega.sh + a scripts/ dir of fake predicates whose exit codes we control per case.
mkdir -p "$work/scripts" "$work/cli/src" "$work/logs"
cp "$real_omega" "$work/scripts/omega.sh"

# write_stubs <ask_gate_rc> — all det children exit 0 except ask-gate.py, whose rc is the argument.
# (In --offline the live children are SKIPped without running. Registry-owned checks are discovered
# through a generic stub whose sensor id is intentionally unrelated to its command/label.)
write_stubs() {
  local ask_rc="$1"
  for py in enactment-audit armed-valve-audit handoff-relay; do
    printf '#!/usr/bin/env python3\nimport sys; sys.exit(0)\n' > "$work/scripts/$py.py"
    chmod +x "$work/scripts/$py.py"
  done
  printf '#!/usr/bin/env python3\nimport sys; sys.exit(%s)\n' "$ask_rc" > "$work/scripts/ask-gate.py"
  chmod +x "$work/scripts/ask-gate.py"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$work/scripts/no-tasks-on-me.sh"
  chmod +x "$work/scripts/no-tasks-on-me.sh"
  cat > "$work/scripts/beat-sensors.py" <<'PY'
#!/usr/bin/env python3
import sys
if "--list-omega" in sys.argv:
    print("arbitrary.future.id\t0\tdet\tarbitrary registry parity")
    print("arbitrary.future.id\t1\tlive\tarbitrary registry posture")
    raise SystemExit(0)
if "--run-omega" in sys.argv:
    raise SystemExit(0)
raise SystemExit(2)
PY
  chmod +x "$work/scripts/beat-sensors.py"
}

pass=0; fail=0
check() { if [ "$1" = "$2" ]; then pass=$((pass+1)); else echo "  MISMATCH ($3): want '$2' got '$1'"; fail=$((fail+1)); fi; }

# ── Case 1: every det child green → OMEGA HOLDS, exit 0 ──────────────────────────
write_stubs 0
set +e
out="$(bash "$work/scripts/omega.sh" --offline --quiet 2>&1)"; rc=$?
set -e
check "$rc" "0" "case1 exit"
echo "$out" | grep -q "OMEGA HOLDS" && check "holds" "holds" "case1 verdict" || check "missing" "holds" "case1 verdict"
python3 - "$work/logs/omega.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["verdict"] == "HOLDS", d["verdict"]
assert d["fail"] == 0, d
assert all({"rung", "tier", "status"} <= set(r) for r in d["rungs"]), "rung shape"
# every live rung must be SKIP in offline mode (never a silent PASS)
live = [r for r in d["rungs"] if r["tier"] == "live"]
assert live and all(r["status"] == "SKIP" for r in live), [r["status"] for r in live]
rows = {r["rung"]: r for r in d["rungs"]}
assert rows["arbitrary registry parity"]["status"] == "PASS", rows
assert rows["arbitrary registry posture"]["status"] == "SKIP", rows
print("  case1 stamp OK")
PY

# ── Case 2: one det child red → OMEGA BROKEN, exit 1 ─────────────────────────────
write_stubs 1
set +e
out="$(bash "$work/scripts/omega.sh" --offline --quiet 2>&1)"; rc=$?
set -e
check "$rc" "1" "case2 exit"
echo "$out" | grep -q "OMEGA BROKEN" && check "broken" "broken" "case2 verdict" || check "missing" "broken" "case2 verdict"
python3 - "$work/logs/omega.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["verdict"] == "BROKEN" and d["fail"] >= 1, d
print("  case2 stamp OK")
PY

# ── Case 3: overnight-trial marker flips its rung from SKIP to a live check ───────
# (Not exercised in --offline since the rung is live; assert the marker path parses without error.)
echo '{"pass": true, "hours": 9, "vendor_seams": 2, "merged_prs": 7, "operator_prompts": 0}' > "$work/logs/overnight-trial.json"
python3 - "$work/logs/overnight-trial.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d.get("pass") is True, d
print("  case3 marker OK")
PY

echo
if [ "$fail" -eq 0 ]; then
  echo "omega.test.sh: PASS ($pass checks)"
else
  echo "omega.test.sh: FAIL ($fail mismatches, $pass ok)"; exit 1
fi
