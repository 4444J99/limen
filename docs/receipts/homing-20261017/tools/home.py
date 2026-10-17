#!/usr/bin/env python3
"""Home local git state onto remotes without mutating any checkout.

Job kinds:
  ref      push an existing local object (branch name or sha) to remote ref
  stash    push a stash commit sha to a remote ref
  snapshot build a commit from the worktree (tracked changes + untracked, honoring
           .gitignore) via a TEMPORARY index, parent = HEAD, then push the new sha.
           The real index, HEAD and files are untouched.

Non-force pushes only. If a push is rejected (non-fast-forward), the object is
pushed to preserve/<fallback> instead. Every outcome is recorded as JSON.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DATE = datetime.now(timezone.utc).strftime("%Y%m%d")
APPLY = "--apply" in sys.argv
JOBS = Path(sys.argv[1])
OUT = Path(sys.argv[2])


def git(repo: str, *args: str, env: dict | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout, env=full_env
    )


def head_sha(repo: str) -> str:
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def snapshot(repo: str, message: str) -> tuple[str | None, str]:
    """Return (new_commit_sha, note). Uses a temp index so the live index is never touched."""
    index_path = git(repo, "rev-parse", "--git-path", "index").stdout.strip()
    index_path = str((Path(repo) / index_path).resolve()) if not os.path.isabs(index_path) else index_path
    tmpdir = tempfile.mkdtemp(prefix="home-idx-")
    tmp_index = os.path.join(tmpdir, "index")
    try:
        if os.path.exists(index_path):
            shutil.copy2(index_path, tmp_index)
        env = {"GIT_INDEX_FILE": tmp_index}
        add = git(repo, "add", "-A", "--", ".", env=env)
        if add.returncode:
            return None, f"add failed: {add.stderr.strip()[:300]}"
        wt = git(repo, "write-tree", env=env)
        if wt.returncode:
            return None, f"write-tree failed: {wt.stderr.strip()[:300]}"
        tree = wt.stdout.strip()
        parent = head_sha(repo)
        head_tree = git(repo, "rev-parse", "HEAD^{tree}").stdout.strip()
        if tree == head_tree:
            return None, "no-op: worktree tree equals HEAD tree"
        ct = git(repo, "commit-tree", tree, "-p", parent, "-m", message, env=env)
        if ct.returncode:
            return None, f"commit-tree failed: {ct.stderr.strip()[:300]}"
        return ct.stdout.strip(), f"snapshot commit over {parent[:12]}"
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def push(repo: str, remote: str, obj: str, ref: str, fallback: str) -> dict:
    if not APPLY:
        return {"pushed": False, "dry_run": True, "target": ref}
    r = git(repo, "push", remote, f"{obj}:refs/heads/{ref}", timeout=600)
    if r.returncode == 0:
        return {"pushed": True, "target": ref, "stderr": r.stderr.strip()[-300:]}
    fb = f"preserve/{fallback}-{DATE}"
    r2 = git(repo, "push", remote, f"{obj}:refs/heads/{fb}", timeout=600)
    return {
        "pushed": r2.returncode == 0,
        "target": fb if r2.returncode == 0 else None,
        "first_error": r.stderr.strip()[-300:],
        "stderr": r2.stderr.strip()[-300:],
    }


def main() -> int:
    jobs = json.loads(JOBS.read_text())
    results = []
    for job in jobs:
        repo = job["repo"]
        kind = job["kind"]
        remote = job.get("remote", "origin")
        rec = {"name": job["name"], "repo": repo, "kind": kind, "remote": remote}
        try:
            if kind == "snapshot":
                sha, note = snapshot(repo, job["message"])
                rec["note"] = note
                if sha is None:
                    rec["status"] = "skipped"
                    results.append(rec)
                    continue
                obj = sha
            else:
                obj = job["src"]
                rv = git(repo, "rev-parse", "--verify", "--quiet", f"{obj}^{{commit}}")
                if rv.returncode:
                    rec["status"] = "error"
                    rec["note"] = f"object not found: {obj}"
                    results.append(rec)
                    continue
                obj = rv.stdout.strip()
            rec["object"] = obj
            rec["push"] = push(repo, remote, obj, job["ref"], job.get("fallback", job["name"]))
            rec["status"] = "pushed" if rec["push"].get("pushed") else ("dry-run" if not APPLY else "push-failed")
        except Exception as exc:  # noqa: BLE001
            rec["status"] = "error"
            rec["note"] = f"{type(exc).__name__}: {exc}"
        results.append(rec)
        print(json.dumps({k: rec[k] for k in rec if k in ("name", "status", "object", "note")} | {"target": rec.get("push", {}).get("target")}))
    OUT.write_text(json.dumps({"date": DATE, "apply": APPLY, "results": results}, indent=2))
    bad = [r for r in results if r["status"] in ("error", "push-failed")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
