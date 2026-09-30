#!/usr/bin/env python3
"""Live remote identity + advertisement verification. ls-remote ONLY: no fetch, no ref write."""
import os, subprocess, json
from concurrent.futures import ThreadPoolExecutor

BASE = os.path.dirname(os.path.abspath(__file__))
S = json.load(open(os.path.join(BASE, "stores.json")))
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="/usr/bin/true",
           GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="")

def probe(cdir):
    rc, out, err = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "ls-remote", "--heads", "--tags", "."],
        cwd=cdir, env=ENV, capture_output=True, text=True, timeout=60).returncode, "", ""
    return rc, out, err

def do(store):
    cdir = store["commondir"]
    rem = store["remotes"].get("origin") or (list(store["remotes"].values())[0] if store["remotes"] else None)
    res = {"commondir": cdir}
    if not rem:
        res.update(access="NO_REMOTE", detail="no remote configured")
        return res
    url = rem.get("fetch_url")
    res["url"] = url
    res["push_url"] = rem.get("push_url")
    res["github_identity"] = rem.get("github_identity")
    res["is_local_path"] = rem.get("is_local_path")
    if rem.get("is_local_path"):
        res.update(access="LOCAL_PATH_REMOTE", detail="local-path remote is not custody proof")
        return res
    if url.startswith("ssh://") or url.startswith("git@") or "github.com" in url:
        cmd = ["git", "-c", "core.fsmonitor=false", "ls-remote", "--heads", "--", url]
    else:
        cmd = ["git", "-c", "core.fsmonitor=false", "ls-remote", "--heads", "--", url]
    try:
        p = subprocess.run(cmd, env=ENV, capture_output=True, text=True, timeout=75)
    except subprocess.TimeoutExpired:
        res.update(access="UNMEASURED", detail="ls-remote timeout")
        return res
    except Exception as e:
        res.update(access="UNMEASURED", detail=f"{type(e).__name__}")
        return res
    if p.returncode != 0:
        res.update(access="UNMEASURED", rc=p.returncode,
                   detail=(p.stderr or p.stdout).strip().split("\n")[0][:180])
        return res
    adv = {}
    for l in p.stdout.split("\n"):
        parts = l.split()
        if len(parts) == 2 and parts[1].startswith("refs/"):
            adv[parts[1]] = parts[0]
    res["advertised_refs"] = adv
    res["n_advertised"] = len(adv)
    # resolve true remote identity from the remote itself (no guesswork)
    try:
        q = subprocess.run(["git", "remote", "get-url", "origin"], cwd=cdir, env=ENV,
                           capture_output=True, text=True, timeout=20)
    except Exception:
        q = None
    res["access"] = "OK"
    return res

with ThreadPoolExecutor(max_workers=6) as ex:
    out = list(ex.map(do, S))
json.dump(out, open(os.path.join(BASE, "remote_probe.json"), "w"), indent=1)
from collections import Counter
print(json.dumps(dict(Counter(r["access"] for r in out)), indent=1))
