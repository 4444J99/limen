#!/usr/bin/env python3
"""Prove that lifecycle state reaches ``tasks.yaml`` only through its keepers.

The audit is deliberately source-based: it catches a new Python, JavaScript, or
instruction-layer bypass before that code can race the canonical projection.
``cli/src/limen/io.py`` owns a local byte serializer for explicitly noncanonical
exports, while the authenticated conduct projection in
``web/worker/src/conduct/projection.js`` is the sole logical lifecycle writer
and owns the remote GitHub compare-and-swap. The TABVLARIVS compatibility relay
is intentionally scanned: it may queue and archive tickets but must not write,
commit, push, reset, or refresh ``tasks.yaml``.

Usage::

    python3 scripts/task-writer-audit.py
    python3 scripts/task-writer-audit.py --enforce-zero
    python3 scripts/task-writer-audit.py --check

The first two deterministically refresh the tracked Markdown receipt and the
ignored JSON detail. ``--check`` is read-only. All modes fail when even one
unauthorized writer or direct-write instruction remains.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
PYTHON_ROOTS = (
    "scripts",
    "cli/src",
    "mcp/src",
    "web/api",
)
JAVASCRIPT_ROOTS = ("web/worker/src",)
SHELL_ROOTS = ("scripts",)
INSTRUCTION_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    ".agents/skills/agy_conductor/SKILL.md",
)
OUT = ROOT / "logs" / "task-writer-audit.json"
DOC_OUT = ROOT / "docs" / "tabularius-writer-audit.md"

AUTHORIZED_PROJECTION_WRITERS = {
    "cli/src/limen/io.py": "noncanonical local cache/export serializer; no lifecycle authority",
    "web/worker/src/conduct/projection.js": "sole lifecycle writer; authenticated remote GitHub SHA-CAS",
}
NON_PRODUCTION_PARTS = {"test", "tests", "__pycache__", "node_modules", ".venv"}
BOARD_NAME_RE = re.compile(r"(?:^|_)(?:board|tasks?)(?:$|_)", re.IGNORECASE)
BOARD_SOURCE_RE = re.compile(r"LIMEN_TASKS|tasks\.ya?ml|task_file|board_path", re.IGNORECASE)
GIT_MUTATION_RE = re.compile(r"\b(?:stash|pull|push)\b", re.IGNORECASE)
SHELL_BOARD_REF_RE = re.compile(
    r"(?:tasks\.ya?ml|\$(?:\{)?(?:LIMEN_TASKS|TASKS|TASKS_FILE|TASKS_PATH)(?:\})?)",
    re.IGNORECASE,
)
SHELL_BOARD_MUTATION_RE = re.compile(
    r"(?:"
    r"(?:^|[;&|]\s*)(?:cp|mv|install|rm|truncate|tee)\b|"
    r"\b(?:sed|perl|yq)\b[^\n]*(?:\s-i\b|\s--in-place\b)|"
    r"\bgit\s+(?:add|checkout|commit|pull|push|reset|restore|stash)\b|"
    r">>?\s*[\"']?(?:tasks\.ya?ml|\$(?:\{)?(?:LIMEN_TASKS|TASKS|TASKS_FILE|TASKS_PATH)(?:\})?)"
    r")",
    re.IGNORECASE,
)
SHELL_DERIVED_ALLOW_MARKER = "task-writer-audit: allow-derived-sandbox"
FORBIDDEN_GUIDANCE = (
    (
        "direct-board-write-guidance",
        re.compile(
            r"(?:edit|write|mutate|update|rewrite|read/write)\s+`?tasks\.ya?ml`?\s+directly",
            re.IGNORECASE,
        ),
    ),
    (
        "direct-board-git-guidance",
        re.compile(
            r"(?:git\s+(?:add|commit|push)[^\n]{0,100}tasks\.ya?ml|"
            r"(?:commit|push|stage)\s+`?tasks\.ya?ml`?)",
            re.IGNORECASE,
        ),
    ),
)


def rel(path: Path, root: Path = ROOT) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def source(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def assigned_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(assigned_names(element) for element in target.elts))
    return set()


def boardish_name(value: str) -> bool:
    return bool(BOARD_NAME_RE.search(value))


def boardish_expr(node: ast.AST, names: set[str]) -> bool:
    rendered = source(node)
    if BOARD_SOURCE_RE.search(rendered):
        return True
    if isinstance(node, ast.Name):
        return node.id in names or boardish_name(node.id)
    if isinstance(node, ast.Attribute):
        return node.attr in names or boardish_name(node.attr)
    return False


def literal_words(node: ast.AST) -> str:
    values: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            values.append(child.value)
    return " ".join(values)


class PythonWriterVisitor(ast.NodeVisitor):
    """Scope-aware writer detector.

    The former audit collected every assignment in an entire module. A harmless
    ``path`` in usage telemetry was therefore mistaken for a board path because
    another function mentioned ``tasks.yaml``. Each function/module now owns a
    separate name set, while direct keeper calls are rejected regardless of the
    caller's local variable spelling.
    """

    def __init__(self, path: str):
        self.path = path
        self.scope_names: list[set[str]] = [{"TASKS", "TASKS_FILE", "TASKS_PATH", "tasks_path", "board_path"}]
        self.scope_functions: list[str] = ["<module>"]
        self.scope_has_board_write: list[bool] = [False]
        self.rows: list[dict[str, Any]] = []

    @property
    def names(self) -> set[str]:
        return self.scope_names[-1]

    @property
    def function(self) -> str:
        return self.scope_functions[-1]

    def row(self, node: ast.AST, kind: str, call: str) -> None:
        self.rows.append(
            {
                "path": self.path,
                "line": int(getattr(node, "lineno", 0) or 0),
                "kind": kind,
                "call": call,
                "function": self.function,
            }
        )
        if kind != "board-git-sync":
            self.scope_has_board_write[-1] = True

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        initial = {
            name
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
            if boardish_name(name := arg.arg)
        }
        self.scope_names.append(set(self.scope_names[0]) | initial)
        self.scope_functions.append(node.name)
        self.scope_has_board_write.append(False)
        for statement in node.body:
            self.visit(statement)
        self.scope_names.pop()
        self.scope_functions.pop()
        self.scope_has_board_write.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if BOARD_SOURCE_RE.search(source(node.value)):
            for target in node.targets:
                self.names.update(assigned_names(target))
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and BOARD_SOURCE_RE.search(source(node.value)):
            self.names.update(assigned_names(node.target))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = call_name(node.func)
        short = name.rsplit(".", 1)[-1]
        if short == "open":
            target: ast.AST | None = None
            mode_nodes: list[ast.AST] = []
            if isinstance(node.func, ast.Attribute):
                target = node.func.value
                mode_nodes = list(node.args[:1])
            elif node.args:
                target = node.args[0]
                mode_nodes = list(node.args[1:2])
            mode_nodes.extend(keyword.value for keyword in node.keywords if keyword.arg == "mode")
            mode = " ".join(literal_words(value) for value in mode_nodes)
            if target is not None and boardish_expr(target, self.names) and re.search(r"[wax+]", mode):
                self.row(node, "direct-yaml-writer", name)
        elif short in {"save_limen_file", "restore_limen_text"}:
            self.row(node, "direct-yaml-writer", name)
        elif short == "atomic_write_text" and node.args and boardish_expr(node.args[0], self.names):
            self.row(node, "direct-yaml-writer", name)
        elif short in {"write_text", "write_bytes"} and isinstance(node.func, ast.Attribute):
            if boardish_expr(node.func.value, self.names):
                self.row(node, "direct-yaml-writer", name)
        elif short == "replace" and node.args and boardish_expr(node.args[0], self.names):
            self.row(node, "direct-yaml-writer", name)
        elif short in {"save_board", "save_github_board"}:
            self.row(node, "direct-board-writer", name)
        elif (
            short in {"github_request", "request", "put"}
            and re.search(r"\bPUT\b", literal_words(node), re.IGNORECASE)
            and (
                BOARD_SOURCE_RE.search(source(node))
                or re.search(r"(?:board|tasks?|github).*(?:save|write|commit)", self.function, re.IGNORECASE)
            )
        ):
            self.row(node, "direct-remote-projection", name)
        elif short in {"run", "Popen", "check_call", "check_output", "_git"}:
            command = literal_words(node)
            function_is_board_sync = re.search(r"(?:save|board|tasks?).*(?:sync|write)", self.function, re.IGNORECASE)
            if (
                re.search(r"\bgit\b", command, re.IGNORECASE)
                and GIT_MUTATION_RE.search(command)
                and (BOARD_SOURCE_RE.search(command) or function_is_board_sync or self.scope_has_board_write[-1])
            ):
                self.row(node, "board-git-sync", name)
        self.generic_visit(node)


def audit_python_source(text: str, path: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as exc:
        return [
            {
                "path": path,
                "line": int(exc.lineno or 0),
                "kind": "audit-parse-error",
                "call": "ast.parse",
                "function": "<module>",
            }
        ]
    visitor = PythonWriterVisitor(path)
    visitor.visit(tree)
    return visitor.rows


def audit_javascript_source(text: str, path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    direct_put_lines = {
        text[: match.start()].count("\n") + 1
        for match in re.finditer(
            r"(?:githubRequest|fetch)\s*\([^;]{0,800}?\b(?:method\s*:\s*)?[\"']PUT[\"']",
            text,
            re.IGNORECASE | re.DOTALL,
        )
    }
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if re.search(r"\b(?:async\s+)?function\s+saveBoard\s*\(", stripped):
            rows.append(
                {
                    "path": path,
                    "line": number,
                    "kind": "direct-board-writer",
                    "call": "function saveBoard",
                    "function": "saveBoard",
                }
            )
        elif re.search(r"\bsaveBoard\s*\(", stripped):
            rows.append(
                {
                    "path": path,
                    "line": number,
                    "kind": "direct-board-writer",
                    "call": "saveBoard",
                    "function": "<javascript>",
                }
            )
        if number in direct_put_lines:
            rows.append(
                {
                    "path": path,
                    "line": number,
                    "kind": "direct-remote-projection",
                    "call": "GitHub/fetch PUT",
                    "function": "<javascript>",
                }
            )
    return rows


def audit_shell_source(text: str, path: str) -> list[dict[str, Any]]:
    """Reject explicit shell mutation of the canonical board.

    Shell is intentionally checked line-by-line: lifecycle scripts must use a
    named broker command, not construct a multi-line board rewrite. A retained
    verification harness may mark only the exact sandbox-copy line with the
    derived-sandbox marker.
    """

    rows: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or SHELL_DERIVED_ALLOW_MARKER in line
            or not SHELL_BOARD_REF_RE.search(line)
            or not SHELL_BOARD_MUTATION_RE.search(line)
        ):
            continue
        rows.append(
            {
                "path": path,
                "line": number,
                "kind": "direct-shell-board-writer",
                "call": stripped[:160],
                "function": "<shell>",
            }
        )
    return rows


def audit_instruction_text(text: str, path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), 1):
        negative = re.search(
            r"\b(?:never|do not|must not|cannot|may not)\b[^\n]{0,100}"
            r"(?:edit|write|mutate|update|rewrite|push|commit|stage)",
            line,
            re.IGNORECASE,
        )
        for kind, pattern in FORBIDDEN_GUIDANCE:
            if pattern.search(line) and not negative:
                rows.append(
                    {
                        "path": path,
                        "line": number,
                        "kind": kind,
                        "call": pattern.pattern,
                        "function": "<instructions>",
                    }
                )
                break
    return rows


def production_files(root: Path, roots: Iterable[str], suffix: str) -> list[Path]:
    files: list[Path] = []
    for relative in roots:
        base = root / relative
        if not base.is_dir():
            continue
        files.extend(
            path
            for path in base.rglob(f"*{suffix}")
            if not NON_PRODUCTION_PARTS.intersection(path.relative_to(root).parts)
        )
    return sorted(set(files), key=lambda path: rel(path, root))


def audit_repo(root: Path = ROOT) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in production_files(root, PYTHON_ROOTS, ".py"):
        relative = rel(path, root)
        if relative in AUTHORIZED_PROJECTION_WRITERS:
            continue
        rows.extend(audit_python_source(path.read_text(encoding="utf-8"), relative))
    for path in production_files(root, JAVASCRIPT_ROOTS, ".js"):
        relative = rel(path, root)
        if relative in AUTHORIZED_PROJECTION_WRITERS:
            continue
        rows.extend(audit_javascript_source(path.read_text(encoding="utf-8"), relative))
    for path in production_files(root, SHELL_ROOTS, ".sh"):
        relative = rel(path, root)
        rows.extend(audit_shell_source(path.read_text(encoding="utf-8"), relative))
    for relative in INSTRUCTION_FILES:
        path = root / relative
        if path.is_file():
            rows.extend(audit_instruction_text(path.read_text(encoding="utf-8"), relative))
    rows.sort(key=lambda row: (str(row["path"]), int(row["line"]), str(row["kind"]), str(row["call"])))
    return {
        "schema_version": "limen.task_writer_audit.v2",
        "authorized_projection_writers": [
            {"path": path, "role": AUTHORIZED_PROJECTION_WRITERS[path]}
            for path in sorted(AUTHORIZED_PROJECTION_WRITERS)
        ],
        "unauthorized_writer_count": len(rows),
        "unauthorized_writers": rows,
    }


def write_receipts(payload: dict[str, Any], root: Path = ROOT) -> None:
    output = root / OUT.relative_to(ROOT)
    document = root / DOC_OUT.relative_to(ROOT)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    rows = payload["unauthorized_writers"]
    lines = [
        "# TABVLARIVS Writer Audit",
        "",
        "<!-- tabularius-writer-audit:zero-unauthorized -->",
        "",
        f"Unauthorized lifecycle writers: `{len(rows)}`",
        "",
        "## Authorized Projection Writers",
        "",
        "| Path | Role |",
        "|---|---|",
    ]
    for writer in payload["authorized_projection_writers"]:
        lines.append(f"| `{writer['path']}` | {writer['role']} |")
    lines.extend(
        [
            "",
            "## Unauthorized Findings",
            "",
            "| Path | Line | Kind | Call | Function |",
            "|---|---:|---|---|---|",
        ]
    )
    if rows:
        for row in rows:
            lines.append(
                f"| `{row['path']}` | `{row['line']}` | `{row['kind']}` | `{row['call']}` | `{row['function']}` |"
            )
    else:
        lines.append("| (none) |  |  |  |  |")
    lines.extend(
        [
            "",
            "## Predicate",
            "",
            "```bash",
            "python3 scripts/task-writer-audit.py --enforce-zero",
            "```",
            "",
            "The predicate is a zero gate, not a baseline ratchet. It scans production Python, "
            "shell, Cloudflare Worker JavaScript, and canonical agent instructions. TABVLARIVS "
            "itself is scanned and has no local projection exemption. Derived inspection/exports "
            "may use the noncanonical serializer or an exact-line sandbox marker, but lifecycle "
            "mutation must submit immutable tickets or conduct packets and wait for the remote "
            "keeper receipt.",
        ]
    )
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="audit unauthorized tasks.yaml lifecycle writers")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--enforce-zero",
        action="store_true",
        help="refresh receipts and fail unless the unauthorized writer count is zero",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="read-only zero gate; do not refresh generated receipts",
    )
    args = parser.parse_args(argv)

    payload = audit_repo(ROOT)
    if not args.check:
        write_receipts(payload, ROOT)
    count = int(payload["unauthorized_writer_count"])
    if count:
        print(f"task-writer-audit: FAIL — {count} unauthorized lifecycle writer(s)")
        for row in payload["unauthorized_writers"][:30]:
            print(f"  {row['path']}:{row['line']} {row['kind']} {row['call']}")
        return 1
    print("task-writer-audit: PASS — zero unauthorized lifecycle writers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
