#!/usr/bin/env bash
# verify-fable-gate.sh — the executable predicate for the Fable role-separation + runtime cap.
#
# Exit 0 ⟺ every piece of the Fable backstop is wired and enforcing:
#   1. The over-cap gate downgrades an accepted Fable selection to Opus (model_selection/dispatch).
#   2. fable-session-guard.py warns (exit 2) on Fable+over_cap and is a no-op on a non-Fable model.
#   3. vendor-cancel-advisor.py: codex=KEEP, an idle mock is CANCEL-CANDIDATE, Fable named the overspend.
#   4. The pytest gate for the tier/cap logic is green.
#   5. Re-running this script makes NO state changes (fixed point).
#
# Idempotent + self-contained: all fixtures live in a mktemp dir, torn down on exit. Read-only w.r.t.
# the repo. Prefers the repo's .venv python (editable limen install); falls back to PYTHONPATH.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Pick an interpreter that can import the worktree's `limen` package.
if [ -x "$ROOT/.venv/bin/python" ]; then
  PY=("$ROOT/.venv/bin/python")
elif [ -x "$HOME/Workspace/limen/.venv/bin/python" ]; then
  PY=("$HOME/Workspace/limen/.venv/bin/python")
else
  PY=(python3)
fi
export PYTHONPATH="$ROOT/cli/src${PYTHONPATH:+:$PYTHONPATH}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
fail() { echo "verify-fable-gate: FAIL — $1" >&2; exit 1; }
pass() { echo "  ok — $1"; }

MONDAY="$("${PY[@]}" - <<'PYEOF'
import datetime as dt
now = dt.datetime.now(dt.timezone.utc)
print((now - dt.timedelta(days=now.weekday())).date().isoformat())
PYEOF
)"

echo "── 1. over-cap gate downgrades an accepted Fable selection to Opus ──"
# Seed a mock OVER-CAP balance + a valid (non-reserve) acceptance receipt, then assert the shared
# resolver returns opus for a Fable tier, and reserve-band behavior (40–50%) passes only reserve.
cat > "$TMP/fable-allotment-over.json" <<JSON
{"week":"$MONDAY","spent_pct":100.0,"deliberate_cap":40,"hard_cap":50,"over_cap":true}
JSON
cat > "$TMP/fable-allotment-band.json" <<JSON
{"week":"$MONDAY","spent_pct":45.0,"deliberate_cap":40,"hard_cap":50,"over_cap":false}
JSON
cat > "$TMP/accept.json" <<JSON
{"schema":"limen.fable_acceptance.v1","week":"$MONDAY","category":"governance","percent":10}
JSON
cat > "$TMP/reserve.json" <<JSON
{"schema":"limen.fable_acceptance.v1","week":"$MONDAY","category":"reserve","percent":5}
JSON

LIMEN_FABLE_BALANCE_PATH="$TMP/fable-allotment-over.json" \
LIMEN_FABLE_ACCEPTANCE="$TMP/accept.json" \
"${PY[@]}" - <<'PYEOF' || fail "over-cap did not downgrade Fable to opus"
from limen import model_selection as M
assert M._resolve_claude_model("fable") == "opus", M._resolve_claude_model("fable")
PYEOF
pass "hard cap (≥50%) → opus even with a valid receipt"

LIMEN_FABLE_BALANCE_PATH="$TMP/fable-allotment-band.json" \
LIMEN_FABLE_ACCEPTANCE="$TMP/accept.json" \
"${PY[@]}" - <<'PYEOF' || fail "reserve band let a non-reserve receipt keep Fable"
from limen import model_selection as M
assert M._resolve_claude_model("fable") == "opus", "non-reserve receipt should downgrade in 40-50 band"
PYEOF
pass "40–50% band + non-reserve receipt → opus"

LIMEN_FABLE_BALANCE_PATH="$TMP/fable-allotment-band.json" \
LIMEN_FABLE_ACCEPTANCE="$TMP/reserve.json" \
"${PY[@]}" - <<'PYEOF' || fail "reserve band rejected a reserve receipt"
from limen import model_selection as M
assert M._resolve_claude_model("fable") == "fable", "reserve receipt should pass in 40-50 band"
PYEOF
pass "40–50% band + reserve receipt → fable"

