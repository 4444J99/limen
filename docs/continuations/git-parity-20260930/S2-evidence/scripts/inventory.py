#!/usr/bin/env python3
"""Per-common-dir + per-checkout read-only inventory. No mutation, no fetch."""
import os, subprocess, json

BASE = os.path.dirname(os.path.abspath(__file__))
C = json.load(open(os.path.join(BASE, "census.json")))
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
           GIT_ASKPASS="/usr/bin/true")

def run(args, cwd, timeout=30):
    try:
        p = subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "gc.auto=0"] + args,
                           cwd=cwd, env=ENV, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return -1, "", f"{type(e).__name__}: {e}"

def lines(s):
    return [l for l in (s or "").split("\n") if l.strip()]

stores = []
for cdir, checkouts in sorted(C["commondirs"].items()):
    s = {"commondir": cdir, "checkouts": sorted(checkouts), "n_checkouts": len(checkouts)}

    rc, out, _ = run(["worktree", "list", "--porcelain"], cdir)
    reg = []
    for blk in (out or "").strip().split("\n\n"):
        d = {}
        for l in lines(blk):
            k, _, v = l.partition(" ")
            d[k] = v
        if d.get("worktree"):
            reg.append({"path": d["worktree"], "head": d.get("HEAD"),
                        "branch": d.get("branch", "").replace("refs/heads/", "") or None,
                        "detached": d.get("detached") == "true",
                        "bare": d.get("bare") == "true",
                        "prunable": d.get("prunable") or None,
                        "locked": d.get("locked") or None})
    s["registered_worktrees"] = reg
    s["n_registered_worktrees"] = len(reg)

    rc, out, _ = run(["remote", "-v"], cdir)
    remotes = {}
    for l in lines(out):
        p = l.split()
        if len(p) < 3:
            continue
        nm, url, direction = p[0], p[1], p[2]
        r = remotes.setdefault(nm, {"name": nm, "fetch_url": None, "push_url": None, "urls": []})
        if url not in r["urls"]:
            r["urls"].append(url)
        if direction == "(fetch)":
            r["fetch_url"] = url
        else:
            r["push_url"] = url
    for r in remotes.values():
        fetch = r["fetch_url"] or ""
        r["push_differs"] = (r["push_url"] or fetch) != fetch
        r["is_local_path"] = fetch.startswith(("/", "file://", ".", "~"))
        r["github_identity"] = None
        r["non_github_urls"] = []
        for u in r["urls"]:
            if "github.com" in u:
                q = u.split("github.com", 1)[1].strip("/")
                q = q[:-4] if q.endswith(".git") else q
                ps = [x for x in q.split("/") if x]
                if len(ps) >= 2:
                    r["github_identity"] = f"{ps[0]}/{ps[1]}"
            elif not r["is_local_path"]:
                r["non_github_urls"].append(u)
    s["remotes"] = remotes
    s["n_remotes"] = len(remotes)

    rc, out, _ = run(["symbolic-ref", "--quiet", "HEAD"], cdir)
    if rc == 0 and out.strip():
        s["head"] = {"detached": False, "branch": out.strip().replace("refs/heads/", "")}
    else:
        rc2, out2, _ = run(["rev-parse", "HEAD"], cdir)
        s["head"] = {"detached": True, "sha": out2.strip() if rc2 == 0 else None}

    rc, out, _ = run(["for-each-ref", "--format=%(refname)%09%(objectname)%09%(upstream)%09%(upstream:track)%09%(committerdate:iso8601)%09%(contents:subject)", "refs/heads/"], cdir)
    br = []
    for l in lines(out):
        f = (l.split("\t") + [""] * 6)[:6]
        br.append({"ref": f[0], "sha": f[1], "upstream": f[2] or None,
                   "track_raw": f[3] or None, "committed": f[4] or None,
                   "subject": (f[5] or "")[:90]})
    s["local_branches"] = br
    s["n_local_branches"] = len(br)

    rc, out, _ = run(["for-each-ref", "--format=%(refname)%09%(objectname)", "refs/remotes/"], cdir)
    s["cached_tracking_refs"] = [dict(zip(("ref", "sha"), l.split("\t"))) for l in lines(out)]

    rc, out, _ = run(["stash", "list", "--format=%H%x09%gd%x09%ci%x09%s"], cdir)
    s["stashes"] = [dict(zip(("sha", "ref", "date", "subject"), l.split("\t"))) for l in lines(out)]
    s["n_stashes"] = len(s["stashes"])

    rc, out, _ = run(["for-each-ref", "--format=%(refname)", "refs/tags/"], cdir)
    s["n_tags"] = len(lines(out))

    alts = os.path.join(cdir, "objects", "info", "alternates")
    s["alternates"] = open(alts).read().split() if os.path.exists(alts) else []
    s["has_alternates"] = bool(s["alternates"])

    gm = os.path.join(cdir, ".gitmodules")
    s["n_submodules_declared"] = 0
    if os.path.exists(gm):
        s["n_submodules_declared"] = sum(
            1 for l in lines(open(gm).read()) if l.strip().startswith("path"))
    moddir = os.path.join(cdir, "modules")
    s["submodule_gitdirs"] = sorted(os.listdir(moddir)) if os.path.isdir(moddir) else []

    s["lfs_object_files"] = 0
    s["lfs_object_bytes"] = 0
    lfsobj = os.path.join(cdir, "lfs", "objects")
    if os.path.isdir(lfsobj):
        for root, dn, fn in os.walk(lfsobj):
            for f in fn:
                fp = os.path.join(root, f)
                s["lfs_object_files"] += 1
                try:
                    s["lfs_object_bytes"] += os.path.getsize(fp)
                except OSError:
                    pass

    rc, out, _ = run(["count-objects", "-vH"], cdir)
    s["count_objects"] = {l.split(":")[0].strip(): l.split(":", 1)[1].strip()
                          for l in lines(out) if ":" in l}

    # per-checkout dirty state (tracked only; untracked counted cheaply)
    ck = []
    for path in sorted(checkouts):
        rc, so, se = run(["status", "--porcelain", "-uno"], path, timeout=40)
        if rc != 0:
            ck.append({"path": path, "status": "ERROR", "err": se[:120]})
            continue
        rec = {"path": path, "tracked_changes": len(lines(so)), "status_rc": rc,
               "staged": sum(1 for l in lines(so) if not l.startswith(" "))}
        rc2, uo, _ = run(["ls-files", "--others", "--exclude-standard"], path, timeout=40)
        rec["untracked"] = len(lines(uo))
        rc3, so2, _ = run(["status", "--porcelain", "--untracked-files=no"], path, timeout=40)
        rec["porcelain_rc"] = rc3
        ck.append(rec)
    s["checkout_status"] = ck

    stores.append(s)

