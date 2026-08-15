#!/usr/bin/env bash
# hydrate-private-board.sh — keep off-repo private board custody current with the keeper.
#
# THE OTHER HALF OF THE PARTITION. `web/worker` (#2299) moved canonical state into the
# authenticated Durable Object and reduced the published `tasks.yaml` to a counts-only
# aggregate. That aggregate is a HEALTH surface, not a work board: the moment the public
# projection lands on `main`, any local consumer still reading it sees ZERO tasks — which
# is indistinguishable from "there is no work" and is precisely the silent failure the
# partition plan warned about, inverted.
#
# So local code resolves its board through `private_board.operational_board_path()`, which
# derives custody from the public file's SHAPE and raises loudly when custody is absent.
# This rung is what keeps that custody present and fresh. It runs BEFORE any board reader
# in the beat, because a stale cache produces stale CAS preconditions and the keeper
# answers those with `exact revision moved` (the 2026-08-15 release-stale wedge).
#
# SELF-ARMING. Pre-cutover the public projection is still the real board, so hydration is
# not required and this exits 0 after one cheap shape probe — no network, no writes. It
# starts doing real work on the beat the cutover lands, with no flag to flip.
#
# FAIL-OPEN on transport, FAIL-LOUD on custody. A broker outage leaves the previous custody
# in place and exits 0 (the next beat retries); but if the public projection IS the
# aggregate and custody has never been hydrated, that is a real blocker and exits non-zero
# so the rung goes red instead of the fleet quietly idling on an empty board.
#
#   scripts/hydrate-private-board.sh            # hydrate if the cutover has landed
#   scripts/hydrate-private-board.sh --force    # hydrate regardless of public shape
set -euo pipefail

LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
PUBLIC_BOARD="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
PY="${LIMEN_VENV_PY:-$LIMEN_ROOT/.venv/bin/python3}"
[ -x "$PY" ] || PY="python3"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

if [ ! -f "$PUBLIC_BOARD" ]; then
  echo "hydrate-private-board: no public projection at $PUBLIC_BOARD — nothing to derive from"
  exit 0
fi

# One cheap shape probe (header bytes only, never a 5.8 MB parse), derived from the same
# module every consumer uses so the rung can never disagree with them about the shape.
shape="$("$PY" - "$PUBLIC_BOARD" "$LIMEN_ROOT/cli/src" <<'PY' 2>/dev/null || echo probe-failed
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[2])
try:
    from limen.private_board import default_private_custody_path, path_is_public_aggregate
except ModuleNotFoundError:
    print("probe-failed")
    raise SystemExit(0)
public = Path(sys.argv[1])
print(f"{'aggregate' if path_is_public_aggregate(public) else 'full-board'} {default_private_custody_path(public)}")
PY
)"

state="${shape%% *}"
custody="${shape#* }"

if [ "$state" = "probe-failed" ] || [ -z "${custody:-}" ] || [ "$custody" = "$state" ]; then
  echo "hydrate-private-board: shape probe unavailable (limen package not importable) — skipped"
  exit 0
fi

if [ "$state" = "full-board" ] && [ "$FORCE" = "0" ]; then
  echo "hydrate-private-board: public projection is still the full board — custody not required yet"
  exit 0
fi

if ! "$PY" -m limen board hydrate --output "$custody" 2>/tmp/hydrate-private-board.err; then
  detail="$(tr '\n' ' ' </tmp/hydrate-private-board.err | tail -c 300)"
  if [ -f "$custody" ]; then
    # Transport failure with custody already on disk: the fleet keeps operating on the
    # previous hydration and the next beat retries. Loud, but not a rung failure.
    echo "hydrate-private-board: keeper unreachable ($detail) — keeping existing custody $custody"
    exit 0
  fi
  echo "hydrate-private-board: FAILED — public projection is the aggregate and custody has never" >&2
  echo "  been hydrated ($custody). Local board reads will raise PrivateCustodyUnavailable." >&2
  echo "  keeper error: $detail" >&2
  exit 1
fi

rows="$("$PY" - "$custody" <<'PY' 2>/dev/null || echo '?'
import sys

import yaml

data = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
print(len(data.get("tasks") or []))
PY
)"
echo "hydrate-private-board: custody current — $rows task(s) at $custody"
