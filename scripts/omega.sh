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
OMEGA_SCHEMA_VERSION=3

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

# rung <stable-id> <label> <tier:det|live> <cmd...>
# Runs the command, classifies PASS/FAIL/SKIP, tallies, and records a row. A live rung in
# --offline mode is SKIPped without running. Child stdout/stderr is shown unless --quiet.
rung() {
  local rung_id="$1"; local label="$2"; local tier="$3"; shift 3
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
    if [[ $rc -eq 0 ]]; then
      status="PASS"
    elif [[ $rc -eq 77 ]]; then
      status="SKIP"
    else
      status="FAIL"
    fi
  fi
  case "$status" in
    PASS) PASS_N=$((PASS_N+1)) ;;
    FAIL) FAIL_N=$((FAIL_N+1)) ;;
    SKIP) SKIP_N=$((SKIP_N+1)) ;;
  esac
  ROWS+=("$status	[$tier] $label")
  JSON_ROWS+=("{\"id\":\"$rung_id\",\"rung\":\"$label\",\"tier\":\"$tier\",\"status\":\"$status\"}")
}

# skip_rung <stable-id> <label> <tier> <reason> — no runnable predicate YET (reported, never faked).
skip_rung() {
  local rung_id="$1"; local label="$2"; local tier="$3"; local reason="$4"
  SKIP_N=$((SKIP_N+1))
  ROWS+=("SKIP	[$tier] $label — $reason")
  JSON_ROWS+=("{\"id\":\"$rung_id\",\"rung\":\"$label\",\"tier\":\"$tier\",\"status\":\"SKIP\",\"reason\":\"$reason\"}")
}

owner_rung() {
  local rung_id="$1"; local label="$2"
  rung "$rung_id" "$label" live python3 "$ROOT/scripts/omega-owner-receipt.py" --rung-id "$rung_id"
}

cd "$ROOT"

# Discover the registry-owned rungs once through the stable JSON contract. A private TSV projection
# carries only the execution coordinates Bash needs; the JSON contract and explicit core registry
# remain the semantic identity hashed into every stamp.
CORE_RUNG_REGISTRY="$ROOT/institutio/governance/omega-core-rungs.json"
REMEDIATION_REGISTRY="$ROOT/institutio/governance/omega-remediations.json"
SENSOR_OMEGA_JSON="$(mktemp "${TMPDIR:-/tmp}/limen-omega-sensors-json.XXXXXX")"
SENSOR_OMEGA_ROWS="$(mktemp "${TMPDIR:-/tmp}/limen-omega-sensors-tsv.XXXXXX")"
trap 'rm -f "$SENSOR_OMEGA_JSON" "$SENSOR_OMEGA_ROWS"' EXIT
SENSOR_DISCOVERY_OK=0
if python3 "$ROOT/scripts/beat-sensors.py" --list-omega-json > "$SENSOR_OMEGA_JSON" && \
   python3 - "$SENSOR_OMEGA_JSON" > "$SENSOR_OMEGA_ROWS" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if payload.get("schema") != "limen.omega_sensor_rungs.v1":
    raise SystemExit("unknown sensor rung discovery schema")
for rung in payload.get("rungs", []):
    fields = [rung["id"], rung["sensor_id"], str(rung["check_index"]), rung["tier"], rung["label"]]
    if any("\t" in field or "\n" in field for field in fields):
        raise SystemExit("invalid tab/newline in omega sensor execution metadata")
    print("\t".join(fields))
PY
then
  SENSOR_DISCOVERY_OK=1
fi
REMEDIATION_OK=0
if python3 "$ROOT/scripts/omega-remediation.py" --check --quiet; then
  REMEDIATION_OK=1
fi
CONTRACT_HASH="$(python3 - "$ROOT/scripts/omega.sh" "$CORE_RUNG_REGISTRY" \
  "$SENSOR_OMEGA_JSON" "$REMEDIATION_REGISTRY" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

from limen.omega_remediation import normalized_registry_payload

script_path, core_path, sensor_path, remediation_path = map(Path, sys.argv[1:])
core = json.loads(core_path.read_text(encoding="utf-8"))
sensors = json.loads(sensor_path.read_text(encoding="utf-8"))
remediations = normalized_registry_payload(json.loads(remediation_path.read_text(encoding="utf-8")))
if core.get("schema") != "limen.omega_rung_registry.v1":
    raise SystemExit("unknown core rung schema")
if sensors.get("schema") != "limen.omega_sensor_rungs.v1":
    raise SystemExit("unknown sensor rung schema")
