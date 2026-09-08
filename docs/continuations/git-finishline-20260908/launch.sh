#!/usr/bin/env bash
set -euo pipefail

capsule_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(git -C "$capsule_dir" rev-parse --show-toplevel)"
slug=git-finishline-20260908

bash "$repository_root/scripts/start-worktree-session.sh" \
  --conduct --from origin/work/git-finishline-20260908 --runway 4h \
  --prompt-file "$capsule_dir/README.md" limen "$slug"

if [[ "${1:-}" == "--prepare-only" ]]; then
  exit 0
fi

worktree_path="$(git -C "$repository_root" worktree list --porcelain | python3 -c '
import sys
for block in sys.stdin.read().split("\n\n"):
    rows = block.splitlines()
    if "branch refs/heads/work/git-finishline-20260908" in rows:
        print(next(row[9:] for row in rows if row.startswith("worktree ")))
        break
else:
    raise SystemExit("continuation worktree is unavailable")
')"
exec bash "$worktree_path/.limen-workstream/kickstart.sh"
