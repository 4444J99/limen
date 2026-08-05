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

ENTRY-LEVEL for keyed registries. A raw path intersection is too blunt for append-mostly registry files
(``sensors.yaml``/``gates.yaml``/``parameters.yaml`` …): ~20 lanes append to them at once, each a
DISTINCT keyed entry whose changes union cleanly. Refusing every such PR is a fence collapsing into a
wall — the exact defect this tool exists to prevent. So when a shared file parses (on BASE) as a
single-top-level-collection YAML registry, the classifier reads each lane's OWN diff — vs its
merge-base, so base drift on a stale branch can't masquerade as a change — and extracts which registry
entries that lane touched. Disjoint entry-sets ⇒ SOFT (a clean union — reported ``~``, NOT a refusal);
a shared entry ⇒ HARD. Derived structurally (no filename allowlist), still fail-closed: a non-registry
file, an unfetchable/empty patch, or an unrecognizable hunk ⇒ HARD.

Exit 0 ⟺ insulated: no HARD overlap and every lane readable (clean-union ``~`` soft overlaps are fine).
Exit 1 ⟺ a HARD overlap (a shared file, or a shared registry entry), OR a lane could not be verified.

Usage:
  lane-overlap.py <PR#>     — check that PR's files against all other lanes
  lane-overlap.py           — check the current worktree's diff (committed vs origin/main + uncommitted)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from functools import partial
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
            path, branch = Path(line[len("worktree ") :]), ""
        elif line.startswith("branch "):
            branch = line[len("branch ") :].strip().removeprefix("refs/heads/")
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
        cwd=ROOT,
        timeout=timeout,
    )
    if rc != 0:
        return None
    try:
        return [int(r["number"]) for r in json.loads(out)]
    except (ValueError, KeyError, TypeError):
        return None


# ── entry-level overlap: a clean union of distinct registry entries is NOT a collision ────────────


