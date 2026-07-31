#!/usr/bin/env bash
# Regression matrix for scripts/heal-hook-wiring.py.
#
# FOUNDING DEFECT (2026-07-31): v1 parsed the cartridge source with json.loads on the
# assumption that every chezmoi {{ … }} action sat inside a JSON string value. The live
# template's statusLine carries `"command": {{ printf … | toJson }}` — an action producing a
# JSON value at the STRUCTURAL level — so the source is not parseable and never will be. The
# effector refused (correctly, rather than corrupting a permission file) and did nothing.
#
# So case 1 below is the live shape: a template that is NOT valid JSON. Every splice case runs
# against it. HERMETIC: fixtures under mktemp, DOMUS_ROOT overridden so the real cartridge is
# never touched and the deploy path is skipped.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HEAL="$ROOT/scripts/heal-hook-wiring.py"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/hookwiring.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

pass=0 fail=0
ok()   { pass=$((pass+1)); printf '  ok   %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  FAIL %s\n' "$1"; }

# HERMETIC TARGET. Every case must be pinned to a fixture target: unpinned, the
# deployed-state check reads the real ~/.claude/settings.json and the suite's verdict depends
# on whether THIS host happens to be wired. The default is a fully-synced target so
# source-level cases see "nothing to deploy"; cases about deployment override it explicitly.
SYNCED="$WORK/target-synced.json"
python3 - "$SYNCED" <<'PY'
import json, sys
json.dump({
    "permissions": {
        "defaultMode": "auto",
        "ask": ["Bash(git push* --force*)", "Bash(git push* -f*)",
                "Bash(rm:*)", "Bash(rmdir:*)", "Bash(shred:*)"],
        "autoMode": {"allow": ["$defaults"]},
    },
    "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": "x/allow-trusted-cd-git.sh"}]}]},
}, open(sys.argv[1], "w"))
PY
export LIMEN_HOOK_WIRING_TARGET="$SYNCED"

# $1 = fixture name, $2 = body
mkfixture() {
  local d="$WORK/$1"
  mkdir -p "$d/private_dot_claude"
  printf '%s\n' "$2" > "$d/private_dot_claude/settings.json.tmpl"
  printf '%s' "$d"
}

# $1 = label, $2 = expected exit, $3 = DOMUS_ROOT, rest = argv
expect_exit() {
  local label="$1" want="$2" root="$3"; shift 3
  local out; out="$(DOMUS_ROOT="$root" python3 "$HEAL" "$@" 2>&1)"; local got=$?
  if [ "$got" = "$want" ]; then ok "$label (exit $got)"
  else bad "$label — wanted exit $want, got $got"; printf '%s\n' "$out" | sed 's/^/       /'; fi
}

# The live shape: a template action OUTSIDE a string, so the file is not valid JSON.
NOT_JSON='{
  "permissions": {
    "defaultMode": "auto"
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "{{ .chezmoi.homeDir }}/.local/bin/domus-claude-host-hook"
          }
        ]
      }
    ]
  },
  "statusLine": {
    "command": {{ printf "bash -c %s" (include "x.sh") | toJson }}
  }
}'

echo "── splice against a NON-JSON template (the founding defect) ──"
F1="$(mkfixture notjson "$NOT_JSON")"
expect_exit "dry-run reports drift"            1 "$F1"
expect_exit "dry-run wrote nothing"            1 "$F1"   # still drifted => still exit 1
expect_exit "apply succeeds"                   0 "$F1" --apply
expect_exit "re-apply is a clean no-op"        0 "$F1" --apply
expect_exit "dry-run after apply is clean"     0 "$F1"

echo "── the applied result carries all three assertions ──"
T="$F1/private_dot_claude/settings.json.tmpl"
grep -q 'allow-trusted-cd-git.sh' "$T" && ok "hook wired"            || bad "hook wired"
grep -q '"Bash(shred:\*)"'        "$T" && ok "ask rules present"     || bad "ask rules present"
grep -q '"\$defaults"'            "$T" && ok "autoMode leads \$defaults" || bad "autoMode leads \$defaults"
grep -q '"defaultMode": "auto"'   "$T" && ok "defaultMode untouched" || bad "defaultMode untouched"
grep -q 'printf "bash -c %s"'     "$T" && ok "template action preserved verbatim" \
                                        || bad "template action preserved verbatim"
[ -f "$T.bak" ] && ok "backup written" || bad "backup written"

echo "── env arm is equivalent to --apply ──"
F2="$(mkfixture envarm "$NOT_JSON")"
out="$(DOMUS_ROOT="$F2" LIMEN_HOOK_WIRING_HEAL=1 python3 "$HEAL" 2>&1)"; got=$?
[ "$got" = 0 ] && ok "LIMEN_HOOK_WIRING_HEAL=1 applies" || bad "LIMEN_HOOK_WIRING_HEAL=1 applies ($got)"

