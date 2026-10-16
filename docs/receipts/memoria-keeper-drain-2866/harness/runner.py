#!/usr/bin/env python3
"""Pinned reproduction harness for issue #2866.

Runs the UNMODIFIED entry point at pinned revision 24da5bffe inside a disposable
sandbox with every writable destination redirected. Production code is never
edited. No live credentials are inherited; no remote keeper is contacted.

Evidence captured per case:
  - filesystem inventory before/after (path, type, size, mode, mtime_ns, sha256)
  - delta (added / removed / changed), creation and overwrite recorded separately
  - write-ATTEMPT log via a PEP 578 audit hook (sitecustomize.py), which observes
    rather than replaces the application writer
"""

import hashlib
import json
import os
import shutil
import subprocess
import time

HARNESS = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HARNESS)
SANDBOX = os.path.join(BASE, "sandbox")
EVIDENCE = os.path.join(BASE, "evidence")
WT = "/Users/4jp/Workspace/limen/.worktrees/memoria-repro-2866"
ENTRY = os.path.join(WT, "scripts", "tabularius-organ.py")
PY = "/Users/4jp/.local/share/limen/runtimes/b7a61c0bfb87926518f4074af446bed49b07ab8d/venv/bin/python"
REV = "24da5bffeefb855f1968e0c830c1ca5445a291cf"

