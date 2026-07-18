#!/usr/bin/env bash
# heal-hook-drift.sh — re-install the deployed Claude Code PreToolUse trust hooks when they drift
# from the repo canonical. Those hooks are the mechanism that silences fleet/auto-mode permission
# prompts (dialogs-silenced.sh class 1b): allow-trusted-cd-git.sh preempts the destructive-ask rules
# + the compound-cd guard for path-gated reap work; insights-capture.sh feeds the insights lineage.
# A stale live copy silently reintroduces the prompt flood.
#
# This effector re-installs the canonical copy (install -m 755) whenever ~/.claude/hooks/<hook> is
# missing or its sha256 differs from the canonical. It ONLY reinstalls the two hook files it owns; it
# NEVER touches ~/.claude/settings.json (that boundary is classifier-blocked and stays a human lever).
# Canonical source = the LIVE checkout (LIMEN_ROOT, default ~/Workspace/limen), NEVER a WIP worktree,
# so an unmerged worktree hook can't be pushed to the live fleet.
#
# Dry-run by default (reports the drift + cure). Arm with LIMEN_HOOK_DRIFT_HEAL=1 to apply (the
# arm-once ~/.limen.env convention, cf. LIMEN_CLAUDE_LSREGISTER_HEAL). Idempotent. Exit 0 ⟺ no drift
# (or all healed); exit 1 if drift is found on a dry-run, or drift remains after apply.
set -uo pipefail

ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
HOOKS_SRC="$ROOT/scripts/hooks"
HOOKS_LIVE="$HOME/.claude/hooks"
HOOKS="allow-trusted-cd-git.sh insights-capture.sh"

ARMED=0
[ "${LIMEN_HOOK_DRIFT_HEAL:-0}" = 1 ] && ARMED=1
[ "${1:-}" = "--apply" ] && ARMED=1   # the sensor-injected arm (args_when on the dialogs-silenced valve)

sha() { shasum -a 256 < "$1" 2>/dev/null | cut -d' ' -f1; }

# True iff the live hook is missing or differs from the canonical (and a canonical exists to heal from).
drifted() {
  local hf="$1" canon="$HOOKS_SRC/$1" live="$HOOKS_LIVE/$1"
  [ -f "$canon" ] || return 1              # no canonical source → nothing we can heal
  [ -f "$live" ] || return 0               # live missing → drift
  [ "$(sha "$canon")" != "$(sha "$live")" ]
}

found=0
for hf in $HOOKS; do
  drifted "$hf" || continue
  found=$((found + 1))
  canon="$HOOKS_SRC/$hf"; live="$HOOKS_LIVE/$hf"
  if [ "$ARMED" = 1 ]; then
    mkdir -p "$HOOKS_LIVE"
    install -m 755 "$canon" "$live" && echo "hook-drift-heal: installed $hf ($canon -> $live)"
  else
    echo "hook-drift-heal: would install $hf: $canon -> $live"
  fi
done

remaining=0
for hf in $HOOKS; do drifted "$hf" && remaining=$((remaining + 1)); done

if [ "$remaining" -eq 0 ] && { [ "$ARMED" = 1 ] || [ "$found" -eq 0 ]; }; then
  echo "hook-drift-heal: clean (live trust hooks == repo canonical)"
  exit 0
fi
if [ "$ARMED" != 1 ]; then
  echo "hook-drift-heal: found $found drifted hook(s) — arm LIMEN_HOOK_DRIFT_HEAL=1 and re-run to cure"
  exit 1
fi
echo "hook-drift-heal: $remaining hook(s) still drifted after apply"
exit 1
