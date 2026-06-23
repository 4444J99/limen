#!/usr/bin/env bash
# clone-maintenance.sh — lifecycle hygiene for limen's local working-set clones (rung 4).
#
# DATA-SAFE: `git worktree prune` only drops refs to already-gone worktrees; `git gc --auto`
# only collects UNREACHABLE objects — neither loses commits or touches the working tree.
# RETIREMENT is DRY-RUN only here: a clone with no active limen task is re-cloneable from
# GitHub, but actual removal stays gated on the user (printed as a candidate, never deleted).
#
# NEVER touches: the conductor + the user's primary repos (CORE), or the live .home-cartridge
# co-tenant, or the .limen-worktrees throwaway root.
set -uo pipefail
WS="${LIMEN_WORKDIR:-$HOME/Workspace}"
ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
export PYTHONPATH="$ROOT/cli/src"
CORE="limen session-meta sovereign-systems--elevate-align portfolio portvs universal-mail--automation"

echo "── clone hygiene: worktree prune + gc --auto (data-safe) ──"
n=0
while IFS= read -r g; do
  d="$(dirname "$g")"
  case "$d" in *.limen-worktrees*|*.home-cartridge*) continue;; esac
  git -C "$d" worktree prune 2>/dev/null || true
  git -C "$d" gc --auto --quiet 2>/dev/null || true
  n=$((n+1))
done < <(find "$WS" -maxdepth 3 -name .git -type d 2>/dev/null)
echo "  hygiene pass over $n repo(s)."

echo "── reapable clones (0 active limen tasks; DRY-RUN — removal gated) ──"
python3 - "$ROOT/tasks.yaml" "$WS" "$CORE" <<'PY'
import yaml, os, sys, subprocess, glob
tasks_path, ws, core = sys.argv[1], sys.argv[2], set(sys.argv[3].split())
d = yaml.safe_load(open(tasks_path))
active = {t["repo"] for t in d.get("tasks", [])
          if t.get("status") in ("open", "dispatched", "in_progress") and t.get("repo")}
cands = []
for g in glob.glob(os.path.join(ws, "**", ".git"), recursive=True):
    repo = os.path.dirname(g)
    if ".limen-worktrees" in repo or ".home-cartridge" in repo:
        continue
    name = os.path.basename(repo)
    if name in core:
        continue
    try:
        url = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"],
                             capture_output=True, text=True).stdout.strip()
    except Exception:
        url = ""
    slug = url.rstrip("/")
    if slug.endswith(".git"):
        slug = slug[:-4]
    slug = "/".join(slug.replace(":", "/").split("/")[-2:]) if slug else name
    if slug not in active:
        cands.append((slug, repo))
if cands:
    for slug, p in cands:
        print(f"    reapable: {slug}")
    print(f"  {len(cands)} clone(s) have no active task — re-cloneable; remove only with user OK.")
else:
    print("  none — every working-set clone still has active tasks.")
PY
