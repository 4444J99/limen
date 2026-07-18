#!/usr/bin/env python3
"""Prove a change is INSULATED from every other in-flight lane — the executable form of "a fence is
not a wall".

A peer-coordination pause (a *fence*) protects a peer agent's active work. The whole point of the
2026-07-17 correction is that a fence must NOT freeze a directed session's *insulated* work — work that
provably touches none of the peer's lanes. "Provably" is the hard part; this predicate is it.

Because the estate has **no first-class PR→agent or worktree→agent ownership map** (worktree ownership
is only the ``.claude/worktrees/agent-<SESSION_ID>`` naming), asking "does this avoid *codex's* lanes?"
is intractable. The tractable, *stronger* question needs no attribution:

    my changed files  ∩  ( every OTHER held worktree's changed files
                           ∪ every OTHER open PR's changed files )   ==  ∅   ?

If the intersection is empty, the change is insulated from ALL in-flight lanes at once — a superset of
"insulated from the peer". If not, it names the offending file and lane.

FAIL-CLOSED. This guards a merge, so uncertainty must never read as insulation: if any lane's files
cannot be determined (gh error, unreadable worktree, offline), that lane counts as an OVERLAP and the
predicate refuses. This deliberately inverts the fail-OPEN bias of the recon helpers
(_pr_scan.enumerate_open_prs returns [] on gh error) — fail-open there means "assume nothing to see",
which for a safety gate would silently green-light a merge it never verified.

Exit 0 ⟺ insulated (disjoint from every readable lane, and every lane was readable).
Exit 1 ⟺ overlap found, OR a lane could not be verified (fail-closed).

Usage:
  lane-overlap.py <PR#>     — check that PR's files against all other lanes
  lane-overlap.py           — check the current worktree's diff (committed vs origin/main + uncommitted)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
DEFAULT_REPO = os.environ.get("LIMEN_GITHUB_REPO") or "organvm/limen"
BASE = "origin/main"


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: float = 30.0) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False, cwd=str(cwd) if cwd else None
        )
        return proc.returncode, proc.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


# ── local git: worktrees and their changed files ────────────────────────────────────────────────

def _worktrees() -> list[tuple[Path, str]]:
    """(path, branch) for every registered worktree, from ``git worktree list --porcelain``."""
    rc, out = _run(["git", "worktree", "list", "--porcelain"], cwd=ROOT)
    if rc != 0:
        return []
    result, path, branch = [], None, ""
    for line in out.splitlines():
        if line.startswith("worktree "):
            if path is not None:
                result.append((path, branch))
            path, branch = Path(line[len("worktree "):]), ""
        elif line.startswith("branch "):
            branch = line[len("branch "):].strip().removeprefix("refs/heads/")
    if path is not None:
        result.append((path, branch))
    return result


def _worktree_held(wt: Path) -> bool:
    """A worktree is an in-flight lane if it has uncommitted changes OR commits ahead of BASE."""
    rc, out = _run(["git", "status", "--porcelain"], cwd=wt)
    if rc == 0 and out.strip():
        return True
    rc, out = _run(["git", "rev-list", "--count", f"{BASE}..HEAD"], cwd=wt)
    return rc == 0 and out.strip().isdigit() and int(out.strip()) > 0


def _worktree_files(wt: Path) -> set[str] | None:
    """Files a worktree touches: committed vs BASE + uncommitted. None ⇒ unreadable (fail-closed)."""
    files: set[str] = set()
    rc, out = _run(["git", "diff", "--name-only", f"{BASE}...HEAD"], cwd=wt)
    if rc != 0:
        return None
    files.update(f for f in out.splitlines() if f.strip())
    rc, out = _run(["git", "status", "--porcelain"], cwd=wt)
    if rc != 0:
        return None
    # porcelain: "XY path" (or "R  old -> new"); take the final path token
    for line in out.splitlines():
        name = line[3:].strip()
        if "->" in name:
            name = name.split("->", 1)[1].strip()
        if name:
            files.add(name)
    return files


# ── gh: open PRs and their files ─────────────────────────────────────────────────────────────────

def _pr_files(pr: int, repo: str, timeout: float) -> set[str] | None:
    rc, out = _run(["gh", "pr", "view", str(pr), "-R", repo, "--json", "files"], cwd=ROOT, timeout=timeout)
    if rc != 0:
        return None
    try:
        data = json.loads(out)
        return {f["path"] for f in data.get("files", []) if f.get("path")}
    except (ValueError, KeyError, TypeError):
        return None


def _pr_head(pr: int, repo: str, timeout: float) -> str | None:
    rc, out = _run(["gh", "pr", "view", str(pr), "-R", repo, "--json", "headRefName"], cwd=ROOT, timeout=timeout)
    if rc != 0:
        return None
    try:
        return str(json.loads(out).get("headRefName", "")) or None
    except (ValueError, TypeError):
        return None


def _open_prs(repo: str, timeout: float) -> list[int] | None:
    """Open PR numbers. None ⇒ enumeration FAILED (fail-closed) — distinct from an empty estate."""
    rc, out = _run(
        ["gh", "pr", "list", "-R", repo, "--state", "open", "--json", "number", "--limit", "200"],
        cwd=ROOT, timeout=timeout,
    )
    if rc != 0:
        return None
    try:
        return [int(r["number"]) for r in json.loads(out)]
    except (ValueError, KeyError, TypeError):
        return None


# ── the predicate ────────────────────────────────────────────────────────────────────────────────

def _current_worktree_files() -> set[str] | None:
    return _worktree_files(ROOT)


def evaluate(*, pr: int | None, repo: str, timeout: float, check_prs: bool = True) -> tuple[int, str]:
    # 1. What am I checking, and which lane is it (so I exclude it from "others")?
    if pr is not None:
        target = _pr_files(pr, repo, timeout)
        if target is None:
            return 1, f"lane-overlap: REFUSED — could not read files of PR #{pr} (fail-closed); cannot prove insulation."
        self_branch = _pr_head(pr, repo, timeout)  # may be None; then no worktree is excluded by branch
        self_label = f"PR #{pr}"
    else:
        target = _current_worktree_files()
        if target is None:
            return 1, "lane-overlap: REFUSED — could not read the current worktree's diff (fail-closed)."
        rc, out = _run(["git", "branch", "--show-current"], cwd=ROOT)
        self_branch = out.strip() if rc == 0 else None
        self_label = f"worktree {ROOT.name}"

    if not target:
        return 0, f"lane-overlap: OK — {self_label} touches no files vs {BASE} (vacuously insulated)."

    collisions: list[str] = []
    unverified: list[str] = []

    # 2. Every OTHER held worktree.
    for path, branch in _worktrees():
        if path.resolve() == ROOT.resolve() or (self_branch and branch == self_branch):
            continue
        if not _worktree_held(path):
            continue
        files = _worktree_files(path)
        if files is None:
            unverified.append(f"worktree {path.name} (unreadable)")
            continue
        shared = sorted(target & files)
        if shared:
            collisions.append(f"worktree {path.name} [{branch or 'detached'}] ← {', '.join(shared[:8])}")

    # 3. Every OTHER open PR (skipped in --local mode: worktrees only, no GitHub round-trips).
    if check_prs:
        prs = _open_prs(repo, timeout)
        if prs is None:
            unverified.append("open-PR enumeration (gh failed)")
        else:
            for n in prs:
                if pr is not None and n == pr:
                    continue
                files = _pr_files(n, repo, timeout)
                if files is None:
                    unverified.append(f"PR #{n} (files unreadable)")
                    continue
                shared = sorted(target & files)
                if shared:
                    collisions.append(f"PR #{n} ← {', '.join(shared[:8])}")

    # 4. Verdict — fail-closed: any collision OR any unverified lane refuses.
    scope = "every in-flight lane" if check_prs else "every held worktree (--local; PRs not checked)"
    if not collisions and not unverified:
        return 0, f"lane-overlap: OK — {self_label} is insulated (disjoint from {scope})."

    lines = [f"lane-overlap: NOT INSULATED — {self_label} overlaps in-flight lanes:"]
    for c in collisions:
        lines.append(f"  ✗ {c}")
    for u in unverified:
        lines.append(f"  ? {u} — could not verify, counted as overlap (fail-closed)")
    return 1, "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prove a change is insulated from every other in-flight lane.")
    ap.add_argument("pr", nargs="?", type=int, help="PR number to check (default: the current worktree's diff)")
    ap.add_argument("--repo", default=DEFAULT_REPO, help=f"owner/name (default {DEFAULT_REPO})")
    ap.add_argument("--timeout", type=float, default=30.0, help="per-gh-call timeout seconds (default 30)")
    ap.add_argument("--local", action="store_true",
                    help="check held worktrees only; skip the open-PR sweep (fast, offline, no GitHub)")
    args = ap.parse_args(argv)
    code, message = evaluate(pr=args.pr, repo=args.repo, timeout=args.timeout, check_prs=not args.local)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
