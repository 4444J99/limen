#!/usr/bin/env python3
"""Classify per-store custody state from LOCAL objects vs FRESHLY ADVERTISED remote refs."""
import json, os, subprocess
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
S = json.load(open(os.path.join(BASE, "stores.json")))
P = {r["commondir"]: r for r in json.load(open(os.path.join(BASE, "remote_probe.json")))}
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="")

def g(args, cwd, t=40):
    try:
        p = subprocess.run(["git", "--git-dir", cwd] + args if cwd.endswith("/.git") else ["git", "-C", cwd] + args,
                           env=ENV, capture_output=True, text=True, timeout=t)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return -1, "", str(e)

def classify(s):
    cdir = s["commondir"]
    pr = P.get(cdir, {})
    adv = pr.get("advertised_refs") or {}
    out = {"commondir": cdir, "access": pr.get("access"), "url": pr.get("url"),
           "github_identity": pr.get("github_identity"),
           "n_checkouts": s["n_checkouts"], "checkouts": s["checkouts"]}

    # which local heads have no advertised counterpart anywhere on the remote
    heads = s["local_branches"]
    adv_heads = {k: v for k, v in adv.items() if k.startswith("refs/heads/")}
    unsynced, synced = [], []
    for b in heads:
        name = b["ref"].replace("refs/heads/", "")
        ar = adv_heads.get("refs/heads/" + name)
        if ar is None:
            unsynced.append({"branch": name, "sha": b["sha"], "committed": b["committed"],
                             "subject": b["subject"], "upstream": b["upstream"],
                             "reason": "no advertised head with this name"})
        elif ar == b["sha"]:
            synced.append({"branch": name, "sha": b["sha"]})
        else:
            unsynced.append({"branch": name, "sha": b["sha"], "remote_sha": ar,
                             "committed": b["committed"], "subject": b["subject"],
                             "upstream": b["upstream"],
                             "reason": "local tip != advertised tip (divergence)"})
    out["n_branches"] = len(heads)
    out["exact_heads"] = len(synced)
    out["unsynced_heads"] = unsynced
    out["n_unsynced"] = len(unsynced)

    # detached HEADs are never advertised by name
    if s["head"]["detached"] and s["head"].get("sha"):
        out["detached_head"] = {"sha": s["head"]["sha"],
                                "on_remote_anywhere": s["head"]["sha"] in adv.values()}

    # unique local history: objects reachable from local-only tips that no advertised
    # ref in this store contains, and no other Workspace store advertises/reaches.
    unique = []
    for u in unsynced:
        sha = u["sha"]
        contained = False
        for k, v in adv.items():
            rc, _, _ = g(["merge-base", "--is-ancestor", sha, v], cdir)
            if rc == 0:
                contained = True
                break
        u["contained_in_advertised_history"] = contained
        u["unique_local_history"] = not contained
        if not contained:
            unique.append(u["branch"])
    out["unique_local_branches"] = unique
    out["n_unique_local"] = len(unique)

    # tags not on remote
    rc, tout, _ = g(["for-each-ref", "--format=%(refname:strip=2)%09%(objectname)", "refs/tags/"], cdir)
    local_tags = {}
    for l in tout.split("\n"):
        if "\t" in l:
            n, sha = l.split("\t")
            local_tags[n] = sha
    out["n_local_tags"] = len(local_tags)
    out["tags_not_advertised"] = sorted(n for n in local_tags
                                         if f"refs/tags/{n}" not in adv)

    # classification
    if pr.get("access") in ("NO_REMOTE",):
        out["state"] = "NO_AUTHORIZED_REMOTE"
    elif pr.get("access") == "LOCAL_PATH_REMOTE":
        out["state"] = "NO_AUTHORIZED_REMOTE"  # local-path is not custody proof
        out["state_detail"] = "local-path remote only"
    elif pr.get("access") != "OK":
        out["state"] = "UNMEASURED_ACCESS"
    elif out["n_unique_local"] > 0:
        out["state"] = "UNIQUE_LOCAL_HISTORY"
    elif out["n_unsynced"] > 0:
        out["state"] = "RECOVERABLE_UNSYNCHRONIZED"
    elif out["tags_not_advertised"] or out.get("detached_head", {}).get("sha"):
        out["state"] = "EXACTLY_SYNCHRONIZED_WITH_LOCAL_EXTRAS"
    else:
        out["state"] = "EXACTLY_SYNCHRONIZED"
    return out

with ThreadPoolExecutor(max_workers=6) as ex:
    R = list(ex.map(classify, S))
json.dump(R, open(os.path.join(BASE, "parity.json"), "w"), indent=1)
from collections import Counter
print(json.dumps(dict(Counter(r["state"] for r in R)), indent=1))
print("checkouts covered:", sum(r["n_checkouts"] for r in R))
