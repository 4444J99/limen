#!/usr/bin/env bash
# publish-flip.test.sh — safety regression for the private→public flip pipeline.
#
# The pipeline is publish-sweep.py (history-aware pre-publication gate) + apply-visibility.py
# (class-G effector). The assertions that must never regress:
#   1. a secret that exists ONLY IN HISTORY (deleted at HEAD) reds the sweep — a flip publishes history;
#   2. a clean repo greens the sweep, and the receipt drives receipt_fresh_green;
#   3. apply-visibility HOLDS a publish at every missing gate: no released lever → held; lever but no
#      receipt → held; lever+receipt but dark (no LIMEN_VISIBILITY_APPLY) → held. Offline throughout.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$here/../.." && pwd)"
export LIMEN_OFFLINE=1
SWEEP="$ROOT/scripts/publish-sweep.py"
APPLY="$ROOT/scripts/apply-visibility.py"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
pass=0; fail=0
ok()   { pass=$((pass+1)); }
bad()  { echo "  MISMATCH ($1)"; shift; for l in "$@"; do echo "    $l"; done; fail=$((fail+1)); }

mkrepo() { # $1=dir  $2=dirty|clean
  git init -q "$1" && cd "$1"
  git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
  if [ "$2" = dirty ]; then
    echo 'api_key: "plantedfixturesecretvalue0001"' > config.txt   # planted FIXTURE, not a real cred
    git add config.txt && git -c user.email=t@t -c user.name=t commit -q -m "add config"
    git rm -q config.txt && git -c user.email=t@t -c user.name=t commit -q -m "remove config"
  fi
  echo "# hello" > README.md
  git add README.md && git -c user.email=t@t -c user.name=t commit -q -m docs
  cd - >/dev/null
}

mkrepo "$work/dirty" dirty
mkrepo "$work/clean" clean

# ── 1. history-only secret reds the sweep ──
out="$(python3 "$SWEEP" --repo test/dirty --clone-from "$work/dirty" 2>&1)"; rc=$?
if [ "$rc" = 1 ] && echo "$out" | grep -q "RED" && echo "$out" | grep -q "history secret hits 1"; then
  ok
else
  bad "history-only secret must red the sweep (rc=$rc)" "$out"
fi

# ── 2. clean repo greens the sweep ──
out="$(python3 "$SWEEP" --repo test/clean --clone-from "$work/clean" 2>&1)"; rc=$?
if [ "$rc" = 0 ] && echo "$out" | grep -q "GREEN"; then
  ok
else
  bad "clean repo must green the sweep (rc=$rc)" "$out"
fi

# ── 3. apply-visibility holds a publish at every missing gate ──
# fixture estate: class demands public; fixture facts: repo observed private.
FIX="$work/estate.yaml"
cat > "$FIX" <<'YAML'
schema_version: 0.1
resource_types:
  repo:
    identity: derived
    desired: ["visibility"]
    observe: "gh api /repos/{owner}/{repo}"
    effector: [{kind: manual}]
    status: active
    owner: gitvs
    note: "fixture"
classes:
  wave:
    match: ["test/**"]
    visibility: public
    branch_protection: exempt
    required_checks: []
    owner: gitvs
    note: "fixture"
YAML
FACTS="$work/facts.json"
cat > "$FACTS" <<'JSON'
{"repos": [{"full_name": "test/clean", "private": true}]}
JSON

run_apply() { LIMEN_GITVS_ESTATE="$FIX" python3 "$APPLY" --apply --facts "$FACTS" --levers "$1" 2>&1; }

# 3a. no released lever → held
echo '{"levers": []}' > "$work/levers-none.json"
out="$(run_apply "$work/levers-none.json")"
echo "$out" | grep -q "held  publish test/clean — no released" && ok || bad "no-lever must hold" "$out"

# 3b. released lever but no receipt → held
cat > "$work/levers-rel.json" <<'JSON'
{"levers": [{"id": "L-PORTAL-PUBLISH-WAVE-1", "status": "released", "unlocks": ["test/clean"]}]}
JSON
rm -f "$ROOT/logs/publish-sweeps/test__clean.json"
out="$(run_apply "$work/levers-rel.json")"
echo "$out" | grep -q "held  publish test/clean — sweep receipt: no receipt" && ok || bad "no-receipt must hold" "$out"

# 3c. lever + green receipt but DARK (no LIMEN_VISIBILITY_APPLY) → held
python3 "$SWEEP" --repo test/clean --clone-from "$work/clean" >/dev/null 2>&1
out="$(run_apply "$work/levers-rel.json")"
echo "$out" | grep -q "held  publish test/clean — dark" && ok || bad "dark gate must hold" "$out"
rm -f "$ROOT/logs/publish-sweeps/test__clean.json" "$ROOT/logs/publish-sweeps/test__dirty.json"

echo
if [ "$fail" -eq 0 ]; then
  echo "publish-flip.test.sh: PASS ($pass checks)"
else
  echo "publish-flip.test.sh: FAIL ($fail mismatches, $pass ok)"; exit 1
fi
