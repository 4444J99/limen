#!/usr/bin/env bash
# split-hygiene.test.sh — regression for the form-twin split predicate (check-split-hygiene.py).
#
# The assertions that must never regress:
#   1. a PROPER twin (fresh git init, allowlisted files, manifest) passes P1-P4 (P5 skipped: local);
#   2. a BRANCH-COPY twin (shares history with the private repo) reds P1 — fork-splits are the leak;
#   3. a twin with a file OUTSIDE the manifest paths reds P3.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$here/../.." && pwd)"
export LIMEN_OFFLINE=1
CHECK="$ROOT/scripts/check-split-hygiene.py"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
pass=0; fail=0
G() { git -c user.email=t@t -c user.name=t "$@"; }

# the private operation repo: real docs + a secret in history + strategy residue.
mkdir -p "$work/private" && cd "$work/private"
git init -q
mkdir -p docs
echo "## spec" > docs/spec.md
echo 'api_key: "plantedfixturesecretvalue0002"' > cfg.txt   # planted FIXTURE
G add -A && G commit -q -m ops
git rm -q cfg.txt && G commit -q -m scrub
cd - >/dev/null

# 1. proper twin: fresh init + allowlist copy + manifest.
mkdir -p "$work/twin" && cd "$work/twin"
git init -q
mkdir -p docs && cp "$work/private/docs/spec.md" docs/
echo "# product" > README.md
printf 'schema_version: 0.1\nsource_repo: test/private\nsource_commit: abc\nextracted: 2026-07-16\npaths:\n  - docs/\n  - README.md\n' > form-manifest.yaml
G add -A && G commit -q -m "form extraction"
cd - >/dev/null
out="$(python3 "$CHECK" --public "$work/twin" --private "$work/private" 2>&1)"; rc=$?
if [ "$rc" = 0 ] && echo "$out" | grep -q "P1–P5 hold"; then pass=$((pass+1)); else
  echo "  MISMATCH (proper twin must pass, rc=$rc)"; echo "$out" | sed 's/^/    /'; fail=$((fail+1)); fi

# 2. branch-copy twin: cloned from private — shared history must red P1.
git clone -q "$work/private" "$work/copytwin" 2>/dev/null
cd "$work/copytwin"
printf 'schema_version: 0.1\npaths:\n  - docs/\n' > form-manifest.yaml
G add -A && G commit -q -m manifest
cd - >/dev/null
out="$(python3 "$CHECK" --public "$work/copytwin" --private "$work/private" 2>&1)"; rc=$?
if [ "$rc" = 1 ] && echo "$out" | grep -q "P1 history-disjoint"; then pass=$((pass+1)); else
  echo "  MISMATCH (branch-copy must red P1, rc=$rc)"; echo "$out" | sed 's/^/    /'; fail=$((fail+1)); fi

# 3. stray file outside the manifest → P3 red.
cd "$work/twin"
echo "x" > stray.txt && G add stray.txt && G commit -q -m stray
cd - >/dev/null
out="$(python3 "$CHECK" --public "$work/twin" --private "$work/private" 2>&1)"; rc=$?
if [ "$rc" = 1 ] && echo "$out" | grep -q "P3 manifest-covered"; then pass=$((pass+1)); else
  echo "  MISMATCH (stray file must red P3, rc=$rc)"; echo "$out" | sed 's/^/    /'; fail=$((fail+1)); fi

echo
if [ "$fail" -eq 0 ]; then
  echo "split-hygiene.test.sh: PASS ($pass checks)"
else
  echo "split-hygiene.test.sh: FAIL ($fail mismatches, $pass ok)"; exit 1
fi
