#!/usr/bin/env python3
"""Metadata resolver — derive each live surface's IDENTITY from its git remote,
not its folder name. Read-only. Embodies the "names are outputs, resolved from
metadata" principle: physical path is incidental; identity = owner/repo from the
remote (+ HEAD, branch, dirty state). Output feeds the Phase-3 one-container plan.

Usage: python3 resolve-identities.py [ROOT ...]   (default: ~/Workspace)
Emits a markdown table on stdout and a JSON manifest to stderr-free file if --json PATH.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def git(cwd: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def canonical(remote: str) -> str:
    """owner/repo from a git remote URL, else '(no remote)'."""
    if not remote:
        return "(no remote)"
    s = remote.removesuffix(".git")
    if s.startswith("git@"):
        s = s.split(":", 1)[-1]
    elif "://" in s:
        s = s.split("://", 1)[-1].split("/", 1)[-1]
    return s


def find_repos(root: Path, maxdepth: int = 3) -> list[Path]:
    repos, root = [], root.resolve()
    base = len(root.parts)
    for dirpath, dirnames, _ in os.walk(root):
        p = Path(dirpath)
        if (p / ".git").exists():
            repos.append(p)
            dirnames[:] = []  # don't descend into a repo's nested checkouts
            continue
        if len(p.parts) - base >= maxdepth:
            dirnames[:] = []
    return repos


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    roots = [Path(a) for a in args] or [Path.home() / "Workspace"]
    json_out = None
    if "--json" in sys.argv:
        json_out = Path(sys.argv[sys.argv.index("--json") + 1])

    rows = []
    for root in roots:
        for repo in sorted(find_repos(root)):
            remote = git(repo, "remote", "get-url", "origin")
            rows.append({
                "identity": canonical(remote),
                "path": str(repo),
                "head": git(repo, "rev-parse", "--short", "HEAD"),
                "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
                "dirty": bool(git(repo, "status", "--porcelain")),
            })

    # group by identity to expose duplicates (same remote, multiple paths)
    by_id: dict[str, list[dict]] = {}
    for r in rows:
        by_id.setdefault(r["identity"], []).append(r)

    print(f"# Resolved identities — {sum(len(v) for v in by_id.values())} checkouts, "
          f"{len(by_id)} distinct identities\n")
    print("| identity (from remote) | path | branch | head | dirty | dup? |")
    print("|---|---|---|---|---|---|")
    for ident in sorted(by_id):
        group = by_id[ident]
        for r in group:
            dup = "⚠︎" if len(group) > 1 and ident != "(no remote)" else ""
            print(f"| {ident} | {r['path']} | {r['branch']} | {r['head']} | "
                  f"{'yes' if r['dirty'] else ''} | {dup} |")

    if json_out:
        json_out.write_text(json.dumps(by_id, indent=2))
        print(f"\nmanifest -> {json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
