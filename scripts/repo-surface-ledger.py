#!/usr/bin/env python3
"""Build a redacted ledger of local repo/product surfaces.

The private index keeps exact local paths, remotes, and product names. Public
markdown only exposes path labels, hashes, counts, and state summaries.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "repo-surface-ledger.json"
DOC_PATH = ROOT / "docs" / "repo-surface-ledger.md"

SCAN_ENV_VARS = ("LIMEN_REPO_ROOTS", "LIMEN_WORKSPACE_ROOT", "LIMEN_WORKTREE_ROOT")
SKIP_DIRS = {
    ".cache",
    ".firebase",
    ".git",
    ".limen-private",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".venv",
    ".wrangler",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "out",
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_hash(value: str, length: int = 16) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        try:
            return str(path.resolve().relative_to(ROOT))
        except (OSError, ValueError):
            return str(path)


def split_paths(value: str) -> list[Path]:
    out: list[Path] = []
    for chunk in re.split(r"[:,]", value):
        chunk = chunk.strip()
        if chunk:
            out.append(Path(chunk).expanduser())
    return out


def configured_scan_roots(extra_roots: list[Path] | None = None) -> list[Path]:
    roots: list[Path] = []
    for env_name in SCAN_ENV_VARS:
        raw = os.environ.get(env_name, "")
        if raw:
            roots.extend(split_paths(raw))
    roots.extend(extra_roots or [])
    if not roots:
        roots.append(ROOT)

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen or not resolved.exists() or not resolved.is_dir():
            continue
        seen.add(key)
        deduped.append(resolved)
    return deduped or [ROOT]


def run_git(repo: Path, args: list[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def repo_roots_under(scan_roots: list[Path], *, max_depth: int = 6, limit: int = 300) -> list[Path]:
    repos: list[Path] = []
    seen: set[str] = set()
    for scan_root in scan_roots:
        base_depth = len(scan_root.parts)
        for dirpath, dirnames, _filenames in os.walk(scan_root):
            current = Path(dirpath)
            depth = len(current.parts) - base_depth
            dirnames[:] = [
                name
                for name in dirnames
                if name not in SKIP_DIRS and not name.endswith(".app") and depth < max_depth
            ]
            if (current / ".git").exists():
                key = str(current.resolve())
                if key not in seen:
                    seen.add(key)
                    repos.append(current)
                    if len(repos) >= limit:
                        return sorted(repos)
    return sorted(repos)


def sanitize_remote(url: str) -> str:
    value = url.strip()
    value = re.sub(r"^(https?://)([^/@]+@)", r"\1", value)
    value = re.sub(r"^git@([^:]+):", r"\1/", value)
    value = re.sub(r"^ssh://git@([^/]+)/", r"\1/", value)
    value = re.sub(r"^https?://", "", value)
    value = value.removesuffix(".git")
    return value.lower()


def package_json_surfaces(repo: Path) -> tuple[list[dict[str, str]], list[str]]:
    path = repo / "package.json"
    if not path.exists():
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except ValueError:
        return [], ["package.json"]
    surfaces: list[dict[str, str]] = []
    scripts: list[str] = []
    name = str(data.get("name") or "").strip()
    if name:
        surfaces.append(product_surface("package_json:name", name))
    script_map = data.get("scripts")
    if isinstance(script_map, dict):
        for script in ("test", "build", "lint", "typecheck"):
            if script in script_map:
                scripts.append(f"package:{script}")
    return surfaces, scripts


def pyproject_surfaces(repo: Path) -> tuple[list[dict[str, str]], list[str]]:
    path = repo / "pyproject.toml"
    if not path.exists():
        return [], []
    surfaces: list[dict[str, str]] = []
    scripts = ["python:pyproject"]
    try:
        import tomllib

        data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
        name = str((data.get("project") or {}).get("name") or "").strip()
        if name:
            surfaces.append(product_surface("pyproject:name", name))
    except Exception:
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"(?m)^name\s*=\s*[\"']([^\"']+)[\"']", text)
        if match:
            surfaces.append(product_surface("pyproject:name", match.group(1)))
    return surfaces, scripts


def readme_surfaces(repo: Path) -> list[dict[str, str]]:
    for name in ("README.md", "readme.md"):
        path = repo / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"(?m)^#\s+(.+?)\s*$", text)
        if match:
            return [product_surface("readme:h1", match.group(1).strip())]
    return []


def product_surface(kind: str, value: str) -> dict[str, str]:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    return {
        "kind": kind,
        "value": value.strip(),
        "hash": stable_hash(f"{kind}:{normalized}"),
    }


def detect_surfaces(repo: Path) -> tuple[list[dict[str, str]], list[str], list[str]]:
    products: list[dict[str, str]] = []
    tests: list[str] = []
    products.extend(readme_surfaces(repo))
    package_surfaces, package_tests = package_json_surfaces(repo)
    pyproject_values, pyproject_tests = pyproject_surfaces(repo)
    products.extend(package_surfaces)
    products.extend(pyproject_values)
    tests.extend(package_tests)
    tests.extend(pyproject_tests)
    for rel in ("pytest.ini", "tox.ini", "Makefile", "scripts/verify-whole.sh"):
        if (repo / rel).exists():
            tests.append(rel)

    deploys: list[str] = []
    for rel in ("wrangler.toml", "vercel.json", "netlify.toml", "firebase.json"):
        if (repo / rel).exists():
            deploys.append(rel)
    if (repo / ".github" / "workflows").exists():
        deploys.append(".github/workflows")
    if (repo / "docs" / "positioning").exists():
        deploys.append("docs/positioning")
    return products, sorted(set(tests)), sorted(set(deploys))


def repo_record(repo: Path) -> dict[str, Any]:
    remote_url = run_git(repo, ["config", "--get", "remote.origin.url"])
    normalized_remote = sanitize_remote(remote_url) if remote_url else ""
    status_lines = run_git(repo, ["status", "--porcelain"]).splitlines()
    branch = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]) or "unknown"
    upstream = run_git(repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"])
    default_branch = run_git(repo, ["symbolic-ref", "refs/remotes/origin/HEAD", "--short"]).removeprefix(
        "origin/"
    )
    if not default_branch:
        remote_show = run_git(repo, ["remote", "show", "-n", "origin"])
        match = re.search(r"HEAD branch:\s*(\S+)", remote_show)
        default_branch = match.group(1) if match else ""
    products, tests, deploys = detect_surfaces(repo)
    return {
        "path": str(repo),
        "path_label": relpath(repo),
        "name": repo.name,
        "branch": branch,
        "upstream": upstream,
        "default_branch": default_branch or None,
        "remote_url": remote_url,
        "normalized_remote": normalized_remote,
        "remote_hash": stable_hash(normalized_remote) if normalized_remote else None,
        "dirty": bool(status_lines),
        "dirty_count": len(status_lines),
        "product_surfaces": products,
        "test_surfaces": tests,
        "deploy_surfaces": deploys,
        "visibility_state": "remote-present" if normalized_remote else "local-only",
    }


def duplicate_remote_groups(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for repo in repos:
        remote_hash = repo.get("remote_hash")
        if remote_hash:
            groups.setdefault(str(remote_hash), []).append(repo)
    return [
        {
            "remote_hash": remote_hash,
            "repo_count": len(items),
            "repos": [item["path_label"] for item in sorted(items, key=lambda row: row["path_label"])],
        }
        for remote_hash, items in sorted(groups.items())
        if len(items) > 1
    ]


def build_snapshot(
    scan_roots: list[Path] | None = None,
    *,
    max_depth: int | None = None,
    limit: int = 300,
) -> dict[str, Any]:
    roots = configured_scan_roots(scan_roots)
    depth = max_depth if max_depth is not None else int(os.environ.get("LIMEN_REPO_SCAN_DEPTH", "6"))
    repos = [repo_record(path) for path in repo_roots_under(roots, max_depth=depth, limit=limit)]
    return {
        "generated_at": now_iso(),
        "scan_roots": [relpath(path) for path in roots],
        "repo_count": len(repos),
        "repos": repos,
        "duplicate_remotes": duplicate_remote_groups(repos),
        "privacy": {
            "public_remote_mode": "hash-only",
            "public_product_surface_mode": "hash-only",
            "private_index": relpath(PRIVATE_INDEX),
        },
    }


def public_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    def cleanse(value: Any) -> Any:
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for key, inner in value.items():
                if key in {"path", "remote_url", "normalized_remote", "value"}:
                    continue
                out[key] = cleanse(inner)
            return out
        if isinstance(value, list):
            return [cleanse(item) for item in value]
        return value

    return cleanse(snapshot)


def render_markdown(snapshot: dict[str, Any]) -> str:
    public = public_snapshot(snapshot)
    lines = [
        "# Repo Surface Ledger",
        "",
        f"Generated: `{public['generated_at']}`",
        f"Repos scanned: `{public['repo_count']}`",
        "",
        "## Scan Roots",
        "",
    ]
    lines.extend(f"- `{root}`" for root in public["scan_roots"])
    lines += [
        "",
        "## Duplicate Remote Groups",
        "",
        "| Remote hash | Repos |",
        "|---|---:|",
    ]
    for group in public["duplicate_remotes"]:
        lines.append(f"| `{group['remote_hash']}` | {group['repo_count']} |")
    if not public["duplicate_remotes"]:
        lines.append("| none | 0 |")
    lines += [
        "",
        "## Repo Surfaces",
        "",
        "| Repo | Branch | Dirty | Remote | Products | Tests | Deploys | Visibility |",
        "|---|---|---:|---|---:|---:|---:|---|",
    ]
    for repo in public["repos"]:
        products = repo.get("product_surfaces") or []
        lines.append(
            f"| `{repo['path_label']}` | `{repo['branch']}` | {repo['dirty_count']} | "
            f"`{repo.get('remote_hash') or 'none'}` | {len(products)} | "
            f"{len(repo.get('test_surfaces') or [])} | {len(repo.get('deploy_surfaces') or [])} | "
            f"`{repo['visibility_state']}` |"
        )
    lines += [
        "",
        "## Contract",
        "",
        "- Public receipts use hashes for remotes and product surfaces.",
        "- Exact local paths, remote URLs, and product names stay in the ignored private index.",
        "- Discovery roots are derived from `LIMEN_REPO_ROOTS`, `LIMEN_WORKSPACE_ROOT`, `LIMEN_WORKTREE_ROOT`, or the current Limen root.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the redacted repo surface ledger.")
    parser.add_argument("--scan-root", action="append", default=[], help="additional root to scan")
    parser.add_argument("--refresh", action="store_true", help="build a fresh snapshot")
    parser.add_argument("--write", action="store_true", help="write public docs and private index")
    parser.add_argument("--dry-run", action="store_true", help="print only; never write")
    parser.add_argument("--json", action="store_true", help="print public JSON instead of markdown")
    parser.add_argument("--max-depth", type=int, default=int(os.environ.get("LIMEN_REPO_SCAN_DEPTH", "6")))
    args = parser.parse_args()

    roots = [Path(value).expanduser() for value in args.scan_root]
    snapshot = build_snapshot(roots, max_depth=args.max_depth)
    markdown = render_markdown(snapshot)
    if args.write and not args.dry_run:
        write_outputs(snapshot, markdown)
        print(f"repo-surface-ledger: wrote {DOC_PATH} and {PRIVATE_INDEX}")
        return 0
    if args.json:
        print(json.dumps(public_snapshot(snapshot), indent=2, sort_keys=True))
    else:
        print(markdown, end="")
        print("repo-surface-ledger: dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
