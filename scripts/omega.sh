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
#   omega.sh --strict     any FAIL or SKIP is non-zero (default remains zero-FAIL compatible)
#   omega.sh --quiet      table + verdict only (suppress per-rung child output)
#
# Fail-open per rung: a rung whose command errors unexpectedly is FAIL (honest), never a crash of
# the whole predicate. Default exit 0 ⟺ zero FAIL rungs (SKIPs are allowed but always reported);
# strict exit 0 ⟺ zero FAIL and zero SKIP rungs.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT/cli/src${PYTHONPATH:+:$PYTHONPATH}"
STAMP="$ROOT/logs/omega.json"   # derived from ROOT; the test drives it via a temp-ROOT copy
OMEGA_SCHEMA_VERSION=1

OFFLINE=0
FULL=0
STRICT=0
QUIET=0
for arg in "$@"; do
  case "$arg" in
    --offline) OFFLINE=1 ;;
    --full)    FULL=1 ;;
    --strict)  STRICT=1 ;;
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

# Discover the registry-owned rungs once.  The same normalized rows feed both execution and the
# contract hash, so the stamp identifies the exact contract that produced its verdict.  Sorting in
# the hash makes registry serialization order irrelevant while add/remove/rename/capability changes
# still change the identity.
SENSOR_OMEGA_ROWS="$(mktemp "${TMPDIR:-/tmp}/limen-omega-sensors.XXXXXX")"
trap 'rm -f "$SENSOR_OMEGA_ROWS"' EXIT
SENSOR_DISCOVERY_OK=0
if python3 "$ROOT/scripts/beat-sensors.py" --list-omega > "$SENSOR_OMEGA_ROWS"; then
  SENSOR_DISCOVERY_OK=1
fi
CONTRACT_HASH="$(python3 - "$ROOT/scripts/omega.sh" "$SENSOR_OMEGA_ROWS" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

script_path, sensor_path = map(Path, sys.argv[1:])
rows = []
for raw in sensor_path.read_text(encoding="utf-8").splitlines():
    if not raw:
        continue
    parts = raw.split("\t", 5)
    if len(parts) != 6:
        raise SystemExit(f"invalid omega sensor row: {raw!r}")
    sensor_id, check_index, tier, label, command, timeout = parts
    rows.append(
        {
            "check_index": int(check_index),
            "id": sensor_id,
            "label": label,
            "tier": tier,
            "command": command,
            "timeout": int(timeout),
        }
    )
normalized = json.dumps(
    sorted(rows, key=lambda row: (row["id"], row["check_index"], row["tier"], row["label"])),
    ensure_ascii=True,
    separators=(",", ":"),
    sort_keys=True,
).encode("ascii")
digest = hashlib.sha256()
digest.update(b"omega.sh\0")
digest.update(script_path.read_bytes())
digest.update(b"\0normalized-sensor-rungs\0")
digest.update(normalized)
print(digest.hexdigest())
PY
)"
if [[ ! "$CONTRACT_HASH" =~ ^[0-9a-f]{64}$ ]]; then
  SENSOR_DISCOVERY_OK=0
  CONTRACT_HASH="$(python3 - "$ROOT/scripts/omega.sh" <<'PY'
import hashlib, sys
from pathlib import Path
print(hashlib.sha256(b"omega.sh\0" + Path(sys.argv[1]).read_bytes() + b"\0sensor-discovery-error").hexdigest())
PY
)"
fi

echo "══ omega.sh — autonomic fixed-point predicate$([[ $OFFLINE == 1 ]] && echo ' (offline/det subset)')$([[ $STRICT == 1 ]] && echo ' (strict)') ══"

# 1. main green — the trunk itself compiles/tests/builds. Authoritative locally via verify-whole.sh
#    (--full); on the beat require the workflow-filtered completed CI run for the exact origin/main.
if [[ "$FULL" == "1" ]]; then
  rung "main-green (verify-whole)" det bash "$ROOT/scripts/verify-whole.sh"
elif command -v gh >/dev/null 2>&1 && [[ "$OFFLINE" == "0" ]]; then
  rung "main-green (exact-head completed CI)" live env LIMEN_ROOT="$ROOT" python3 "$ROOT/scripts/check-main-green.py" --exact-head-check
