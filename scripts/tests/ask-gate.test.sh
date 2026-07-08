#!/usr/bin/env bash
# ask-gate.test.sh — regression test for scripts/ask-gate.py
#
# The predicate must encode the retro's drift predictors STRUCTURALLY: a task with
# an executable done-check, bounded scope, and a named owner passes; a predicate-less
# or multi-goal ask is a SPLIT (exit 1 with --check); narrative-success vocabulary
# and ungated armed-behavior deliverables surface as ADVISE findings without
# hard-tripping. Deterministic: --task-file fixtures only — no board, no network.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
gate="$here/../ask-gate.py"
[ -f "$gate" ] || { echo "FAIL: cannot find ask-gate.py at $gate" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

run() { python3 "$gate" --check --task-file "$1"; }

echo "case 1: predicate-shaped, bounded, owned ask → PASS, exit 0"
cat > "$work/good.json" <<'JSON'
{"id": "T-GOOD", "title": "Build the legal validator",
 "description": "One validator. Predicate: python3 organs/legal/validate-legal.py --fleet; exit 0 means done.",
 "repo": "organvm/limen", "target_agent": "any"}
JSON
out="$(run "$work/good.json")" || { echo "FAIL: good ask tripped the gate: $out" >&2; exit 1; }
grep -q '"verdict": "PASS"' <<<"$out" || { echo "FAIL: expected PASS, got: $out" >&2; exit 1; }

echo "case 2: no done-predicate → SPLIT, exit 1, children skeleton offered"
cat > "$work/nopred.json" <<'JSON'
{"id": "T-NOPRED", "title": "Improve the dashboard",
 "description": "Make the dashboard better and more useful for daily work.",
 "repo": "organvm/limen", "target_agent": "any"}
JSON
if out="$(run "$work/nopred.json" 2>&1)"; then
  echo "FAIL: predicate-less ask passed the gate: $out" >&2; exit 1
fi
grep -q '"verdict": "SPLIT"' <<<"$out" || { echo "FAIL: expected SPLIT, got: $out" >&2; exit 1; }
grep -q '"T-NOPRED-C1"' <<<"$out" || { echo "FAIL: expected child skeleton, got: $out" >&2; exit 1; }

echo "case 3: multi-goal bundle → SPLIT even with a predicate"
cat > "$work/bundle.json" <<'JSON'
{"id": "T-BUNDLE", "title": "Do the whole slate",
 "description": "(1) build the page (2) wire the api (3) fix the tests (4) write the docs (5) deploy it. Predicate: verify-whole.sh green.",
 "repo": "organvm/limen", "target_agent": "any"}
JSON
if run "$work/bundle.json" >/dev/null 2>&1; then
  echo "FAIL: multi-goal bundle passed the gate" >&2; exit 1
fi

echo "case 4: narrative success + ungated armed behavior → ADVISE (soft), exit 0"
cat > "$work/advise.json" <<'JSON'
{"id": "T-ADVISE", "title": "Ship the mint page",
 "description": "Deploy the landing so it is world-class. Predicate: scripts/tests/landing.test.sh exits 0.",
 "repo": "organvm/limen", "target_agent": "any"}
JSON
out="$(run "$work/advise.json")" || { echo "FAIL: ADVISE verdict must not hard-trip --check" >&2; exit 1; }
grep -q '"verdict": "ADVISE"' <<<"$out" || { echo "FAIL: expected ADVISE, got: $out" >&2; exit 1; }
grep -q "narrative success" <<<"$out" || { echo "FAIL: expected narrative finding, got: $out" >&2; exit 1; }
grep -q "no artifact gate" <<<"$out" || { echo "FAIL: expected armed-behavior finding, got: $out" >&2; exit 1; }

echo "case 5: armed behavior WITH an artifact gate cited → that finding clears"
cat > "$work/gated.json" <<'JSON'
{"id": "T-GATED", "title": "Deploy the mint landing",
 "description": "Deploy it; done = ship-gate green on the landing URL returning 200. Predicate: python3 scripts/ship-gate.py --check.",
 "repo": "organvm/limen", "target_agent": "any"}
JSON
out="$(run "$work/gated.json")" || { echo "FAIL: gated deploy tripped the gate: $out" >&2; exit 1; }
grep -q "no artifact gate" <<<"$out" && { echo "FAIL: artifact-gated deploy still flagged: $out" >&2; exit 1; }

echo "case 6: missing owner surfaces as OWNED finding"
cat > "$work/unowned.json" <<'JSON'
{"id": "T-UNOWNED", "title": "Fix the thing",
 "description": "Predicate: pytest -q green.", "repo": "", "target_agent": ""}
JSON
out="$(run "$work/unowned.json")" || true
grep -q "OWNED" <<<"$out" || { echo "FAIL: expected OWNED findings, got: $out" >&2; exit 1; }

echo "ask-gate.test: all cases pass"
