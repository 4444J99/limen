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

# ---------------------------------------------------------------------------------------------
# EFFICACY rung — the axis wiring+liveness are structurally blind to.
#
# Measured 2026-08-07: heal-board.py --canonical failed on EVERY beat with "Exceeded allowed rows
# written in Durable Objects free tier" while this very audit printed "3 rung(s) green/skip", and
# twelve regressed needs-human atoms stayed regressed for hours. The flag was declared AND on: what
# was missing was not a list entry but a whole axis — is the rung LANDING, not merely enabled.
#
# Driven with --efficacy-only against fixture ledgers so the host-dependent liveness rung cannot
# flap the result between CI and the live host.
# ---------------------------------------------------------------------------------------------
row() { printf '{"ts":"2026-08-07T00:00:00Z","rung":"%s","exit":%s}\n' "$2" "$3" >> "$work/$1"; }

: > "$work/healthy.jsonl"
for _ in 1 2 3; do row healthy.jsonl heal-board 0; row healthy.jsonl route 0; done

: > "$work/streak.jsonl"
for _ in 1 2 3; do row streak.jsonl heal-board 0; row streak.jsonl publish-board-pr 1; done

: > "$work/blip.jsonl"          # failed once, recovered, failed once — under threshold
row blip.jsonl route 1; row blip.jsonl route 0; row blip.jsonl route 1

: > "$work/tempfail.jsonl"      # a blocker already filed with a human owner
for _ in 1 2 3 4 5; do row tempfail.jsonl heal-board-canonical 75; done

: > "$work/recovered.jsonl"     # long failure then a success — the TRAILING streak is what counts
for _ in 1 2 3 4 5; do row recovered.jsonl heal-board-canonical 75; done
row recovered.jsonl heal-board-canonical 0

: > "$work/junk.jsonl"          # a sensor must not die on a torn write
echo 'not json at all'  >> "$work/junk.jsonl"
echo '{"rung":"x"}'     >> "$work/junk.jsonl"
row junk.jsonl route 0

eff() { # <label> <ledger> <want_exit> [<want_substring>]
  local label="$1" ledger="$2" want="$3" needle="${4:-}" got=0 out
  out="$(LIMEN_BEAT_RUNG_LOG="$work/$ledger" python3 "$audit" --efficacy-only --check 2>&1)" || got=$?
  if [ "$got" -ne "$want" ]; then
    echo "FAIL $label: expected exit $want, got $got" >&2; echo "$out" >&2; exit 1
  fi
  if [ -n "$needle" ] && ! printf '%s' "$out" | grep -q -- "$needle"; then
    echo "FAIL $label: output did not mention '$needle'" >&2; echo "$out" >&2; exit 1
  fi
  echo "ok   $label (exit $got)"; pass=$((pass+1))
}

eff "GREEN when every rung succeeded on its latest beat"                  healthy.jsonl   0
eff "RED when a rung has failed N consecutive beats (enacted, ineffective)" streak.jsonl  1 "publish-board-pr"
eff "not red for a single bad beat — noise is not a defect"               blip.jsonl      0
eff "not red for EX_TEMPFAIL: a filed human-gated blocker, and a permanently-red gate is ignored" \
    tempfail.jsonl 0
eff "a recovered rung is healthy — the TRAILING streak is what counts"   recovered.jsonl 0
eff "a torn/malformed ledger line is skipped, never fatal"               junk.jsonl      0

# An absent ledger must SKIP, never fail: CI has no beat, and neither does a daemon that has not
# yet run a loop carrying beat_run.
eff "SKIP when no rung-outcome ledger exists at all"                     absent.jsonl    0

# And the RED case must be reachable ONLY through a real streak — prove the threshold is honoured
# rather than the rung reporting red on any failure it sees.
if ! LIMEN_BEAT_RUNG_LOG="$work/streak.jsonl" LIMEN_RUNG_FAIL_STREAK_RED=9 \
     python3 "$audit" --efficacy-only --check >/dev/null 2>&1; then
  echo "FAIL threshold: a 3-beat streak went RED against a 9-beat threshold" >&2; exit 1
fi
echo "ok   the RED threshold is a real parameter, not a hardcoded any-failure trip"
pass=$((pass+1))

# The count is an ASSERTION, not a label. A case that stops running — an `eff` call deleted, a
# fixture that vanished — would otherwise leave a cheerful summary behind and cover nothing, which
# is the same silence this suite's newest rung exists to catch one layer down.
EXPECTED_CASES=12
if [ "$pass" -ne "$EXPECTED_CASES" ]; then
  echo "FAIL suite: $pass case(s) ran, expected $EXPECTED_CASES — a case was skipped or removed" >&2
  exit 1
fi
echo "enactment-audit.test.sh: $pass/$EXPECTED_CASES cases passed"
