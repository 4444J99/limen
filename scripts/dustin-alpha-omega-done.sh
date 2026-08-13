#!/usr/bin/env bash
# dustin-alpha-omega-done — exit 0 ⟺ the dustin alpha→omega roadmap task is closed.
#
# Read-only. Verifies, per venture repo (post-dsp-platform, the-consulate,
# new-ancients-social): clone sync with origin/main, roadmap artifacts present
# AT HEAD (git cat-file — a written-but-unpushed file reads as absent), the
# repo's own validator green, tests green, tag v0.1.0 on the remote, milestone
# SET equality (never counts), and issue↔manifest parity via the repo's own
# reconcile tool against a fresh capture. Limen side: register dossier fields
# filled, derived artifacts at parity, the constellation validator's output
# byte-identical to the PINNED pre-existing red (any other output is a fresh
# regression), the plan chain closed, and the five dustin levers present.
#
# Predicate exit codes are read bare, never through a pipe (CLAUDE.md).
# Binds plan decisions #1 (JSON ledgers validated by each repo's checker) and
# #9 (pinned red embedded below) of docs/plans/2026-08-13-dustin-alpha-omega-roadmaps.md.
set -u

LIMEN_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
note() { printf '%-4s %s\n' "$1" "$2"; if [ "$1" = FAIL ]; then FAIL=1; fi; }

TMPDIR_DONE="$(mktemp -d /tmp/dustin-done.XXXXXX)"
trap 'rm -rf "$TMPDIR_DONE"' EXIT

check_repo() {
  # $1 = repo short name
  local r="$1"
  local d="/Users/4jp/Workspace/$r"

  if [ ! -d "$d/.git" ]; then
    note FAIL "$r: no clone at $d (GitHub is the copy of record — reclone)"
    return
  fi

  local local_sha remote_sha
  local_sha="$(git -C "$d" rev-parse HEAD 2>/dev/null)"
  remote_sha="$(gh api "repos/4444J99/$r/commits/main" --jq .sha 2>/dev/null)"
  if [ -n "$remote_sha" ] && [ "$local_sha" = "$remote_sha" ]; then
    note OK "$r: clone in sync with origin/main ($local_sha)"
  else
    note FAIL "$r: local $local_sha != remote ${remote_sha:-<unreachable>}"
  fi

  local f
  for f in ROADMAP.md roadmap/ladder.json roadmap/atoms.json roadmap/sources.json \
           roadmap/findings.json roadmap/issues/manifest.json roadmap/DESIGN.md \
           roadmap/redaction-denylist.json docs/research/dossier-extract.md; do
    if git -C "$d" cat-file -e "HEAD:$f" 2>/dev/null; then
      note OK "$r: $f at HEAD"
    else
      note FAIL "$r: $f missing at HEAD"
    fi
  done

  ( cd "$d" && node bin/check-roadmap.js >/dev/null 2>&1 )
  if [ $? -eq 0 ]; then note OK "$r: check-roadmap green"; else note FAIL "$r: check-roadmap red"; fi

  ( cd "$d" && npm test >/dev/null 2>&1 )
  if [ $? -eq 0 ]; then note OK "$r: tests green"; else note FAIL "$r: tests red"; fi

  gh api "repos/4444J99/$r/git/ref/tags/v0.1.0" >/dev/null 2>&1
  if [ $? -eq 0 ]; then note OK "$r: tag v0.1.0 on remote"; else note FAIL "$r: tag v0.1.0 missing on remote"; fi

  # Milestone SET equality: manifest titles vs GitHub titles.
  local want have
  want="$(node -e "
    const m = JSON.parse(require('fs').readFileSync('$d/roadmap/issues/manifest.json','utf8'));
    console.log(m.milestones.map(x => x.title).sort().join('\n'));
  " 2>/dev/null)"
  have="$(gh api --paginate "repos/4444J99/$r/milestones?state=all&per_page=100" --jq '.[].title' 2>/dev/null | sort)"
  if [ -n "$want" ] && [ "$want" = "$have" ]; then
    note OK "$r: milestone set matches manifest"
  else
    note FAIL "$r: milestone set differs from manifest"
  fi

  # Issue parity by marker, via the repo's own reconcile tool on a fresh capture.
  local cap="$TMPDIR_DONE/$r-capture.json"
  gh issue list -R "4444J99/$r" --state all --limit 500 \
    --json number,title,state,body,labels,milestone,url > "$cap" 2>/dev/null
  ( cd "$d" && node bin/reconcile-issues.js --capture "$cap" >/dev/null 2>&1 )
  if [ $? -eq 0 ]; then note OK "$r: issue reconcile PARITY"; else note FAIL "$r: issue reconcile has defects"; fi
}