json.dump(stores, open(os.path.join(BASE, "stores.json"), "w"), indent=1)
print(json.dumps({
    "stores": len(stores),
    "checkouts": sum(s["n_checkouts"] for s in stores),
    "registered_worktrees": sum(s["n_registered_worktrees"] for s in stores),
    "no_remote": sum(1 for s in stores if s["n_remotes"] == 0),
    "local_path_remote": sum(1 for s in stores if any(r["is_local_path"] for r in s["remotes"].values())),
    "github_identity": sum(1 for s in stores if any(r["github_identity"] for r in s["remotes"].values())),
    "stashes": sum(s["n_stashes"] for s in stores),
    "detached_head": sum(1 for s in stores if s["head"]["detached"]),
    "alternates": sum(1 for s in stores if s["has_alternates"]),
    "submodule_gitdirs": sum(len(s["submodule_gitdirs"]) for s in stores),
    "lfs_files": sum(s["lfs_object_files"] for s in stores),
    "lfs_bytes": sum(s["lfs_object_bytes"] for s in stores),
    "dirty_checkouts": sum(1 for s in stores for c in s["checkout_status"] if c.get("tracked_changes")),
    "untracked_total": sum(c.get("untracked", 0) for s in stores for c in s["checkout_status"]),
    "prunable_worktrees": sum(1 for s in stores for w in s["registered_worktrees"] if w.get("prunable")),
    "worktrees_outside_workspace": sum(
        1 for s in stores for w in s["registered_worktrees"]
        if not w["path"].startswith("/Users/4jp/Workspace")),
}, indent=1))
