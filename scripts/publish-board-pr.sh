#!/usr/bin/env bash
# publish-board-pr.sh — open the PR that carries the keeper's published board into `main`.
#
# THE MISSING HALF OF A RETIREMENT. `preserve_board_projection` was retired to
# `PreserveResult(skipped=True, reason="remote-keeper-owns-projection")` — correctly, since a local
# process must never commit or push the canonical board. But that function was ALSO the only thing
# that opened this PR, and nothing replaced it. `BOARD_PUBLICATION_TITLE` has been a dead constant
# ever since: the keeper kept publishing to `tabularius/board-projection` and nothing carried it to
# `main`.
#
# Measured 2026-08-07. Last publication merged: 2026-07-26 (#1569) — exactly the `track.date` the
# board was frozen at, 12 days later. The local `tasks.yaml` was byte-identical to `origin/main`
# (so the live checkout was current; this was not a sync problem), while the publication branch sat
# +107 tasks and +177 dispatch receipts ahead. Everything downstream reads the frozen copy:
# `dispatch` SELECTS from it (launching jules work on tasks the keeper considers blocked), every
# receipt ticket computes its compare-and-swap precondition from it (so the keeper answers
# `exact revision moved`), and `lane_throughput_window` counts 0 dispatches in it — which pinned the
# jules lane in bootstrap at 25/day and made the requested 100/day structurally unreachable (#1995).
#
# WHY SHELL. Opening a PR is an outward action, and `check-effectors.py` Class C exists because a
# `PreToolUse(Bash)` hook can never see `subprocess.run(["gh", ...])` inside a Python module. The
# `gh` call belongs on the Bash rail where that guard can reach it — the same reason
# `session-plan.py` prints its `gh` command instead of making it (see CLAUDE.md).
#
# This script NEVER merges and NEVER pushes. It opens or reports the PR; `merge-policy.sh` decides
# the merge, and the beat's merge rung owns it. Idempotent: an already-open PR is a no-op, and so is
# a projection branch with nothing new in it.
#
#   scripts/publish-board-pr.sh              # open the PR if one is due
#   scripts/publish-board-pr.sh --dry-run    # report what it would do; no writes
set -euo pipefail

LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
BRANCH="${LIMEN_BOARD_PUBLICATION_BRANCH:-tabularius/board-projection}"
BASE="${LIMEN_BOARD_PUBLICATION_BASE:-main}"
TITLE="tabularius: publish board projection"
DRY_RUN=0
[ "${1:-}" = "--dry-run" ] && DRY_RUN=1

cd "$LIMEN_ROOT"

# Fail OPEN on every unreadable condition: this rung must never take a beat down.
if ! git fetch origin "$BRANCH" "$BASE" --quiet 2>/dev/null; then
  echo "publish-board-pr: cannot fetch origin/$BRANCH — skipped"
  exit 0
fi

if ! git rev-parse --verify --quiet "refs/remotes/origin/$BRANCH" >/dev/null; then
  echo "publish-board-pr: origin/$BRANCH does not exist — nothing to publish"
  exit 0
fi

ahead="$(git rev-list --count "origin/$BASE..origin/$BRANCH" 2>/dev/null || echo 0)"
if [ "$ahead" = "0" ]; then
  echo "publish-board-pr: origin/$BRANCH is not ahead of origin/$BASE — nothing to publish"
  exit 0
fi

# A branch can be "ahead" by commits that change nothing in the tree (a reconcile merge of main).
# The PR only exists to carry board content, so gate on the tree, not the commit count.
if git diff --quiet "origin/$BASE...origin/$BRANCH" -- tasks.yaml 2>/dev/null; then
  echo "publish-board-pr: origin/$BRANCH has $ahead commit(s) but no tasks.yaml change — nothing to publish"
  exit 0
fi

existing="$(gh pr list --head "$BRANCH" --base "$BASE" --state open --json number \
  --jq '.[0].number // empty' 2>/dev/null || true)"
if [ -n "$existing" ]; then
  echo "publish-board-pr: PR #$existing already open for $BRANCH -> $BASE (owner: the beat's merge rung)"
  exit 0
fi

stat_line="$(git diff --shortstat "origin/$BASE...origin/$BRANCH" -- tasks.yaml 2>/dev/null || true)"

if [ "$DRY_RUN" = "1" ]; then
  echo "publish-board-pr: WOULD open '$TITLE' for $BRANCH -> $BASE ($ahead commit(s);${stat_line:- no stat})"
  exit 0
fi

body="$(
  cat <<EOF
Carries the keeper's published board projection into \`$BASE\`.

Opened by \`scripts/publish-board-pr.sh\` — the replacement for the PR-opening half of
\`preserve_board_projection\`, which was retired with the local publication writer and never
replaced. Without it the keeper publishes to \`$BRANCH\` and nothing carries it to \`$BASE\`, which
froze the local projection for 12 days and made the 100/day jules target structurally unreachable
(#1995).

- \`$BRANCH\` is $ahead commit(s) ahead of \`$BASE\`
- \`tasks.yaml\`:${stat_line:- (see diff)}

Per \`ci.yml\`'s board fast lane, a board-projection PR implicates no code, so the matrix runs
post-merge for \`check-main-green\`'s exact-head evidence rather than on this PR's critical path.

This rung never merges: \`merge-policy.sh\` decides and the beat's merge rung owns it.

Refs #1995
EOF
)"

number="$(gh pr create --base "$BASE" --head "$BRANCH" --title "$TITLE" --body "$body" 2>&1 | tail -1)"
echo "publish-board-pr: opened $number"
