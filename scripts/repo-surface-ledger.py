#!/usr/bin/env python3
"""Discover repo/product surfaces across configured roots.

This is intentionally conservative: it records local repo facts and avoids
network calls. Dry-run prints a redacted summary; --write records private JSON
plus tracked markdown.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "repo-surface-ledger.json"
DOC_PATH = ROOT / "docs" / "repo-surface-ledger.md"
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".cache",
    ".firebase",
    ".next",
    "dist",
    "build",
    ".wrangler",
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def split_paths(value: str | None) -> list[Path]:
    if not value:
        return []
    out: list[Path] = []
    for chunk in value.split(os.pathsep):
        out.extend(Path(item.strip()).expanduser() for item in chunk.split(",") if item.strip())
    return out


def default_roots() -> list[Path]:
    return [HOME / "Workspace", ROOT.parent]


def scan_roots() -> list[Path]:
    env_roots = split_paths(os.environ.get("LIMEN_REPO_ROOTS"))
    roots = env_roots if env_roots else default_roots()
    seen: set[str] = set()
    out: list[Path] = []
    for root in roots:
        key = str(root.expanduser())
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def display_path(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser().absolute()
    try:
        return "~/" + str(resolved.relative_to(HOME))
    except ValueError:
        return str(resolved)


def run_git(repo: Path, *args: str, timeout: int = 6) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def iter_repos(root: Path, *, max_depth: int) -> list[Path]:
    root = root.expanduser()
    if not root.exists():
        return []
    repos: list[Path] = []
    stack: list[tuple[Path, int]] = [(root, 0)]
    seen: set[Path] = set()
    while stack:
        path, depth = stack.pop()
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if (path / ".git").exists():
            repos.append(path)
        if depth >= max_depth:
            continue
        try:
            children = sorted([child for child in path.iterdir() if child.is_dir()], reverse=True)
        except OSError:
            continue
        for child in children:
            if child.name in SKIP_DIRS:
                continue
            stack.append((child, depth + 1))
    return repos


def package_surfaces(repo: Path) -> list[str]:
    surfaces: list[str] = []
    for name in ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "Dockerfile", "firebase.json"):
        if (repo / name).exists():
            surfaces.append(name)
    if (repo / ".github" / "workflows").exists():
        surfaces.append("github-actions")
    if (repo / "vercel.json").exists() or (repo / "netlify.toml").exists():
        surfaces.append("deploy-config")
    return surfaces


def repo_row(repo: Path, roots: list[Path]) -> dict[str, Any]:
    remote = run_git(repo, "remote", "get-url", "origin")
    branch = run_git(repo, "branch", "--show-current")
    dirty = [line for line in run_git(repo, "status", "--porcelain=v1").splitlines() if line.strip()]
    git_dir = run_git(repo, "rev-parse", "--git-dir")
    common_dir = run_git(repo, "rev-parse", "--git-common-dir")
    parent_repo = ""
    for other in roots:
        try:
            if repo.resolve() != other.resolve() and repo.resolve().is_relative_to(other.resolve()):
                parent_repo = display_path(other)
                break
        except (OSError, AttributeError):
            continue
    return {
        "path": str(repo.expanduser()),
        "display_path": display_path(repo),
        "remote": remote,
        "branch": branch,
        "dirty_entries": len(dirty),
        "dirty_sample": dirty[:12],
        "surfaces": package_surfaces(repo),
        "is_worktree": bool(git_dir and common_dir and git_dir != common_dir),
        "nested_under": parent_repo,
    }


def build_snapshot(*, max_depth: int = 4) -> dict[str, Any]:
    roots = [root for root in scan_roots() if root.exists()]
    repos: list[Path] = []
    for root in roots:
        repos.extend(iter_repos(root, max_depth=max_depth))
    deduped: dict[str, Path] = {}
    for repo in repos:
        try:
            key = str(repo.resolve())
        except OSError:
            key = str(repo.absolute())
        deduped[key] = repo
    repo_paths = sorted(deduped.values(), key=lambda item: display_path(item))
    rows = [repo_row(repo, repo_paths) for repo in repo_paths]
    remotes = Counter(row["remote"] or "(none)" for row in rows)
    duplicate_remotes = {remote: count for remote, count in remotes.items() if remote != "(none)" and count > 1}
    return {
        "generated_at": now_iso(),
        "scan_roots": [display_path(root) for root in roots],
        "repo_count": len(rows),
        "dirty_count": sum(1 for row in rows if row["dirty_entries"]),
        "worktree_count": sum(1 for row in rows if row["is_worktree"]),
        "duplicate_remotes": duplicate_remotes,
        "repos": rows,
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Repo Surface Ledger",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Repos discovered: `{snapshot['repo_count']}`",
        f"Dirty repos: `{snapshot['dirty_count']}`",
        f"Worktrees: `{snapshot['worktree_count']}`",
        "",
        "## Scan Roots",
        "",
    ]
    for root in snapshot["scan_roots"]:
        lines.append(f"- `{root}`")
    lines += ["", "## Duplicate Remotes", ""]
    if snapshot["duplicate_remotes"]:
        for remote, count in sorted(snapshot["duplicate_remotes"].items()):
            lines.append(f"- `{remote}`: {count}")
    else:
        lines.append("- none")
    lines += [
        "",
        "## Repos",
        "",
        "| Repo | Remote | Branch | Dirty | Surfaces |",
        "|---|---|---:|---:|---|",
    ]
    for row in snapshot["repos"][:200]:
        remote = row["remote"] or "(none)"
        surfaces = ", ".join(f"`{item}`" for item in row["surfaces"]) or "none"
        lines.append(
            f"| `{row['display_path']}` | `{remote}` | `{row['branch'] or '(detached)'}` | "
            f"{row['dirty_entries']} | {surfaces} |"
        )
    if len(snapshot["repos"]) > 200:
        lines.append(f"| ... | ... | ... | ... | {len(snapshot['repos']) - 200} additional repos in private index |")
    return "\n".join(lines) + "\n"


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the repo surface ledger.")
    parser.add_argument("--refresh", action="store_true", help="accepted for operator symmetry")
    parser.add_argument("--write", action="store_true", help="write tracked summary and private index")
    parser.add_argument("--max-depth", type=int, default=int(os.environ.get("LIMEN_REPO_SCAN_DEPTH", "4")))
    args = parser.parse_args()
    snapshot = build_snapshot(max_depth=args.max_depth)
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
        print(f"repo-surface-ledger: repos={snapshot['repo_count']}; wrote {DOC_PATH} and {PRIVATE_INDEX}")
    else:
        print(markdown, end="")
        print(f"repo-surface-ledger: repos={snapshot['repo_count']}; dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
