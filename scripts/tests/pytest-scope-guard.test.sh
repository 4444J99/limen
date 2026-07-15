#!/usr/bin/env bash
# Hermetic deny/pass matrix for scripts/hooks/pytest-scope-guard.sh — builds a fake limen
# checkout (marked by scripts/verify-scoped.sh, the walk-up sentinel) in mktemp so it never
# depends on the real checkout; CI-safe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HOOK="$ROOT/scripts/hooks/pytest-scope-guard.sh"

FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT

LIVE="$FIX/limen"                                  # fake limen checkout (sentinel present)
mkdir -p "$LIVE/scripts" "$LIVE/cli/tests/unit" "$LIVE/web/api/tests" "$LIVE/tests" "$LIVE/mcp/tests"
touch "$LIVE/scripts/verify-scoped.sh" "$LIVE/cli/tests/test_dispatch.py"
WT="$LIVE/.claude/worktrees/wt"                    # worktree: its own sentinel, own suites
mkdir -p "$WT/scripts" "$WT/cli/tests"
touch "$WT/scripts/verify-scoped.sh"
OTHER="$FIX/other"                                 # unrelated repo: no sentinel anywhere above
mkdir -p "$OTHER/tests" "$OTHER/cli/tests"

payload() { python3 -c 'import json,sys; print(json.dumps({"tool_input":{"command":sys.argv[1]},"cwd":sys.argv[2]}))' "$1" "$2"; }
decision() { payload "$1" "$2" | "$HOOK"; }

assert_denied() { local out; out="$(decision "$1" "$2")"
  printf '%s' "$out" | grep -q '"permissionDecision":"deny"' || { printf 'expected deny: %s (cwd %s)\nout: %s\n' "$1" "$2" "$out" >&2; exit 1; }; }
assert_passes() { local out; out="$(decision "$1" "$2")"
  [ -z "$out" ] || { printf 'expected silent pass: %s (cwd %s)\nout: %s\n' "$1" "$2" "$out" >&2; exit 1; }; }

# THE incident lane: full-suite collections inside a limen checkout
assert_denied 'cd cli && uv run python -m pytest tests/ -q 2>&1 | tail -15'  "$LIVE"  # the 2026-07-15 command
assert_denied 'python3 -m pytest cli/tests -q'                "$LIVE"
assert_denied 'python -m pytest web/api/tests'                "$LIVE"
assert_denied 'pytest tests/'                                 "$LIVE"
assert_denied 'uv run pytest tests -q'                        "$LIVE/cli"        # relative to cli cwd
assert_denied 'pytest cli/tests -k dispatch'                  "$LIVE"            # -k is still a full collection
assert_denied 'pytest -q'                                     "$LIVE/cli"        # bare pytest from a suite parent
assert_denied 'pytest'                                        "$LIVE"            # bare pytest from the root
assert_denied 'cli/.venv/bin/python3 -m pytest cli/tests -q'  "$LIVE"            # venv python path
assert_denied 'env -u LIMEN_API_TOKEN pytest cli/tests'       "$LIVE"            # env prefix
assert_denied 'pytest cli/tests'                              "$WT"              # worktrees are the same law
assert_denied 'pytest tests'                                  "$WT/cli"          # relative suite inside a worktree
assert_denied 'ls && python3 -m pytest cli/tests -q'          "$LIVE"            # pytest after separator

# Legitimate lanes — must never block
assert_passes 'pytest cli/tests/test_dispatch.py -q'          "$LIVE"            # file-scoped
assert_passes 'pytest cli/tests/test_dispatch.py::test_x'     "$LIVE"            # node id
assert_passes 'uv run python -m pytest tests/test_dispatch.py' "$LIVE/cli"       # file-scoped (.py rule)
assert_passes 'pytest cli/tests/unit'                         "$LIVE"            # suite SUBdirectory — scoped enough
assert_passes 'pytest mcp/tests'                              "$LIVE"            # not a heavy suite root
assert_passes 'pytest tests/'                                 "$OTHER"           # other repo — no sentinel
assert_passes 'pytest'                                        "$OTHER/cli"
assert_passes 'bash scripts/verify-scoped.sh'                 "$LIVE"            # the lawful lane itself
assert_passes 'python3 scripts/verify.py --changed'           "$LIVE"
assert_passes 'bash scripts/verify-whole.sh'                  "$LIVE"
assert_passes 'echo "pytest tests/"'                          "$LIVE"            # token at arg position only
assert_passes 'grep -r pytest tests/'                         "$LIVE"
assert_passes 'pip install pytest'                            "$LIVE"
assert_passes 'ls -la'                                        "$LIVE"            # prefilter
assert_passes 'cd $SOMEWHERE && pytest tests/'                "$LIVE"            # unresolved var → fail open
assert_passes 'pytest $SUITE'                                 "$LIVE"            # unresolved arg → fail open

# Malformed payload → fail open (silent pass)
out="$(printf 'not json' | "$HOOK")"
[ -z "$out" ] || { echo "malformed payload should fail open: $out" >&2; exit 1; }

# Escape hatch
out="$(payload 'pytest tests/' "$LIVE" | LIMEN_ALLOW_FULL_PYTEST=1 "$HOOK")"
[ -z "$out" ] || { echo "escape hatch failed: $out" >&2; exit 1; }

printf 'pytest-scope-guard.test: ok\n'