echo "── anchors: absent or ambiguous is a hard stop, never a guess ──"
F3="$(mkfixture noanchor '{ "hooks": { "PreToolUse": [] } }')"
expect_exit "missing defaultMode anchor -> exit 2"   2 "$F3" --apply
F4="$(mkfixture dupanchor '{
  "permissions": { "defaultMode": "auto" },
  "other":       { "defaultMode": "auto" },
  "hooks": { "PreToolUse": [] }
}')"
expect_exit "duplicate defaultMode anchor -> exit 2" 2 "$F4" --apply
grep -q 'allow-trusted' "$F4/private_dot_claude/settings.json.tmpl" \
  && bad "ambiguous anchor must not write" || ok "ambiguous anchor wrote nothing"

echo "── a missing source is exit 2, not a traceback ──"
expect_exit "absent cartridge source -> exit 2" 2 "$WORK/nope" --apply

echo "── FALSE GREEN: a correct source with an UNDEPLOYED target must not report clean ──"
# v3's early return checked only the source. A prior run had written the source then died at
# deploy (no TTY), so the next run printed "clean" and exited 0 while the live settings.json
# still had the hook unwired, ask empty and autoMode empty. F1 is already spliced-clean above.
UNSYNCED="$WORK/target-unsynced.json"
printf '%s\n' '{"permissions":{"defaultMode":"auto"},"hooks":{"PreToolUse":[]}}' > "$UNSYNCED"
out="$(DOMUS_ROOT="$F1" LIMEN_HOOK_WIRING_TARGET="$UNSYNCED" python3 "$HEAL" 2>&1)"; got=$?
[ "$got" = 1 ] && ok "clean source + unsynced target -> exit 1" \
               || bad "clean source + unsynced target -> exit 1 (got $got)"
printf '%s' "$out" | grep -q 'DEPLOYED target is out of sync' \
  && ok "names the deployed target as the gap" || bad "names the deployed target as the gap"
printf '%s' "$out" | grep -q 'clean (deployed target matches' \
  && bad "must not claim clean" || ok "does not claim clean"

# The converse: a target that already carries all three IS clean, exit 0.
out="$(DOMUS_ROOT="$F1" LIMEN_HOOK_WIRING_TARGET="$SYNCED" python3 "$HEAL" 2>&1)"; got=$?
[ "$got" = 0 ] && ok "clean source + synced target -> exit 0" \
               || bad "clean source + synced target -> exit 0 (got $got)"
printf '%s' "$out" | grep -q 'clean (deployed target matches' \
  && ok "reports clean only when the target matches" || bad "reports clean only when the target matches"

echo "── app-atom guard: --allow-drop is a real flag, and the refusal names the key ──"
# The guard only runs on the real deploy path (fixtures skip render+deploy), so assert the
# contract statically: the flag exists, the refusal is wired, and it is opt-in not default.
HW="$ROOT/scripts/heal-hook-wiring.py"
grep -q '"--allow-drop" not in sys.argv' "$HW" && ok "guard is opt-out via --allow-drop" \
                                              || bad "guard is opt-out via --allow-drop"
grep -q 'REFUSING TO DEPLOY' "$HW"            && ok "refusal path present" \
                                              || bad "refusal path present"
grep -q '"apply", "--force"' "$HW"            && ok "apply forces (no TTY prompt)" \
                                              || bad "apply forces (no TTY prompt)"
# The force must come AFTER the guard, never before it.
gline=$(grep -n 'REFUSING TO DEPLOY' "$HW" | head -1 | cut -d: -f1)
aline=$(grep -n '"apply", "--force"' "$HW" | head -1 | cut -d: -f1)
[ "$gline" -lt "$aline" ] && ok "guard precedes the forced apply" \
                          || bad "guard precedes the forced apply ($gline vs $aline)"

echo "── argv is refused, never ignored (a silently-dropped flag misreports which run happened) ──"
# Every case here is env-pinned to a fixture: argv is adjudicated before any source or target
# is touched, so a usage error must never depend on the host being wired.
expect_exit "--help exits 0"                    0 "$F1" --help
expect_exit "-h exits 0"                        0 "$F1" -h
expect_exit "--help wins over a missing source" 0 "$WORK/nope" --help
expect_exit "typo'd --apply is refused"         2 "$F1" --aply
expect_exit "typo'd --allow-drop is refused"    2 "$F1" --apply --allow-drops
expect_exit "bare positional is refused"        2 "$F1" settings.json
expect_exit "--allow-drop is a known flag"      0 "$F1" --apply --allow-drop

out="$(DOMUS_ROOT="$F1" python3 "$HEAL" --help 2>&1)"
printf '%s' "$out" | grep -q 'USAGE' && ok "--help prints the usage block" \
                                     || bad "--help prints the usage block"
printf '%s' "$out" | grep -q 'chezmoi' && ok "--help prints the docstring, not a stub" \
                                       || bad "--help prints the docstring, not a stub"

out="$(DOMUS_ROOT="$F1" python3 "$HEAL" --aply 2>&1)"
printf '%s' "$out" | grep -q 'unknown argument' && ok "refusal names the offending token" \
                                                || bad "refusal names the offending token"
printf '%s' "$out" | grep -q -- '--allow-drop'  && ok "refusal lists the known flags" \
                                                || bad "refusal lists the known flags"
# A refused argv must not have reached the deploy path.
printf '%s' "$out" | grep -q 'cartridge source already carries' \
  && bad "refusal short-circuits before touching the source" \
  || ok "refusal short-circuits before touching the source"

printf '\nheal-hook-wiring.test: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
