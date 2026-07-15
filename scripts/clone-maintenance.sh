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

# ── DISK PRESSURE — the reclaim intensity tracks genuine low free space, not df% alone.
# On APFS, df% counts purgeable-but-reclaimable space as used, so a high percentage can still have
# enough raw free GiB. Keep percent for display; make pressure decisions from the absolute floor.
# Under pressure we (a) waive the node_modules idle window and (b) capture-then-reap in this same run.
disk_pct() { df -P "$1" 2>/dev/null | awk 'NR==2 {gsub("%","",$5); print $5+0}'; }
disk_free_gib() { df -Pk "$1" 2>/dev/null | awk 'NR==2 {print int($4/1048576)}'; }
HIGH="${LIMEN_DISK_HIGH_WATER:-85}"
FREE_FLOOR="${LIMEN_DISK_FREE_FLOOR_GIB:-15}"
PCT="$(disk_pct "$WS")"; [ -n "$PCT" ] || PCT=0
FREE_GIB="$(disk_free_gib "$WS")"; [ -n "$FREE_GIB" ] || FREE_GIB=999999
PRESSURE=0; [ "$FREE_GIB" -le "$FREE_FLOOR" ] 2>/dev/null && PRESSURE=1
echo "── clone-maintenance: disk ${PCT}% used, ${FREE_GIB}GiB free (floor ${FREE_FLOOR}GiB, high-water ${HIGH}% info) → pressure=$([ "$PRESSURE" = 1 ] && echo ON || echo off) ──"

# ── PRUNE GUARD (prune-race prevention). `git worktree prune` reaps the admin gitdir of any
# worktree whose checkout dir looks GONE — but a worktree on an UNMOUNTED external volume (Scratch)
# looks gone though it isn't, and pruning it ORPHANS the checkout on remount (the not-a-git-dir
# debris that tripled worktree debt on 2026-07-15). Skip prune whenever the configured worktree
# volume is offline; deferring prune is data-safe (it only cleans stale refs, never touches data).
prune_safe=1
wr="$(PYTHONPATH="$ROOT/cli/src" python3 -c 'from limen.worktree_roots import effective_worktree_root as e; print(e())' 2>/dev/null || true)"
case "$wr" in
  /Volumes/*)
    vol="/$(printf '%s' "$wr" | cut -d/ -f2-3)"   # /Volumes/<Name>
    { [ -d "$vol" ] && [ -w "$vol" ]; } || prune_safe=0 ;;
esac
[ "$prune_safe" = 1 ] || echo "  prune GUARD: worktree volume '$wr' offline — SKIPPING 'git worktree prune' this pass (prevents orphaning)."

echo "── clone hygiene: worktree prune + gc --auto (data-safe) ──"
n=0
while IFS= read -r g; do
  d="$(dirname "$g")"
  case "$d" in *.limen-worktrees*|*.home-cartridge*) continue;; esac
  [ "$prune_safe" = 1 ] && { git -C "$d" worktree prune 2>/dev/null || true; }
  git -C "$d" gc --auto --quiet 2>/dev/null || true
  n=$((n+1))
done < <(find "$WS" -maxdepth 3 -name .git -type d 2>/dev/null)
echo "  hygiene pass over $n repo(s)$([ "$prune_safe" = 1 ] || echo ' (prune skipped — worktree volume offline)')."

# ── node_modules census (REGENERABLE build cache, not data; reversible via reinstall) ──
# The single biggest creep source the fleet leaves behind (per-dispatch worktree builds).
# Even regenerable cache removal now needs a separate archive/redaction acceptance surface, so this
# organ only reports candidates. Guarded HARD anyway: never CORE, never the live $LIMEN_ROOT, never
# a dirty tree, never a repo with an active limen task, and never one touched within
# LIMEN_NM_IDLE_DAYS — EXCEPT a .limen-worktrees/gen-* root whose work is already a PR
# (age-exempt, but still clean + no-active-task gated).
NM_IDLE="${LIMEN_NM_IDLE_DAYS:-2}"; [ "$PRESSURE" = 1 ] && NM_IDLE=0
echo "── node_modules census (regenerable; core/live/dirty/active/fresh skipped; idle=${NM_IDLE}d) ──"
python3 - "$ROOT/tasks.yaml" "$WS" "$CORE" "$ROOT" "$NM_IDLE" <<'PY'
import glob, os, subprocess, sys, time
import yaml
tasks_path, ws, core, live_root, idle_days = sys.argv[1:6]
core = set(core.split()); idle_days = int(idle_days)
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
    print(f"  WOULD reclaim: {nm}  ({sz/1e9:.2f} GB)")
print(f"  (dry-run) node_modules: {n} dir(s) would free {freed/1e9:.2f} GB; "
      f"{kept} kept (core/live/dirty/active/fresh); physical cache removal requires acceptance.")
PY

# ── clone reap — the LAST step of the developer lifecycle (clone→work→push→accepted reclaim).
# A pure pushed mirror is a disposable cache of GitHub, but physical local removal still requires
# archive/redaction acceptance. reap-clones.py enforces the loss-free gate + acceptance ledger and is
# unit-proven by cli/tests/test_reap_clones.py. Escape hatch: LIMEN_CLONE_REAP_APPLY=0 → dry-run.
# Under pressure, CAPTURE first (push every repo's work to origin, recursively) so the dirty/unpushed
# clones become pure mirrors this cycle instead of waiting for the every-48 backup beat.
if [ "$PRESSURE" = 1 ] && [ -x "$ROOT/scripts/capture.sh" ]; then
  echo "── pressure: capture (push work off disk) before reap ──"
  LIMEN_WORKSPACE="$WS" bash "$ROOT/scripts/capture.sh" 2>&1 | tail -2 || true
fi
reap_args=(); [ "${LIMEN_CLONE_REAP_APPLY:-1}" = "1" ] && reap_args+=(--apply)
LIMEN_WORKSPACE="$WS" python3 "$ROOT/scripts/reap-clones.py" "${reap_args[@]}" 2>&1 | tail -6 || true

# ── branch reap — the REF sibling of the clone/worktree reapers. Local branch refs can pile up after
# merges. reap-branches.py deletes ONLY accepted, provably-landed branches (tip is an ancestor of
# main, OR the PR is MERGED and the tip is not advanced past mergedAt). Unfinished branches are KEPT
# and surfaced to docs/branch-hygiene.md. Unit-proven by cli/tests/test_reap_branches.py. Escape:
# LIMEN_BRANCH_REAP_APPLY=0.
breap_args=(); [ "${LIMEN_BRANCH_REAP_APPLY:-1}" = "1" ] && breap_args+=(--apply)
python3 "$ROOT/scripts/reap-branches.py" "${breap_args[@]}" 2>&1 | tail -4 || true
