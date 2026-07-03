#!/usr/bin/env bash
# enactment-audit.test.sh — regression test for scripts/enactment-audit.py
#
# The predicate must go RED whenever a flag that DECLARES a fleet_runtime intent is not
# actually wired to that value in the beat — the exact TABVLARIVS #576 failure, where a
# switch shipped OFF, the parameters.yaml note *claimed* the fleet enabled it, and every
# "done" gate went green on the dark state. It must stay GREEN only when the beat wiring
# genuinely resolves the flag to the declared value.
#
# Deterministic + idempotent (exit 0 ⟺ all cases pass): uses --wiring-only so the
# host-state liveness rung never makes the code-contract test flap between CI and the
# live host, and stubs the heartbeat/params inputs instead of reading the live ones.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
audit="$here/../enactment-audit.py"
[ -f "$audit" ] || { echo "FAIL: cannot find enactment-audit.py at $audit" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# A params fixture that declares the enactment contract (fleet must resolve FLAG_X to 1).
cat > "$work/params.yaml" <<'YAML'
parameters:
  FLAG_X:
    default: "0"
    env: FLAG_X
    fleet_runtime: "1"
    owner: test
YAML

green_hb="$work/hb-green.sh"      # wires it to 1 (matches contract)
dark_hb="$work/hb-dark.sh"        # wires it NOWHERE (the #576 dark switch)
wrong_hb="$work/hb-wrong.sh"      # wires it to 0 (diverges from contract)
printf '#!/usr/bin/env bash\nexport FLAG_X="${FLAG_X:-1}"\n' > "$green_hb"
printf '#!/usr/bin/env bash\n# no FLAG_X wiring at all\n' > "$dark_hb"
printf '#!/usr/bin/env bash\nexport FLAG_X="${FLAG_X:-0}"\n' > "$wrong_hb"

run() { python3 "$audit" --check --wiring-only --params "$work/params.yaml" --heartbeat "$1"; }

pass=0
expect() { # <label> <heartbeat> <want_exit>
  local label="$1" hb="$2" want="$3" got=0
  run "$hb" >/dev/null 2>&1 || got=$?
  if [ "$got" -eq "$want" ]; then
    echo "ok   $label (exit $got)"; pass=$((pass+1))
  else
    echo "FAIL $label: expected exit $want, got $got" >&2; exit 1
  fi
}

expect "GREEN when the beat wires the flag to the declared fleet value" "$green_hb" 0
expect "RED when the beat wires the flag NOWHERE (the #576 dark switch)"  "$dark_hb"  1
expect "RED when the beat wires the flag to the wrong value"             "$wrong_hb" 1

# Guard the live enactment contract itself: the real parameters.yaml must still declare
# fleet_runtime for LIMEN_TICKETS_PRODUCE (so the cutover can never silently lose its gate).
real_params="$here/../../institutio/governance/parameters.yaml"
if ! python3 - "$real_params" <<'PY'
import sys, yaml
p = yaml.safe_load(open(sys.argv[1]).read())["parameters"]
spec = p.get("LIMEN_TICKETS_PRODUCE", {})
assert str(spec.get("fleet_runtime")) == "1", "LIMEN_TICKETS_PRODUCE lost its fleet_runtime=1 enactment contract"
PY
then
  echo "FAIL live contract: LIMEN_TICKETS_PRODUCE missing fleet_runtime=1" >&2; exit 1
fi
echo "ok   live parameters.yaml still declares LIMEN_TICKETS_PRODUCE fleet_runtime=1"
pass=$((pass+1))

echo "enactment-audit.test.sh: $pass/4 cases passed"