ids = []
owner_receipt_paths = []
for source, rung in [
    *(("core", rung) for rung in core.get("rungs", [])),
    *(("sensor", rung) for rung in sensors.get("rungs", [])),
]:
    rung_id = rung.get("id")
    if not isinstance(rung_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", rung_id):
        raise SystemExit("missing or invalid omega rung id")
    semantic_inputs = rung.get("semantic_inputs")
    if not isinstance(semantic_inputs, list) or not semantic_inputs:
        raise SystemExit(f"{rung_id}: missing semantic inputs")
    if rung.get("tier") not in {"det", "live"}:
        raise SystemExit(f"{rung_id}: invalid tier")
    owner_receipts = [
        descriptor
        for descriptor in semantic_inputs
        if isinstance(descriptor, dict) and descriptor.get("role") == "owner_receipt"
    ]
    if rung.get("tier") == "live":
        if len(owner_receipts) != 1:
            raise SystemExit(f"{rung_id}: live rung must declare exactly one owner receipt")
        descriptor = owner_receipts[0]
        if (
            descriptor.get("normalization") != "json"
            or descriptor.get("volatile_fields") != ["observed_at"]
            or isinstance(descriptor.get("max_age_seconds"), bool)
            or not isinstance(descriptor.get("max_age_seconds"), int)
            or not 1 <= descriptor["max_age_seconds"] <= 604800
        ):
            raise SystemExit(f"{rung_id}: live owner receipt descriptor is invalid")
        receipt_path = descriptor.get("path")
        if (
            not isinstance(receipt_path, str)
            or not receipt_path
            or Path(receipt_path).is_absolute()
            or ".." in Path(receipt_path).parts
        ):
            raise SystemExit(f"{rung_id}: live owner receipt path is invalid")
        owner_receipt_paths.append(receipt_path)
        if source == "core":
            timeout = rung.get("timeout")
            if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 7200:
                raise SystemExit(f"{rung_id}: live core timeout is invalid")
    ids.append(rung_id)
if len(ids) != len(set(ids)):
    raise SystemExit("duplicate omega rung id")
if len(owner_receipt_paths) != len(set(owner_receipt_paths)):
    raise SystemExit("duplicate live owner receipt path")
core_for_hash = {**core, "rungs": sorted(core["rungs"], key=lambda rung: rung["id"])}
sensors_for_hash = {**sensors, "rungs": sorted(sensors["rungs"], key=lambda rung: rung["id"])}
normalized_core = json.dumps(core_for_hash, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
normalized_sensors = json.dumps(sensors_for_hash, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
digest = hashlib.sha256()
digest.update(b"omega.sh\0")
digest.update(script_path.read_bytes())
digest.update(b"\0normalized-core-rungs\0")
digest.update(normalized_core)
digest.update(b"\0normalized-sensor-rungs\0")
digest.update(normalized_sensors)
digest.update(b"\0normalized-remediations\0")
digest.update(json.dumps(remediations, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii"))
print(digest.hexdigest())
PY
)"
echo "══ omega.sh — autonomic fixed-point predicate$([[ $OFFLINE == 1 ]] && echo ' (offline/det subset)')$([[ $STRICT == 1 ]] && echo ' (strict)') ══"
if [[ "$SENSOR_DISCOVERY_OK" != "1" || ! "$CONTRACT_HASH" =~ ^[0-9a-f]{64}$ ]]; then
  echo "══ OMEGA CONTRACT INVALID ══  (rung discovery or contract validation failed; no stamp was written)" >&2
  exit 1
fi
if [[ "$REMEDIATION_OK" != "1" ]]; then
  echo "══ OMEGA CONTRACT INVALID ══  (every discovered rung requires typed remediation metadata)" >&2
  exit 1
fi

# 1. main green — the trunk itself compiles/tests/builds. Authoritative locally via verify-whole.sh
#    (--full); on the beat require the workflow-filtered completed CI run for the exact origin/main.
if [[ "$FULL" == "1" ]]; then
  rung core.main-green "main-green (verify-whole)" det bash "$ROOT/scripts/verify-whole.sh"
elif command -v gh >/dev/null 2>&1 && [[ "$OFFLINE" == "0" ]]; then
  rung core.main-green "main-green (exact-head completed CI)" live env LIMEN_ROOT="$ROOT" python3 "$ROOT/scripts/check-main-green.py" --exact-head-check
else
  skip_rung core.main-green "main-green" live "no gh / offline — run omega.sh --full for the authoritative check"
fi

# 2. enactment — every declared-ON fleet gate is actually wired live, not merely merged.
rung core.enactment "enactment (gates wired)" det python3 "$ROOT/scripts/enactment-audit.py" --check --wiring-only

# 3. armed-valve — no deliverable-IS-behavior valve is silently OFF (registry-completeness contract).
rung core.armed-valve "armed-valve (no silent-off)" det python3 "$ROOT/scripts/armed-valve-audit.py" --check --contract --offline --stamp /dev/null

# 4. ask-gate — every intake-window ask is predicate-shaped/bounded/owned (no SPLIT verdicts).
rung core.ask-gate "ask-gate (intake predicate-shaped)" det python3 "$ROOT/scripts/ask-gate.py" --audit --since 7 --check --top 0

# 5. ask-lineage convergence — the prompt-corpus control plane is coherent and can advance:
#    cursor checkpoint-bound, scanner version current, no unresolved obligation orphaned on a
#    stale scan-version key (the merge-deadlock class, fixed 2026-07-14). The sensor default is 1
#    (armed since PR fix/agy-steps-schema-v2); the rung runs unless LIMEN_PROMPT_ATOM_CONTROL=0.
if [[ "${LIMEN_PROMPT_ATOM_CONTROL:-1}" == "1" ]]; then
  rung core.ask-lineage "ask-lineage convergence" det python3 "$ROOT/scripts/prompt-atom-ledger.py" --check-cursor
else
  skip_rung core.ask-lineage "ask-lineage convergence" det "prompt-corpus sensor dark: source cursor not bound to private checkpoint — reseal via prompt-atom-ledger.py --scan"
fi

# 6. ship-gate — every product-facing done-claim resolves to a reachable external artifact.
owner_rung core.ship-gate "ship-gate (products reachable)"

# 7. heal-convergence — the healer converges (no chronic cluster re-spending on the same wall).
owner_rung core.heal-convergence "heal-convergence (no chronic wall)"

# 8. overnight-trial — the most recent unattended overnight run met its content-addressed contract.
#    The producer verifies eight-hour coverage, every 90-minute value/blocker window, a warm handoff,
#    at least one structured session seam, zero operator interventions, zero alerts, and
#    evaluator/input hashes reconstructed from the exact bounded source receipts.
owner_rung core.overnight-trial "overnight-trial (last run passed)"

# 9. handoff-relay — a fresh, complete seam-survival packet exists (a warm resume IS possible).
rung core.handoff "handoff (warm resume ready)" det python3 "$ROOT/scripts/handoff-relay.py" --check

# 10. autonomy-acting — the maintenance rail is ACTING: no resume predicate sits stuck
#     unrunnable or red past its window (the distinct state PR #1827 surfaced).
rung core.autonomy-acting "autonomy-acting (no stuck maintenance blocker)" det python3 "$ROOT/scripts/autonomy-governor.py" acting

# 11. no-tasks-on-me — nothing hangs on the ephemeral session; every owed item is homed in a
#     git-tracked owner (lever / credential organ / registry), no stranded staged refs.
owner_rung core.no-tasks-on-me "no-tasks-on-me (owed work homed)"

# 12. credential-wall — every secret in use is homed in its organ (validity, not just presence).
owner_rung core.credential-wall "credential-wall (secrets homed)"

# 13. lifecycle closure — preserved worktree debt is a diagnostic during ordinary dispatch, but
#     Omega is the exact-zero fixed point: no debt roots and no accepted-reaper residue. The scan is
#     intentionally live/explicit (not a dispatch hot-path check), so offline CI reports SKIP.
owner_rung core.worktree-lifecycle "worktree lifecycle (exact zero)"

# 14+. Registry-declared fixed-point checks. Sensor ids and commands remain inside sensors.yaml;
#      omega consumes only generic {id,index,tier,label} metadata and therefore needs no edit when a
#      sensor is added or renamed. ``rung`` owns offline handling, so every live check remains an
#      explicit SKIP rather than a fake pass.
while IFS=$'\t' read -r rung_id sensor_id check_index tier label; do
  [[ -n "$rung_id" ]] || continue
  rung "$rung_id" "$label" "$tier" python3 "$ROOT/scripts/beat-sensors.py" --run-omega "$sensor_id" "$check_index"
done < "$SENSOR_OMEGA_ROWS"

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
STAMP_OK=0
if python3 - "$ROOT" "$STAMP" "$OMEGA_SCHEMA_VERSION" "$CONTRACT_HASH" "$VERDICT" \
  "$PASS_N" "$FAIL_N" "$SKIP_N" "$OFFLINE" "$STRICT" "${JSON_ROWS[@]}" <<'PY'
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

from limen.omega_remediation import annotate_omega_stamp, load_omega_remediations

root, stamp, schema, contract_hash, verdict, p, f, s, offline, strict, *rows = sys.argv[1:]
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
rung_contracts, remediations = load_omega_remediations(Path(root))
payload = annotate_omega_stamp(payload, rung_contracts, remediations)
stamp_path = Path(stamp)
with tempfile.NamedTemporaryFile(
    dir=stamp_path.parent,
    prefix=f".{stamp_path.name}.",
    delete=False,
) as handle:
    handle.write((json.dumps(payload, indent=1, sort_keys=True) + "\n").encode("ascii"))
    handle.flush()
    os.fsync(handle.fileno())
    temporary = Path(handle.name)
try:
    os.replace(temporary, stamp_path)
finally:
    temporary.unlink(missing_ok=True)
PY
then
  STAMP_OK=1
fi
if [[ "$STAMP_OK" != "1" ]]; then
  echo "══ OMEGA CONTRACT INVALID ══  (typed remediation stamp could not be written)" >&2
  exit 1
fi

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