else
  skip_rung "main-green" live "no gh / offline — run omega.sh --full for the authoritative check"
fi

# 2. enactment — every declared-ON fleet gate is actually wired live, not merely merged.
rung "enactment (gates wired)" det python3 "$ROOT/scripts/enactment-audit.py" --check --wiring-only

# 3. armed-valve — no deliverable-IS-behavior valve is silently OFF (registry-completeness contract).
rung "armed-valve (no silent-off)" det python3 "$ROOT/scripts/armed-valve-audit.py" --check --contract --offline --stamp /dev/null

# 4. ask-gate — every intake-window ask is predicate-shaped/bounded/owned (no SPLIT verdicts).
rung "ask-gate (intake predicate-shaped)" det python3 "$ROOT/scripts/ask-gate.py" --audit --since 7 --check --top 0

# 5. ask-lineage convergence has a manual predicate, but its heartbeat sensor remains DARK until a
#    measured first-pass + idempotent-no-op canary proves the host-safe activation gate. It is not
#    Omega-eligible before then; report the missing proof explicitly instead of running it here.
skip_rung "ask-lineage convergence" det "prompt-corpus sensor is dark pending a measured bounded canary"

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
if [[ "$SENSOR_DISCOVERY_OK" == "1" ]]; then
  while IFS=$'\t' read -r sensor_id check_index tier label _command _timeout; do
    [[ -n "$sensor_id" ]] || continue
    rung "$label" "$tier" python3 "$ROOT/scripts/beat-sensors.py" --run-omega "$sensor_id" "$check_index"
  done < "$SENSOR_OMEGA_ROWS"
else
  rung "sensor registry fixed-point discovery" det false
fi

# ── verdict ──────────────────────────────────────────────────────────────────
echo
echo "── omega rungs ──"
for row in "${ROWS[@]}"; do
  printf '  %s\n' "$row"
done
echo
printf 'omega: %d PASS · %d FAIL · %d SKIP\n' "$PASS_N" "$FAIL_N" "$SKIP_N"

if [[ $FAIL_N -gt 0 ]]; then
  VERDICT="BROKEN"
elif [[ $STRICT -eq 1 && $SKIP_N -gt 0 ]]; then
  VERDICT="INCOMPLETE"
else
  VERDICT="HOLDS"
fi

# Stamp logs/omega.json so session-orient / handoff can read the fixed-point state without re-running.
mkdir -p "$(dirname "$STAMP")" 2>/dev/null || true
python3 - "$STAMP" "$OMEGA_SCHEMA_VERSION" "$CONTRACT_HASH" "$VERDICT" "$PASS_N" "$FAIL_N" "$SKIP_N" "$OFFLINE" "$STRICT" "${JSON_ROWS[@]}" <<'PY' 2>/dev/null || true
import datetime as dt, json, sys
stamp, schema, contract_hash, verdict, p, f, s, offline, strict, *rows = sys.argv[1:]
generated_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
payload = {
    "schema_version": int(schema),
    "generated": generated_at,
    "generated_at": generated_at,
    "contract_hash": contract_hash,
    "verdict": verdict,
    "offline": offline == "1",
    "strict": strict == "1",
    "pass": int(p), "fail": int(f), "skip": int(s),
    "rungs": [json.loads(r) for r in rows],
}
tmp = stamp + ".tmp"
open(tmp, "w").write(json.dumps(payload, indent=1, sort_keys=True))
import os; os.replace(tmp, stamp)
PY

if [[ "$VERDICT" == "HOLDS" ]]; then
  echo "══ OMEGA HOLDS ══  (SKIPs above are unverified rungs, not failures — close them to raise confidence)"
  exit 0
elif [[ "$VERDICT" == "INCOMPLETE" ]]; then
  echo "══ OMEGA INCOMPLETE ══  ($SKIP_N rung(s) skipped under --strict — every rung must be verified)"
  exit 1
else
  echo "══ OMEGA BROKEN ══  ($FAIL_N rung(s) failed — the system is not at its fixed point)"
  exit 1
fi
