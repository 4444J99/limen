#!/usr/bin/env bash
#
# omega.sh — the fixed-point predicate for the whole autonomic institution.
#
# The retro (06-24→07-08) closed with a definition of "omega" that no single script could yet
# assert: the system runs nights unattended across vendor seams, products earn without the
# operator's hand, every intake ask is predicate-shaped, healing converges, and nothing hangs on
# the ephemeral session. Each of those already has its OWN shipped predicate (ship-gate,
# heal-convergence, armed-valve-audit, ask-gate, enactment-audit, handoff-relay, no-tasks-on-me,
# credential-wall). omega.sh is their CONJUNCTION: exit 0 ⟺ every rung holds. Beat-wired, it turns
# "drift away from omega" from a discovery into an alarm.
#
# The cardinal rule (retro finding: MONETA read green while its URL returned curl-000): a rung that
# CANNOT be checked here is reported SKIP, never silently PASS. A fixed point you faked is not a
# fixed point. Each rung is tagged det (repo-deterministic, CI-safe) or live (needs host/network);
# --offline runs only the det rungs and SKIPs the rest visibly.
#
#   omega.sh              all rungs (live host / beat) — the real fixed point
#   omega.sh --offline    det rungs only; live rungs → SKIP (CI-safe, deterministic)
#   omega.sh --full       also runs verify-whole.sh for the authoritative main-green rung
#   omega.sh --quiet      table + verdict only (suppress per-rung child output)
#
# Fail-open per rung: a rung whose command errors unexpectedly is FAIL (honest), never a crash of
# the whole predicate. Exit 0 ⟺ zero FAIL rungs (SKIPs are allowed but always reported).

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/cli/src${PYTHONPATH:+:$PYTHONPATH}"
STAMP="$ROOT/logs/omega.json"   # derived from ROOT; the test drives it via a temp-ROOT copy

OFFLINE=0
FULL=0
QUIET=0
for arg in "$@"; do
  case "$arg" in
    --offline) OFFLINE=1 ;;
    --full)    FULL=1 ;;
    --quiet)   QUIET=1 ;;
    -h|--help) grep '^#' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "omega.sh: unknown arg '$arg'" >&2; exit 2 ;;
  esac
done

PASS_N=0; FAIL_N=0; SKIP_N=0
declare -a ROWS=()      # "STATUS\tlabel" for the summary table
declare -a JSON_ROWS=() # {"rung":..,"tier":..,"status":..} for the stamp

# rung <label> <tier:det|live> <cmd...>
# Runs the command, classifies PASS/FAIL/SKIP, tallies, and records a row. A live rung in
# --offline mode is SKIPped without running. Child stdout/stderr is shown unless --quiet.
rung() {
  local label="$1"; local tier="$2"; shift 2
  local status
  if [[ "$tier" == "live" && "$OFFLINE" == "1" ]]; then
    status="SKIP"
  else
    if [[ "$QUIET" == "1" ]]; then
      "$@" >/dev/null 2>&1
    else
      printf '  ── %s ──\n' "$label"
      "$@"
    fi
    local rc=$?
    if [[ $rc -eq 0 ]]; then status="PASS"; else status="FAIL"; fi
  fi
  case "$status" in
    PASS) PASS_N=$((PASS_N+1)) ;;
    FAIL) FAIL_N=$((FAIL_N+1)) ;;
    SKIP) SKIP_N=$((SKIP_N+1)) ;;
  esac
  ROWS+=("$status	[$tier] $label")
  JSON_ROWS+=("{\"rung\":\"$label\",\"tier\":\"$tier\",\"status\":\"$status\"}")
}

# skip_rung <label> <tier> <reason> — a rung with no runnable predicate YET (reported, never faked).
skip_rung() {
  local label="$1"; local tier="$2"; local reason="$3"
  SKIP_N=$((SKIP_N+1))
  ROWS+=("SKIP	[$tier] $label — $reason")
  JSON_ROWS+=("{\"rung\":\"$label\",\"tier\":\"$tier\",\"status\":\"SKIP\",\"reason\":\"$reason\"}")
}

cd "$ROOT"

echo "══ omega.sh — autonomic fixed-point predicate$([[ $OFFLINE == 1 ]] && echo ' (offline/det subset)') ══"

# 1. main green — the trunk itself compiles/tests/builds. Authoritative only via verify-whole.sh
#    (--full); on the beat we read the last CI conclusion for origin/main if gh is reachable.
if [[ "$FULL" == "1" ]]; then
  rung "main-green (verify-whole)" det bash "$ROOT/scripts/verify-whole.sh"
elif command -v gh >/dev/null 2>&1 && [[ "$OFFLINE" == "0" ]]; then
  rung "main-green (last CI on origin/main)" live bash -c '
    concl=$(gh run list --branch main --limit 1 --json conclusion -q ".[0].conclusion" 2>/dev/null)
    [[ "$concl" == "success" ]] || { echo "  latest main CI conclusion: ${concl:-unknown} (want: success)"; exit 1; }
    echo "  latest main CI: success"'
else
  skip_rung "main-green" live "no gh / offline — run omega.sh --full for the authoritative check"
fi

# 2. enactment — every declared-ON fleet gate is actually wired live, not merely merged.
rung "enactment (gates wired)" det python3 "$ROOT/scripts/enactment-audit.py" --check --wiring-only

