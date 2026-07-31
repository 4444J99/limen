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

printf '\nheal-hook-wiring.test: %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1
