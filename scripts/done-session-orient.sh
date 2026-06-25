#!/usr/bin/env bash
# done-session-orient.sh — executable definition of done for the session-orientation organ.
#
# Exit 0  ⟺  the organ is built, read-only, PII-free, idempotent, and fail-open.
# Activation (writing the SessionStart/PostToolUse/SessionEnd entries into a settings.json)
# is a harness-gated his-hand act; this predicate REPORTS activation status but never
# depends on it — the organ is correct and safe whether armed or not.
#
# Run from the repo root:  bash scripts/done-session-orient.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
GEN="scripts/session-orient.py"
HOOK="scripts/hooks/session-orient.sh"
DIGEST="logs/session-orientation.md"
fail() { echo "✗ $*"; exit 1; }
ok()   { echo "✓ $*"; }

# 1. artifacts exist
[ -f "$GEN" ]  || fail "missing generator $GEN"
[ -f "$HOOK" ] || fail "missing hook $HOOK"
[ -x "$HOOK" ] || fail "hook not executable $HOOK"
ok "artifacts present and executable"

# 2. generator runs, prints a digest, writes the cached fallback, exits 0
out="$(python3 "$GEN")" || fail "generator exited non-zero"
printf '%s' "$out" | grep -q "Session orientation" || fail "generator printed no digest header"
[ -f "$DIGEST" ] || fail "generator did not write $DIGEST"
ok "generator runs, prints digest, writes $DIGEST"

# 3. PII firewall — counts-only. NO clinical literal may appear in the generator
#    SOURCE or the generated DIGEST (the firewall guards the generator, not just output).
DENY='seroquel|quetiapine|nocturia|apnea|urinat|antipsychotic|insomnia|diagnos|prescrib|dosage|[0-9]+ *mg'
if grep -Eiq "$DENY" "$GEN"; then fail "PII deny-list hit in generator source $GEN"; fi
if grep -Eiq "$DENY" "$DIGEST"; then fail "PII deny-list hit in generated digest $DIGEST"; fi
ok "PII-free: no clinical literal in generator source or digest"

# 4. idempotent — two consecutive runs are byte-identical (counts are stable within a tick)
a="$(python3 "$GEN")"; b="$(python3 "$GEN")"
[ "$a" = "$b" ] || fail "generator output not idempotent across two runs"
ok "idempotent across consecutive runs"

# 5. fail-open — empty LIMEN_ROOT yields exit 0 and an (almost) empty digest, never a crash
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
LIMEN_ROOT="$tmp" python3 "$GEN" >/dev/null 2>&1 || fail "generator crashed on empty root (not fail-open)"
ok "generator fails open on a missing/empty root"

# 6. hook fails open outside a project — emits nothing, exits 0
hk="$(CLAUDE_PROJECT_DIR=/nonexistent-$$ bash "$HOOK" 2>/dev/null)"; rc=$?
[ "$rc" -eq 0 ] || fail "hook non-zero outside a project (rc=$rc)"
[ -z "$hk" ] || fail "hook emitted output outside a project (should be silent)"
ok "hook is a clean no-op outside a project"

# 7. lint the generator + syntax-check the hook
if command -v ruff >/dev/null 2>&1 || python3 -m ruff --version >/dev/null 2>&1; then
  python3 -m ruff check --quiet "$GEN" || fail "ruff lint failed on $GEN"
  ok "ruff clean: $GEN"
fi
bash -n "$HOOK" || fail "bash syntax error in $HOOK"
ok "bash syntax ok: $HOOK"

# 8. activation status — reported, never required (harness-gated his-hand act)
SET=".claude/settings.json"
if grep -q "session-orient.sh" "$SET" 2>/dev/null; then
  echo "● ACTIVATION: WIRED in $SET"
else
  echo "● ACTIVATION: PENDING — paste the SessionStart block into $SET (harness-gated; his hand)"
fi

echo "session-orientation organ: DONE (built, PII-free, idempotent, fail-open)"
