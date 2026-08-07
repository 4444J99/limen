#!/usr/bin/env bash
# armed-valve-audit.test.sh — regression test for scripts/armed-valve-audit.py
#
# The predicate must separate the three states the retro conflated (finding 8;
# PREC-2026-07-08-armed-valve-outcome):
#   ARMED       env arm active                          → exit 0
#   PARKED      disarmed deliverable, lever cites it    → exit 0 (owned, not dropped)
#   SILENT-OFF  disarmed deliverable, NO lever citation → exit 1 (the failure class)
# and a new disarmed-by-default gate absent from the registry must surface as
# UNCLASSIFIED without failing the gate (self-surfacing registry, never a hard trip).
#
# Deterministic + idempotent (exit 0 ⟺ all cases pass): env-kind valves only (no
# network), stubbed sources/registry/levers/env-file, stamps into the tmpdir.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
audit="$here/../armed-valve-audit.py"
[ -f "$audit" ] || { echo "FAIL: cannot find armed-valve-audit.py at $audit" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# Beat-source fixture: one deliverable gate (off by default), one unclassified new gate.
cat > "$work/beat.sh" <<'SH'
#!/usr/bin/env bash
if [ "${VALVEFIX_TEST_VALVE:-0}" = "1" ]; then echo on; fi
if [ "${VALVEFIX_TEST_NEWGATE:-0}" = "1" ]; then echo new; fi
SH

cat > "$work/registry.json" <<'JSON'
{"deliverable": [{"id": "VALVEFIX_TEST_VALVE", "kind": "env", "expected": "1", "what": "test valve"}], "safety": []}
JSON

echo '{"levers": []}' > "$work/levers-empty.json"
echo '{"levers": [{"id": "L-TEST", "label": "arm VALVEFIX_TEST_VALVE when ready"}]}' > "$work/levers-cites.json"
: > "$work/env-unarmed"
echo 'export VALVEFIX_TEST_VALVE=1' > "$work/env-armed"

run() { # $1=env-file $2=levers-file
  env -u VALVEFIX_TEST_VALVE python3 "$audit" --check --offline --gate-prefix VALVEFIX_ \
    --registry "$work/registry.json" --sources "$work/beat.sh" \
    --env-file "$1" --levers "$2" --stamp "$work/stamp.json"
}

echo "case 1: armed valve → exit 0"
run "$work/env-armed" "$work/levers-empty.json" >/dev/null || { echo "FAIL: armed valve tripped the gate" >&2; exit 1; }

echo "case 2: disarmed + lever citation → PARKED, exit 0"
out="$(run "$work/env-unarmed" "$work/levers-cites.json")" || { echo "FAIL: parked lever tripped the gate" >&2; exit 1; }
grep -q "PARKED" <<<"$out" || { echo "FAIL: expected PARKED verdict, got: $out" >&2; exit 1; }

echo "case 3: disarmed + no citation → SILENT-OFF, exit 1"
if out="$(run "$work/env-unarmed" "$work/levers-empty.json" 2>&1)"; then
  echo "FAIL: silently-off valve did NOT trip the gate: $out" >&2; exit 1
fi
grep -q "SILENT-OFF" <<<"$out" || { echo "FAIL: expected SILENT-OFF verdict, got: $out" >&2; exit 1; }

echo "case 4: new disarmed-by-default gate → UNCLASSIFIED warning, never a hard trip"
out="$(run "$work/env-armed" "$work/levers-empty.json")"
grep -q "UNCLASSIFIED.*VALVEFIX_TEST_NEWGATE" <<<"$out" || { echo "FAIL: new gate did not surface as UNCLASSIFIED: $out" >&2; exit 1; }

echo "case 5: stamp written with counts"
python3 -c "import json,sys; d=json.load(open('$work/stamp.json')); sys.exit(0 if d.get('counts') and d.get('valves') else 1)" \
  || { echo "FAIL: stamp missing counts/valves" >&2; exit 1; }

echo "armed-valve-audit.test: all cases pass"

echo "case 6: --contract trips only on UNCLASSIFIED (repo-deterministic rung)"
if env -u VALVEFIX_TEST_VALVE python3 "$audit" --check --contract --offline --gate-prefix VALVEFIX_ \
    --registry "$work/registry.json" --sources "$work/beat.sh" \
    --env-file "$work/env-unarmed" --levers "$work/levers-empty.json" --stamp "$work/stamp.json" >/dev/null 2>&1; then
  echo "FAIL: contract mode missed the unclassified gate" >&2; exit 1
fi
cat > "$work/registry-complete.json" <<'JSON'
{"deliverable": [{"id": "VALVEFIX_TEST_VALVE", "kind": "env", "expected": "1", "what": "test valve"}], "safety": ["VALVEFIX_TEST_NEWGATE"]}
JSON
env -u VALVEFIX_TEST_VALVE python3 "$audit" --check --contract --offline --gate-prefix VALVEFIX_ \
    --registry "$work/registry-complete.json" --sources "$work/beat.sh" \
    --env-file "$work/env-unarmed" --levers "$work/levers-empty.json" --stamp "$work/stamp.json" >/dev/null \
  || { echo "FAIL: complete registry failed contract mode (SILENT-OFF must not trip --contract)" >&2; exit 1; }

echo "armed-valve-audit.test: contract cases pass"

echo "case 7: arbitrary sensor id classifies its conditional valve from sensors.yaml"
cat > "$work/sensors.yaml" <<'YAML'
sensors:
  arbitrary.future.id:
    section: heartbeat
    title: arbitrary future sensor
    source: [heartbeat]
    steps:
      - command: "python3 scripts/arbitrary.py"
        args_when:
          - env: VALVEFIX_TEST_NEWGATE
            default: "0"
            equals: "1"
            args: ["--apply"]
            armed_valve_type: safety
        severity: silent
        escalation: skipped
YAML
out="$(env -u VALVEFIX_TEST_VALVE python3 "$audit" --check --contract --offline --gate-prefix VALVEFIX_ \
  --registry "$work/registry.json" --sensors "$work/sensors.yaml" --sources "$work/beat.sh" \
  --env-file "$work/env-armed" --levers "$work/levers-empty.json" --stamp "$work/stamp.json")" \
  || { echo "FAIL: registry-declared safety valve failed contract mode" >&2; exit 1; }
grep -q "SAFE-OFF.*VALVEFIX_TEST_NEWGATE" <<<"$out" \
  || { echo "FAIL: sensor capability did not classify renamed valve: $out" >&2; exit 1; }

echo "armed-valve-audit.test: sensor capability cases pass"

# ── file_json probes: is a LOCAL arming state present? (F5 of the cadence-guard arc) ───────────
# The gap: an unarmed SessionStart guard is byte-identical to a guard that ran and found nothing.
# These cases pin that an absent/unparseable/unset arm is NOT armed, that a cited lever makes it
# PARKED rather than SILENT-OFF, and — load-bearing — that --offline never skips a local probe
# (skipping would restore the very silence the row exists to break).
echo 'export VALVEFIX_TEST_VALVE=1' > "$work/env-armed"
echo '{"levers": [{"id": "L-ARM-TEST", "label": "paste the snippet"}]}' > "$work/levers-arm.json"

cat > "$work/reg-file.json" <<JSON
{"deliverable": [
  {"id": "ARM_NEEDLE", "kind": "file_json", "path": "$work/settings.json",
   "needle": "guard.py", "lever": "L-ARM-TEST", "what": "hook wired"},
  {"id": "ARM_POINTER", "kind": "file_json", "path": "$work/settings.json",
   "pointer": "model", "expected_any": ["sonnet", "haiku"], "lever": "L-ARM-TEST", "what": "opening pin"}
], "safety": ["VALVEFIX_TEST_NEWGATE"]}
JSON

runfile() { # $1 = extra args
  env -u VALVEFIX_TEST_VALVE python3 "$audit" --check --offline --gate-prefix VALVEFIX_ \
    --registry "$work/reg-file.json" --sources "$work/beat.sh" \
    --env-file "$work/env-armed" --levers "$work/levers-arm.json" --stamp "$work/stamp.json" ${1:-}
}

echo "case 8: absent settings file → not armed, cited lever → PARKED (owned, not dropped)"
rm -f "$work/settings.json"
out="$(runfile)" || { echo "FAIL: absent file should be PARKED (exit 0), not SILENT-OFF" >&2; exit 1; }
grep -q "PARKED *ARM_NEEDLE" <<<"$out" || { echo "FAIL: expected PARKED ARM_NEEDLE, got: $out" >&2; exit 1; }
grep -q "absent" <<<"$out" || { echo "FAIL: note should name the absent file: $out" >&2; exit 1; }

echo "case 9: armed settings file → ARMED on both needle and pointer"
echo '{"model": "sonnet", "hooks": {"SessionStart": [{"hooks": [{"command": "python3 guard.py"}]}]}}' > "$work/settings.json"
out="$(runfile)" || { echo "FAIL: armed file tripped the gate: $out" >&2; exit 1; }
grep -q "ARM_NEEDLE" <<<"$out" && { echo "FAIL: ARMED rows must stay silent, saw ARM_NEEDLE: $out" >&2; exit 1; }
grep -q "ARM_POINTER" <<<"$out" && { echo "FAIL: ARMED rows must stay silent, saw ARM_POINTER: $out" >&2; exit 1; }

echo "case 10: pointer present but ABOVE the ceiling → not armed (expected_any is a whitelist)"
echo '{"model": "opus", "hooks": {"SessionStart": [{"hooks": [{"command": "python3 guard.py"}]}]}}' > "$work/settings.json"
out="$(runfile)" || { echo "FAIL: off-ceiling pin should be PARKED, not SILENT-OFF" >&2; exit 1; }
grep -q "PARKED *ARM_POINTER" <<<"$out" || { echo "FAIL: expected PARKED ARM_POINTER, got: $out" >&2; exit 1; }
grep -q "model=opus" <<<"$out" || { echo "FAIL: note should report the offending value: $out" >&2; exit 1; }

echo "case 11: unparseable settings file → NOT armed (a corrupt file is a finding, never a pass)"
echo '{ this is not json' > "$work/settings.json"
out="$(runfile)" || { echo "FAIL: unparseable file should be PARKED, not SILENT-OFF" >&2; exit 1; }
grep -q "unparseable" <<<"$out" || { echo "FAIL: expected an unparseable note, got: $out" >&2; exit 1; }

echo "case 12: --offline must NOT skip a local file probe (skipping restores the silence)"
grep -q "SKIP *ARM_NEEDLE" <<<"$out" && { echo "FAIL: --offline skipped a local file_json probe: $out" >&2; exit 1; }

echo "case 13: no lever citation → a disarmed file probe is SILENT-OFF, exit 1"
if out="$(env -u VALVEFIX_TEST_VALVE python3 "$audit" --check --offline --gate-prefix VALVEFIX_ \
    --registry "$work/reg-file.json" --sources "$work/beat.sh" \
    --env-file "$work/env-armed" --levers "$work/levers-empty.json" --stamp "$work/stamp.json" 2>&1)"; then
  echo "FAIL: uncited disarmed file probe did NOT trip the gate: $out" >&2; exit 1
fi
grep -q "SILENT-OFF" <<<"$out" || { echo "FAIL: expected SILENT-OFF, got: $out" >&2; exit 1; }

echo "armed-valve-audit.test: file_json cases pass"
