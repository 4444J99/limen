#!/usr/bin/env bash
set -euo pipefail

hub_root="${LIMEN_COLLABORATION_HUB_ROOT:-$HOME/Workspace/collaboration-operations-platform}"
workspace="${LIMEN_COLLABORATION_HUB_WORKSPACE:-$HOME/Workspace/_collaboration-operations-private}"
endpoint="${LIMEN_COLLABORATION_HUB_ENDPOINT:-https://collaboration-operations-hub.ivixivi.workers.dev}"
registry="${LIMEN_COLLABORATION_HUB_REGISTRY:-${LIMEN_ROOT:-$HOME/Workspace/limen}/organs/consulting/constellation/registry.yaml}"

if ! git -C "$hub_root" rev-parse --git-dir >/dev/null 2>&1; then
  echo "collaboration-hub-sync: owner checkout absent"
  exit 1
fi
if [[ "$(git -C "$hub_root" branch --show-current 2>/dev/null || true)" != "main" ]]; then
  echo "collaboration-hub-sync: owner checkout is not on main"
  exit 1
fi
if [[ -n "$(git -C "$hub_root" status --porcelain --untracked-files=no 2>/dev/null)" ]]; then
  echo "collaboration-hub-sync: owner checkout has tracked changes"
  exit 1
fi

GIT_TERMINAL_PROMPT=0 git -C "$hub_root" fetch -q origin main
GIT_TERMINAL_PROMPT=0 git -C "$hub_root" merge -q --ff-only origin/main
if [[ ! -f "$hub_root/package-lock.json" || ! -x "$hub_root/scripts/heartbeat-sync.sh" ]]; then
  echo "collaboration-hub-sync: owner release is incomplete"
  exit 1
fi
if [[ ! -x "$hub_root/node_modules/.bin/tsx" ]]; then
  npm --prefix "$hub_root" ci --ignore-scripts --no-audit --no-fund >/dev/null
fi

COLLABORATION_HUB_WORKSPACE="$workspace" \
COLLABORATION_HUB_ENDPOINT="$endpoint" \
COLLABORATION_HUB_REGISTRY="$registry" \
  bash "$hub_root/scripts/heartbeat-sync.sh"
