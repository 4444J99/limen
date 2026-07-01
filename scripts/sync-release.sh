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

# Regenerable daemon bookkeeping — receipt files the beat REWRITES every cycle. A commit touching ONLY
# these is "unique" by patch-id yet carries NO genuine work: it is loss-free to re-converge past. This
# is the exact commit that otherwise strands the live checkout — a receipt committed while in sync, then
# left diverged when origin advanced (a merged PR) before its push landed → ff-only fails open forever,
# pinning the daemon to stale code. Distinct from the patch-id valve ("already upstream"): this is
# "regenerable, so losing it costs nothing". Override the globs via LIMEN_SYNC_RECEIPT_GLOBS.
RECEIPT_GLOBS="${LIMEN_SYNC_RECEIPT_GLOBS:-docs/worktree-preservation-receipts.json docs/pr-receipts.json docs/*-receipts.json docs/*-receipt.json}"
_only_receipts() {  # exit 0 ⟺ stdin has ≥1 path AND every path matches a receipt glob
  local f p matched any=0
  local -a globs
  read -r -a globs <<<"$RECEIPT_GLOBS"   # split on whitespace WITHOUT pathname-expanding the globs
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    any=1; matched=0
    for p in "${globs[@]}"; do
      # shellcheck disable=SC2254  # $p is an intentional case glob-pattern, not a literal to quote
      case "$f" in $p) matched=1; break ;; esac
    done
    [ "$matched" = 1 ] || return 1
  done
  [ "$any" = 1 ]
}

cd "$ROOT" 2>/dev/null || { echo "sync-release: no LIMEN_ROOT ($ROOT) — fail open"; exit 0; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "sync-release: not a git repo — fail open"; exit 0; }

git fetch --quiet origin "$BRANCH" 2>/dev/null || { echo "sync-release: fetch failed — fail open"; exit 0; }
LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
REMOTE="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo)"
[ -n "$REMOTE" ] || { echo "sync-release: no origin/$BRANCH — fail open"; exit 0; }
[ "$LOCAL" = "$REMOTE" ] && { echo "sync-release: at release ${REMOTE:0:7} ✓"; exit 0; }

# fast-forward ONLY — never touch a diverged or rewound history…
if ! git merge-base --is-ancestor "$LOCAL" "$REMOTE" 2>/dev/null; then
  # …EXCEPT the one provably-safe divergence: every local-only commit is ALREADY on origin by
  # content (git patch-id). That is the observed "session redid work that already landed" drift
  # (e.g. the Studium Odyssey commits replayed on a stale checkout). No unique work exists to lose,
  # so re-converging to the release is loss-free. We still NEVER force-move when ANY local commit
  # is genuinely unique — that path stays fail-open + hand-reconcile (the live-checkout-chaos guard).
  BASE="$(git merge-base "$LOCAL" "$REMOTE" 2>/dev/null || echo)"
  unique=1
  if [ -n "$BASE" ]; then
    unique=0
    upstream_ids="$(git log --no-merges --format=%H "$BASE..$REMOTE" 2>/dev/null \
      | while read -r h; do git show "$h" 2>/dev/null | git patch-id --stable 2>/dev/null | cut -d' ' -f1; done)"
    while read -r h; do
      [ -n "$h" ] || continue
      pid="$(git show "$h" 2>/dev/null | git patch-id --stable 2>/dev/null | cut -d' ' -f1)"
      [ -n "$pid" ] || { unique=1; break; }                       # empty diff / unknown ⇒ treat as unique (safe)
      printf '%s\n' "$upstream_ids" | grep -qxF "$pid" || { unique=1; break; }
    done <<EOF
$(git log --no-merges --format=%H "$BASE..$LOCAL" 2>/dev/null)
EOF
  fi
  reconcile_reason="all local commits already upstream (patch-id)"
  # Second loss-free valve: the unique local commits touch ONLY regenerable receipts (the beat rewrites
  # them next cycle). Guarded by --is-ancestor so we NEVER discard a commit origin doesn't already have
  # as a descendant — i.e. only when the release is strictly AHEAD of BASE, never on a rewound remote.
  if [ "$unique" = 1 ] && [ -n "$BASE" ] \
     && git merge-base --is-ancestor "$BASE" "$REMOTE" 2>/dev/null \
     && git diff --name-only "$BASE..$LOCAL" 2>/dev/null | _only_receipts; then
    unique=0
    reconcile_reason="local commit(s) touch ONLY regenerable receipts"
  fi
  CUR="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo)"
  if [ "$unique" = 0 ] && [ "$CUR" = "$BRANCH" ]; then
    TMP="$(mktemp 2>/dev/null || echo "$ROOT/logs/.tasks.sync.$$")"
    [ -f tasks.yaml ] && cp -f tasks.yaml "$TMP" 2>/dev/null || true
    # reset --hard leaves UNTRACKED runtime (logs/, usage.json) untouched; the valve above proved no
    # genuine committed work is lost; tasks.yaml (daemon-owned) is restored after.
    if git reset --hard "origin/$BRANCH" --quiet 2>/dev/null; then
      [ -f "$TMP" ] && cp -f "$TMP" tasks.yaml 2>/dev/null || true
      rm -f "$TMP" 2>/dev/null || true
      echo "sync-release: diverged but ${reconcile_reason} — re-converged ${LOCAL:0:7} → ${REMOTE:0:7} ✓ (no unique work lost)"
      exit 0
    fi
    rm -f "$TMP" 2>/dev/null || true
  fi
  echo "sync-release: local (${LOCAL:0:7}) diverged from origin/$BRANCH (${REMOTE:0:7}) with UNIQUE local work — fail open"
  echo "sync-release: cheapest path = reconcile by hand (this organ NEVER force-moves genuinely-unique history)"
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

# An UNTRACKED local file that collides with a path the release now TRACKS also blocks the ff (git
# refuses to overwrite untracked files — the .claude/settings.json drift observed 2026-06-24). Those
# paths are release-owned, so the released version must win, exactly like the tracked stash-drop above.
# Back up ONLY the colliding paths (logs/.sync-collision — never deleted) and remove them so the ff can
# write the tracked version. Untracked runtime the release does NOT track (logs/, usage.json, caches,
# the governor gate) is never in this set and stays untouched — the deliberate "no git add -A" invariant.
collided=0
untracked="$(git ls-files --others --exclude-standard 2>/dev/null || echo)"
if [ -n "$untracked" ]; then
  release_tracked="$(git ls-tree -r --name-only "origin/$BRANCH" 2>/dev/null || echo)"
  BK="$ROOT/logs/.sync-collision"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    printf '%s\n' "$release_tracked" | grep -qxF "$f" || continue   # only paths the release tracks
    mkdir -p "$BK/$(dirname "$f")" 2>/dev/null || true
    cp -f "$f" "$BK/$f" 2>/dev/null || true                         # back up (never delete) before removing
    rm -f "$f" 2>/dev/null && collided=1 || true
  done <<EOF
$untracked
EOF
  [ "$collided" = 1 ] && echo "sync-release: cleared release-owned untracked file(s) blocking ff (backup: logs/.sync-collision) — release version wins"
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
