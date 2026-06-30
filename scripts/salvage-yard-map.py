#!/usr/bin/env python3
"""Build a hash-only salvage map from repo surface records."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
REPO_SURFACE_INDEX = PRIVATE_ROOT / "lifecycle" / "repo-surface-ledger.json"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "salvage-yard-map.json"
PLAN_PACKET = ROOT / "docs" / "current-session-fanout" / "repo-salvage-consolidation-plan-04.json"

DISPOSITIONS = {
    "build",
    "verify",
    "consolidate",
    "private-sauce",
    "publish-stage",
    "blocked-human",
    "retire",
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        try:
            return str(path.resolve().relative_to(ROOT))
        except (OSError, ValueError):
            return str(path)


def stable_hash(value: str, length: int = 16) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def load_script(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def repo_surface_snapshot() -> dict[str, Any]:
    existing = read_json(REPO_SURFACE_INDEX)
    if existing:
        return existing
    module = load_script(ROOT / "scripts" / "repo-surface-ledger.py", "repo_surface_ledger")
    return module.build_snapshot([])


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def repo_cluster_keys(repo: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    if repo.get("remote_hash"):
        keys.append(f"remote:{repo['remote_hash']}")
    for surface in repo.get("product_surfaces") or []:
        if isinstance(surface, dict) and surface.get("hash"):
            keys.append(f"product:{surface['hash']}")
    return keys


def choose_canonical(repos: list[dict[str, Any]]) -> dict[str, Any]:
    def score(repo: dict[str, Any]) -> tuple[int, int, int, int, str]:
        label = str(repo.get("path_label") or "")
        return (
            0 if repo.get("remote_hash") else 1,
            1 if ".worktrees" in label else 0,
            int(repo.get("dirty_count") or 0),
            len(label),
            label,
        )

    return sorted(repos, key=score)[0]


def disposition_for(repo: dict[str, Any], *, duplicate_cluster: bool = False) -> str:
    if duplicate_cluster:
        return "consolidate"
    if not repo.get("remote_hash"):
        return "private-sauce"
    if repo.get("dirty"):
        return "verify"
    if repo.get("deploy_surfaces"):
        return "publish-stage"
    if repo.get("test_surfaces"):
        return "build"
    return "verify"


def cluster_repos(repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    union = UnionFind(len(repos))
    by_key: dict[str, int] = {}
    for idx, repo in enumerate(repos):
        for key in repo_cluster_keys(repo):
            if key in by_key:
                union.union(by_key[key], idx)
            else:
                by_key[key] = idx

    groups: dict[int, list[dict[str, Any]]] = {}
    for idx, repo in enumerate(repos):
        groups.setdefault(union.find(idx), []).append(repo)

    clusters: list[dict[str, Any]] = []
    for items in groups.values():
        canonical = choose_canonical(items)
        duplicate_cluster = len(items) > 1
        remote_hashes = sorted({str(item.get("remote_hash")) for item in items if item.get("remote_hash")})
        product_hashes = sorted(
            {
                str(surface.get("hash"))
                for item in items
                for surface in (item.get("product_surfaces") or [])
                if isinstance(surface, dict) and surface.get("hash")
            }
        )
        children = []
        for item in sorted(items, key=lambda row: str(row.get("path_label") or "")):
            if item is canonical:
                continue
            children.append(
                {
                    "repo": item.get("path_label"),
                    "remote_hash": item.get("remote_hash"),
                    "product_surface_hashes": [
                        surface.get("hash")
                        for surface in (item.get("product_surfaces") or [])
                        if isinstance(surface, dict) and surface.get("hash")
                    ],
                    "disposition": "consolidate" if duplicate_cluster else disposition_for(item),
                }
            )
        disposition = disposition_for(canonical, duplicate_cluster=duplicate_cluster)
        clusters.append(
            {
                "id": f"SY-{stable_hash('|'.join(remote_hashes + product_hashes + [str(canonical.get('path_label'))]), 10)}",
                "canonical_repo": canonical.get("path_label"),
                "repo_count": len(items),
                "remote_hashes": remote_hashes,
                "product_surface_hashes": product_hashes,
                "disposition": disposition,
                "children": children,
            }
        )
    return sorted(clusters, key=lambda item: str(item.get("canonical_repo") or ""))


def disposition_counts(clusters: list[dict[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in sorted(DISPOSITIONS)}
    for cluster in clusters:
        disposition = str(cluster.get("disposition") or "")
        if disposition in counts:
            counts[disposition] += 1
        for child in cluster.get("children") or []:
            child_disposition = str(child.get("disposition") or "")
            if child_disposition in counts:
                counts[child_disposition] += 1
    return {key: value for key, value in counts.items() if value}


def build_salvage_map(
    repo_snapshot: dict[str, Any] | None = None,
    plan_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    repo_snapshot = repo_snapshot or repo_surface_snapshot()
    plan_packet = plan_packet if plan_packet is not None else read_json(PLAN_PACKET)
    clusters = cluster_repos(list(repo_snapshot.get("repos") or []))
    plan_proof = plan_packet.get("plan_source_proof") if isinstance(plan_packet.get("plan_source_proof"), dict) else {}
    return {
        "generated_at": now_iso(),
        "repo_surface_generated_at": repo_snapshot.get("generated_at"),
        "repo_count": repo_snapshot.get("repo_count", len(repo_snapshot.get("repos") or [])),
        "cluster_count": len(clusters),
        "clusters": clusters,
        "disposition_counts": disposition_counts(clusters),
        "source_plan_hashes": list(plan_proof.get("source_plan_hashes") or []),
        "unconsolidated_plan_hashes": list(plan_proof.get("unconsolidated_plan_hashes") or []),
        "blocked_local_work": list(plan_packet.get("blocked_local_work") or []),
        "executor_stop_conditions": list(plan_packet.get("executor_stop_conditions") or []),
        "privacy": {
            "raw_prompt_bodies_included": False,
            "raw_plan_bodies_included": False,
            "remote_mode": "hash-only",
            "product_surface_mode": "hash-only",
        },
    }


def public_salvage_map(snapshot: dict[str, Any]) -> dict[str, Any]:
    return snapshot


def render_markdown(snapshot: dict[str, Any]) -> str:
    public = public_salvage_map(snapshot)
    lines = [
        "# Salvage Yard Map",
        "",
        f"Generated: `{public['generated_at']}`",
        f"Repo count: `{public['repo_count']}`",
        f"Cluster count: `{public['cluster_count']}`",
        "",
        "## Dispositions",
        "",
        "| Disposition | Count |",
        "|---|---:|",
    ]
    for disposition, count in public.get("disposition_counts", {}).items():
        lines.append(f"| `{disposition}` | {count} |")
    if not public.get("disposition_counts"):
        lines.append("| none | 0 |")
    lines += [
        "",
        "## Clusters",
        "",
        "| Cluster | Canonical repo | Disposition | Repos | Children |",
        "|---|---|---|---:|---:|",
    ]
    for cluster in public.get("clusters") or []:
        lines.append(
            f"| `{cluster['id']}` | `{cluster['canonical_repo']}` | `{cluster['disposition']}` | "
            f"{cluster['repo_count']} | {len(cluster.get('children') or [])} |"
        )
    lines += [
        "",
        "## Contract",
        "",
        "- Duplicate remotes and duplicate product surfaces collapse into one owner cluster.",
        "- Raw prompt and plan bodies are excluded; source provenance is hash-only.",
        "- Irreversible repo consolidation remains staged behind human gates.",
    ]
    return "\n".join(lines) + "\n"


def write_private(snapshot: dict[str, Any]) -> None:
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the repo salvage consolidation map.")
    parser.add_argument("--write", action="store_true", help="write the ignored private structured index")
    parser.add_argument("--dry-run", action="store_true", help="print only; never write")
    parser.add_argument("--json", action="store_true", help="print public JSON instead of markdown")
    args = parser.parse_args()

    snapshot = build_salvage_map()
    if args.write and not args.dry_run:
        write_private(snapshot)
        print(f"salvage-yard-map: wrote {PRIVATE_INDEX}")
        return 0
    if args.json:
        print(json.dumps(public_salvage_map(snapshot), indent=2, sort_keys=True))
    else:
        print(render_markdown(snapshot), end="")
        print("salvage-yard-map: dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
