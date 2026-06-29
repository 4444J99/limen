#!/usr/bin/env python3
"""reclaim-worktrees.py — the SPRAWL-RECLAIM organ.

The fleet creates ephemeral worktrees in TWO places and reaps neither; left alone they
accumulate (the dispatch root hit 91 dirs / 3.4 GB; the interactive root leaked ~50 GB /
21 worktrees on 2026-06-26). This organ reaps the ones that are *provably dead* — and ONLY
those:

  • clean working tree (no uncommitted or untracked changes), AND
  • HEAD is reachable from some remote ref, or every local patch is equivalent to default, AND
  • HEAD/content is already merged into the remote default branch (the work finished its PR/base lifecycle), AND
  • idle for >= the root's min-age (so a task/session mid-run is never touched).

It scans every known creation site (the historical blind spot — see worktree-lifecycle-blind-spot):
  • LIMEN_WORKTREE_ROOT (~/Workspace/.limen-worktrees) — dispatch throwaway, min-age 6h.
  • LIMEN_ROOT/.claude/worktrees — EnterWorktree / bg-job / interactive cells, min-age 24h.
  • repo-local .worktrees roots discovered under LIMEN_RECLAIM_WORKSPACE_ROOTS.
  • registered git worktrees from LIMEN_RECLAIM_MAIN_REPOS (default: Limen and Portvs).
Set LIMEN_RECLAIM_CLAUDE_WT=0 to disable the interactive sweep.

It is LOSS-FREE by construction (those three gates) and FAILS OPEN: any error on one dir is
logged and skipped, never aborting the rest ("never a silent no"). It NEVER reaps the live
checkout (LIMEN_ROOT) nor the worktree it is itself running from. It removes registered
worktrees via `git worktree remove` (never rm) and standalone clones via rmtree. Bounded per
run (LIMEN_RECLAIM_MAX); if it hits the cap it LOGS the remainder rather than silently dropping.

Dry-run by default; pass --apply to execute. Self-throttles to once per
LIMEN_RECLAIM_EVERY_MIN minutes so it is cheap to call every beat.

Env: LIMEN_WORKTREE_ROOT, LIMEN_RECLAIM_MIN_AGE_H (6), LIMEN_RECLAIM_CLAUDE_WT (1),
     LIMEN_RECLAIM_CLAUDE_AGE_H (24), LIMEN_RECLAIM_REPO_LOCAL_WT, LIMEN_RECLAIM_REPO_LOCAL_AGE_H,
     LIMEN_RECLAIM_REGISTERED_WT, LIMEN_RECLAIM_REGISTERED_AGE_H, LIMEN_RECLAIM_MAIN_REPOS,
     LIMEN_RECLAIM_WORKSPACE_ROOTS, LIMEN_RECLAIM_MAX (50), LIMEN_RECLAIM_EVERY_MIN (30).
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_ROOT / "cli" / "src"))

from limen.worktree_roots import iter_worktree_targets  # noqa: E402

HOME = os.environ.get("HOME", "/Users/4jp")
MAX_REMOVE = int(os.environ.get("LIMEN_RECLAIM_MAX", "50"))
EVERY_MIN = float(os.environ.get("LIMEN_RECLAIM_EVERY_MIN", "30"))
LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", f"{HOME}/Workspace/limen"))
LOG = LIMEN_ROOT / "logs" / "reclaim-worktrees.jsonl"
MARKER = LIMEN_ROOT / "logs" / ".reclaim-last"
APPLY = "--apply" in sys.argv
FORCE = "--force" in sys.argv  # ignore the throttle

# Never reap the live checkout nor the worktree this process is running from (else we yank
# the rug from under an active session). Resolved once; classify() honors it as a HARD skip.
try:
    _SELF_GUARD = {LIMEN_ROOT.resolve()}
    _cwd = Path.cwd().resolve()
    for _p in (_cwd, *_cwd.parents):
        if (_p / ".git").exists():
            _SELF_GUARD.add(_p); break
except Exception:
    _SELF_GUARD = {LIMEN_ROOT}


def git(args, cwd, timeout=30):
    try:
        return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                              text=True, timeout=timeout)
    except Exception as e:  # fail open per-dir
        r = subprocess.CompletedProcess(args, 1, "", str(e))
        return r


def reachable_from_remote(cwd, head) -> bool:
    r = git(["for-each-ref", "--format=%(refname)", "refs/remotes"], cwd)
    if r.returncode != 0:
        return False
    for ref in r.stdout.split():
        if git(["merge-base", "--is-ancestor", head, ref], cwd).returncode == 0:
            return True
    return False


def remote_default_ref(cwd) -> str | None:
    r = git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], cwd)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    for ref in ("origin/main", "origin/master"):
        if git(["show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"], cwd).returncode == 0:
            return ref
    return None


def merged_into_default(cwd, head) -> bool:
    ref = remote_default_ref(cwd)
    if not ref:
        return False
    return git(["merge-base", "--is-ancestor", head, ref], cwd).returncode == 0


def patch_equivalent_to_default(cwd) -> bool:
    ref = remote_default_ref(cwd)
    if not ref:
        return False
    r = git(["cherry", ref, "HEAD"], cwd)
    if r.returncode != 0:
        return False
    lines = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("-") for line in lines)


def superproject(cwd) -> str | None:
    wl = git(["worktree", "list", "--porcelain"], cwd).stdout.splitlines()
    if wl and wl[0].startswith("worktree "):
        return wl[0].split(" ", 1)[1]
    return None


def classify(d: Path, now: float, min_age_h: float):
    """Return (action, reason). action in {remove-worktree, remove-clone, skip}."""
    try:
        if d.resolve() in _SELF_GUARD:
            return "skip", "self/live-checkout"
    except Exception:
        return "skip", "unresolved"
    if git(["rev-parse", "--is-inside-work-tree"], d).returncode != 0:
        return "skip", "not-a-git-dir"
    age_h = (now - d.stat().st_mtime) / 3600.0
    if age_h < min_age_h:
        return "skip", f"active(<{min_age_h:g}h, age={age_h:.1f}h)"
    if git(["status", "--porcelain"], d).stdout.strip():
        return "skip", "dirty"
    head = git(["rev-parse", "HEAD"], d).stdout.strip()
    patch_equivalent = patch_equivalent_to_default(d)
    if not head or (not reachable_from_remote(d, head) and not patch_equivalent):
        return "skip", "unpushed-commits"
    if not (merged_into_default(d, head) or patch_equivalent):
        return "skip", "not-merged-to-default"
    is_wt = (d / ".git").is_file()  # gitdir-pointer ⇒ registered worktree
    return ("remove-worktree" if is_wt else "remove-clone"), "clean+merged+idle"


def main():
    # Every known creation site, each with its own idle gate. Missing roots simply disappear
    # from the target list; discovery must never block the heartbeat.
    targets = iter_worktree_targets(LIMEN_ROOT)
    if not targets:
        print("reclaim: no worktree roots present — nothing to do")
        return 0
    # self-throttle (skip silently if run recently, unless --force or dry-run inspection)
    if APPLY and not FORCE and MARKER.exists():
        if (time.time() - MARKER.stat().st_mtime) / 60.0 < EVERY_MIN:
            print(f"reclaim: ran < {EVERY_MIN}min ago — skip (set --force to override)")
            return 0
    now = time.time()
    dirs = [(target.path, target.min_age_h) for target in targets]
    removed, skipped, failed, deferred = [], [], [], []
    for d, min_age_h in dirs:
        action, reason = classify(d, now, min_age_h)
        if action == "skip":
            skipped.append((d.name, reason)); continue
        if len(removed) >= MAX_REMOVE:
            deferred.append(d.name); continue  # bounded — but NOT silent (logged below)
        if not APPLY:
            removed.append((d.name, f"would-{action}")); continue
        try:
            if action == "remove-worktree":
                sp = superproject(d)
                base = sp if sp and Path(sp).resolve() != d.resolve() else d
                r = git(["worktree", "remove", "--force", str(d)], base)
                if r.returncode != 0:
                    failed.append((d.name, r.stderr.strip()[:120])); continue
            else:
                shutil.rmtree(d)
            removed.append((d.name, action))
        except Exception as e:  # fail open
            failed.append((d.name, str(e)[:120]))

    if APPLY:
        try:
            MARKER.parent.mkdir(parents=True, exist_ok=True)
            MARKER.write_text(str(now))
            with LOG.open("a") as fh:
                fh.write(json.dumps({
                    "ts": now, "apply": APPLY, "scanned": len(dirs),
                    "removed": [n for n, _ in removed], "skipped": dict(skipped),
                    "failed": dict(failed), "deferred_over_cap": deferred,
                }) + "\n")
        except Exception:
            pass  # logging must never break the beat

    mode = "APPLY" if APPLY else "dry-run"
    print(f"reclaim [{mode}]: {len(removed)} reclaimed, {len(skipped)} kept-safe, "
          f"{len(failed)} failed, {len(deferred)} deferred-over-cap (of {len(dirs)})")
    for n, why in skipped:
        print(f"  keep {why:24} {n}")
    for n, why in removed:
        print(f"  {'reclaimed' if APPLY else 'would'}: {n}")
    if deferred:
        print(f"  NOTE: {len(deferred)} dirs over the {MAX_REMOVE}-cap this run, next run takes them: "
              + ", ".join(deferred[:5]) + ("…" if len(deferred) > 5 else ""))
    for n, why in failed:
        print(f"  FAIL {n}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
