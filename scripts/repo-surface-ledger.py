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
CONSOLIDATION_SOURCE_OWNERS = {
    "4444J99",
    "a-organvm",
    "meta-organvm",
    "organvm-i-theoria",
    "organvm-ii-poiesis",
    "organvm-iii-ergon",
    "organvm-iv-taxis",
    "organvm-v-logos",
    "organvm-vi-koinonia",
    "organvm-vii-kerygma",
}
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

DISPOSITIONS = {
    "build",
    "verify",
    "consolidate",
    "private-sauce",
    "publish-stage",
    "blocked-human",
    "retire",
}
LOCATION_CLASSES = ("archive", "nested", "workspace", "worktree")
REMOTE_CLASSES = ("github-organvm", "github-other", "github-source-owner", "local-only", "remote-other")
GATE_CLASSES = ("none", "post-transfer-owner-rewrite-pending")


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


def github_owner(normalized_remote: str) -> str:
    parts = normalized_remote.split("/")
    if len(parts) >= 3 and parts[0] == "github.com":
        return parts[1]
    return ""


def remote_class(normalized_remote: str) -> str:
    if not normalized_remote:
        return "local-only"
    owner = github_owner(normalized_remote)
    if owner == "organvm":
        return "github-organvm"
    if owner in {name.lower() for name in CONSOLIDATION_SOURCE_OWNERS}:
        return "github-source-owner"
    if normalized_remote.startswith("github.com/"):
        return "github-other"
    return "remote-other"


def path_has_archive_part(path: Path) -> bool:
    return any(part.lower() in {"archive", "archives", "archive4t"} for part in path.parts)


def path_has_worktree_part(path: Path) -> bool:
    parts = set(path.parts)
    return bool({".worktrees", ".limen-worktrees", "worktrees"} & parts)


def nested_parent(path: Path, repo_paths: list[Path]) -> Path | None:
    for candidate in sorted(repo_paths, key=lambda item: len(item.parts), reverse=True):
        if candidate == path:
            continue
        try:
            path.relative_to(candidate)
        except ValueError:
            continue
        return candidate
    return None


def location_class(path: Path, parent: Path | None) -> str:
    if path_has_archive_part(path):
        return "archive"
    if path_has_worktree_part(path):
        return "worktree"
    if parent is not None:
        return "nested"
    return "workspace"


def product_surface_hashes(repo: dict[str, Any]) -> list[str]:
    return [
        str(surface.get("hash"))
        for surface in repo.get("product_surfaces") or []
        if isinstance(surface, dict) and surface.get("hash")
    ]


def disposition_for_repo(
    repo: dict[str, Any],
    *,
    duplicate_remote_hashes: set[str],
    duplicate_product_hashes: set[str],
) -> str:
    remote_hash = str(repo.get("remote_hash") or "")
    if remote_hash and remote_hash in duplicate_remote_hashes:
        return "consolidate"
    if duplicate_product_hashes.intersection(product_surface_hashes(repo)):
        return "consolidate"
    if not repo.get("remote_hash"):
        return "private-sauce"
    if repo.get("classification", {}).get("remote") == "github-source-owner":
        return "blocked-human"
    if repo.get("dirty"):
        return "verify"
    if repo.get("deploy_surfaces"):
        return "publish-stage"
    if repo.get("test_surfaces"):
        return "build"
    return "verify"


