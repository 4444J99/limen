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

ALLOWED_DIRECT_WRITERS = {
    "scripts/tabularius-organ.py",
    "cli/src/limen/tabularius.py",
    "cli/src/limen/io.py",
}
BOARD_NAME_HINTS = {"board", "tasks", "tasks_file", "tasks_yaml"}
BOARD_SOURCE_HINTS = {"LIMEN_TASKS", "tasks.yaml"}


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
        if name in {"save_limen_file", "atomic_write_text"} and node.args and looks_like_board_arg(
            node.args[0], names
        ):
            rows.append({"path": rel(path), "line": getattr(node, "lineno", None), "call": name})
            continue
        if name.endswith(".write_text") and isinstance(node.func, ast.Attribute):
            if looks_like_board_arg(node.func.value, names):
                rows.append({"path": rel(path), "line": getattr(node, "lineno", None), "call": name})
    return rows


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

    payload = {
        "allowed_direct_writers": sorted(ALLOWED_DIRECT_WRITERS),
        "direct_writer_count": len(rows),
        "direct_writers": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if rows:
        print(f"task-writer-audit: {len(rows)} legacy direct writer call(s); see {rel(OUT)}")
        for row in rows[:20]:
            print(f"  {row['path']}:{row['line']} {row['call']}")
        return 1
    print("task-writer-audit: PASS — only Tabularius/io can write the board")
    return 0


if __name__ == "__main__":
    sys.exit(main())
