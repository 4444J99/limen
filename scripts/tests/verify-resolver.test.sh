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
#   - Executable Git/GitHub writer surfaces now implicate direct-main-writer-contract;
#     the release parameter implicates the sync-release default-branch regression.
#   - check-note-links appears in EVERY case. It carries `paths: ["**"]` deliberately: a
#     `[[wikilink]]` citation can be introduced in any file, so path-scoping it would put the
#     blind spot exactly where the defect lives (see IF-NOTE-HOMED). At 0.12s that is
#     affordable. This fixture set is what made the change visible — all 20 cases shifted at
#     once, and each was verified to be an INSERT ONLY (nothing dropped, nothing else added)
#     before the expectations were updated. A universal gate is the one kind of gate that can
#     quietly rewrite every selection, so it should be the one kind that is hardest to add.

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
diff-hygiene
check-docs-manifest
check-docs-exports
check-note-links' docs/some-note.md

# io.py is a DIRECT child of cli/src/limen — load-bearing for check-effectors, whose glob dialect
# makes `cli/src/limen/**/*.py` match only NESTED files. Scoping its paths to .py without also
# listing `cli/src/limen/*.py` silently drops this case, and dispatch.py (a live `gh pr merge`
# site) sits in exactly that directory. organs-change below is the matching negative: a .md must
# NOT pull in an AST scan.
expect cli-change 'syntax-changed
diff-hygiene
direct-main-writer-contract
tasks-parse
check-params
check-note-links
check-effectors
ruff-lint
ruff-format
pytest-cli
pytest-api' cli/src/limen/io.py

expect api-change 'syntax-changed
diff-hygiene
direct-main-writer-contract
check-params
check-note-links
ruff-lint
ruff-format
pytest-api' web/api/main.py

expect mcp-change 'syntax-changed
diff-hygiene
direct-main-writer-contract
agent-docs
check-note-links
check-effectors
ruff-lint
ruff-format' mcp/src/limen_mcp/server.py

expect merge-policy-change 'syntax-changed
diff-hygiene
merge-policy-test
merge-queue-contract-test
direct-main-writer-contract
await-pr-test
check-params
check-gates
check-note-links' scripts/merge-policy.sh

expect enactment-change 'syntax-changed
diff-hygiene
direct-main-writer-contract
enactment-test
check-params
check-note-links
check-effectors' scripts/enactment-audit.py

expect board-change 'syntax-changed
diff-hygiene
task-board
tasks-parse
check-root-manifest
check-note-links
check-board-partition' tasks.yaml

expect organs-change 'syntax-changed
diff-hygiene
nomenclator
check-note-links' organs/consulting/FUNNEL-ENGINE.md

expect naming-roll-change 'syntax-changed
diff-hygiene
nomenclator
check-note-links
web-build' spec/index-nominum/roll.yaml

expect charter-change 'syntax-changed
diff-hygiene
agent-docs
check-gates
check-root-manifest
check-note-links' CLAUDE.md

# check-runner-coverage is implicated because a workflow is a REACHABILITY ROOT: adding a
# `run: bash scripts/metabolize.sh` step is exactly what would make an orphaned runner reachable,
# so the verdict genuinely changes when a workflow does.
expect workflow-change 'syntax-changed
diff-hygiene
direct-main-writer-contract
workflow-yaml
check-gates
check-runner-coverage
check-note-links' .github/workflows/ci.yml

expect dashboard-change 'syntax-changed
diff-hygiene
check-params
check-note-links
web-build' web/app/app/page.tsx

expect worker-change 'syntax-changed
diff-hygiene
direct-main-writer-contract
check-params
check-note-links
worker-check' web/worker/src/index.ts

expect moneta-change 'syntax-changed
diff-hygiene
check-note-links
moneta-tests' moneta/src/mint.ts

expect spec-change 'syntax-changed
diff-hygiene
nomenclator
check-note-links
web-build' spec/contracts/readiness.schema.json

# paused-beat-test is implicated because its fixtures assert that each paused-branch escape hatch
# (LIMEN_PAUSED_SENSING, LIMEN_PAUSED_SYNC) is DECLARED in the panel — deleting a declaration there
# is exactly the drift those checks exist to catch, so a params change must run them.
expect params-change 'syntax-changed
diff-hygiene
sync-release-test
check-params
paused-beat-test
check-note-links' institutio/governance/parameters.yaml

# agent-docs joined this set 2026-08-06: check S reads gates.yaml's instruction_surfaces
# block, so a registry change must re-run the byte-budget ratchet.
expect registry-change 'syntax-changed
diff-hygiene
merge-policy-test
verify-resolver-test
verify-parallel-test
agent-docs
check-gates
check-note-links' institutio/governance/gates.yaml

expect resolver-change 'syntax-changed
diff-hygiene
merge-queue-contract-test
direct-main-writer-contract
verify-resolver-test
verify-parallel-test
verify-ci-hardening-test
check-params
check-gates
check-note-links
check-effectors' scripts/verify.py

expect parallel-verifier-change 'syntax-changed
diff-hygiene
direct-main-writer-contract
verify-parallel-test
check-params
check-note-links' scripts/tests/verify-parallel.test.sh

expect mixed-change 'syntax-changed
diff-hygiene
direct-main-writer-contract
tasks-parse
check-params
check-note-links
check-effectors
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