def classify_repos(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    repo_paths = [Path(str(repo["path"])) for repo in repos]
    remote_counts: dict[str, int] = {}
    product_counts: dict[str, int] = {}
    for repo in repos:
        remote_hash = repo.get("remote_hash")
        if remote_hash:
            remote_counts[str(remote_hash)] = remote_counts.get(str(remote_hash), 0) + 1
        for surface_hash in product_surface_hashes(repo):
            product_counts[surface_hash] = product_counts.get(surface_hash, 0) + 1
    duplicate_remote_hashes = {key for key, count in remote_counts.items() if count > 1}
    duplicate_product_hashes = {key for key, count in product_counts.items() if count > 1}

    classified: list[dict[str, Any]] = []
    for repo in repos:
        path = Path(str(repo["path"]))
        parent = nested_parent(path, repo_paths)
        remote = remote_class(str(repo.get("normalized_remote") or ""))
        gate = "post-transfer-owner-rewrite-pending" if remote == "github-source-owner" else "none"
        row = {
            **repo,
            "classification": {
                "location": location_class(path, parent),
                "nested": parent is not None,
                "remote": remote,
                "gate": gate,
                "blocker": "none",
            },
        }
        row["classification"]["disposition"] = disposition_for_repo(
            row,
            duplicate_remote_hashes=duplicate_remote_hashes,
            duplicate_product_hashes=duplicate_product_hashes,
        )
        classified.append(row)
    return classified


def count_values(repos: list[dict[str, Any]], field: str, allowed: tuple[str, ...] = ()) -> dict[str, int]:
    counts: dict[str, int] = {name: 0 for name in allowed}
    for repo in repos:
        value = str((repo.get("classification") or {}).get(field) or "unclassified")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def classification_summary(repos: list[dict[str, Any]]) -> dict[str, Any]:
    unclassified = [
        repo
        for repo in repos
        if not repo.get("classification")
        or not (repo.get("classification") or {}).get("location")
        or not (repo.get("classification") or {}).get("remote")
        or not (repo.get("classification") or {}).get("disposition")
    ]
    return {
        "location_counts": count_values(repos, "location", LOCATION_CLASSES),
        "remote_counts": count_values(repos, "remote", REMOTE_CLASSES),
        "disposition_counts": count_values(repos, "disposition", tuple(sorted(DISPOSITIONS))),
        "gate_counts": count_values(repos, "gate", GATE_CLASSES),
        "nested_repo_count": sum(1 for repo in repos if (repo.get("classification") or {}).get("nested")),
        "unclassified_count": len(unclassified),
        "valid_dispositions": sorted(DISPOSITIONS),
    }


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def markdown_field(text: str, field: str) -> str:
    match = re.search(rf"(?m)^\|\s*{re.escape(field)}\s*\|\s*`?([^`|\n]+)`?\s*\|", text)
    return match.group(1).strip() if match else ""


def markdown_backtick_value(text: str, field: str) -> str:
    match = re.search(rf"(?m)^\s*(?:\*\*)?{re.escape(field)}(?:\*\*)?:\s*`([^`]+)`", text)
    return match.group(1).strip() if match else ""


def harvested_receipts() -> list[dict[str, Any]]:
    previous = read_text(DOC_PATH)
    gates = read_text(ROOT / "docs" / "consolidation" / "GATES.md")
    manifest = read_text(ROOT / "docs" / "consolidation" / "EXECUTION-MANIFEST.md")
    plan = read_json(ROOT / "docs" / "current-session-fanout" / "repo-salvage-consolidation-plan-04.json")

    receipts: list[dict[str, Any]] = []
    receipts.append(
        {
            "receipt": relpath(DOC_PATH),
            "status": "existing" if previous else "missing",
            "evidence": {
                "generated_at": markdown_backtick_value(previous, "Generated"),
                "repos_scanned": markdown_backtick_value(previous, "Repos scanned"),
            },
        }
    )
    receipts.append(
        {
            "receipt": relpath(ROOT / "docs" / "consolidation" / "GATES.md"),
            "status": "current" if gates else "missing",
            "evidence": {
                "generated_at": markdown_backtick_value(gates, "Generated"),
                "blocking_gates": markdown_field(gates, "Blocking gates"),
                "source_repos_outside_organvm": markdown_field(gates, "Source repos outside `organvm`"),
                "transfer_apply_gate_open": markdown_field(gates, "Transfer apply gate open"),
                "local_remotes_to_rewrite": markdown_field(gates, "Local remotes to rewrite post-transfer"),
                "app_token_wired": markdown_field(gates, "App token wired"),
            },
        }
    )
    manifest_gate = re.search(r"(?m)^\*\*Gate:\*\*\s*(.+)$", manifest)
    manifest_status = re.search(r"(?m)^\*\*Status:\*\*\s*(.+?)(?:\s{2,})?$", manifest)
    receipts.append(
        {
            "receipt": relpath(ROOT / "docs" / "consolidation" / "EXECUTION-MANIFEST.md"),
            "status": "stale-transfer-stage"
            if manifest and markdown_field(gates, "Transfer apply gate open") == "True"
            else ("existing" if manifest else "missing"),
            "evidence": {
                "status": manifest_status.group(1).strip().rstrip(".") if manifest_status else "",
                "gate": manifest_gate.group(1).strip() if manifest_gate else "",
            },
        }
    )
    receipts.append(
        {
            "receipt": relpath(ROOT / "docs" / "current-session-fanout" / "repo-salvage-consolidation-plan-04.json"),
            "status": str(plan.get("status") or "missing"),
            "evidence": {
                "packet_id": plan.get("packet_id"),
                "blocked_local_work": len(plan.get("blocked_local_work") or []),
                "unconsolidated_plan_hashes": len(
                    ((plan.get("plan_source_proof") or {}).get("unconsolidated_plan_hashes") or [])
                ),
            },
        }
    )
    return receipts


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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
    repos = classify_repos([repo_record(path) for path in repo_roots_under(roots, max_depth=depth, limit=limit)])
    return {
        "generated_at": now_iso(),
        "scan_roots": [relpath(path) for path in roots],
        "repo_count": len(repos),
        "repos": repos,
        "duplicate_remotes": duplicate_remote_groups(repos),
        "classification_summary": classification_summary(repos),
        "harvested_receipts": harvested_receipts(),
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
    summary = public.get("classification_summary") or {}
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
        "## Harvested Receipts",
        "",
        "| Receipt | Status | Evidence |",
        "|---|---|---|",
    ]
    for receipt in public.get("harvested_receipts") or []:
        evidence = ", ".join(
            f"{key}={value}"
            for key, value in (receipt.get("evidence") or {}).items()
            if value not in {None, ""}
        )
        lines.append(
            f"| `{receipt.get('receipt')}` | `{receipt.get('status')}` | {evidence or '`none`'} |"
        )
    if not public.get("harvested_receipts"):
        lines.append("| none | `missing` | `none` |")
    lines += [
        "",
        "## Classification Summary",
        "",
        f"- Unclassified roots: `{summary.get('unclassified_count', 0)}`.",
        f"- Nested repos: `{summary.get('nested_repo_count', 0)}`.",
        "",
        "### Locations",
        "",
        "| Location | Count |",
        "|---|---:|",
    ]
    for name, count in (summary.get("location_counts") or {}).items():
        lines.append(f"| `{name}` | {count} |")
    if not (summary.get("location_counts") or {}):
        lines.append("| none | 0 |")
    lines += [
        "",
        "### Remote Classes",
        "",
        "| Remote class | Count |",
        "|---|---:|",
    ]
    for name, count in (summary.get("remote_counts") or {}).items():
        lines.append(f"| `{name}` | {count} |")
    if not (summary.get("remote_counts") or {}):
        lines.append("| none | 0 |")
    lines += [
        "",
        "### Dispositions",
        "",
        "| Disposition | Count |",
        "|---|---:|",
    ]
    for name, count in (summary.get("disposition_counts") or {}).items():
        lines.append(f"| `{name}` | {count} |")
    if not (summary.get("disposition_counts") or {}):
        lines.append("| none | 0 |")
    lines += [
        "",
        "### Gates",
        "",
        "| Gate | Count |",
        "|---|---:|",
    ]
    for name, count in (summary.get("gate_counts") or {}).items():
        lines.append(f"| `{name}` | {count} |")
    if not (summary.get("gate_counts") or {}):
        lines.append("| none | 0 |")
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
        "| Repo | Branch | Dirty | Remote | Products | Tests | Deploys | Visibility | Location | Remote class | Disposition | Gate |",
        "|---|---|---:|---|---:|---:|---:|---|---|---|---|---|",
    ]
    for repo in public["repos"]:
        products = repo.get("product_surfaces") or []
        classification = repo.get("classification") or {}
        lines.append(
            f"| `{repo['path_label']}` | `{repo['branch']}` | {repo['dirty_count']} | "
            f"`{repo.get('remote_hash') or 'none'}` | {len(products)} | "
            f"{len(repo.get('test_surfaces') or [])} | {len(repo.get('deploy_surfaces') or [])} | "
            f"`{repo['visibility_state']}` | `{classification.get('location', 'unclassified')}` | "
            f"`{classification.get('remote', 'unclassified')}` | "
            f"`{classification.get('disposition', 'unclassified')}` | "
            f"`{classification.get('gate', 'unclassified')}` |"
        )
    lines += [
        "",
        "## Contract",
        "",
        "- Public receipts use hashes for remotes and product surfaces.",
        "- Exact local paths, remote URLs, and product names stay in the ignored private index.",
        "- Every discovered root carries a location class, remote class, disposition, and gate field.",
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
