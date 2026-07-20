#!/usr/bin/env bash
# sync-release.sh — the SUBSTRATE SELF-HEAL organ. Closes the self-* loop: root → leaf → root.
#
# Every few beats it re-converges the live daemon checkout to the release (origin/main):
#   • CODE follows the release automatically — a push to origin/main IS a deploy (push is retired
#     as a lever; continuous deployment). All organ scripts + the cli package update in place and
#     take effect for the very next subprocess the beat spawns.
#   • DATA follows the remote owner — tasks.yaml is a read-only local cache. This organ never
#     copies, restores, checks out, or preserves a locally mutated board across a release change.
#   • It FAILS OPEN, always — fast-forward ONLY, never force / reset / merge-commit; on a diverged
#     history or a blocked tree it logs the cheapest path and returns 0 so the beat never stops
#     (the "never a silent no" invariant). It NEVER exits or re-execs the daemon (KeepAlive=false:
#     an exit would not respawn — that is the documented dead-daemon failure mode).
#   • HEAD RESTS ON THE RELEASE BRANCH — a checkout parked on a work branch is UNPARKED back to
#     the release, but only when provably loss-free (branch tip safe on origin + no tracked dirt
#     beyond generated cache drift); see the unpark valve below.
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

if [ "${1:-}" = "--census" ]; then
  python3 - "$ROOT" "$BRANCH" "$RECEIPT_GLOBS" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

root = Path(sys.argv[1])
branch = sys.argv[2]
receipt_globs = [item for item in sys.argv[3].split() if item]


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def count_lines(proc: subprocess.CompletedProcess[str]) -> int:
    if proc.returncode != 0:
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


inside = git("rev-parse", "--is-inside-work-tree")
is_repo = inside.returncode == 0 and inside.stdout.strip() == "true"
tracked_dirty = git("diff", "--name-only", "HEAD") if is_repo else subprocess.CompletedProcess([], 1, "", "")
cached_dirty = git("diff", "--cached", "--name-only") if is_repo else subprocess.CompletedProcess([], 1, "", "")
untracked = git("ls-files", "--others", "--exclude-standard") if is_repo else subprocess.CompletedProcess([], 1, "", "")
current = git("symbolic-ref", "--quiet", "--short", "HEAD") if is_repo else subprocess.CompletedProcess([], 1, "", "")
remote = git("rev-parse", f"origin/{branch}") if is_repo else subprocess.CompletedProcess([], 1, "", "")

print(
    json.dumps(
        {
            "root_present": root.exists(),
            "git_repo": is_repo,
            "on_release_branch": bool(current.stdout.strip() == branch) if is_repo else False,
            "remote_tracking_present": remote.returncode == 0,
            "tracked_dirty_count": count_lines(tracked_dirty),
            "cached_dirty_count": count_lines(cached_dirty),
            "untracked_count": count_lines(untracked),
            "tasks_present": (root / "tasks.yaml").exists(),
            "logs_present": (root / "logs").exists(),
            "sync_collision_present": (root / "logs" / ".sync-collision").exists(),
            "loop_update_pending": (root / "logs" / ".loop-update-pending").exists(),
            "receipt_globs": len(receipt_globs),
        },
        indent=2,
        sort_keys=True,
    )
)
PY
  exit 0
fi

cd "$ROOT" 2>/dev/null || { echo "sync-release: no LIMEN_ROOT ($ROOT) — fail open"; exit 0; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "sync-release: not a git repo — fail open"; exit 0; }

# LIMEN_RELEASE_BRANCH selects the convergence target; it is not authority to
# reinterpret the repository's actual default branch as a disposable parked
# topic branch. Resolve origin/HEAD independently and refuse before any
# preservation commit or push when an override would otherwise make the real
# default branch enter the unpark path.
DEFAULT_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
if [ -z "$DEFAULT_BRANCH" ]; then
  DEFAULT_BRANCH="$(git ls-remote --symref origin HEAD 2>/dev/null \
    | awk '$1 == "ref:" && $2 ~ /^refs\/heads\// { sub(/^refs\/heads\//, "", $2); print $2; exit }')"
fi
[ -n "$DEFAULT_BRANCH" ] || DEFAULT_BRANCH="main"
CUR="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo)"
if [ -n "$CUR" ] && [ "$CUR" = "$DEFAULT_BRANCH" ] && [ "$BRANCH" != "$DEFAULT_BRANCH" ]; then
  echo "sync-release: REFUSED — '$CUR' is origin's default branch; LIMEN_RELEASE_BRANCH='$BRANCH' cannot reclassify or push it"
  exit 0
fi

git fetch --quiet origin "$BRANCH" 2>/dev/null || { echo "sync-release: fetch failed — fail open"; exit 0; }
LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
REMOTE="$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo)"
[ -n "$REMOTE" ] || { echo "sync-release: no origin/$BRANCH — fail open"; exit 0; }

# A dirty local board is neither a release artifact nor authority to overwrite the GitHub-backed
# projection. Leave it byte-identical and require authenticated cache hydration.
if ! git diff --quiet -- tasks.yaml 2>/dev/null \
   || ! git diff --cached --quiet -- tasks.yaml 2>/dev/null; then
  echo "sync-release: local tasks.yaml cache is dirty — refusing to copy/restore/discard it; hydrate from the authenticated keeper"
  exit 0
fi