check_repo post-dsp-platform
check_repo the-consulate
check_repo new-ancients-social

# ── limen side ────────────────────────────────────────────────────────────────

python3 - "$LIMEN_ROOT/organs/consulting/constellation/registry.yaml" <<'PY'
import sys
import yaml

doc = yaml.safe_load(open(sys.argv[1]))
person = next(p for p in doc["people"] if p["slug"] == "dustin")
bad = [pr["name"] for pr in person["projects"] if not (pr.get("dossier") or "").strip()]
sys.exit(1 if bad else 0)
PY
if [ $? -eq 0 ]; then note OK "limen: all dustin dossier fields filled"; else note FAIL "limen: dustin dossier field(s) empty"; fi

for p in dustin-dsp-platform dustin-ai-consultation dustin-social-presence; do
  if [ -f "$LIMEN_ROOT/organs/consulting/constellation/dossiers/$p.md" ]; then
    note OK "limen: pointer $p.md exists"
  else
    note FAIL "limen: pointer $p.md missing"
  fi
done

python3 "$LIMEN_ROOT/organs/consulting/constellation/derive-streams.py" --check >/dev/null 2>&1
if [ $? -eq 0 ]; then note OK "limen: derived streams at parity"; else note FAIL "limen: derived streams drift"; fi

# Constellation validator: output must be byte-identical to the PINNED
# pre-existing red (Rule #6 overlay-parity gap, 12 public-only slugs).
PINNED="$TMPDIR_DONE/pinned-red.txt"
cat > "$PINNED" <<'EOF'
FAIL  organs/consulting/constellation/registry.yaml
      violation: Rule #6 violation: slug sets differ — public-only ['aaron', 'ari', 'chris', 'david', 'derek', 'jessica', 'john-f', 'john-m', 'mike-s', 'rob', 'scott', 'shari'], overlay-only []
EOF
ACTUAL="$TMPDIR_DONE/actual-red.txt"
( cd "$LIMEN_ROOT" && python3 organs/consulting/constellation/validate-constellation.py > "$ACTUAL" 2>&1 )
VRC=$?
if [ $VRC -eq 0 ]; then
  note OK "limen: constellation validator fully green (pre-existing red healed)"
elif diff -q "$PINNED" "$ACTUAL" >/dev/null 2>&1; then
  note OK "limen: constellation red is byte-identical to the pinned pre-existing baseline"
else
  note FAIL "limen: constellation validator output differs from the pinned baseline — FRESH regression"
fi

python3 "$LIMEN_ROOT/scripts/session-plan.py" audit > "$TMPDIR_DONE/plan-audit.txt" 2>&1
if grep -E "GAP.*dustin-alpha-omega-roadmaps" "$TMPDIR_DONE/plan-audit.txt" >/dev/null 2>&1; then
  note FAIL "limen: plan chain GAP for dustin-alpha-omega-roadmaps"
else
  note OK "limen: plan chain has no GAP for dustin-alpha-omega-roadmaps"
fi

for lever in L-DUSTIN-GH-PROFILE L-DSP-TEN-QUESTIONS L-CONS-PRICE L-NAS-TERMS L-NAS-CREDENTIALS; do
  if grep -q "\"$lever\"" "$LIMEN_ROOT/his-hand-levers.json" 2>/dev/null; then
    note OK "limen: lever $lever registered"
  else
    note FAIL "limen: lever $lever missing from his-hand-levers.json"
  fi
done

if [ "$FAIL" -eq 0 ]; then
  echo "DUSTIN ALPHA→OMEGA: DONE — all predicates green"
else
  echo "DUSTIN ALPHA→OMEGA: NOT DONE — failures above"
fi
exit "$FAIL"
