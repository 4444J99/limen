#!/usr/bin/env bash
set -euo pipefail

# Selection-equivalence regression for scripts/verify.py --explain.
#
# Each case is one path list and the exact gate selection (registry order) it must
# implicate. The fixtures were transcribed from the 11 hardcoded rules the pre-registry
# scripts/verify-scoped.sh carried, so this test IS the proof that the resolver selects
# what the old script ran — and it stays as the permanent guard on selection semantics.
#
# Known deliberate deltas vs the old script (improvements, not parity breaks):
#   - CLAUDE.md, .github/workflows/**, and gates.yaml itself now also implicate the
#     check-gates drift predicate (the gate did not exist before the registry).
#   - gates.yaml implicates merge-policy-test (deploy_triggers feed the verdict matrix),
#     and merge-policy.sh implicates check-gates (ratchet F reads it for literal regexes).
#   - The scoped pr-gate rewrite (issue #1048) registered the three steps pr-gate had
#     hand-wired outside the registry — nomenclator, tasks-parse, ruff-format — plus
#     verify-ci-hardening-test (the resolver's own CI fail-closed contract).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERIFY="$ROOT/scripts/verify.py"
fails=0

expect() {
  local label="$1" expected="$2"; shift 2
  local actual
  actual="$(python3 "$VERIFY" --explain "$@")"
  if [[ "$actual" != "$expected" ]]; then
    printf 'FAIL %s\n  paths:    %s\n  expected: %s\n  actual:   %s\n' \
      "$label" "$*" "$(tr '\n' ' ' <<<"$expected")" "$(tr '\n' ' ' <<<"$actual")"
    fails=$((fails + 1))
  else
    printf 'ok %s\n' "$label"
  fi
}

expect docs-only 'syntax-changed
diff-hygiene' docs/some-note.md

expect cli-change 'syntax-changed
diff-hygiene
tasks-parse
check-params
ruff-lint
ruff-format
pytest-cli
pytest-api' cli/src/limen/io.py

expect api-change 'syntax-changed
diff-hygiene
check-params
ruff-lint
ruff-format
pytest-api' web/api/main.py

expect mcp-change 'syntax-changed
diff-hygiene
ruff-lint
ruff-format' mcp/src/limen_mcp/server.py

expect merge-policy-change 'syntax-changed
diff-hygiene
merge-policy-test
await-pr-test
check-params
check-gates' scripts/merge-policy.sh

expect enactment-change 'syntax-changed
diff-hygiene
enactment-test
check-params' scripts/enactment-audit.py

expect board-change 'syntax-changed
diff-hygiene
task-board
tasks-parse' tasks.yaml

expect organs-change 'syntax-changed
diff-hygiene
nomenclator' organs/consulting/FUNNEL-ENGINE.md

expect naming-roll-change 'syntax-changed
diff-hygiene
nomenclator
web-build' spec/index-nominum/roll.yaml

expect charter-change 'syntax-changed
diff-hygiene
agent-docs
check-gates' CLAUDE.md

expect workflow-change 'syntax-changed
diff-hygiene
workflow-yaml
check-gates' .github/workflows/ci.yml

expect dashboard-change 'syntax-changed
diff-hygiene
check-params
web-build' web/app/app/page.tsx

expect worker-change 'syntax-changed
diff-hygiene
check-params
worker-check' web/worker/src/index.ts

expect moneta-change 'syntax-changed
diff-hygiene
moneta-tests' moneta/src/mint.ts

expect spec-change 'syntax-changed
diff-hygiene
nomenclator
web-build' spec/contracts/readiness.schema.json

expect params-change 'syntax-changed
diff-hygiene
check-params' institutio/governance/parameters.yaml

expect registry-change 'syntax-changed
diff-hygiene
merge-policy-test
verify-resolver-test
check-gates' institutio/governance/gates.yaml

expect resolver-change 'syntax-changed
diff-hygiene
verify-resolver-test
verify-ci-hardening-test
check-params
check-gates' scripts/verify.py

expect mixed-change 'syntax-changed
diff-hygiene
tasks-parse
check-params
ruff-lint
ruff-format
pytest-cli
pytest-api
moneta-tests' cli/src/limen/io.py moneta/src/mint.ts

if ((fails)); then
  printf '\nverify-resolver: %d case(s) FAILED\n' "$fails"
  exit 1
fi
printf '\nverify-resolver: all selection fixtures pass\n'