# ── UNPARK valve — the live checkout must REST ON THE RELEASE BRANCH. A session that leaves HEAD
# parked on a work branch strands the daemon on stale code with no way home (observed
# 2026-06-29 → 07-04: five days pinned to a jules-capfill branch, 65 behind release, every
# autonomic capture entangling runtime state into that branch — because the valve fail-opened on
# dirt and merely HOPED capture.sh would land it "next beat"; for five days nothing did).
# PRESERVE-THEN-UNPARK (the operator's standing rule: nothing is abandoned that is not first safe on
# origin): the valve no longer depends on capture.sh's ordering — it lands the parked branch's own
# work to origin ITSELF (commits tracked dirt onto the branch, pushes the tip), THEN rests HEAD on
# the release. tasks.yaml must already be a clean remote-owned cache. The ONLY fail-open is a push
# that genuinely fails (offline/auth) — because then the work is not yet preserved and switching
# away would lose it. Detached HEAD is left alone.
CUR="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || echo)"
if [ -n "$CUR" ] && [ "$CUR" != "$BRANCH" ]; then
  git fetch --quiet origin "$CUR" 2>/dev/null || true
  dirt="$( { git diff --name-only HEAD 2>/dev/null; git diff --cached --name-only 2>/dev/null; } | grep -vxF 'tasks.yaml' | sort -u)"
  if [ -n "$dirt" ]; then
    # Stage ONLY tracked modifications (never untracked — no new secret can ride in; untracked
    # release-collisions are handled by the backup sweep below) and preserve them onto the branch.
    printf '%s\n' "$dirt" | while IFS= read -r f; do [ -n "$f" ] && git add -- "$f" 2>/dev/null || true; done
    git commit --quiet -m "capture(sync-release): preserve parked dirt before unpark [skip ci]" 2>/dev/null || true
    LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
  fi
  # Push the branch tip to origin if it is not already there — the valve preserves it itself rather
  # than waiting a beat. Only when the tip is provably safe on origin do we proceed to switch.
  RCUR="$(git rev-parse "origin/$CUR" 2>/dev/null || echo)"
  if [ "$RCUR" != "$LOCAL" ]; then
    if git push --quiet origin "$CUR" 2>/dev/null; then
      git fetch --quiet origin "$CUR" 2>/dev/null || true
      RCUR="$(git rev-parse "origin/$CUR" 2>/dev/null || echo)"
    fi
  fi
  if [ -z "$RCUR" ] || [ "$RCUR" != "$LOCAL" ]; then
    echo "sync-release: parked on '$CUR' — could not preserve tip to origin (offline/auth?) — fail open (work kept local, valve retries next beat)"
    exit 0
  fi
  # A switch is blocked by exactly what blocks the ff below (observed on the 2026-07-04 live heal):
  # (a) an UNTRACKED file the release now TRACKS (censor/precedents.jsonl that day) — release-owned,
  # so back it up to logs/.sync-collision and remove it, the same invariant as the ff collision
  # valve. A branch already checked out in another worktree also refuses; that stays fail-open
  # (surfaced in the message). The dirty-cache guard above keeps tasks.yaml out of this repair path.
  release_tracked="$(git ls-tree -r --name-only "origin/$BRANCH" 2>/dev/null || echo)"
  untracked="$(git ls-files --others --exclude-standard 2>/dev/null || echo)"
  BK="$ROOT/logs/.sync-collision"
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    printf '%s\n' "$release_tracked" | grep -qxF "$f" || continue   # only paths the release tracks
    mkdir -p "$BK/$(dirname "$f")" 2>/dev/null || true
    cp -f "$f" "$BK/$f" 2>/dev/null || true                         # back up (never delete) before removing
    rm -f "$f" 2>/dev/null || true
  done <<UNPARK_EOF
$untracked
UNPARK_EOF
  unparked=0
  why="$(git switch --quiet "$BRANCH" 2>&1)" && unparked=1
  if [ "$unparked" = 1 ]; then
    LOCAL="$(git rev-parse HEAD 2>/dev/null || echo)"
    echo "sync-release: UNPARKED '$CUR' → '$BRANCH' (branch tip safe on origin/$CUR) ✓"
  else
    why="$(printf '%s' "$why" | head -2 | tr '\n' ' ' | cut -c1-200)"
    echo "sync-release: switch '$CUR' → '$BRANCH' refused (${why}) — fail open (reconcile by hand)"
    exit 0
  fi
fi

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
    # reset --hard leaves UNTRACKED runtime (logs/, usage.json) untouched; the valve above proved no
    # genuine committed work is lost. The clean tasks.yaml cache follows the release projection.
    if git reset --hard "origin/$BRANCH" --quiet 2>/dev/null; then
      echo "sync-release: diverged but ${reconcile_reason} — re-converged ${LOCAL:0:7} → ${REMOTE:0:7} ✓ (no unique work lost)"
      exit 0
    fi
  fi
  echo "sync-release: local (${LOCAL:0:7}) diverged from origin/$BRANCH (${REMOTE:0:7}) with UNIQUE local work — fail open"
  echo "sync-release: cheapest path = reconcile by hand (this organ NEVER force-moves genuinely-unique history)"
  exit 0
fi
CUR="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo)"
[ "$CUR" = "$BRANCH" ] || { echo "sync-release: on '$CUR' not '$BRANCH' — fail open (no auto-switch)"; exit 0; }

# Set tracked working changes aside so the ff is not blocked by build artifacts. The dirty-cache
# guard above ensures tasks.yaml is not among them; the released projection wins.
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
  [ "$stashed" = 1 ] && git stash drop --quiet 2>/dev/null || true
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
  echo "sync-release: ff blocked (untracked file would be overwritten?) — fail open, beat continues"
fi
exit 0
