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
PRESSURE_GEN="scripts/session-lifecycle-pressure.py"
PRESSURE_HOOK="scripts/hooks/session-lifecycle-pressure.sh"
DIGEST="logs/session-orientation.md"
fail() { echo "✗ $*"; exit 1; }
ok()   { echo "✓ $*"; }

# 1. artifacts exist
[ -f "$GEN" ]  || fail "missing generator $GEN"
[ -f "$HOOK" ] || fail "missing hook $HOOK"
[ -x "$HOOK" ] || fail "hook not executable $HOOK"
[ -f "$PRESSURE_GEN" ] || fail "missing lifecycle pressure generator $PRESSURE_GEN"
[ -f "$PRESSURE_HOOK" ] || fail "missing lifecycle pressure hook $PRESSURE_HOOK"
[ -x "$PRESSURE_GEN" ] || fail "lifecycle pressure generator not executable $PRESSURE_GEN"
[ -x "$PRESSURE_HOOK" ] || fail "lifecycle pressure hook not executable $PRESSURE_HOOK"
ok "artifacts present and executable"

# 2. generators run, print digests, write cached fallbacks, exit 0
pressure="$(LIMEN_ROOT="$ROOT" python3 "$PRESSURE_GEN" --write)" || fail "lifecycle pressure generator exited non-zero"
printf '%s' "$pressure" | grep -q "Lifecycle pressure" || fail "pressure generator printed no lifecycle pressure line"
[ -f "logs/session-lifecycle-pressure.json" ] || fail "pressure generator did not write logs/session-lifecycle-pressure.json"
[ -f "logs/session-lifecycle-pressure.md" ] || fail "pressure generator did not write logs/session-lifecycle-pressure.md"
out="$(LIMEN_ROOT="$ROOT" python3 "$GEN")" || fail "generator exited non-zero"
printf '%s' "$out" | grep -q "Session orientation" || fail "generator printed no digest header"
printf '%s' "$out" | grep -q "Lifecycle pressure" || fail "generator omitted lifecycle pressure section"
[ -f "$DIGEST" ] || fail "generator did not write $DIGEST"
ok "generators run, print digests, write cached logs"

# 3. PII firewall — counts-only. NO clinical literal may appear in the generator
#    SOURCE or the generated DIGEST (the firewall guards the generator, not just output).
DENY='seroquel|quetiapine|nocturia|apnea|urinat|antipsychotic|insomnia|diagnos|prescrib|dosage|[0-9]+ *mg'
if grep -Eiq "$DENY" "$GEN"; then fail "PII deny-list hit in generator source $GEN"; fi
if grep -Eiq "$DENY" "$DIGEST"; then fail "PII deny-list hit in generated digest $DIGEST"; fi
if grep -Eiq "$DENY" "$PRESSURE_GEN"; then fail "PII deny-list hit in pressure source $PRESSURE_GEN"; fi
if grep -Eiq "$DENY" "logs/session-lifecycle-pressure.md"; then fail "PII deny-list hit in pressure digest"; fi
ok "PII-free: no clinical literal in generator source or digest"

# 4. idempotent — two consecutive runs are byte-identical for a stable input snapshot
tasks_snapshot="$(mktemp)"
echo "● retained verification snapshot: $tasks_snapshot"
cp "tasks.yaml" "$tasks_snapshot" # task-writer-audit: allow-derived-sandbox
git_section=""
branch="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [ -n "$branch" ]; then
  dirty="clean"
  if [ -n "$(git -C "$ROOT" status --porcelain 2>/dev/null || true)" ]; then
    dirty="dirty"
  fi
  counts="$(git -C "$ROOT" rev-list --left-right --count origin/main...HEAD 2>/dev/null || true)"
  pos=""
  set -- $counts
  if [ "$#" -eq 2 ]; then
    behind="$1"
    ahead="$2"
    pos=" · ahead $ahead/behind $behind of main"
  fi
  git_section="**Git** — $branch$pos · $dirty"
fi
a="$(LIMEN_ROOT="$ROOT" LIMEN_ORIENT_TASKS="$tasks_snapshot" LIMEN_ORIENT_GIT_SECTION="$git_section" LIMEN_ORIENT_NO_WRITE=1 python3 "$GEN")"
b="$(LIMEN_ROOT="$ROOT" LIMEN_ORIENT_TASKS="$tasks_snapshot" LIMEN_ORIENT_GIT_SECTION="$git_section" LIMEN_ORIENT_NO_WRITE=1 python3 "$GEN")"
[ "$a" = "$b" ] || fail "generator output not idempotent across two runs"
ok "idempotent across consecutive runs"

# 5. fail-open — empty LIMEN_ROOT yields exit 0 and an (almost) empty digest, never a crash
tmp="$(mktemp -d)"
echo "● retained empty-root fixture: $tmp"
LIMEN_ROOT="$tmp" python3 "$GEN" >/dev/null 2>&1 || fail "generator crashed on empty root (not fail-open)"
ok "generator fails open on a missing/empty root"

# 6. hook fails open with a stale Claude project dir — the executable may live in the
#    stable Limen checkout while Claude reports a since-reaped worktree.
hk="$(CLAUDE_PROJECT_DIR=/nonexistent-$$ bash "$HOOK" 2>/dev/null)"; rc=$?
[ "$rc" -eq 0 ] || fail "hook non-zero with stale project dir (rc=$rc)"
printf '%s' "$hk" | grep -q "Session orientation" || fail "hook did not fall back to stable Limen root"
ok "hook survives a stale Claude project dir"

# 7. lint the generator + syntax-check the hook
if command -v ruff >/dev/null 2>&1 || python3 -m ruff --version >/dev/null 2>&1; then
  python3 -m ruff check --quiet "$GEN" || fail "ruff lint failed on $GEN"
  ok "ruff clean: $GEN"
fi
bash -n "$HOOK" || fail "bash syntax error in $HOOK"
bash -n "$PRESSURE_HOOK" || fail "bash syntax error in $PRESSURE_HOOK"
ok "bash syntax ok: hooks"

# 8. activation status
SET=".claude/settings.json"
if grep -q "session-orient.sh" "$SET" 2>/dev/null; then
  echo "● ACTIVATION: WIRED in $SET"
else
  echo "● ACTIVATION: PENDING — paste the SessionStart block into $SET (harness-gated; his hand)"
fi
grep -q "session-lifecycle-pressure.sh" "$SET" 2>/dev/null || fail "SessionEnd pressure hook is not wired in $SET"
ok "SessionEnd lifecycle pressure hook is wired"

echo "session-orientation organ: DONE (built, PII-free, idempotent, fail-open)"
