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

# ── node_modules reclaim (REGENERABLE build cache, not data; reversible via reinstall) ──
# The single biggest creep source the fleet leaves behind (per-dispatch worktree builds).
# DATA-SAFE by construction: node_modules is always reproducible from a lockfile, so this is
# cache reclamation, NOT the never-auto-delete-DATA rule. Guarded HARD anyway: never CORE,
# never the live $LIMEN_ROOT, never a dirty tree, never a repo with an active limen task, and
# never one touched within LIMEN_NM_IDLE_DAYS — EXCEPT a throwaway .limen-worktrees/gen-* whose
# work is already a PR (age-exempt, but still clean + no-active-task gated). LIMEN_RECLAIM_DRYRUN=1
# reports without removing. Every reclaim is logged (no silent truncation).
echo "── node_modules reclaim (regenerable; core/live/dirty/active/fresh all skipped) ──"
python3 - "$ROOT/tasks.yaml" "$WS" "$CORE" "$ROOT" "${LIMEN_NM_IDLE_DAYS:-2}" "${LIMEN_RECLAIM_DRYRUN:-0}" <<'PY'
import glob, os, shutil, subprocess, sys, time
import yaml
tasks_path, ws, core, live_root, idle_days, dry = sys.argv[1:7]
core = set(core.split()); idle_days = int(idle_days); dry = (dry == "1")
d = yaml.safe_load(open(tasks_path)) or {}
active = {t.get("repo") for t in d.get("tasks", [])
          if t.get("status") in ("open", "dispatched", "in_progress") and t.get("repo")}
now = time.time(); freed = 0; n = 0; kept = 0
for nm in glob.glob(os.path.join(ws, "**", "node_modules"), recursive=True):
    if "/node_modules/" in nm:            # only a repo's TOP-level node_modules, not nested
        continue
    if "/.claude/worktrees/" in nm or "/.home-cartridge/" in nm:
        continue   # HARD: interactive Claude sessions live in .claude/worktrees — never touch them

    repo = os.path.dirname(nm)
    try:
        top = subprocess.run(["git", "-C", repo, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True).stdout.strip() or repo
    except Exception:
        top = repo
    name = os.path.basename(top)
    is_gen = ".limen-worktrees" in repo and "/gen-" in repo + "/"
    reason = None
    if top == live_root:
        reason = "live-root"
    elif name in core:
        reason = "core"
    else:
        # TRACKED-only dirty: reclaiming node_modules never touches source, so the risk we
        # guard is active HAND-DEV (uncommitted edits to tracked files), NOT untracked files
        # (node_modules itself shows untracked → would falsely protect everything).
        dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True).stdout.strip()
        if dirty:
            reason = "tracked-edits"
        else:
            url = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"],
                                 capture_output=True, text=True).stdout.strip()
            slug = url[:-4] if url.endswith(".git") else url
            slug = "/".join(slug.replace(":", "/").split("/")[-2:]) if slug else name
            if slug in active:
                reason = "active-task"
            elif not is_gen and (now - os.path.getmtime(nm)) / 86400 < idle_days:
                reason = "fresh"
    if reason:
        kept += 1
        continue
    sz = 0
    for r, _, fs in os.walk(nm):
        for f in fs:
            try:
                sz += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    freed += sz; n += 1
    print(f"  {'WOULD reclaim' if dry else 'reclaimed'}: {nm}  ({sz/1e9:.2f} GB)")
    if not dry:
        shutil.rmtree(nm, ignore_errors=True)
print(f"  {'(dry-run) ' if dry else ''}node_modules: {n} dir(s) "
      f"{'would free' if dry else 'freed'} {freed/1e9:.2f} GB; {kept} kept (core/live/dirty/active/fresh).")
PY

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
