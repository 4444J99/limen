#!/usr/bin/env python3
"""Read-only git census. No fetch/stage/commit/stash/switch/prune/delete."""
import os, subprocess, json, sys, stat

ROOT = "/Users/4jp/Workspace"
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="/usr/bin/true",
           GIT_CONFIG_PARAMETERS="'core.fsmonitor=false' 'gc.auto=0'")
SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".mypy_cache", ".ruff_cache",
             ".cache", "Library", ".Trash", "site-packages", ".pnpm-store"}

def run(args, cwd=None, timeout=25):
    try:
        p = subprocess.run(["git", "-c", "core.fsmonitor=false"] + args, cwd=cwd, env=ENV,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except Exception as e:
        return -1, "", f"{type(e).__name__}: {e}"

def is_dir(p):
    try:
        return stat.S_ISDIR(os.lstat(p).st_mode)
    except OSError:
        return False

def is_file(p):
    try:
        return stat.S_ISREG(os.lstat(p).st_mode)
    except OSError:
        return False

# --- walk: find .git markers, and bare store candidates ------------------------
markers = []           # (checkout_path, git_marker_path, marker_kind)
bare_candidates = []
unreadable = []
n_scanned = 0

for dirpath, dirnames, filenames in os.walk(ROOT, topdown=True, followlinks=False):
    n_scanned += 1
    has_git_file = ".git" in filenames
    has_git_dir = ".git" in dirnames
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d != ".git"]
    if has_git_dir:
        markers.append((dirpath, os.path.join(dirpath, ".git"), "dir"))
    if has_git_file:
        markers.append((dirpath, os.path.join(dirpath, ".git"), "file"))
    if not has_git_dir and not has_git_file:
        # bare store heuristic: HEAD + objects + refs (skip .git which is pruned above)
        try:
            names = set(os.listdir(dirpath))
        except OSError as e:
            unreadable.append({"path": dirpath, "error": f"{type(e).__name__}: {e}"})
            continue
        if {"HEAD", "objects", "refs"} <= names:
            bare_candidates.append(dirpath)

# --- second pass: symlinked checkout roots (os.walk does not follow) ------------
symlink_roots = []
for dirpath, dirnames, filenames in os.walk(ROOT, topdown=True, followlinks=False):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d != ".git"]
    for d in list(dirnames):
        p = os.path.join(dirpath, d)
        if os.path.islink(p):
            t = os.path.realpath(p)
            if os.path.exists(os.path.join(t, ".git")):
                symlink_roots.append({"link": p, "target": t})
                markers.append((t, os.path.join(t, ".git"), "dir-via-symlink"))
            dirnames.remove(d)

# --- resolve each checkout to its common git dir -------------------------------
records = []
commondirs = {}   # realpath(commondir) -> [checkout paths]

for checkout, gp, kind in markers:
    rc, out, err = run(["rev-parse", "--absolute-git-dir"], cwd=checkout)
    if rc != 0 or not out:
        records.append({"checkout": checkout, "marker": gp, "marker_kind": kind,
                        "resolve": "FAILED", "error": err[:200] or "no-output"})
        continue
    gitdir = out
    rc2, cdir, _ = run(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=checkout)
    if rc2 != 0 or not cdir:
        records.append({"checkout": checkout, "gitdir": gitdir, "marker_kind": kind,
                        "resolve": "COMMON-FAILED", "error": "common-dir-unreadable"})
        continue
    cdir = os.path.realpath(cdir)
    rc3, super_ok, _ = run(["rev-parse", "--is-bare-repository"], cwd=checkout)
    records.append({"checkout": checkout, "gitdir": os.path.realpath(gitdir), "commondir": cdir,
                    "marker_kind": kind, "bare": super_ok == "true",
                    "linked_worktree": os.path.realpath(gitdir) != cdir,
                    "resolve": "OK"})
    commondirs.setdefault(cdir, []).append(checkout)

json.dump({"records": records, "n_commondirs": len(commondirs),
           "commondirs": commondirs, "n_bare_candidates": len(bare_candidates),
           "bare_candidates_sample": sorted(bare_candidates)[:40],
           "unreadable": unreadable[:60], "n_unreadable": len(unreadable),
           "symlink_roots": symlink_roots,
           "dirs_scanned": n_scanned},
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "census.json"), "w"), indent=1)

ok = [r for r in records if r.get("resolve") == "OK"]
failed = [r for r in records if r.get("resolve") != "OK"]
print(json.dumps({
    "checkouts_total": len(records),
    "checkouts_resolved": len(ok),
    "checkouts_unresolved": len(failed),
    "common_dirs": len(commondirs),
    "linked_worktrees": len([r for r in ok if r.get("linked_worktree")]),
    "bare_marker_candidates": len(bare_candidates),
    "unreadable_dirs": len(unreadable),
    "symlinked_checkout_roots": len(symlink_roots),
    "dirs_scanned": n_scanned,
}, indent=1))
print("--- unresolved markers (sample) ---")
for r in failed[:25]:
    print(f'  {r["checkout"]}  [{r["resolve"]}] {r.get("error","")[:90]}')
print("--- bare candidate roots (top 15 by prefix) ---")
from collections import Counter
c = Counter(os.path.relpath(b, ROOT).split(os.sep)[0] for b in bare_candidates)
for k, v in c.most_common(15):
    print(f"  {k}: {v}")