echo "── 2. session guard warns on Fable over-cap, no-op on non-Fable ──"
echo '{"model":"claude-opus-4-8"}' | "${PY[@]}" scripts/fable-session-guard.py >/dev/null 2>&1 \
  || fail "session guard should exit 0 on a non-Fable model"
pass "non-Fable model → exit 0 (no-op)"
if echo '{"model":"claude-fable-5"}' | LIMEN_FABLE_BALANCE_PATH="$TMP/fable-allotment-over.json" \
    "${PY[@]}" scripts/fable-session-guard.py >/dev/null 2>&1; then
  fail "session guard should exit non-zero on Fable + over_cap"
fi
pass "Fable + over_cap → exit 2 (hard warn)"

echo "── 3. vendor-cancel-advisor: codex=KEEP, idle mock=CANCEL-CANDIDATE, Fable named ──"
cat > "$TMP/usage.json" <<'JSON'
{"vendors":{"codex":{"health":"rate-limited","recent_rate_limit":true,"headroom_pct":5},
"opencode":{"health":"ok","headroom_pct":99}}}
JSON
LIMEN_FABLE_BALANCE_PATH="$TMP/fable-allotment-over.json" \
  "${PY[@]}" scripts/vendor-cancel-advisor.py --usage "$TMP/usage.json" --json > "$TMP/advice.json" \
  || fail "advisor exited non-zero (a contradiction?)"
ADVICE="$TMP/advice.json" "${PY[@]}" - <<'PYEOF' || fail "advisor verdict wrong"
import json, os
r = json.load(open(os.environ["ADVICE"]))
assert r["codex_keep"] is True, "codex must be KEEP"
assert "opencode" in r["cancel_candidates"], r["cancel_candidates"]
assert r["fable_over_cap"] is True and "Fable" in r["real_overspend"], r["real_overspend"]
assert r["contradictions"] == [], r["contradictions"]
PYEOF
pass "codex=KEEP, opencode=CANCEL-CANDIDATE, Fable-at-cap named, no contradictions"

echo "── 4. pytest gate for the tier/cap logic ──"
# Scope to the Fable cap + advisor + session-guard suites (the units this predicate owns). A broader
# `-k dispatch` sweep pulls slow, environment-sensitive dispatch integration tests into a tight gate;
# the full suite is covered by verify-whole / CI, not here.
"${PY[@]}" -m pytest \
  cli/tests/test_claude_tier.py \
  cli/tests/test_fable_allotment.py \
  cli/tests/test_fable_session_guard.py \
  cli/tests/test_vendor_cancel_advisor.py \
  -q >/dev/null 2>&1 || fail "pytest tier/cap suite failed (run the four Fable test files for detail)"
pass "tier/cap pytest suite green"

echo "── 5. fixed point: balance write is idempotent ──"
BAL_ROOT="$TMP/balroot"; mkdir -p "$BAL_ROOT/logs"
EMPTY="$TMP/no-transcripts"; mkdir -p "$EMPTY"
LIMEN_ROOT="$BAL_ROOT" LIMEN_CLAUDE_TRANSCRIPTS_DIR="$EMPTY" \
  "${PY[@]}" scripts/fable-allotment.py balance >/dev/null || fail "balance run 1 failed"
H1="$(shasum "$BAL_ROOT/logs/fable-allotment.json" | awk '{print $1}')"
LIMEN_ROOT="$BAL_ROOT" LIMEN_CLAUDE_TRANSCRIPTS_DIR="$EMPTY" \
  "${PY[@]}" scripts/fable-allotment.py balance >/dev/null || fail "balance run 2 failed"
H2="$(shasum "$BAL_ROOT/logs/fable-allotment.json" | awk '{print $1}')"
[ "$H1" = "$H2" ] || fail "balance is not idempotent ($H1 != $H2)"
pass "balance re-run produces an identical file"

echo "verify-fable-gate: PASS"
