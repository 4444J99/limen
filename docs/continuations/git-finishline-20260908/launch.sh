#!/usr/bin/env bash
set -euo pipefail

capsule_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(git -C "$capsule_dir" rev-parse --show-toplevel)"
slug=git-finishline-handoff-20260908

find_worktree() {
  git -C "$repository_root" worktree list --porcelain | python3 -c '
import sys
for block in sys.stdin.read().split("\n\n"):
    rows = block.splitlines()
    if "branch refs/heads/work/git-finishline-handoff-20260908" in rows:
        print(next(row[9:] for row in rows if row.startswith("worktree ")))
        break
'
}

worktree_path="$(find_worktree)"
if [[ -z "$worktree_path" ]]; then
  bash "$repository_root/scripts/start-worktree-session.sh" \
    --conduct --from origin/work/git-finishline-20260908 --runway 4h \
    --prompt-file "$capsule_dir/README.md" limen "$slug"
  worktree_path="$(find_worktree)"
fi
[[ -n "$worktree_path" ]] || { echo 'continuation worktree unavailable' >&2; exit 1; }

# Re-entry verifies the existing capsule; it never rerenders a changed identity.
python3 - "$worktree_path/.limen-workstream" <<'PYTHON'
import json,subprocess,sys
from pathlib import Path
capsule=Path(sys.argv[1]);identity=capsule/"capsule.identity"
data=json.loads(identity.read_text())
command=[sys.executable,str(capsule/"workstream-contract.py"),"verify-identity",
         "--identity",str(identity),"--invocation-sha256",data["invocation_sha256"]]
for name in data["modules"]:
    command.extend(["--module",name+"="+str(capsule/name)])
subprocess.run(command,check=True)
PYTHON

if [[ "${1:-}" == "--prepare-only" ]]; then
  exit 0
fi
exec bash "$worktree_path/.limen-workstream/kickstart.sh"
