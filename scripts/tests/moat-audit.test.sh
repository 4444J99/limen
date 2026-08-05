#!/usr/bin/env bash
# moat-audit.test.sh — regression test for the moat + lure boundary predicate
# (scripts/moat-audit.py). The form/operation split must be ENFORCED by a
# runnable check, not just described in positioning-seeds.json prose.
#
# Hermetic: builds a throwaway git "public repo" whose tree contains (or omits)
# a declared leak-VALUE, points a fixture moat-guard.json's clone_root at it,
# and asserts the predicate reddens on a leak and passes when clean — and that
# the leak scan reads origin/main, not the working tree.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$here/../.." && pwd)"
AUDIT="$ROOT/scripts/moat-audit.py"
[ -f "$AUDIT" ] || { echo "FAIL: cannot find moat-audit.py at $AUDIT" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

pass=0; fail=0
check() {  # check <want_rc> <grep|-> <label>  (env: GUARD, plus optional flags in EXTRA)
  local want_rc="$1" pattern="$2" label="$3" out rc
  out="$(LIMEN_MOAT_GUARD="$GUARD" LIMEN_VALUE_REPOS="$VALREPOS" \
         LIMEN_POSITIONING_SEEDS="$SEEDS" LIMEN_POSITIONING_DIR="$work/positioning" \
         python3 "$AUDIT" --no-visibility ${EXTRA:-} 2>&1)"; rc=$?
  if [ "$rc" != "$want_rc" ]; then
    echo "  MISMATCH ($label): want exit $want_rc got $rc"; echo "$out" | sed 's/^/    /'; fail=$((fail+1)); return
  fi
  if [ "$pattern" != "-" ] && ! echo "$out" | grep -q "$pattern"; then
    echo "  MISMATCH ($label): output missing /$pattern/"; echo "$out" | sed 's/^/    /'; fail=$((fail+1)); return
  fi
  pass=$((pass+1))
}

# --- Build a fake public repo clone at $work/testowner/testrepo ------------
CLONE="$work/testowner/testrepo"
mkdir -p "$CLONE/src"
git -C "$CLONE" init -q
git -C "$CLONE" config user.email t@t.test
git -C "$CLONE" config user.name test
git -C "$CLONE" checkout -q -b main
# A DATA line that mimics a curated source-map id (the leak) + a harmless type.
cat > "$CLONE/src/channel.ts" <<'TS'
export interface SourceMap { id: string }
const SOURCE = { id: 'DATASET-abc123-secret-id' }
TS
git -C "$CLONE" add -A && git -C "$CLONE" commit -qm init
# Simulate a remote origin/main (the predicate audits origin/main, not worktree).
git -C "$CLONE" update-ref refs/remotes/origin/main HEAD

VALREPOS="$work/value-repos.json"
cat > "$VALREPOS" <<'JSON'
{ "repos": ["testowner/testrepo"] }
JSON

SEEDS="$work/seeds.json"
cat > "$SEEDS" <<'JSON'
{ "repos": { "testowner/testrepo": { "display_name": "x" } } }
JSON

mkdir -p "$work/positioning"

# --- Case 1: a leak IS present on origin/main -> exit 1 --------------------
GUARD="$work/guard-leak.json"
cat > "$GUARD" <<JSON
{
  "clone_root": "$work",
  "repos": {
    "testowner/testrepo": {
      "scan_paths": ["src"],
      "leak_patterns": [
        { "name": "fake-source-id", "regex": "DATASET-abc123-secret-id", "why": "test source-map id" }
      ]
    }
  }
}
JSON
EXTRA=""; check 1 "fake-source-id" "leak present on origin/main reddens the predicate"
EXTRA=""; check 1 "LEAK" "leak is labelled in the report"

# --- Case 2: the pattern does NOT match -> exit 0 -------------------------
GUARD="$work/guard-clean.json"
cat > "$GUARD" <<JSON
{
  "clone_root": "$work",
  "repos": {
    "testowner/testrepo": {
      "scan_paths": ["src"],
      "leak_patterns": [
        { "name": "absent-secret", "regex": "THIS-STRING-IS-NOT-IN-THE-TREE", "why": "should not match" }
      ]
    }
  }
}
JSON
EXTRA=""; check 0 "PASS" "no matching pattern passes clean"

# --- Case 3: origin/main is authoritative (worktree-only change is ignored) -
# guard-clean's pattern is absent from origin/main. Add it to the WORKING TREE
# only; the predicate must still PASS because it scans origin/main, not worktree.
echo "const LATER = 'THIS-STRING-IS-NOT-IN-THE-TREE'" >> "$CLONE/src/channel.ts"
GUARD="$work/guard-clean.json"
EXTRA=""; check 0 "PASS" "uncommitted worktree leak is ignored (audits origin/main)"
git -C "$CLONE" checkout -q -- src/channel.ts  # restore

# --- Case 4: --strict fails on a lure gap (public, seeded, no page) --------
# testrepo is seeded but has no positioning page -> gap; --strict must fail.
GUARD="$work/guard-clean.json"
EXTRA="--strict"; check 1 "lure gap" "--strict reddens on a magnet-ready-but-dark repo"

echo "moat-audit.test.sh: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
