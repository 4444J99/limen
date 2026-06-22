#!/usr/bin/env bash
# sync-release.sh — the SUBSTRATE SELF-HEAL organ. Closes the self-* loop: root → leaf → root.
#
# Every few beats it re-converges the live daemon checkout to the release (origin/main):
#   • CODE follows the release automatically — a push to origin/main IS a deploy (push is retired
#     as a lever; continuous deployment). All organ scripts + the cli package update in place and
#     take effect for the very next subprocess the beat spawns.
#   • DATA is preserved — the daemon OWNS the live tasks.yaml queue; the committed copy in a release
#     is only a stale snapshot, so the live queue always wins.
#   • It FAILS OPEN, always — fast-forward ONLY, never force / reset / merge-commit; on a diverged
#     history or a blocked tree it logs the cheapest path and returns 0 so the beat never stops
#     (the "never a silent no" invariant). It NEVER exits or re-execs the daemon (KeepAlive=false:
#     an exit would not respawn — that is the documented dead-daemon failure mode).
#
# Untracked runtime state (logs/autonomy-policy.json governor gate, usage.json, caches) is SAFE:
# a fast-forward only advances committed history and leaves untracked files untouched. This organ
# deliberately does NOT `git add -A` (that is what once swept the governor gate into a commit).
set -uo pipefail
export HOME="${HOME:-/Users/4jp}"
ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
BRANCH="${LIMEN_RELEASE_BRANCH:-main}"

cd "$ROOT" 2>/dev/null || { echo "sync-release: no LIMEN_ROOT ($ROOT) — fail open"; exit 0; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "sync-release: not a git repo — fail open"; exit 0; }

git fetch --quiet origin "$BRANCH" 2>/dev/null || { echo "sync-release: fetch failed — fail open"; exit 0; }
LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
REMOTE="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo)"
[ -n "$REMOTE" ] || { echo "sync-release: no origin/$BRANCH — fail open"; exit 0; }
[ "$LOCAL" = "$REMOTE" ] && { echo "sync-release: at release ${REMOTE:0:7} ✓"; exit 0; }

# fast-forward ONLY — never touch a diverged or rewound history
if ! git merge-base --is-ancestor "$LOCAL" "$REMOTE" 2>/dev/null; then
  echo "sync-release: local (${LOCAL:0:7}) diverged from origin/$BRANCH (${REMOTE:0:7}) — fail open"
  echo "sync-release: cheapest path = reconcile by hand (this organ NEVER force-moves a branch)"
  exit 0
fi
CUR="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo)"
[ "$CUR" = "$BRANCH" ] || { echo "sync-release: on '$CUR' not '$BRANCH' — fail open (no auto-switch)"; exit 0; }

# preserve the LIVE queue (daemon-owned) across the ff
TMP="$(mktemp 2>/dev/null || echo "$ROOT/logs/.tasks.sync.$$")"
[ -f tasks.yaml ] && cp -f tasks.yaml "$TMP" 2>/dev/null || true

# set tracked working changes aside so the ff isn't blocked (build artifacts, the live tasks.yaml);
# we DROP this stash afterward — the released versions win, except tasks.yaml which we restore.
stashed=0
if ! git diff --quiet 2>/dev/null; then
  git stash push --quiet 2>/dev/null && stashed=1 || true
fi

LOOP_BEFORE="$(git rev-parse "HEAD:scripts/heartbeat-loop.sh" 2>/dev/null || echo)"
if git merge --ff-only "origin/$BRANCH" --quiet 2>/dev/null; then
  [ -f "$TMP" ] && cp -f "$TMP" tasks.yaml 2>/dev/null || true   # live queue wins over the snapshot
  [ "$stashed" = 1 ] && git stash drop --quiet 2>/dev/null || true
  rm -f "$TMP" 2>/dev/null || true
  echo "sync-release: ff ${LOCAL:0:7} → ${REMOTE:0:7} ✓ — release deployed (organs live next subprocess)"
  LOOP_AFTER="$(git rev-parse "HEAD:scripts/heartbeat-loop.sh" 2>/dev/null || echo)"
  if [ -n "$LOOP_BEFORE" ] && [ "$LOOP_BEFORE" != "$LOOP_AFTER" ]; then
    # the conductor's OWN loop body changed; organs are already current. Do NOT exit (KeepAlive=false
    # would leave it dead) — flag for a deliberate kickstart to load the new loop.
    touch "$ROOT/logs/.loop-update-pending" 2>/dev/null || true
    echo "sync-release: heartbeat-loop.sh itself changed — kickstart to load it: launchctl kickstart -k gui/\$(id -u)/com.limen.heartbeat"
  fi
else
  [ "$stashed" = 1 ] && git stash pop --quiet 2>/dev/null || true
  rm -f "$TMP" 2>/dev/null || true
  echo "sync-release: ff blocked (untracked file would be overwritten?) — fail open, beat continues"
fi
exit 0
