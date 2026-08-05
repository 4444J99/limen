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

# ── DERIVE: an ask already owned by a registry is derived, not surfaced ──────────
# (PREC-2026-07-08-ask-already-decided). Deterministic via a FIXTURE registry: point LIMEN_ROOT at
# $work so _already_decided reads our fixture his-hand-levers.json, not the live one.
mkdir -p "$work/censor"
cat > "$work/his-hand-levers.json" <<'JSON'
{"levers": [{"id": "L-FIXTURE-DECIDED", "label": "an already-owned decision"}]}
JSON
echo '{"id":"PREC-2099-01-01-fixture","subject":"x"}' > "$work/censor/precedents.jsonl"
echo '[]' > "$work/organ-ladder.json"
run_root() { LIMEN_ROOT="$work" python3 "$gate" --check --task-file "$1"; }

echo "case 7: ask referencing an owned lever (decision-shaped) → DERIVE, exit 0 (no surface)"
cat > "$work/decided.json" <<'JSON'
{"id": "T-DECIDED", "title": "should we flip L-FIXTURE-DECIDED or wait",
 "description": "decide the cutover"}
JSON
out="$(run_root "$work/decided.json")" || { echo "FAIL: DERIVE must not hard-trip --check: $out" >&2; exit 1; }
grep -q '"verdict": "DERIVE"' <<<"$out" || { echo "FAIL: expected DERIVE, got: $out" >&2; exit 1; }
grep -q "L-FIXTURE-DECIDED" <<<"$out" || { echo "FAIL: expected the owning lever cited, got: $out" >&2; exit 1; }

echo "case 8: a lever-LOOKALIKE not in the registry must NOT DERIVE (membership-checked)"
cat > "$work/lookalike.json" <<'JSON'
{"id": "T-LOOKALIKE", "title": "handle the L-NOT-REAL bracket, which one",
 "description": "no predicate here"}
JSON
out="$(run_root "$work/lookalike.json" 2>&1)" || true
grep -q '"verdict": "DERIVE"' <<<"$out" && { echo "FAIL: false-fired DERIVE on a non-registry token: $out" >&2; exit 1; }

echo "case 9: ordinary AND clauses are one bounded repair, not a false bundle"
cat > "$work/ordinary-and.json" <<'JSON'
{"id": "HEAL-rebase-stale-organvm-limen-434",
 "title": "Rebase the stale repair branch",
 "description": "Rebase the branch AND keep its unique change AND restore current base content AND verify the PR AND preserve its owner receipt AND report the exact head receipt. Predicate: gh pr view 434 --repo organvm/limen --json state.",
 "repo": "organvm/limen", "target_agent": "codex"}
JSON
out="$(run "$work/ordinary-and.json")" || { echo "FAIL: ordinary AND prose tripped boundedness: $out" >&2; exit 1; }
grep -q '"verdict": "PASS"' <<<"$out" || { echo "FAIL: expected PASS for ordinary AND prose, got: $out" >&2; exit 1; }

echo "ask-gate.test: all cases pass"
