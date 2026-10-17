#!/usr/bin/env python3
"""Classify local branches with no live upstream; push the ones whose tip exists on no remote.

For every repo given: fetch origin, then for each local branch whose upstream is missing
or gone, test `git branch -r --contains <tip>`. Contained -> "reapable" (loss-free to delete,
left for the operator reap script). Not contained -> pushed to origin under its own name
(non-force; on rejection, under preserve/<name>-<date>). Writes a JSON report.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DATE = datetime.now(timezone.utc).strftime("%Y%m%d")
APPLY = "--apply" in sys.argv
REPOS = [a for a in sys.argv[1:-1] if not a.startswith("--")]
OUT = Path(sys.argv[-1])


def git(repo: str, *args: str, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout)


def main() -> int:
    report = {"date": DATE, "apply": APPLY, "repos": []}
    for repo in REPOS:
        entry = {"repo": repo, "reapable": [], "pushed": [], "failed": [], "skipped_protected": []}
        remote = git(repo, "remote", "get-url", "origin")
        if remote.returncode:
            entry["error"] = "no origin remote"
            report["repos"].append(entry)
            continue
        entry["remote"] = remote.stdout.strip()
        f = git(repo, "fetch", "--quiet", "--prune", "origin", timeout=600)
        entry["fetch"] = "ok" if f.returncode == 0 else f.stderr.strip()[-200:]
        refs = git(
            repo, "for-each-ref", "--format=%(refname:short)%09%(objectname)%09%(upstream:short)%09%(upstream:track)", "refs/heads"
        ).stdout
        for line in refs.splitlines():
            name, sha, upstream, track = (line.split("\t") + ["", "", ""])[:4]
            if upstream and "gone" not in track:
                continue  # has a live upstream; owned by normal flow
            if name in ("main", "master"):
                entry["skipped_protected"].append(name)
                continue
            contained = git(repo, "branch", "-r", "--contains", sha).stdout.strip()
            if contained:
                entry["reapable"].append({"branch": name, "sha": sha[:12], "on": contained.splitlines()[0].strip()})
                continue
            if not APPLY:
                entry["pushed"].append({"branch": name, "sha": sha[:12], "dry_run": True})
                continue
            p = git(repo, "push", "origin", f"{sha}:refs/heads/{name}", timeout=600)
            if p.returncode == 0:
                entry["pushed"].append({"branch": name, "sha": sha[:12], "target": name})
                continue
            fb = f"preserve/{name.replace('/', '-')}-{DATE}"
            p2 = git(repo, "push", "origin", f"{sha}:refs/heads/{fb}", timeout=600)
            if p2.returncode == 0:
                entry["pushed"].append({"branch": name, "sha": sha[:12], "target": fb, "note": p.stderr.strip()[-160:]})
            else:
                entry["failed"].append({"branch": name, "sha": sha[:12], "error": p2.stderr.strip()[-200:]})
        print(
            json.dumps(
                {
                    "repo": repo,
                    "reapable": len(entry["reapable"]),
                    "to_push" if not APPLY else "pushed": len(entry["pushed"]),
                    "failed": len(entry["failed"]),
                }
            )
        )
        report["repos"].append(entry)
    OUT.write_text(json.dumps(report, indent=2))
    return 1 if any(r.get("failed") for r in report["repos"]) else 0


if __name__ == "__main__":
    sys.exit(main())