# 3. armed-valve — no deliverable-IS-behavior valve is silently OFF (registry-completeness contract).
rung "armed-valve (no silent-off)" det python3 "$ROOT/scripts/armed-valve-audit.py" --check --contract --offline --stamp /dev/null

# 4. ask-gate — every intake-window ask is predicate-shaped/bounded/owned (no SPLIT verdicts).
rung "ask-gate (intake predicate-shaped)" det python3 "$ROOT/scripts/ask-gate.py" --audit --since 7 --check --top 0

# 5. ask-lineage convergence — no ask-lineage exceeds 15 repeats without a converged grade. No
#    machine predicate emits this metric yet (censor-lineage territory); reported SKIP, not faked.
skip_rung "ask-lineage <15 unconverged" det "no censor-lineage repeat-count predicate yet"

# 6. ship-gate — every product-facing done-claim resolves to a reachable external artifact.
rung "ship-gate (products reachable)" live python3 "$ROOT/scripts/ship-gate.py" --check

# 7. heal-convergence — the healer converges (no chronic cluster re-spending on the same wall).
rung "heal-convergence (no chronic wall)" live python3 "$ROOT/scripts/heal-convergence.py" --check

# 8. overnight-trial — the most recent unattended overnight run met its thresholds. Written by the
#    trial harness to logs/overnight-trial.json ({pass:true,...}); SKIP until a trial has run.
if [[ -f "$ROOT/logs/overnight-trial.json" ]]; then
  rung "overnight-trial (last run passed)" live python3 -c '
import json,sys
d=json.load(open("logs/overnight-trial.json"))
ok=bool(d.get("pass"))
print(f"  overnight-trial: pass={ok} "
      f"hours={d.get(\"hours\")} seams={d.get(\"vendor_seams\")} merged={d.get(\"merged_prs\")} prompts={d.get(\"operator_prompts\")}")
sys.exit(0 if ok else 1)'
else
  skip_rung "overnight-trial (last run passed)" live "no logs/overnight-trial.json yet — run one trial"
fi

# 9. handoff-relay — a fresh, complete seam-survival packet exists (a warm resume IS possible).
rung "handoff (warm resume ready)" det python3 "$ROOT/scripts/handoff-relay.py" --check

# 10. no-tasks-on-me — nothing hangs on the ephemeral session; every owed item is homed in a
#     git-tracked owner (lever / credential organ / registry), no stranded staged refs.
rung "no-tasks-on-me (owed work homed)" det bash "$ROOT/scripts/no-tasks-on-me.sh"

# 11. credential-wall — every secret in use is homed in its organ (validity, not just presence).
if [[ "$OFFLINE" == "1" ]]; then
  skip_rung "credential-wall (secrets homed)" live "--offline (credential validity authenticates against services)"
else
  rung "credential-wall (secrets homed)" live python3 "$ROOT/scripts/credential-wall.py" --check
fi

# 12+. Registry-declared fixed-point checks. Sensor ids and commands remain inside sensors.yaml;
#      omega consumes only generic {id,index,tier,label} metadata and therefore needs no edit when a
#      sensor is added or renamed. ``rung`` owns offline handling, so every live check remains an
#      explicit SKIP rather than a fake pass.
SENSOR_OMEGA_ROWS="$(mktemp "${TMPDIR:-/tmp}/limen-omega-sensors.XXXXXX")"
if python3 "$ROOT/scripts/beat-sensors.py" --list-omega > "$SENSOR_OMEGA_ROWS"; then
  while IFS=$'\t' read -r sensor_id check_index tier label; do
    [[ -n "$sensor_id" ]] || continue
    rung "$label" "$tier" python3 "$ROOT/scripts/beat-sensors.py" --run-omega "$sensor_id" "$check_index"
  done < "$SENSOR_OMEGA_ROWS"
else
  rung "sensor registry fixed-point discovery" det false
fi
rm -f "$SENSOR_OMEGA_ROWS"

# ── verdict ──────────────────────────────────────────────────────────────────
echo
echo "── omega rungs ──"
for row in "${ROWS[@]}"; do
  printf '  %s\n' "$row"
done
echo
printf 'omega: %d PASS · %d FAIL · %d SKIP\n' "$PASS_N" "$FAIL_N" "$SKIP_N"

VERDICT=$([[ $FAIL_N -eq 0 ]] && echo "HOLDS" || echo "BROKEN")

# Stamp logs/omega.json so session-orient / handoff can read the fixed-point state without re-running.
mkdir -p "$(dirname "$STAMP")" 2>/dev/null || true
python3 - "$STAMP" "$VERDICT" "$PASS_N" "$FAIL_N" "$SKIP_N" "$OFFLINE" "${JSON_ROWS[@]}" <<'PY' 2>/dev/null || true
import datetime as dt, json, sys
stamp, verdict, p, f, s, offline, *rows = sys.argv[1:]
payload = {
    "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "verdict": verdict,
    "offline": offline == "1",
    "pass": int(p), "fail": int(f), "skip": int(s),
    "rungs": [json.loads(r) for r in rows],
}
tmp = stamp + ".tmp"
open(tmp, "w").write(json.dumps(payload, indent=1, sort_keys=True))
import os; os.replace(tmp, stamp)
PY

if [[ $FAIL_N -eq 0 ]]; then
  echo "══ OMEGA HOLDS ══  (SKIPs above are unverified rungs, not failures — close them to raise confidence)"
  exit 0
else
  echo "══ OMEGA BROKEN ══  ($FAIL_N rung(s) failed — the system is not at its fixed point)"
  exit 1
fi
