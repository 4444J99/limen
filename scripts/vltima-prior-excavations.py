#!/usr/bin/env python3
"""Register prior excavation surfaces before wider VLTIMA estate scans.

This is the "excavate the excavations prior" layer. It inventories existing
Limen census/ledger/preservation surfaces by metadata only, then writes:

* tracked docs/vltima-prior-excavations.md: redacted operator register;
* ignored .limen-private/.../vltima-prior-excavations.json: path-level index.

It intentionally does not read raw prompt bodies, private object-store text,
skill bodies, or plugin manifest contents. Private JSON is summarized by keys,
collection counts, and timestamps only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CODE_ROOT = Path(__file__).resolve().parents[1]
STATE_ROOT = Path(os.environ.get("LIMEN_STATE_ROOT", os.environ.get("LIMEN_ROOT", CODE_ROOT))).expanduser().resolve()


def writable_output_root() -> Path:
    explicit = os.environ.get("LIMEN_OUTPUT_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_root = os.environ.get("LIMEN_ROOT")
    if env_root:
        candidate = Path(env_root).expanduser()
        docs = candidate / "docs"
        if os.access(candidate, os.W_OK) and (docs.exists() or os.access(candidate, os.W_OK)):
            return candidate.resolve()
    return CODE_ROOT


OUTPUT_ROOT = writable_output_root()
STATE_PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", STATE_ROOT / ".limen-private" / "session-corpus")
).expanduser()
OUTPUT_PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_OUTPUT_PRIVATE_SESSION_CORPUS", OUTPUT_ROOT / ".limen-private" / "session-corpus")
).expanduser()
DOC_PATH = OUTPUT_ROOT / "docs" / "vltima-prior-excavations.md"
PRIVATE_INDEX = OUTPUT_PRIVATE_ROOT / "lifecycle" / "vltima-prior-excavations.json"

GENERATED_RE = re.compile(r"^Generated:\s*`?([^`\n]+)`?", re.MULTILINE)
PRIVATE_OBJECT_MARKERS = (
    "/objects/",
    "/corpus-command-center/objects/",
    "/full-stack-review/session-",
)


@dataclass(frozen=True)
class SurfaceSpec:
    id: str
    lane: str
    role: str
    script: str | None = None
    tracked: tuple[str, ...] = ()
    private: tuple[str, ...] = ()
    logs: tuple[str, ...] = ()
    command: str = ""
    refresh_mode: str = "dry-run-first"
    notes: str = ""
    depends_on: tuple[str, ...] = ()


SURFACES: tuple[SurfaceSpec, ...] = (
    SurfaceSpec(
        id="session-corpus-ledger",
        lane="session-corpus",
        role="local session/corpus material inventory and private object materialization register",
        script="scripts/session-corpus-ledger.py",
        tracked=("docs/session-corpus-ledger.md",),
        private=(".limen-private/session-corpus/inventory/session-corpus-ledger.json",),
        command="python3 scripts/session-corpus-ledger.py --write",
        refresh_mode="write-safe-redacted",
    ),
    SurfaceSpec(
        id="prompt-lifecycle-ledger",
        lane="prompt-lifecycle",
        role="prompt/session/worktree/task/GitHub crosswalk",
        script="scripts/prompt-lifecycle-ledger.py",
        tracked=("docs/prompt-lifecycle-ledger.md",),
        private=(".limen-private/session-corpus/lifecycle/prompt-lifecycle-index.json",),
        command="python3 scripts/prompt-lifecycle-ledger.py --write --all",
        refresh_mode="write-safe-redacted",
        depends_on=("session-corpus-ledger",),
    ),
    SurfaceSpec(
        id="session-lifecycle-blockers",
        lane="priority-routing",
        role="redacted blockers over prompt/session lifecycle surfaces",
        script="scripts/session-blockers-ledger.py",
        tracked=("docs/session-lifecycle-blockers.md",),
        private=(".limen-private/session-corpus/lifecycle/session-lifecycle-blockers.json",),
        command="python3 scripts/session-blockers-ledger.py --write",
        refresh_mode="write-safe-redacted",
        depends_on=("prompt-lifecycle-ledger",),
    ),
    SurfaceSpec(
        id="session-lifecycle-pressure",
        lane="priority-routing",
        role="local/remote lifecycle pressure for hooks and orientation",
        script="scripts/session-lifecycle-pressure.py",
        logs=("logs/session-lifecycle-pressure.json", "logs/session-lifecycle-pressure.md"),
        command="python3 scripts/session-lifecycle-pressure.py --write",
        refresh_mode="write-safe-ignored",
        depends_on=("prompt-lifecycle-ledger", "worktree-preservation"),
    ),
    SurfaceSpec(
        id="session-attack-paths",
        lane="priority-routing",
        role="ranked attack paths from redacted prompt/worktree/blocker evidence",
        script="scripts/session-attack-paths.py",
        tracked=("docs/session-attack-paths.md",),
        private=(".limen-private/session-corpus/lifecycle/session-attack-paths.json",),
        command="python3 scripts/session-attack-paths.py --write",
        refresh_mode="write-safe-redacted",
        depends_on=("session-lifecycle-blockers", "session-lifecycle-pressure"),
    ),
    SurfaceSpec(
        id="prompt-priority-map",
        lane="priority-routing",
        role="review batches and hash/session priority map",
        script="scripts/prompt-priority-map.py",
        tracked=("docs/prompt-priority-map.md",),
        private=(".limen-private/session-corpus/lifecycle/prompt-priority-map.json",),
        command="python3 scripts/prompt-priority-map.py --write",
        refresh_mode="write-safe-redacted",
        depends_on=("session-attack-paths",),
    ),
    SurfaceSpec(
        id="corpus-command-center",
        lane="session-corpus",
        role="aggregate corpus surface over prompts, replies, artifacts, tasks, and positioning",
        script="scripts/corpus-command-center.py",
        tracked=("docs/corpus-command-center.md",),
        private=(
            ".limen-private/session-corpus/lifecycle/corpus-command-center.private.json",
            ".limen-private/session-corpus/lifecycle/corpus-command-center.public.json",
            ".limen-private/session-corpus/lifecycle/corpus-command-center.private.html",
        ),
        command="python3 scripts/corpus-command-center.py --write",
        refresh_mode="write-safe-redacted",
        depends_on=("prompt-lifecycle-ledger", "prompt-priority-map"),
    ),
    SurfaceSpec(
        id="repo-surface-ledger",
        lane="repo-surfaces",
        role="local repo/product/test/deploy surface ledger",
        script="scripts/repo-surface-ledger.py",
        tracked=("docs/repo-surface-ledger.md",),
        private=(".limen-private/session-corpus/lifecycle/repo-surface-ledger.json",),
        command="python3 scripts/repo-surface-ledger.py --max-depth 8 --dry-run",
        refresh_mode="dry-run-first",
        notes="Tracked receipt can be stale/shallow; run with explicit scan roots before trusting coverage.",
    ),
    SurfaceSpec(
        id="capability-substrate-ledger",
        lane="capability-substrate",
        role="skills/plugins/MCP markers by metadata only",
        script="scripts/capability-substrate-ledger.py",
        tracked=("docs/capability-substrate-ledger.md",),
        private=(".limen-private/session-corpus/lifecycle/capability-substrate-index.json",),
        command="python3 scripts/capability-substrate-ledger.py --write",
        refresh_mode="write-safe-redacted",
    ),
    SurfaceSpec(
        id="product-ledger",
        lane="product-surface",
        role="prompt-to-product/product-to-owner surface",
        script="scripts/product-ledger.py",
        tracked=("docs/product-ledger.md",),
        private=(".limen-private/session-corpus/lifecycle/product-ledger.json",),
        command="python3 scripts/product-ledger.py --write",
        refresh_mode="write-safe-redacted",
        depends_on=("repo-surface-ledger", "prompt-lifecycle-ledger"),
    ),
    SurfaceSpec(
        id="substrate-ledger",
        lane="archive-durability",
        role="mounted/configured local substrates and storage pressure",
        script="scripts/substrate-ledger.py",
        tracked=("docs/substrate-ledger.md",),
        private=(".limen-private/session-corpus/lifecycle/substrate-ledger.json",),
        command="python3 scripts/substrate-ledger.py --write",
        refresh_mode="write-safe-redacted",
    ),
    SurfaceSpec(
        id="worktree-preservation",
        lane="worktree-preservation",
        role="worktree debt plus preservation receipts before any reclaim",
        script="scripts/worktree-debt.py",
        tracked=(
            "docs/worktree-lifecycle-ledger.md",
            "docs/worktree-preservation-receipts.json",
            "docs/worktree-reclaim-acceptance.md",
            "docs/removal-acceptance-covenant.md",
        ),
        private=(".limen-private/session-corpus/lifecycle/worktree-preserve",),
        command="python3 scripts/worktree-debt.py --json",
        refresh_mode="read-only",
    ),
    SurfaceSpec(
        id="prompt-batch-review-ledger",
        lane="prompt-lifecycle",
        role="review batches and recorded prompt-batch dispositions",
        script="scripts/prompt-batch-review-ledger.py",
        tracked=("docs/prompt-batch-review-ledger.md", "docs/prompt-batch-resolution-receipts.json"),
        private=(".limen-private/session-corpus/lifecycle/prompt-batch-review-ledger.json",),
        command="python3 scripts/prompt-batch-review-ledger.py --write",
        refresh_mode="write-safe-redacted",
        depends_on=("prompt-priority-map",),
    ),
    SurfaceSpec(
        id="prompt-packet-ledger",
        lane="prompt-lifecycle",
        role="open/recorded prompt packets and packet-resolution receipts",
        script="scripts/prompt-packet-ledger.py",
        tracked=("docs/prompt-packet-ledger.md", "docs/prompt-packet-resolution-receipts.json"),
        private=(".limen-private/session-corpus/lifecycle/prompt-packet-ledger.json",),
        command="python3 scripts/prompt-packet-ledger.py --write",
        refresh_mode="write-safe-redacted",
    ),
    SurfaceSpec(
        id="agent-session-full-stack-review",
        lane="session-corpus",
        role="cross-agent session review with private prompt extracts",
        script="scripts/agent-session-full-stack-review.py",
        tracked=("docs/agent-session-full-stack-review.md",),
        private=(".limen-private/session-corpus/full-stack-review",),
        command="python3 scripts/agent-session-full-stack-review.py --write",
        refresh_mode="dry-run-first",
        notes="Can produce large private extracts; use only for selected review windows.",
    ),
    SurfaceSpec(
        id="agent-reconstruction-review",
        lane="session-corpus",
        role="session/worktree reconstruction review over preserved evidence",
        script="scripts/agent-reconstruction-review.py",
        tracked=("docs/agent-reconstruction-review.md",),
        private=(".limen-private/session-corpus/full-stack-review/agent-reconstruction-review.json",),
        command="python3 scripts/agent-reconstruction-review.py --write",
        refresh_mode="dry-run-first",
    ),
    SurfaceSpec(
        id="agent-code-review-queue",
        lane="session-corpus",
        role="changed-file/session queue for prompt-vs-code review",
        script="scripts/agent-code-review-queue.py",
        tracked=("docs/agent-code-review-queue.md", "docs/agent-code-diff-review.md"),
        private=(".limen-private/session-corpus/full-stack-review/agent-code-review-queue.json",),
        command="python3 scripts/agent-code-review-queue.py --write",
        refresh_mode="dry-run-first",
    ),
    SurfaceSpec(
        id="session-value-review",
        lane="priority-routing",
        role="session value review over batch receipts, commits, and queue state",
        script="scripts/session-value-review.py",
        tracked=("docs/session-value-review.md",),
        private=(".limen-private/session-corpus/lifecycle/session-value-review.json",),
        command="python3 scripts/session-value-review.py --write",
        refresh_mode="write-safe-redacted",
    ),
    SurfaceSpec(
        id="antigravity-scratch-bridge",
        lane="worktree-preservation",
        role="Antigravity scratch preservation and bridge receipts",
        script="scripts/antigravity-scratch-bridge.py",
        tracked=(
            "docs/antigravity-scratch-bridge.md",
            "docs/antigravity-scratch-preservation.jsonl",
            "docs/antigravity-scratch-bridge-history.jsonl",
        ),
        private=(".limen-private/session-corpus/lifecycle/agy-scratch-preserve",),
        command="python3 scripts/antigravity-scratch-bridge.py --help",
        refresh_mode="manual-only",
        notes="Preservation can copy large scratch roots; never run as generic refresh.",
    ),
    SurfaceSpec(
        id="hooks-excavation",
        lane="hooks-orientation",
        role="prior hook inventory and implementation plan",
        tracked=("docs/hooks-excavation-and-plan.md",),
        command="read docs/hooks-excavation-and-plan.md",
        refresh_mode="manual-doc",
    ),
    SurfaceSpec(
        id="offsite-durability-proposal",
        lane="archive-durability",
        role="Archive4T/T7Recovery/offsite tier proposal and measured sliver scope",
        tracked=("docs/OFFSITE-DURABILITY-PROPOSAL-2026-06-19.md",),
        command="read docs/OFFSITE-DURABILITY-PROPOSAL-2026-06-19.md",
        refresh_mode="manual-doc",
    ),
    SurfaceSpec(
        id="library-preserve",
        lane="archive-durability",
        role="personal library/workspace additive preservation organ",
        script="scripts/library-preserve.py",
        logs=("logs/library-levers.json",),
        command="python3 scripts/library-preserve.py",
        refresh_mode="manual-only",
        notes="Dry-run by default; apply mode preserves data and is not part of prior-register refresh.",
    ),
    SurfaceSpec(
        id="pre-build-excavate",
        lane="repo-surfaces",
        role="pre-build duplicate-work excavation predicate over PR/commit streams",
        script="scripts/pre-build-excavate.sh",
        tracked=("docs/pre-build-excavate.md",),
        command="scripts/pre-build-excavate.sh <owner/repo> [keyword ...]",
        refresh_mode="read-only",
    ),
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def repo_rel(path: Path, *, root: Path = STATE_ROOT) -> str:
    try:
        return str(path.expanduser().resolve().relative_to(root))
    except (OSError, ValueError):
        try:
            return str(path.expanduser().relative_to(root))
        except ValueError:
            return str(path.expanduser())


def path_from_label(label: str, *, root: Path = STATE_ROOT, private_root: Path = STATE_PRIVATE_ROOT) -> Path:
    if label.startswith(".limen-private/session-corpus/"):
        return private_root / label.removeprefix(".limen-private/session-corpus/")
    return (root / label).expanduser()


def file_mtime(path: Path) -> str | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def is_private_body_path(path: Path) -> bool:
    text = str(path)
    return any(marker in text for marker in PRIVATE_OBJECT_MARKERS)


def json_summary(path: Path) -> dict[str, Any] | None:
    if is_private_body_path(path):
        return {"skipped": "private-body-path"}
    if path.is_dir():
        try:
            children = list(path.iterdir())
        except OSError:
            return {"kind": "directory", "readable": False}
        return {
            "kind": "directory",
            "entries": len(children),
            "json_files": sum(1 for child in children if child.suffix in {".json", ".jsonl"}),
        }
    if path.suffix not in {".json", ".jsonl"}:
        return None
    if path.suffix == ".jsonl":
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                count = sum(1 for _line in handle)
        except OSError:
            return {"kind": "jsonl", "readable": False}
        return {"kind": "jsonl", "records": count}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"kind": "json", "readable": False}
    if isinstance(data, dict):
        counts = {key: len(value) for key, value in data.items() if isinstance(value, (list, dict))}
        return {
            "kind": "json",
            "top_level": "dict",
            "keys": sorted(data.keys())[:20],
            "collection_counts": dict(sorted(counts.items())[:20]),
            "generated_at": data.get("generated_at"),
        }
    if isinstance(data, list):
        return {"kind": "json", "top_level": "list", "records": len(data)}
    return {"kind": "json", "top_level": type(data).__name__}


def markdown_generated_at(path: Path) -> str | None:
    if path.suffix.lower() != ".md":
        return None
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return None
    match = GENERATED_RE.search(text)
    return match.group(1).strip() if match else None


def artifact_record(label: str, kind: str, *, root: Path, private_root: Path) -> dict[str, Any]:
    path = path_from_label(label, root=root, private_root=private_root)
    exists = path.exists()
    summary = json_summary(path) if exists and kind == "private" else None
    generated_at = None
    if exists:
        generated_at = markdown_generated_at(path)
        if generated_at is None and summary:
            generated_at = summary.get("generated_at")
    return {
        "label": label,
        "kind": kind,
        "exists": exists,
        "is_dir": path.is_dir() if exists else False,
        "mtime": file_mtime(path) if exists else None,
        "generated_at": generated_at,
        "summary": summary,
        "path": str(path),
    }


def newest(values: list[str | None]) -> str | None:
    present = [value for value in values if value]
    return max(present) if present else None


def surface_status(script_exists: bool, tracked_count: int, private_count: int, log_count: int, stale: bool) -> str:
    output_count = tracked_count + private_count + log_count
    if output_count == 0 and not script_exists:
        return "manual-or-missing"
    if output_count == 0:
        return "script-only"
    if tracked_count == 0 and private_count > 0:
        return "private-only"
    if private_count == 0 and tracked_count > 0:
        return "tracked-only"
    if stale:
        return "stale"
    return "current"


def build_surface(spec: SurfaceSpec, *, root: Path, private_root: Path) -> dict[str, Any]:
    script_exists = bool(spec.script and (root / spec.script).exists())
    script_mtime = file_mtime(root / spec.script) if spec.script else None
    tracked = [artifact_record(label, "tracked", root=root, private_root=private_root) for label in spec.tracked]
    private = [artifact_record(label, "private", root=root, private_root=private_root) for label in spec.private]
    logs = [artifact_record(label, "log", root=root, private_root=private_root) for label in spec.logs]
    all_outputs = tracked + private + logs
    tracked_count = sum(1 for item in tracked if item["exists"])
    private_count = sum(1 for item in private if item["exists"])
    log_count = sum(1 for item in logs if item["exists"])
    output_newest = newest([item.get("mtime") for item in all_outputs])
    generated_at = newest([item.get("generated_at") for item in all_outputs])
    stale = bool(script_mtime and output_newest and output_newest < script_mtime)
    status = surface_status(script_exists, tracked_count, private_count, log_count, stale)
    return {
        "id": spec.id,
        "lane": spec.lane,
        "role": spec.role,
        "script": spec.script,
        "script_exists": script_exists,
        "script_mtime": script_mtime,
        "tracked": tracked,
        "private": private,
        "logs": logs,
        "tracked_present": tracked_count,
        "private_present": private_count,
        "logs_present": log_count,
        "generated_at": generated_at,
        "output_newest": output_newest,
        "status": status,
        "refresh_mode": spec.refresh_mode,
        "command": spec.command,
        "notes": spec.notes,
        "depends_on": list(spec.depends_on),
    }


def lane_for_path(path: Path) -> str:
    text = str(path).lower()
    for lane, needles in (
        ("session-corpus", ("corpus", "full-stack", "session-value", "agent-session", "agent-reconstruction")),
        ("prompt-lifecycle", ("prompt",)),
        ("repo-surfaces", ("repo", "surface")),
        ("product-surface", ("product",)),
        ("capability-substrate", ("capability", "skill", "plugin", "mcp")),
        ("worktree-preservation", ("worktree", "preservation", "reap", "removal")),
        ("archive-durability", ("archive", "offsite", "substrate", "library")),
        ("hooks-orientation", ("hook", "orient")),
        ("priority-routing", ("attack", "blocker", "priority", "pressure")),
    ):
        if any(needle in text for needle in needles):
            return lane
    return "other"


def iter_bounded(base: Path, max_depth: int) -> list[Path]:
    rows: list[Path] = []
    stack: list[tuple[Path, int]] = [(base, 0)]
    while stack:
        current, depth = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: str(item))
        except OSError:
            continue
        for child in children:
            child_depth = depth + 1
            rows.append(child)
            if child.is_dir() and child_depth < max_depth:
                stack.append((child, child_depth))
    return rows


def discover_artifacts(*, root: Path, private_root: Path, known_labels: set[str]) -> list[dict[str, Any]]:
    candidates: list[tuple[Path, str]] = []
    for base, kind in (
        (root / "scripts", "script"),
        (root / "docs", "tracked"),
        (private_root / "lifecycle", "private"),
        (private_root / "inventory", "private"),
        (root / "logs", "log"),
    ):
        if not base.exists():
            continue
        max_depth = 1 if base.name == "logs" else 2
        for path in iter_bounded(base, max_depth):
            if not path.is_file() and not path.is_dir():
                continue
            name = path.name.lower()
            text = str(path).lower()
            if not any(
                token in name or token in text
                for token in (
                    "ledger",
                    "census",
                    "corpus",
                    "surface",
                    "receipt",
                    "preserv",
                    "excavat",
                    "lifecycle",
                    "index",
                    "review",
                    "substrate",
                    "priority",
                    "attack",
                    "blocker",
                )
            ):
                continue
            candidates.append((path, kind))
    rows = []
    seen: set[str] = set()
    for path, kind in sorted(candidates, key=lambda item: str(item[0])):
        label = repo_rel(path, root=root)
        if label in known_labels or label in seen:
            continue
        if ".limen-private/session-corpus/corpus-command-center/objects/" in label:
            continue
        seen.add(label)
        rows.append(
            {
                "label": label,
                "kind": kind,
                "lane": lane_for_path(path),
                "mtime": file_mtime(path),
                "is_dir": path.is_dir(),
                "summary": json_summary(path) if kind == "private" else None,
                "path": str(path),
            }
        )
    return rows


def refresh_order(surfaces: list[dict[str, Any]]) -> list[str]:
    by_id = {surface["id"]: surface for surface in surfaces}
    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(surface_id: str) -> None:
        if surface_id in ordered or surface_id in visiting:
            return
        visiting.add(surface_id)
        for dep in by_id.get(surface_id, {}).get("depends_on", []):
            if dep in by_id:
                visit(dep)
        visiting.remove(surface_id)
        ordered.append(surface_id)

    preferred = (
        "session-corpus-ledger",
        "prompt-lifecycle-ledger",
        "session-lifecycle-blockers",
        "session-lifecycle-pressure",
        "session-attack-paths",
        "prompt-priority-map",
        "corpus-command-center",
        "capability-substrate-ledger",
        "repo-surface-ledger",
        "product-ledger",
        "substrate-ledger",
    )
    for surface_id in preferred:
        visit(surface_id)
    for surface in surfaces:
        visit(str(surface["id"]))
    return ordered


def build_snapshot(
    *,
    root: Path = STATE_ROOT,
    private_root: Path = STATE_PRIVATE_ROOT,
    output_root: Path = OUTPUT_ROOT,
    output_private_root: Path = OUTPUT_PRIVATE_ROOT,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    private_root = private_root.expanduser()
    output_root = output_root.expanduser().resolve()
    output_private_root = output_private_root.expanduser()
    surfaces = [build_surface(spec, root=root, private_root=private_root) for spec in SURFACES]
    known_labels: set[str] = set()
    for surface in surfaces:
        for group in ("tracked", "private", "logs"):
            known_labels.update(str(item["label"]) for item in surface[group])
        if surface.get("script"):
            known_labels.add(str(surface["script"]))
    discovered = discover_artifacts(root=root, private_root=private_root, known_labels=known_labels)
    lane_counts = Counter(surface["lane"] for surface in surfaces)
    status_counts = Counter(surface["status"] for surface in surfaces)
    refresh_counts = Counter(surface["refresh_mode"] for surface in surfaces)
    coverage = {
        "surface_count": len(surfaces),
        "discovered_extra_artifacts": len(discovered),
        "tracked_outputs": sum(surface["tracked_present"] for surface in surfaces),
        "private_outputs": sum(surface["private_present"] for surface in surfaces),
        "log_outputs": sum(surface["logs_present"] for surface in surfaces),
        "scripts_present": sum(1 for surface in surfaces if surface["script_exists"]),
        "status_counts": dict(sorted(status_counts.items())),
        "lane_counts": dict(sorted(lane_counts.items())),
        "refresh_mode_counts": dict(sorted(refresh_counts.items())),
    }
    mismatches = [
        {
            "surface": surface["id"],
            "lane": surface["lane"],
            "status": surface["status"],
            "reason": "missing or asymmetric outputs",
        }
        for surface in surfaces
        if surface["status"] not in {"current", "tracked-only"}
    ]
    return {
        "generated_at": now_iso(),
        "decision": "prior-excavation metadata register; raw private bodies are not read",
        "privacy": {
            "tracked_output": repo_rel(output_root / "docs" / "vltima-prior-excavations.md", root=output_root),
            "private_index": str(output_private_root / "lifecycle" / "vltima-prior-excavations.json"),
            "raw_bodies_read": False,
        },
        "coverage": coverage,
        "surfaces": surfaces,
        "discovered_artifacts": discovered,
        "mismatches": mismatches,
        "refresh_order": refresh_order(surfaces),
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    coverage = snapshot["coverage"]
    lane_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["lane_counts"].items())
    status_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["status_counts"].items())
    refresh_bits = ", ".join(f"`{key}` {value}" for key, value in coverage["refresh_mode_counts"].items())
    lines = [
        "# VLTIMA Prior Excavations",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- Before a new estate-wide VLTIMA scan, excavate and reconcile the prior excavations.",
        "- This register is metadata-only: it reads paths, mtimes, JSON keys, collection counts, and tracked generated timestamps.",
        "- It does not read raw prompt bodies, private object-store text, skill bodies, plugin manifest contents, or credential values.",
        "- Tracked output is redacted; exact path-level evidence and private JSON summaries live in the ignored private index.",
        "",
        "## Coverage",
        "",
        f"- Prior surfaces: `{coverage['surface_count']}`.",
        f"- Scripts present: `{coverage['scripts_present']}`.",
        f"- Outputs present: tracked `{coverage['tracked_outputs']}`, private `{coverage['private_outputs']}`, logs `{coverage['log_outputs']}`.",
        f"- Discovered extra artifacts: `{coverage['discovered_extra_artifacts']}`.",
        f"- Lanes: {lane_bits or 'none'}.",
        f"- Statuses: {status_bits or 'none'}.",
        f"- Refresh modes: {refresh_bits or 'none'}.",
        "",
        "## Refresh Order",
        "",
    ]
    for idx, surface_id in enumerate(snapshot["refresh_order"], start=1):
        surface = next(item for item in snapshot["surfaces"] if item["id"] == surface_id)
        lines.append(f"{idx}. `{surface_id}` - `{surface['refresh_mode']}` - {surface['command'] or 'manual review'}")
    lines += [
        "",
        "## Prior Excavation Surfaces",
        "",
        "| Surface | Lane | Status | Outputs | Refresh | Command |",
        "|---|---|---|---:|---|---|",
    ]
    for surface in snapshot["surfaces"]:
        outputs = surface["tracked_present"] + surface["private_present"] + surface["logs_present"]
        command = str(surface["command"] or "manual review").replace("|", "\\|")
        lines.append(
            f"| `{surface['id']}` | `{surface['lane']}` | `{surface['status']}` | {outputs} | "
            f"`{surface['refresh_mode']}` | `{command}` |"
        )
    lines += [
        "",
        "## Mismatches To Reconcile",
        "",
    ]
    if snapshot["mismatches"]:
        lines += ["| Surface | Lane | Status | Reason |", "|---|---|---|---|"]
        for item in snapshot["mismatches"]:
            lines.append(f"| `{item['surface']}` | `{item['lane']}` | `{item['status']}` | {item['reason']} |")
    else:
        lines.append("- No prior-excavation mismatches detected.")
    lines += [
        "",
        "## Extra Artifacts",
        "",
        "These matched excavation naming patterns but are not part of the canonical surface list yet.",
        "",
    ]
    extras = snapshot["discovered_artifacts"][:40]
    if extras:
        lines += ["| Artifact | Lane | Kind |", "|---|---|---|"]
        for item in extras:
            lines.append(f"| `{item['label']}` | `{item['lane']}` | `{item['kind']}` |")
        remaining = len(snapshot["discovered_artifacts"]) - len(extras)
        if remaining > 0:
            lines.append(f"| `...` | `truncated` | `{remaining} more in private index` |")
    else:
        lines.append("- No extra excavation artifacts detected.")
    lines += [
        "",
        "## Contract",
        "",
        "- This register does not authorize deletion, dedupe, branch cleanup, repo movement, archive rewrite, or task-board mutation.",
        "- `Archive4T` and other mounted volumes are read-only inputs unless a separate preservation command explicitly owns a copy operation.",
        "- A stale or partial prior excavation is a routing signal, not a global blocker.",
        "- The next VLTIMA estate census must reuse these surfaces before adding a new scanner.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(
    snapshot: dict[str, Any], markdown: str, *, doc_path: Path = DOC_PATH, private_index: Path = PRIVATE_INDEX
) -> None:
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    private_index.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(markdown, encoding="utf-8")
    private_index.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the VLTIMA prior-excavations register.")
    parser.add_argument("--write", action="store_true", help="write tracked summary and private index")
    parser.add_argument("--json", action="store_true", help="print private-style JSON snapshot")
    args = parser.parse_args()
    snapshot = build_snapshot()
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(snapshot, markdown)
        print(f"vltima-prior-excavations: wrote {DOC_PATH} and {PRIVATE_INDEX}")
    elif args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(markdown, end="")
        print("vltima-prior-excavations: dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
