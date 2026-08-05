#!/usr/bin/env python3
"""Resolve biography source surfaces without collapsing older evidence.

The registry owns the declared source list; this resolver only reports durable
paths and availability. It never synthesizes a current context or reads source
bodies into a public artifact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "institutio" / "governance" / "biography.yaml"


def _source_paths(root: Path, registry: Path) -> list[str]:
    document = yaml.safe_load(registry.read_text(encoding="utf-8")) or {}
    facts = document.get("facts") or {}
    paths: set[str] = set()
    for row in facts.values():
        if not isinstance(row, dict):
            continue
        for source in row.get("source_documents") or []:
            if isinstance(source, str) and source.strip():
                paths.add(source.strip())
    return sorted(paths)


def resolve_biography(root: Path = ROOT, registry: Path = REGISTRY) -> dict:
    """Return a deterministic, body-free union of declared biography sources."""
    sources: list[dict[str, object]] = []
    unavailable: list[str] = []
    for relative in _source_paths(root, registry):
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            unavailable.append(relative)
            continue
        if path.is_dir():
            children = sorted(child for child in path.rglob("*.md") if child.is_file())
            if not children:
                unavailable.append(relative)
                continue
            for child in children:
                sources.append({"path": str(child.relative_to(root)), "available": True})
        elif path.is_file():
            sources.append({"path": relative, "available": True})
        else:
            unavailable.append(relative)
    return {
        "schema": "limen.biography_resolution.v1",
        "sources": sorted(sources, key=lambda item: str(item["path"])),
        "unavailable": sorted(set(unavailable)),
        "source_count": len(sources),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve declared biography sources")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)
    result = resolve_biography()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"biography sources: {result['source_count']}")
        for row in result["sources"]:
            print(f"  available {row['path']}")
        for path in result["unavailable"]:
            print(f"  unavailable {path}")
    return 0 if result["source_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
