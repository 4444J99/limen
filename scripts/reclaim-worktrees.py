#!/usr/bin/env python3
"""reclaim-worktrees.py — the SPRAWL-RECLAIM organ.

The fleet dispatch creates ephemeral per-task worktrees under .limen-worktrees/ and never
reaps them; left alone they accumulate (observed: 91 dirs / 3.4 GB). This organ reaps the
ones that are *provably dead* — and ONLY those:

  • clean working tree (no uncommitted or untracked changes), AND
  • HEAD is reachable from some remote ref (nothing unpushed would be lost), AND
  • idle for >= LIMEN_RECLAIM_MIN_AGE_H hours (so a fleet task mid-run is never touched).

It is LOSS-FREE by construction (those three gates) and FAILS OPEN: any error on one dir is
logged and skipped, never aborting the rest ("never a silent no"). It removes registered
worktrees via `git worktree remove` (never rm) and standalone clones via rmtree. Bounded per
run (LIMEN_RECLAIM_MAX); if it hits the cap it LOGS the remainder rather than silently dropping.

Dry-run by default; pass --apply to execute. Self-throttles to once per
LIMEN_RECLAIM_EVERY_MIN minutes so it is cheap to call every beat.

Env: LIMEN_WORKTREE_ROOT, LIMEN_RECLAIM_MIN_AGE_H (6), LIMEN_RECLAIM_MAX (50),
     LIMEN_RECLAIM_EVERY_MIN (30).
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time
from pathlib import Path

HOME = os.environ.get("HOME", "/Users/4jp")
ROOT = Path(os.environ.get("LIMEN_WORKTREE_ROOT", f"{HOME}/Workspace/.limen-worktrees"))
MIN_AGE_H = float(os.environ.get("LIMEN_RECLAIM_MIN_AGE_H", "6"))
MAX_REMOVE = int(os.environ.get("LIMEN_RECLAIM_MAX", "50"))
EVERY_MIN = float(os.environ.get("LIMEN_RECLAIM_EVERY_MIN", "30"))
LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", f"{HOME}/Workspace/limen"))
LOG = LIMEN_ROOT / "logs" / "reclaim-worktrees.jsonl"
MARKER = LIMEN_ROOT / "logs" / ".reclaim-last"
APPLY = "--apply" in sys.argv
FORCE = "--force" in sys.argv  # ignore the throttle


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


def superproject(cwd) -> str | None:
    wl = git(["worktree", "list", "--porcelain"], cwd).stdout.splitlines()
    if wl and wl[0].startswith("worktree "):
        return wl[0].split(" ", 1)[1]
    return None


def classify(d: Path, now: float):
    """Return (action, reason). action in {remove-worktree, remove-clone, skip}."""
    if git(["rev-parse", "--is-inside-work-tree"], d).returncode != 0:
        return "skip", "not-a-git-dir"
    age_h = (now - d.stat().st_mtime) / 3600.0
    if age_h < MIN_AGE_H:
        return "skip", f"active(<{MIN_AGE_H}h, age={age_h:.1f}h)"
    if git(["status", "--porcelain"], d).stdout.strip():
        return "skip", "dirty"
    head = git(["rev-parse", "HEAD"], d).stdout.strip()
    if not head or not reachable_from_remote(d, head):
        return "skip", "unpushed-commits"
    is_wt = (d / ".git").is_file()  # gitdir-pointer ⇒ registered worktree
    return ("remove-worktree" if is_wt else "remove-clone"), "clean+pushed+idle"


def main():
    if not ROOT.is_dir():
        print(f"reclaim: no worktree root ({ROOT}) — nothing to do")
        return 0
    # self-throttle (skip silently if run recently, unless --force or dry-run inspection)
    if APPLY and not FORCE and MARKER.exists():
        if (time.time() - MARKER.stat().st_mtime) / 60.0 < EVERY_MIN:
            print(f"reclaim: ran < {EVERY_MIN}min ago — skip (set --force to override)")
            return 0
    now = time.time()
    dirs = sorted(p for p in ROOT.iterdir() if p.is_dir())
    removed, skipped, failed, deferred = [], [], [], []
    for d in dirs:
        action, reason = classify(d, now)
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
