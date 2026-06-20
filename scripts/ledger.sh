#!/usr/bin/env bash
# ledger.sh "line" — append to the INTERNAL canonical master-plan ledger (detach-safe),
# then mirror to the Archive4T backup copy IFF that volume is mounted.
#
# Why: the external SSD must be detachable for travel/mobile work with zero operational
# impact. The canonical ledger therefore lives on the INTERNAL disk; Archive4T holds only
# a mirror that catches up on remount. Appending never fails when the SSD is unplugged.
set -uo pipefail
ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
LEDGER="$ROOT/MASTER-PLAN.md"
MIRROR="/Volumes/Archive4T/agent-operating-system--master-plan-2026-06-16.md"

[ -n "${1:-}" ] && printf '%s\n' "$1" >> "$LEDGER"

if /sbin/mount | grep -q " on /Volumes/Archive4T "; then
  cp "$LEDGER" "$MIRROR" 2>/dev/null && echo "  ledger: internal canonical + mirrored to Archive4T"
else
  echo "  ledger: internal canonical only (Archive4T detached — will mirror on remount)"
fi
