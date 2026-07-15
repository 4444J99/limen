#!/usr/bin/env python3
"""Audit direct `tasks.yaml` writers.

Tabularius is the board record-keeper. During migration there are legacy direct writers, but they
must stay explicit and counted. This script prevents new "one more writer" regressions and gives
the heartbeat/operator a precise list to burn down.
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
SEARCH_ROOTS = (ROOT / "scripts", ROOT / "cli" / "src", ROOT / "mcp" / "src")
OUT = ROOT / "logs" / "task-writer-audit.json"
DOC_OUT = ROOT / "docs" / "tabularius-writer-audit.md"

ALLOWED_DIRECT_WRITERS = {
    "scripts/tabularius-organ.py",
    "cli/src/limen/tabularius.py",
    "cli/src/limen/io.py",
}
BOARD_NAME_HINTS = {"board", "tasks", "tasks_file", "tasks_yaml"}
BOARD_SOURCE_HINTS = {"LIMEN_TASKS", "tasks.yaml"}

OWNER_PACKETS = {
    "TAB-STATUS-DISPATCH-RESULTS": {
        "tier": "status-result",
        "owner": "codex-integrator",
        "predicate": "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q",
        "disposition": "convert dispatch claim/result application to task.status tickets or keeper-drained status batches",
    },
    "TAB-STATUS-HARVEST-RESULTS": {
        "tier": "status-result",
        "owner": "codex-integrator",
        "predicate": "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q",
        "disposition": "convert harvest/Jules landing result application to task.status tickets",
    },
    "TAB-HUMAN-ATOM-STATUS-WRITERS": {
        "tier": "human-atom-status",
        "owner": "codex-integrator",
        "predicate": "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q",
        "disposition": "convert continuity/routine needs_human atom upserts to keeper-owned status/upsert tickets",
    },
    "TAB-STATUS-ASYNC-HEAL": {
        "tier": "status-result",
        "owner": "codex-integrator",
        "predicate": "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py cli/tests/test_async_dispatch.py -q",
        "disposition": "convert async reserve/reap/heal transitions to task.status tickets with no double-dispatch window",
    },
    "TAB-ROUTE-RESIDUE-MUTATORS": {
        "tier": "routing-metadata",
        "owner": "codex-integrator",
        "predicate": "PYTHONPATH=cli/src python3 -m pytest cli/tests/test_tabularius.py -q",
        "disposition": "convert routing, residue, and self-improve board patches to keeper-owned tickets",
    },
    "TAB-CREATION-FALLBACKS": {
        "tier": "creation-fallback",
        "owner": "codex-integrator",
        "predicate": "python3 scripts/task-writer-audit.py",
        "disposition": "remove or gate legacy direct fallback branches after producer parity is proven live",
    },
    "TAB-MAINTENANCE-BOARD-FALLBACKS": {
        "tier": "board-maintenance",
        "owner": "codex-integrator",
        "predicate": "python3 scripts/task-writer-audit.py",
        "disposition": "decide whether each maintenance writer belongs to Tabularius/io allowlist or becomes a ticket producer",
    },
    "TAB-UNCLASSIFIED-WRITER": {
        "tier": "unclassified",
        "owner": "codex-integrator",
        "predicate": "python3 scripts/task-writer-audit.py",
        "disposition": "classify this writer before Step 2.2 can be owner-recorded",
    },
}


def rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except OSError:
        return str(path)


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def source_hint(node: ast.AST) -> bool:
    try:
        src = ast.unparse(node)
    except Exception:
        return False
    return any(hint in src for hint in BOARD_SOURCE_HINTS)


def assigned_names(target: ast.AST) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        out: list[str] = []
        for elt in target.elts:
            out.extend(assigned_names(elt))
        return out
    return []


def board_path_names(tree: ast.AST) -> set[str]:
    names = {"TASKS", "TASKS_FILE", "TASKS_PATH", "BOARD", "tasks_path", "board_path"}
    for node in ast.walk(tree):
        value: ast.AST | None = None
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        if value is None or not source_hint(value):
            continue
        for target in targets:
            names.update(assigned_names(target))
    return names


def looks_like_board_arg(node: ast.AST, names: set[str]) -> bool:
    if source_hint(node):
        return True
    if isinstance(node, ast.Name):
        if node.id in names:
            return True
        lower = node.id.lower()
        return any(hint in lower for hint in BOARD_NAME_HINTS)
    if isinstance(node, ast.Attribute):
        lower = node.attr.lower()
        return any(hint in lower for hint in BOARD_NAME_HINTS)
    return False


def direct_writer_calls(path: Path) -> list[dict[str, object]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    names = board_path_names(tree)
    rows: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = call_name(node.func)
        if name in {"save_limen_file", "atomic_write_text"} and node.args and looks_like_board_arg(node.args[0], names):
            rows.append({"path": rel(path), "line": getattr(node, "lineno", None), "call": name})
            continue
        if name.endswith(".write_text") and isinstance(node.func, ast.Attribute):
            if looks_like_board_arg(node.func.value, names):
                rows.append({"path": rel(path), "line": getattr(node, "lineno", None), "call": name})
    return rows


def owner_packet(path: str) -> str:
    if path == "cli/src/limen/dispatch.py":
        return "TAB-STATUS-DISPATCH-RESULTS"
    if path in {"cli/src/limen/harvest.py", "scripts/jules-land.py"}:
        return "TAB-STATUS-HARVEST-RESULTS"
    if path in {"scripts/dispatch-continuity-check.py", "scripts/routine-freshness-audit.py"}:
        return "TAB-HUMAN-ATOM-STATUS-WRITERS"
    if path in {"scripts/dispatch-async.py", "scripts/heal-dispatch.py"}:
        return "TAB-STATUS-ASYNC-HEAL"
    if path in {"scripts/quicken.py", "scripts/rewrite-owners.py", "scripts/route.py", "scripts/self-improve.py"}:
        return "TAB-ROUTE-RESIDUE-MUTATORS"
    if path in {"scripts/mine-backlog.py", "scripts/self-heal.py"}:
        return "TAB-CREATION-FALLBACKS"
    if path in {"cli/src/limen/cli.py", "scripts/heal-board.py", "scripts/usage-telemetry.py"}:
        return "TAB-MAINTENANCE-BOARD-FALLBACKS"
    return "TAB-UNCLASSIFIED-WRITER"


def enrich_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        packet = owner_packet(str(row["path"]))
        out.append({**row, "owner_packet": packet, "tier": OWNER_PACKETS[packet]["tier"]})
    return out


def packet_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        packet = str(row["owner_packet"])
        counts[packet] = counts.get(packet, 0) + 1
    return dict(sorted(counts.items()))


def write_doc(rows: list[dict[str, object]]) -> None:
    counts = packet_counts(rows)
    unclassified = counts.get("TAB-UNCLASSIFIED-WRITER", 0)
    lines = [
        "# Tabularius Writer Audit",
        "",
        "<!-- tabularius-writer-audit:owner-recorded -->",
        "",
        f"Direct writer calls: `{len(rows)}`",
        f"Unclassified calls: `{unclassified}`",
        "",
        "## Owner Packets",
        "",
        "| Packet | Tier | Calls | Owner | Predicate | Disposition |",
        "|---|---|---:|---|---|---|",
    ]
    for packet, count in counts.items():
        meta = OWNER_PACKETS[packet]
        lines.append(
            f"| `{packet}` | `{meta['tier']}` | `{count}` | `{meta['owner']}` | "
            f"`{meta['predicate']}` | {meta['disposition']} |"
        )
    lines.extend(["", "## Direct Writers", "", "| Path | Line | Call | Owner packet |", "|---|---:|---|---|"])
    for row in rows:
        lines.append(f"| `{row['path']}` | `{row['line']}` | `{row['call']}` | `{row['owner_packet']}` |")
    lines.extend(
        [
            "",
            "## Contract",
            "",
            "- This receipt does not bless direct writers as done; it prevents hidden writer drift.",
            "- Step 2.2 is owner-recorded when every remaining direct writer maps to a bounded packet and no row is unclassified.",
            "- The burn-down remains complete only when this audit exits zero or the remaining writers are explicitly allowlisted as Tabularius/io ownership.",
        ]
    )
    DOC_OUT.parent.mkdir(parents=True, exist_ok=True)
    DOC_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def python_files() -> list[Path]:
    files: list[Path] = []
    for root in SEARCH_ROOTS:
        if root.is_dir():
            files.extend(root.rglob("*.py"))
    return sorted(files)


def main() -> int:
    rows: list[dict[str, object]] = []
    for path in python_files():
        r = rel(path)
        if r in ALLOWED_DIRECT_WRITERS:
            continue
        rows.extend(direct_writer_calls(path))

    rows = enrich_rows(rows)
    payload = {
        "allowed_direct_writers": sorted(ALLOWED_DIRECT_WRITERS),
        "direct_writer_count": len(rows),
        "owner_packet_counts": packet_counts(rows),
        "direct_writers": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_doc(rows)
    if rows:
        print(f"task-writer-audit: {len(rows)} legacy direct writer call(s); see {rel(OUT)} and {rel(DOC_OUT)}")
        for row in rows[:20]:
            print(f"  {row['path']}:{row['line']} {row['call']}")
        return 1
    print("task-writer-audit: PASS — only Tabularius/io can write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
