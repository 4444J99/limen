#!/usr/bin/env bash
set -euo pipefail

# Scoped verification gate — run ONLY the gates implicated by what actually changed.
#
# verify-whole.sh is the whole-system predicate: full pytest, npm installs, a MONETA
# vitest+tsc run, a uvicorn probe, a wrangler-dev (workerd) probe, and a full Next.js
# production build. Paying that price for a docs append or a one-file script fix — from
# several parallel sessions at once — is what exhausts the host. This script maps the
# changed paths (vs. origin/main, plus any uncommitted/untracked work) to the gates they
# implicate and runs only those, reporting every gate it skipped and why. Pass --full to
# defer to verify-whole.sh unchanged.
#
# Exit 0 ⟺ every implicated gate passed. merge-policy.sh still owns the merge decision;
# website-sensitive PRs still require green CI (the full matrix) before merge.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/cli/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ "${1:-}" == "--full" ]]; then
  shift
  exec "$ROOT/scripts/verify-whole.sh" "$@"
fi

step() { printf '\n==> %s\n' "$*"; }
skip() { printf 'skipped: %s (no implicated change)\n' "$*"; }

# --- Collect the changed set: branch diff vs origin/main + staged + unstaged + untracked ---
base_ref=""
for candidate in origin/main main; do
  if git rev-parse --verify --quiet "$candidate" >/dev/null; then
    base_ref="$(git merge-base "$candidate" HEAD 2>/dev/null || true)"
    [[ -n "$base_ref" ]] && break
  fi
done

changed_file="$(mktemp)"
trap 'rm -f "$changed_file"' EXIT
{
  [[ -n "$base_ref" ]] && git diff --name-only "$base_ref" HEAD
  git diff --name-only
  git diff --name-only --cached
  git ls-files --others --exclude-standard
} | sort -u | while IFS= read -r path; do
  [[ -e "$path" || -n "$(git ls-files -- "$path")" ]] && printf '%s\n' "$path"
done > "$changed_file"

if [[ ! -s "$changed_file" ]]; then
  printf 'No changes vs %s and no local modifications — nothing to verify.\n' "${base_ref:-HEAD}"
  exit 0
fi

printf 'Changed paths (%s):\n' "$(grep -c '' "$changed_file")"
sed 's/^/  /' "$changed_file"

matches() { grep -qE "$1" "$changed_file"; }

# --- Gate: syntax on exactly the files touched (always cheap, always scoped) ---
step "Compile / syntax-check changed files"
while IFS= read -r path; do
  [[ -f "$path" ]] || continue
  case "$path" in
    *.py) python3 -m py_compile "$path" ;;
    *.sh) bash -n "$path" ;;
  esac
done < "$changed_file"

# --- Gate: Python lint + tests ---
if matches '^(cli/|web/api/|mcp/|ianva/)'; then
  step "Lint Python surfaces"
  python3 -m ruff check cli/src cli/tests web/api mcp ianva
  step "Run implicated pytest suites"
  suites=()
  matches '^cli/' && suites+=(cli/tests web/api/tests)   # web/api imports limen — a cli change implicates both
  matches '^web/api/' && suites+=(web/api/tests)
  if ((${#suites[@]})); then
    deduped="$(printf '%s\n' "${suites[@]}" | sort -u | tr '\n' ' ')"
    # shellcheck disable=SC2086
    env -u LIMEN_API_TOKEN -u LIMEN_OWNER_TOKEN -u LIMEN_CLIENT_TOKEN \
      python3 -m pytest $deduped -q
  else
    printf 'mcp/ianva change: lint + compile only (no gated test suite for these packages)\n'
  fi
else
  skip "ruff + pytest"
fi

# --- Gate: scripts/** changes with shipped regression tests ---
if matches '^scripts/(merge-policy\.sh|tests/merge-policy\.test\.sh)'; then
  step "Verify the merge-policy predicate"
  bash scripts/tests/merge-policy.test.sh
fi
if matches '^scripts/(enactment-audit\.py|tests/enactment-audit\.test\.sh)'; then
  step "Verify the enactment predicate"
  bash scripts/tests/enactment-audit.test.sh
fi

# --- Gate: no-hardcode ratchet (new LIMEN_* vars must be declared in the parameter panel) ---
if matches '^(institutio/governance/parameters\.yaml|scripts/check-params\.py|scripts/|cli/|web/)'; then
  step "No-hardcode gate (VIGILIA parameter panel ratchet)"
  python3 scripts/check-params.py
else
  skip "no-hardcode gate"
fi

# --- Gate: task board ---
if matches '^tasks\.yaml$'; then
  step "Validate task-board statuses"
  python3 scripts/validate-task-board.py
else
  skip "task-board validation"
fi

# --- Gate: agent-instruction docs ---
if matches '^(CLAUDE\.md|AGENTS\.md|GEMINI\.md|CONTRIBUTING\.md|docs/agent-instruction-standard\.md|scripts/check-agent-docs\.py)$'; then
  step "Verify agent-instruction docs"
  python3 scripts/check-agent-docs.py
else
  skip "agent-doc vocabulary check"
fi

# --- Gate: workflow YAML ---
if matches '^\.github/workflows/'; then
  step "Parse GitHub workflow YAML"
  python3 - <<'PY'
from pathlib import Path
import yaml
for path in sorted(Path(".github/workflows").glob("*.yml")) + sorted(Path(".github/workflows").glob("*.yaml")):
    with path.open() as handle:
        yaml.safe_load(handle)
    print(f"ok {path}")
PY
else
  skip "workflow YAML parse"
fi

# --- Heavy gates: only when their surface actually changed ---
if matches '^(web/app/|spec/)'; then
  step "Generate surfaces, validate contracts, build dashboard"
  ( cd web/app && npm run generate:data && npm run build )
  node scripts/validate-contract-schemas.mjs
else
  skip "surface generation + contract schemas + dashboard build"
fi

if matches '^web/worker/'; then
  step "Worker lint/check"
  ( cd web/worker && npm run check )
else
  skip "worker check"
fi

if matches '^moneta/'; then
  step "MONETA tests (vitest + tsc)"
  ( cd moneta && npm test )
else
  skip "MONETA tests"
fi

step "Check diff hygiene"
git diff --check

# --- Pre-merge reminder: scoped green is not deploy green ---
if matches '^(web/app/|web/api/|cli/|firebase\.json$|tasks\.yaml$|scripts/preflight-cloud-run\.sh$|\.github/workflows/deploy)'; then
  printf '\nNOTE: diff touches deploy-trigger paths — the PR is website-sensitive.\n'
  printf 'merge-policy.sh will require green CI (the full matrix) before merge; run\n'
  printf 'scripts/verify-whole.sh (or let CI run it) before merging. Scoped green is a\n'
  printf 'push gate, not a deploy gate.\n'
fi

printf '\nScoped verification passed\n'
