#!/usr/bin/env bash
# heal-claude-cask.sh — remove a duplicate Homebrew *cask* install of claude-code, which re-seeds the
# Gatekeeper "'claude' is an app downloaded from the Internet" dialog on every brew upgrade
# (dialogs-silenced.sh class 4).
#
# Casks (unlike bottled formulae) stamp com.apple.quarantine on every download, so each cask upgrade
# is a fresh quarantined Mach-O at a new Caskroom path = a Gatekeeper first-open prompt, and
# `brew upgrade --greedy-auto-updates` re-seeds it forever — silently defeating DISABLE_AUTOUPDATER
# (which only stops the NATIVE updater). The one sanctioned install is the native ~/.local/bin/claude.
#
# This effector detects the cask duplicate and uninstalls it. It uninstalls ONLY the cask
# (`brew uninstall --cask claude-code`); the native ~/.local/bin/claude is a separate install and is
# never touched. After an armed uninstall it VERIFIES the native install is still intact.
#
# Dry-run by default. Arm with LIMEN_CASK_DUPLICATE_HEAL=1 to apply (the arm-once ~/.limen.env
# convention). Idempotent. Exit 0 ⟺ no cask duplicate; exit 1 if the cask is present on a dry-run, or
# remains after apply.
set -uo pipefail

if [ "$(uname 2>/dev/null)" != "Darwin" ]; then
  echo "claude-cask-heal: non-darwin — inapplicable"
  exit 0
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "claude-cask-heal: brew not installed — inapplicable"
  exit 0
fi

ARMED=0
[ "${LIMEN_CASK_DUPLICATE_HEAL:-0}" = 1 ] && ARMED=1
[ "${1:-}" = "--apply" ] && ARMED=1   # the sensor-injected arm (args_when on the dialogs-silenced valve)

NATIVE="$HOME/.local/bin/claude"
cask_present() { brew list --cask 2>/dev/null | grep -qx 'claude-code'; }

if ! cask_present; then
  echo "claude-cask-heal: clean (no duplicate Homebrew cask 'claude-code')"
  exit 0
fi

if [ "$ARMED" != 1 ]; then
  echo "claude-cask-heal: duplicate Homebrew cask 'claude-code' present — arm LIMEN_CASK_DUPLICATE_HEAL=1 and re-run to uninstall (native ~/.local/bin/claude is the sanctioned install)"
  exit 1
fi

brew uninstall --cask claude-code 2>&1 | tail -2 || true
if cask_present; then
  echo "claude-cask-heal: cask 'claude-code' still present after uninstall"
  exit 1
fi
# Safety: the native install must survive (the cask uninstall never touches ~/.local/bin/claude).
if [ -e "$NATIVE" ] || command -v claude >/dev/null 2>&1; then
  echo "claude-cask-heal: uninstalled duplicate cask 'claude-code' (native install intact)"
  exit 0
fi
echo "claude-cask-heal: WARNING cask removed but native claude not found — verify ~/.local/bin/claude"
exit 1