TICKET = {
    "id": "synthetic-repro-ticket",
    "slug": "repro",
    "title": "synthetic ticket for #2866 reproduction",
    "body": "synthetic; never drained against live state",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(root):
    out = {}
    if not os.path.exists(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(dirnames) + sorted(filenames):
            p = os.path.join(dirpath, name)
            rel = os.path.relpath(p, root)
            st = os.lstat(p)
            if os.path.islink(p):
                kind = "link"
            elif os.path.isdir(p):
                kind = "dir"
            else:
                kind = "file"
            rec = {
                "type": kind,
                "mode": oct(st.st_mode & 0o7777),
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
            }
            if kind == "file":
                try:
                    rec["sha256"] = sha256(p)
                except OSError as exc:
                    rec["sha256"] = f"unreadable:{exc}"
            out[rel] = rec
    return out


def delta(before, after):
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
    }


def run_case(name, argv, env_spec, preseed=None):
    """env_spec: callable(case_dir, paths) -> dict of extra env (None omits key)."""
    case_dir = os.path.join(SANDBOX, name)
    if os.path.exists(case_dir):
        shutil.rmtree(case_dir)
    for sub in ("home", "tmp", "xdg-cache", "xdg-config", "xdg-data", "board"):
        os.makedirs(os.path.join(case_dir, sub), exist_ok=True)

    paths = {
        "root": os.path.join(case_dir, "root"),
        "root_absent": os.path.join(case_dir, "root_absent"),
        "board": os.path.join(case_dir, "board", "tasks.yaml"),
        "mem": os.path.join(case_dir, "mem"),
    }
    with open(paths["board"], "w") as fh:
        fh.write("")
    if preseed:
        preseed(case_dir, paths)

    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": os.path.join(case_dir, "home"),
        "TMPDIR": os.path.join(case_dir, "tmp"),
        "XDG_CACHE_HOME": os.path.join(case_dir, "xdg-cache"),
        "XDG_CONFIG_HOME": os.path.join(case_dir, "xdg-config"),
        "XDG_DATA_HOME": os.path.join(case_dir, "xdg-data"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": HARNESS,
        "REPRO_WRITE_LOG": os.path.join(EVIDENCE, "writes.jsonl"),
        "NO_COLOR": "1",
    }
    for k, v in env_spec(case_dir, paths).items():
        if v is not None:
            env[k] = v

    root = env.get("LIMEN_ROOT", paths["root"])
    state_rel = os.path.relpath(os.path.join(root, "logs", "tabularius-organ-state.json"), case_dir)

    before = inventory(case_dir)
    t0 = time.time()
    proc = subprocess.run([PY, ENTRY] + argv, env=env, capture_output=True, text=True, timeout=180, cwd=WT)
    elapsed = round(time.time() - t0, 3)
    after = inventory(case_dir)

    sb, sa = before.get(state_rel), after.get(state_rel)
    rec = {
        "case": name,
        "argv": argv,
        "exit_code": proc.returncode,
        "elapsed_s": elapsed,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()[-1500:],
        "state_relpath": state_rel,
        "state_before": sb,
        "state_after": sa,
        "state_created": sb is None and sa is not None,
        "state_overwritten": sb is not None and sa is not None and sb != sa,
        "delta": delta(before, after),
        "env_controlled": {k: env.get(k) for k in
                           ("LIMEN_ROOT", "LIMEN_TASKS", "LIMEN_MEMORY_DIR",
                            "LIMEN_MEMORIA", "LIMEN_WORKDIR", "GITHUB_WORKSPACE", "HOME")},
    }
    if sa and sa.get("type") == "file":
        try:
            with open(os.path.join(case_dir, state_rel)) as fh:
                rec["state_content"] = fh.read()
        except OSError:
            pass
    return rec


def seed_preexisting_state(case_dir, paths):
    logs = os.path.join(paths["root"], "logs")
    os.makedirs(logs, exist_ok=True)
    with open(os.path.join(logs, "tabularius-organ-state.json"), "w") as fh:
        fh.write('{"updated": "1970-01-01T00:00:00+00:00", "preExisting": true}')


def seed_populated_memory(case_dir, paths):
    inbox = os.path.join(paths["mem"], ".covenant-inbox")
    os.makedirs(inbox, exist_ok=True)
    with open(os.path.join(inbox, "synthetic-repro-ticket.json"), "w") as fh:
        json.dump(TICKET, fh)


def both(mems, health):
    def _s(case_dir, paths):
        if mems:
            seed_populated_memory(case_dir, paths)
        if health:
            seed_preexisting_state(case_dir, paths)
    return _s


def memoria_on(case_dir, paths, root_key="root"):
    return {
        "LIMEN_MEMORIA": "1",
        "LIMEN_ROOT": paths[root_key],
        "LIMEN_TASKS": paths["board"],
        "LIMEN_MEMORY_DIR": paths["mem"],
    }


def main():
    os.makedirs(SANDBOX, exist_ok=True)
    os.makedirs(EVIDENCE, exist_ok=True)
    wl = os.path.join(EVIDENCE, "writes.jsonl")
    if os.path.exists(wl):
        os.remove(wl)

    results = []

    # Group A — unmodified baseline; stale-root condition reproduced in a
    # disposable area (initially absent), never the historical host destination.
    results.append(run_case(
        "A_baseline_check_memoria_enabled",
        ["--check"],
        lambda c, p: memoria_on(c, p, "root_absent"),
    ))

    # Group B — no-write contract: 2 modes x 2 memory states x 2 health states
    for mode in ("check", "dry-run"):
        for memstate in ("absent", "populated"):
            for health in ("absent", "preexisting"):
                results.append(run_case(
                    f"B_{mode}_mem-{memstate}_health-{health}",
                    [f"--{mode}"],
                    lambda c, p: memoria_on(c, p),
                    both(memstate == "populated", health == "preexisting"),
                ))

    # Group C — feature-disabled control: is the outer write dependent on the
    # memory failure, or unconditional?
    results.append(run_case(
        "C_control_check_memoria_disabled",
        ["--check"],
        lambda c, p: {
            "LIMEN_ROOT": p["root"],
            "LIMEN_TASKS": p["board"],
            "LIMEN_MEMORY_DIR": p["mem"],
            "LIMEN_MEMORIA": None,
        },
    ))

    # Group D — normal-mode reporting: what reaches the stamp / exit status
    results.append(run_case(
        "D_normal_mode_empty_board",
        [],
        lambda c, p: memoria_on(c, p),
    ))

    with open(os.path.join(EVIDENCE, "results.json"), "w") as fh:
        json.dump({"revision": REV, "entry": ENTRY, "interpreter": PY, "results": results}, fh, indent=2)

    print(f"revision={REV}")
    print(f"{'case':<44} {'exit':>4} {'state':<18} {'memory_err_in_state'}")
    print("-" * 92)
    for r in results:
        tag = ("created" if r["state_created"]
               else "OVERWRITTEN" if r["state_overwritten"]
               else "pre-existing" if r["state_before"] else "absent")
        has_err = "memory_error" in (r.get("state_content") or "")
        print(f"{r['case']:<44} {r['exit_code']:>4} {tag:<18} {has_err}")
    return results


if __name__ == "__main__":
    main()