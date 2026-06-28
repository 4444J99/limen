#!/usr/bin/env python3
"""Inventory local agent capability substrate without reading raw skill bodies.

This is the dedicated resurfacing lane for the roots counted by
session-blockers-ledger.py. It records names, counts, paths, and activation
routes only:

* tracked docs/capability-substrate-ledger.md: public-safe summary;
* ignored .limen-private/.../capability-substrate-index.json: path evidence.

The scanner intentionally does not read SKILL.md or *.skill bodies. It only uses
file names, relative paths, mtimes, and sizes. Plugin/MCP manifests are counted
by path only; their JSON contents are not inspected because they can carry local
commands, env handles, or account-specific wiring.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
DOC_PATH = ROOT / "docs" / "capability-substrate-ledger.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"

CAPABILITY_ROOTS_ENV = "LIMEN_CAPABILITY_ROOTS"
CAPABILITY_SCAN_LIMIT_ENV = "LIMEN_CAPABILITY_SCAN_LIMIT"
DEFAULT_SCAN_LIMIT = 50000
DEFAULT_CAPABILITY_ROOTS = (
    HOME / ".codex" / "skills",
    HOME / ".codex" / "plugins",
    HOME / ".claude" / "plugins",
    HOME / "Workspace" / "organvm" / "_agent",
    HOME / "Workspace" / "organvm" / "claude-runtime-state",
    HOME / "Workspace" / "organvm" / "a-i--skills",
    HOME / "Workspace" / "a-i--skills",
    HOME / "Workspace" / "domus-genoma",
    HOME / "Workspace" / "4444J99",
    ROOT / ".agents",
    ROOT / ".claude" / "skills",
    ROOT / "mcp",
)

CAPABILITY_SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "env",
    "node_modules",
    "venv",
}
SKILL_FILENAMES = {"SKILL.md", "skill.md"}
MANIFEST_FILENAMES = {"plugin.json", ".mcp.json", "mcp.json"}

DOMAIN_KEYWORDS = (
    ("agent_orchestration", ("agent", "swarm", "handoff", "orchestr", "workflow", "coordination")),
    ("session_corpus", ("session", "transcript", "corpus", "memory", "knowledge", "artifact", "prompt")),
    ("mcp_acp", ("mcp", "acp", "connector", "integration", "tool")),
    ("verification_quality", ("verify", "verification", "test", "tdd", "qa", "audit", "review")),
    ("repo_delivery", ("github", "repo", "deployment", "cicd", "monorepo", "worktree")),
    ("product_frontend", ("product", "frontend", "design", "web", "nextjs", "app")),
    ("data_research", ("data", "sql", "analytics", "research", "market", "graph")),
    ("writing_docs", ("doc", "writing", "essay", "presentation", "profile", "curriculum")),
    ("security_ops", ("security", "oauth", "credential", "compliance", "incident", "risk")),
)

ACTIVATION_KEYWORDS = {
    "closeout": 30,
    "session": 26,
    "lifecycle": 26,
    "artifact": 22,
    "transcript": 22,
    "prompt": 22,
    "mcp": 20,
    "acp": 20,
    "agent": 18,
    "swarm": 18,
    "handoff": 18,
    "knowledge": 16,
    "corpus": 16,
    "verification": 15,
    "verify": 15,
    "testing": 12,
    "tdd": 12,
    "github": 12,
    "repo": 12,
    "deployment": 10,
    "cicd": 10,
    "workspace": 10,
    "skill": 8,
}

LANE_PRIORITY = {
    "codex-user-skills": 86,
    "limen-local-skills": 84,
    "organvm-ai-skills": 74,
    "organvm-agent-archive": 70,
    "organvm-runtime-tasks": 64,
    "limen-mcp": 58,
    "domus-genoma-config": 50,
    "workspace-mirror": 42,
    "codex-plugin-cache": 34,
    "claude-plugin-cache": 30,
    "other-capability-root": 25,
}


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def fmt_bytes(n: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    return lowered.strip("-") or "unknown"


def capability_roots() -> list[Path]:
    raw = os.environ.get(CAPABILITY_ROOTS_ENV)
    if raw:
        return [Path(part).expanduser() for part in raw.split(os.pathsep) if part]
    return list(DEFAULT_CAPABILITY_ROOTS)


def scan_limit() -> int:
    raw = os.environ.get(CAPABILITY_SCAN_LIMIT_ENV)
    if not raw:
        return DEFAULT_SCAN_LIMIT
    try:
        return max(100, int(raw))
    except ValueError:
        return DEFAULT_SCAN_LIMIT


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def walk_files(root: Path, *, limit: int) -> tuple[list[Path], bool]:
    if not root.exists():
        return [], False
    out: list[Path] = []
    stack = [root]
    truncated = False
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda path: path.name)
        except OSError:
            continue
        for child in children:
            if child.name in CAPABILITY_SKIP_DIRS:
                continue
            if child.is_dir():
                stack.append(child)
            elif child.is_file():
                out.append(child)
                if len(out) >= limit:
                    return out, True
    return out, truncated


def root_lane(root: Path) -> dict[str, str]:
    root = root.expanduser()
    workspace = HOME / "Workspace"
    if root == HOME / ".codex" / "skills":
        return {
            "lane": "codex-user-skills",
            "owner": "Codex local skill registry",
            "state": "available",
            "route": "Already visible to Codex when the skill registry loads; keep as the active baseline.",
        }
    if is_relative_to(root, HOME / ".codex" / "plugins"):
        return {
            "lane": "codex-plugin-cache",
            "owner": "Codex plugin cache",
            "state": "available-vendor-cache",
            "route": "Already surfaced by installed Codex plugins; do not port cache internals by hand.",
        }
    if is_relative_to(root, HOME / ".claude" / "plugins"):
        return {
            "lane": "claude-plugin-cache",
            "owner": "Claude plugin cache",
            "state": "legacy-plugin-cache",
            "route": "Treat as Claude-side plugin state; inspect only through its plugin owner.",
        }
    if is_relative_to(root, workspace / "organvm" / "a-i--skills") or is_relative_to(
        root, workspace / "a-i--skills"
    ):
        return {
            "lane": "organvm-ai-skills",
            "owner": "organvm/a-i--skills",
            "state": "custom-skill-archive",
            "route": "Port selected high-signal skills into the current Codex skill registry after body review.",
        }
    if is_relative_to(root, workspace / "organvm" / "_agent"):
        return {
            "lane": "organvm-agent-archive",
            "owner": "organvm/_agent",
            "state": "custom-agent-archive",
            "route": "Converge legacy global skills and MCP registry pieces into the current capability layer.",
        }
    if is_relative_to(root, workspace / "organvm" / "claude-runtime-state"):
        return {
            "lane": "organvm-runtime-tasks",
            "owner": "organvm/claude-runtime-state",
            "state": "scheduled-runtime-archive",
            "route": "Convert scheduled-task skills into Limen packets or LaunchAgent receipts, not chat-only memory.",
        }
    if is_relative_to(root, workspace / "domus-genoma"):
        return {
            "lane": "domus-genoma-config",
            "owner": "domus-genoma",
            "state": "config-mcp-wrapper-substrate",
            "route": "Keep as dotfile/config owner state; activate through chezmoi and MCP wrapper receipts.",
        }
    if is_relative_to(root, workspace / "4444J99"):
        return {
            "lane": "workspace-mirror",
            "owner": "4444J99 workspace mirror",
            "state": "mirror-candidate",
            "route": "Use only after checking the source owner; count it so duplicate capability copies are visible.",
        }
    if is_relative_to(root, ROOT / ".agents") or is_relative_to(root, ROOT / ".claude" / "skills"):
        return {
            "lane": "limen-local-skills",
            "owner": "limen",
            "state": "repo-local-active",
            "route": "Keep mirrored local skills minimal and tested by Limen verification.",
        }
    if is_relative_to(root, ROOT / "mcp"):
        return {
            "lane": "limen-mcp",
            "owner": "limen/mcp",
            "state": "active-mcp-server",
            "route": "Treat as Limen MCP implementation; verify through API/CLI and adapter predicates.",
        }
    return {
        "lane": "other-capability-root",
        "owner": "unknown capability owner",
        "state": "detected",
        "route": "Classify the owner before activation.",
    }


def relative_parts(root: Path, path: Path) -> tuple[str, ...]:
    try:
        return path.relative_to(root).parts
    except ValueError:
        return path.parts[-4:]


def skill_name(path: Path) -> str:
    if path.name in SKILL_FILENAMES:
        return path.parent.name
    if path.suffix == ".skill":
        return path.stem
    return path.stem


def namespace_for(root: Path, path: Path) -> str:
    parts = relative_parts(root, path)
    lowered = [part.lower() for part in parts]
    if "scheduled-tasks" in lowered:
        return "scheduled-tasks"
    if ".codex-plugin" in lowered:
        return "plugin-manifest"
    if ".claude-plugin" in lowered:
        return "plugin-manifest"
    if "distributions" in lowered:
        try:
            idx = lowered.index("distributions")
            return "/".join(parts[idx : min(len(parts), idx + 3)])
        except ValueError:
            return "distributions"
    if "skills" in lowered:
        idx = lowered.index("skills")
        if idx + 2 < len(parts):
            return "/".join(parts[idx : idx + 2])
        return "skills"
    if len(parts) > 1:
        return parts[0]
    return "."


def domain_for(slug: str) -> str:
    for domain, needles in DOMAIN_KEYWORDS:
        if any(needle in slug for needle in needles):
            return domain
    return "other"


def file_info(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"bytes": 0, "mtime": None}
    mtime = dt.datetime.fromtimestamp(stat.st_mtime, dt.timezone.utc).isoformat(timespec="seconds")
    return {"bytes": stat.st_size, "mtime": mtime}


def scan_root(root: Path, *, limit: int) -> dict[str, Any]:
    lane = root_lane(root)
    files, truncated = walk_files(root, limit=limit)
    skill_records = []
    manifest_records = []
    mcp_acp_markers = []
    total_bytes = 0
    newest = None

    for path in files:
        info = file_info(path)
        total_bytes += int(info["bytes"] or 0)
        if info["mtime"] and (newest is None or info["mtime"] > newest):
            newest = info["mtime"]
        name = path.name.lower()
        parent_names = {part.lower() for part in path.parts[-6:]}
        rel = "/".join(relative_parts(root, path))
        if path.name in SKILL_FILENAMES or path.suffix == ".skill":
            label = skill_name(path)
            slug = slugify(label)
            skill_records.append(
                {
                    "name": label,
                    "slug": slug,
                    "domain": domain_for(slug),
                    "namespace": namespace_for(root, path),
                    "root": relpath(root),
                    "relpath": rel,
                    "bytes": info["bytes"],
                    "mtime": info["mtime"],
                    "lane": lane["lane"],
                    "owner": lane["owner"],
                    "state": lane["state"],
                }
            )
        if path.name in MANIFEST_FILENAMES or ".claude-plugin" in parent_names or ".codex-plugin" in parent_names:
            manifest_records.append(
                {
                    "name": path.name,
                    "kind": "mcp" if "mcp" in name else "plugin",
                    "root": relpath(root),
                    "relpath": rel,
                    "bytes": info["bytes"],
                    "mtime": info["mtime"],
                    "lane": lane["lane"],
                }
            )
        if "mcp" in name or "acp" in name or "mcp" in parent_names or "acp" in parent_names:
            mcp_acp_markers.append(
                {
                    "name": path.name,
                    "root": relpath(root),
                    "relpath": rel,
                    "bytes": info["bytes"],
                    "mtime": info["mtime"],
                    "lane": lane["lane"],
                }
            )

    unique_names = sorted({item["slug"] for item in skill_records})
    domains = Counter(item["domain"] for item in skill_records)
    namespaces = Counter(item["namespace"] for item in skill_records)
    return {
        "root": relpath(root),
        "lane": lane["lane"],
        "owner": lane["owner"],
        "state": lane["state"],
        "route": lane["route"],
        "present": root.exists(),
        "scanned_files": len(files),
        "truncated": truncated,
        "bytes": total_bytes,
        "newest": newest,
        "skill_files": len(skill_records),
        "unique_skill_names": len(unique_names),
        "plugin_manifests": len(manifest_records),
        "mcp_acp_markers": len(mcp_acp_markers),
        "domain_counts": dict(sorted(domains.items())),
        "namespace_counts": dict(sorted(namespaces.items())),
        "sample_skill_names": [item["name"] for item in sorted(skill_records, key=lambda rec: rec["slug"])[:14]],
        "skills": skill_records,
        "manifests": manifest_records,
        "mcp_acp": mcp_acp_markers,
    }


def candidate_score(record: dict[str, Any]) -> int:
    slug = str(record["slug"])
    score = LANE_PRIORITY.get(str(record.get("lane")), 25)
    for keyword, bonus in ACTIVATION_KEYWORDS.items():
        if keyword in slug:
            score += bonus
    if record.get("state") in {"available", "repo-local-active"}:
        score += 8
    namespace = str(record.get("namespace") or "")
    if namespace.startswith("distributions"):
        score -= 10
    if "staging" in namespace:
        score -= 14
    if record.get("lane") in {"codex-plugin-cache", "claude-plugin-cache"}:
        score -= 24
    return score


def activation_route(record: dict[str, Any]) -> str:
    lane = str(record.get("lane"))
    if lane == "codex-user-skills":
        return "Already active in the Codex skill registry; keep as baseline."
    if lane == "limen-local-skills":
        return "Already repo-local; keep mirrored only when Limen verification needs it."
    if lane == "organvm-ai-skills":
        return "Port after body review into `~/.codex/skills` or a checked-in Limen skill."
    if lane == "organvm-agent-archive":
        return "Converge the legacy agent skill into the current Codex skill format."
    if lane == "organvm-runtime-tasks":
        return "Convert into a scheduled Limen work packet or LaunchAgent receipt."
    if lane == "limen-mcp":
        return "Verify through Limen MCP/API predicates before exposing as a tool route."
    if lane == "domus-genoma-config":
        return "Activate through the dotfile/config owner, not by copying local wrappers."
    if lane == "workspace-mirror":
        return "Check source-owner freshness before treating this mirror as canonical."
    return "Classify owner and review body before activation."


def build_activation_queue(roots: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    by_slug: dict[str, dict[str, Any]] = {}
    for root in roots:
        for record in root["skills"]:
            scored = dict(record)
            scored["score"] = candidate_score(record)
            scored["activation_route"] = activation_route(record)
            current = by_slug.get(scored["slug"])
            if current is None or (scored["score"], -len(scored["relpath"])) > (
                current["score"],
                -len(current["relpath"]),
            ):
                by_slug[scored["slug"]] = scored
    return sorted(by_slug.values(), key=lambda rec: (-int(rec["score"]), rec["slug"]))[:limit]


def build_snapshot(*, limit: int) -> dict[str, Any]:
    existing_roots = [root for root in capability_roots() if root.exists()]
    root_rows = [scan_root(root, limit=scan_limit()) for root in existing_roots]
    skill_records = [skill for root in root_rows for skill in root["skills"]]
    manifest_records = [manifest for root in root_rows for manifest in root["manifests"]]
    mcp_acp_records = [marker for root in root_rows for marker in root["mcp_acp"]]
    slug_counts = Counter(skill["slug"] for skill in skill_records)
    domain_counts = Counter(skill["domain"] for skill in skill_records)
    lane_counts = Counter(root["lane"] for root in root_rows)
    duplicate_slugs = [
        {"slug": slug, "count": count}
        for slug, count in sorted(slug_counts.items(), key=lambda item: (-item[1], item[0]))
        if count > 1
    ][:20]

    activation_queue = build_activation_queue(root_rows, limit=limit)
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in activation_queue:
        if len(grouped[item["domain"]]) < 10:
            grouped[item["domain"]].append(str(item["name"]))

    coverage = {
        "roots_seen": len(root_rows),
        "scanned_files": sum(int(root["scanned_files"]) for root in root_rows),
        "truncated_roots": sum(1 for root in root_rows if root["truncated"]),
        "skill_files": len(skill_records),
        "unique_skill_names": len(slug_counts),
        "plugin_manifests": len(manifest_records),
        "mcp_acp_markers": len(mcp_acp_records),
        "bytes": sum(int(root["bytes"]) for root in root_rows),
        "domain_counts": dict(sorted(domain_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "duplicate_skill_names": duplicate_slugs,
    }
    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "decision": "names-counts-paths-only; skill bodies and plugin manifest contents are not read",
        "coverage": coverage,
        "roots": [
            {key: value for key, value in root.items() if key not in {"skills", "manifests", "mcp_acp"}}
            for root in root_rows
        ],
        "skills": skill_records,
        "plugin_manifests": manifest_records,
        "mcp_acp_markers": mcp_acp_records,
        "activation_queue": activation_queue,
        "activation_groups": dict(sorted(grouped.items())),
        "private_index": str(PRIVATE_INDEX),
    }


def render_markdown(snapshot: dict[str, Any], *, limit: int) -> str:
    coverage = snapshot["coverage"]
    lane_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["lane_counts"].items()) or "none"
    domain_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["domain_counts"].items()) or "none"
    lines = [
        "# Capability Substrate Ledger",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- This ledger resurfaces local skills, plugins, MCP/ACP markers, and scheduled capability roots by names, counts, paths, and activation routes only.",
        "- It does not read or print `SKILL.md` bodies, `*.skill` bodies, plugin manifest contents, credential values, or raw prompt/session text.",
        "- Current Codex-session skills remain the active baseline; legacy Claude/custom archives are activation candidates, not automatically installed tools.",
        "- Activation means owner review, body review, then a small checked-in or Codex-home skill/plugin change with its own verification.",
        "",
        "## Coverage",
        "",
        f"- Roots seen: `{coverage['roots_seen']}`.",
        f"- Scanned files: `{coverage['scanned_files']}`; truncated roots: `{coverage['truncated_roots']}`.",
        f"- Skill files: `{coverage['skill_files']}`; unique skill names: `{coverage['unique_skill_names']}`.",
        f"- Plugin/MCP manifests: `{coverage['plugin_manifests']}`; MCP/ACP markers: `{coverage['mcp_acp_markers']}`.",
        f"- Capability bytes counted by metadata only: `{fmt_bytes(int(coverage.get('bytes') or 0))}`.",
        f"- Lanes: {lane_bits}.",
        f"- Domains: {domain_bits}.",
        "",
        "## Roots",
        "",
        "| Root | Lane | State | Skills | Unique | Plugin/MCP | MCP/ACP | Files | Route |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for root in snapshot["roots"]:
        lines.append(
            f"| `{root['root']}` | `{root['lane']}` | `{root['state']}` | "
            f"{root['skill_files']} | {root['unique_skill_names']} | {root['plugin_manifests']} | "
            f"{root['mcp_acp_markers']} | {root['scanned_files']} | {root['route']} |"
        )

    lines += [
        "",
        "## Activation Queue",
        "",
        "| Rank | Capability | Domain | Lane | Score | Source | Route |",
        "|---:|---|---|---|---:|---|---|",
    ]
    for idx, item in enumerate(snapshot["activation_queue"][:limit], start=1):
        lines.append(
            f"| {idx} | `{item['name']}` | `{item['domain']}` | `{item['lane']}` | "
            f"{item['score']} | `{item['root']}/{item['relpath']}` | {item['activation_route']} |"
        )
    if not snapshot["activation_queue"]:
        lines.append("| 0 | none | n/a | n/a | 0 | n/a | No activation candidates found. |")

    lines += [
        "",
        "## High-Signal Groups",
        "",
    ]
    for domain, names in snapshot["activation_groups"].items():
        lines.append(f"- `{domain}`: " + ", ".join(f"`{name}`" for name in names) + ".")
    if not snapshot["activation_groups"]:
        lines.append("- none.")

    duplicates = coverage.get("duplicate_skill_names") or []
    if duplicates:
        lines += [
            "",
            "## Duplicate Names",
            "",
        ]
        lines.append(
            "- "
            + ", ".join(f"`{item['slug']}` x{item['count']}" for item in duplicates[:12])
            + "."
        )

    lines += [
        "",
        "## Private Output",
        "",
        f"- Private capability index: `{relpath(PRIVATE_INDEX)}`.",
        "- The private index keeps path-level evidence and metadata counts; it still contains no skill body text, plugin manifest content, secret values, or raw prompts.",
        "",
        "## Commands",
        "",
        "- Refresh capability resurfacing: `python3 scripts/capability-substrate-ledger.py --write`",
        "- Refresh parked blockers after capability resurfacing: `python3 scripts/session-blockers-ledger.py --write`",
        "- Refresh ranked attack paths: `python3 scripts/session-attack-paths.py --write`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the redacted capability substrate ledger.")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    parser.add_argument("--limit", type=int, default=30, help="activation candidates to show")
    args = parser.parse_args()

    limit = max(1, args.limit)
    snapshot = build_snapshot(limit=limit)
    markdown = render_markdown(snapshot, limit=limit)
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = (
        "capability-substrate-ledger: "
        f"{snapshot['coverage']['roots_seen']} roots, "
        f"{snapshot['coverage']['skill_files']} skill files, "
        f"{snapshot['coverage']['plugin_manifests']} plugin/MCP manifests"
    )
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