def _registry_entries(text: str) -> dict[str, str] | None:
    """Map each entry-key of a registry's ONE top-level collection to a stable serialization of its
    value. None ⇒ NOT a single-collection keyed registry, or unparseable ⇒ caller falls back to HARD.

    The VIGILIA registries (sensors/gates/parameters.yaml …) are ``schema_version:`` scalars plus ONE
    mapping whose children are the keyed entries. Requiring exactly one mapping-valued top-level key
    means a non-registry YAML can never be mistaken for one (fail-closed)."""
    try:
        import yaml  # local: a missing PyYAML ⇒ None ⇒ HARD, never a crash

        data = yaml.safe_load(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    collections = [k for k, v in data.items() if isinstance(v, dict)]
    if len(collections) != 1:
        return None
    entries = data[collections[0]]
    if not isinstance(entries, dict):
        return None
    out: dict[str, str] = {}
    for key, value in entries.items():
        try:
            out[str(key)] = yaml.safe_dump(value, sort_keys=True, default_flow_style=False)
        except Exception:
            return None
    return out


def _base_file_text(path: str, cache: dict[str, str | None]) -> str | None:
    if path not in cache:
        rc, out = _run(["git", "show", f"{BASE}:{path}"], cwd=ROOT)
        cache[path] = out if rc == 0 else None
    return cache[path]


def _touched_keys_from_patch(patch: str) -> set[str]:
    """Top-level collection entries a unified diff touches — added/removed entry keys, plus any entry
    whose nested lines changed. A context line (marker ' ') sets the *current* entry so a changed field
    is attributed to its parent. Tied to the registries' 2-space entry indent; an unrecognizable hunk
    yields no keys ⇒ the caller reads that as uncertainty ⇒ HARD (fail-closed)."""
    keys: set[str] = set()
    current: str | None = None
    for line in patch.splitlines():
        if line.startswith("@@"):
            current = None
            continue
        if line.startswith(("+++", "---", "diff ", "index ", "new file", "deleted", "rename", "similarity")):
            continue
        if not line or line[0] not in "+- ":
            continue
        marker, body = line[0], line[1:]
        m = re.match(r"  ([A-Za-z0-9_.\-]+):", body)  # a 2-space-indented entry key
        if m:
            current = m.group(1)
            if marker in "+-":
                keys.add(current)
        elif marker in "+-" and current is not None:
            keys.add(current)  # a changed nested field belongs to the current entry
    return keys


def _worktree_patch(wt: Path, path: str) -> str | None:
    """A worktree lane's OWN diff of ``path`` — merge-base(BASE, HEAD) → working tree, so it captures
    the lane's committed + uncommitted change WITHOUT base drift. ``-U100`` gives generous context so a
    DEEPLY nested field change still carries its 2-space parent entry key into the hunk (default 3-line
    context can strand a deep change above its key ⇒ unattributable ⇒ needlessly HARD). None ⇒ HARD."""
    rc, mb = _run(["git", "merge-base", BASE, "HEAD"], cwd=wt)
    if rc != 0 or not mb.strip():
        return None
    rc, out = _run(["git", "diff", "-U100", mb.strip(), "--", path], cwd=wt)
    return out if rc == 0 else None


def _pr_patch(pr: int, path: str, repo: str, timeout: float) -> str | None:
    """A PR lane's OWN diff of ``path`` (GitHub computes it vs the merge-base). None ⇒ unfetchable ⇒
    HARD; an empty/omitted patch (e.g. a too-large file) reads as uncertainty ⇒ HARD upstream."""
    rc, out = _run(
        [
            "gh",
            "api",
            f"repos/{repo}/pulls/{pr}/files",
            "--paginate",
            "--jq",
            f'.[] | select(.filename=="{path}") | .patch',
        ],
        cwd=ROOT,
        timeout=timeout,
    )
    return out if rc == 0 else None


def _classify_shared(
    shared, target_patch_of, other_patch_of, base_cache: dict[str, str | None]
) -> tuple[list[str], list[str]]:
    """Split shared files into (hard, soft). SOFT = a shared file that is a keyed registry (on BASE)
    where each lane's OWN diff touches a NON-EMPTY, DISJOINT set of entries — a clean union. Everything
    else — a non-registry file, an empty/ambiguous patch, or a shared entry — is HARD (fail-closed)."""
    hard: list[str] = []
    soft: list[str] = []
    for f in shared:
        base_t = _base_file_text(f, base_cache)
        is_registry = base_t is not None and _registry_entries(base_t) is not None
        target_p = target_patch_of(f)
        other_p = other_patch_of(f)
        if not is_registry or not target_p or not other_p:
            hard.append(f)
            continue
        target_keys = _touched_keys_from_patch(target_p)
        other_keys = _touched_keys_from_patch(other_p)
        if target_keys and other_keys and not (target_keys & other_keys):
            soft.append(f)
        else:
            hard.append(f)
    return hard, soft


# ── the predicate ────────────────────────────────────────────────────────────────────────────────


def _current_worktree_files() -> set[str] | None:
    return _worktree_files(ROOT)


def evaluate(*, pr: int | None, repo: str, timeout: float, check_prs: bool = True) -> tuple[int, str]:
    # 1. What am I checking, and which lane is it (so I exclude it from "others")?
    if pr is not None:
        target = _pr_files(pr, repo, timeout)
        if target is None:
            return (
                1,
                f"lane-overlap: REFUSED — could not read files of PR #{pr} (fail-closed); cannot prove insulation.",
            )
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
    soft_notes: list[str] = []
    unverified: list[str] = []
    base_cache: dict[str, str | None] = {}

    # Target-side patch fetcher (cached once per file): the current worktree's own diff, or the PR's
    # own diff via the GitHub files API. Consulted only when a shared file needs entry-level classify.
    _tgt_cache: dict[str, str | None] = {}

    def target_patch_of(f: str) -> str | None:
        if f not in _tgt_cache:
            if pr is not None:
                _tgt_cache[f] = _pr_patch(pr, f, repo, timeout)
            else:
                _tgt_cache[f] = _worktree_patch(ROOT, f)
        return _tgt_cache[f]

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
        if not shared:
            continue
        hard, soft = _classify_shared(shared, target_patch_of, partial(_worktree_patch, path), base_cache)
        label = f"worktree {path.name} [{branch or 'detached'}]"
        if hard:
            collisions.append(f"{label} ← {', '.join(hard[:8])}")
        if soft:
            soft_notes.append(f"{label} ~ {', '.join(soft[:8])}")

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
                if not shared:
                    continue
                other_of = partial(_pr_patch, n, repo=repo, timeout=timeout)
                hard, soft = _classify_shared(shared, target_patch_of, other_of, base_cache)
                if hard:
                    collisions.append(f"PR #{n} ← {', '.join(hard[:8])}")
                if soft:
                    soft_notes.append(f"PR #{n} ~ {', '.join(soft[:8])}")

    # 4. Verdict — fail-closed: any HARD collision OR any unverified lane refuses. SOFT (clean-union)
    #    overlaps are reported but never refuse.
    scope = "every in-flight lane" if check_prs else "every held worktree (--local; PRs not checked)"
    if not collisions and not unverified:
        msg = f"lane-overlap: OK — {self_label} is insulated (disjoint from {scope})."
        for s in soft_notes:
            msg += f"\n  ~ {s} — disjoint registry entries, clean union (not a collision)"
        return 0, msg

    lines = [f"lane-overlap: NOT INSULATED — {self_label} overlaps in-flight lanes:"]
    for c in collisions:
        lines.append(f"  ✗ {c}")
    for u in unverified:
        lines.append(f"  ? {u} — could not verify, counted as overlap (fail-closed)")
    for s in soft_notes:
        lines.append(f"  ~ {s} — disjoint registry entries, clean union (not a collision)")
    return 1, "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Prove a change is insulated from every other in-flight lane.")
    ap.add_argument("pr", nargs="?", type=int, help="PR number to check (default: the current worktree's diff)")
    ap.add_argument("--repo", default=DEFAULT_REPO, help=f"owner/name (default {DEFAULT_REPO})")
    ap.add_argument("--timeout", type=float, default=30.0, help="per-gh-call timeout seconds (default 30)")
    ap.add_argument(
        "--local",
        action="store_true",
        help="check held worktrees only; skip the open-PR sweep (fast, offline, no GitHub)",
    )
    args = ap.parse_args(argv)
    code, message = evaluate(pr=args.pr, repo=args.repo, timeout=args.timeout, check_prs=not args.local)
    print(message)
    return code


if __name__ == "__main__":
    sys.exit(main())
