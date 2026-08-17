#!/usr/bin/env python3
"""Record-keeper covenant drift predicate — holds the covenant registry to the repo.

TABVLARIVS is the sole writer of the testament surfaces (the memory dir + tasks.yaml). The
registry (institutio/governance/covenant.yaml) declares each surface's sole writer, its lane
(the ticket a session submits so a blocked write is never lost), and its enforcement ids. This
predicate proves the declaration, the scripts, and the charter have not drifted apart. Exit 0
⟺ no drift.

Sequencing law: the lane exists before the wall; nothing arms by merge. Every check is
PENDING-tolerant where the lane/wall has not yet landed — an unbuilt lane and an unarmed guard
are GREEN, so each covenant PR merges as a green no-op. Once a lane file or the arming flag is
present, the corresponding check gains teeth.

Named checks (mirrors scripts/check-removal-acceptance.py's structure):
  A  schema validity — required fields per entry; path_kind enum; in_repo needs path,
     out_of_repo needs path_env + index_file; agent writers with ticket lanes need keeper_env
  B  writer-exists — the drain script exists; board needs cli/src/limen/tabularius.py
  C  lane-exists (PENDING-tolerant) — memory lane files may be absent (GREEN); once present,
     the submit CLI compiles and the engine defines submit_memory_ticket + drain_memory_once;
     board's submit funcs live in tabularius.py
  D  no-other-writer — scan scripts/, cli/src/, mcp/src/ for writes to the MEMORY surface
     outside the allowlist (board's teeth are task-writer-audit — delegated, not duplicated)
  E  enforcement parity (RATCHET-gated) — armed false → warn only; armed true → the hook and
     its settings.json wiring must exist; declared gate/sensor ids are verified only if present
  F  out-of-repo CI safety — resolve the memory dir; if it is absent, schema-only, never fail
  G  doc parity — the charter names every entry's path/path_env, sole writer, and submit command

Run directly (``scripts/check-covenant.py``) or via pr-gate / verify-whole.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from covenant import (  # noqa: E402
    COVENANT_DOC,
    MEMORY_READONLY_TOLERATED,
    MEMORY_WRITER_ALLOWLIST,
    covenant_entries,
    resolve_memory_dir,
)

VALID_PATH_KINDS = {"in_repo", "out_of_repo"}
DRAIN_SCRIPT = "scripts/tabularius-organ.py"
BOARD_ENGINE = "cli/src/limen/tabularius.py"
MEMORY_SUBMIT_CLI = "scripts/memory-ticket.py"
MEMORY_ENGINE = "cli/src/limen/memoria.py"
MEMORY_ENGINE_FUNCS = ("submit_memory_ticket", "drain_memory_once")
BOARD_SUBMIT_FUNCS = ("submit_task_upsert", "submit_task_status")
# Scan roots for the no-other-writer sweep (check D).
SCAN_SUBDIRS = ("scripts", "cli/src", "mcp/src")
# Memory-path write signals: a string literal a write call targets.
MEMORY_WRITE_TOKENS = ("LIMEN_MEMORY_DIR", "MEMORY.md", ".covenant-inbox", ".covenant-archive")
WRITE_CALLS = {"write_text", "write_bytes"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        return str(path)


# ── A: schema validity ────────────────────────────────────────────────────────
def check_schema(entries: dict) -> list[str]:
    errors: list[str] = []
    if not entries:
        return ["schema: covenant.yaml declares no covenants"]
    for name, entry in entries.items():
        for field in ("title", "path_kind", "sole_writer", "lane", "enforcement"):
            if not entry.get(field):
                errors.append(f"schema[{name}]: missing `{field}`")
        path_kind = entry.get("path_kind")
        if path_kind not in VALID_PATH_KINDS:
            errors.append(f"schema[{name}]: path_kind must be one of {sorted(VALID_PATH_KINDS)}")
        elif path_kind == "in_repo" and not entry.get("path"):
            errors.append(f"schema[{name}]: in_repo needs `path`")
        elif path_kind == "out_of_repo" and not (entry.get("path_env") and entry.get("index_file")):
            errors.append(f"schema[{name}]: out_of_repo needs `path_env` and `index_file`")

        writer = entry.get("sole_writer") or {}
        lane = entry.get("lane") or {}
        if not writer.get("identity"):
            errors.append(f"schema[{name}]: sole_writer needs `identity`")
        if not lane.get("submit"):
            errors.append(f"schema[{name}]: lane needs a `submit` command")
        # An agent writer with a ticket lane must name the drain's arming env var.
        if writer.get("kind") == "agent" and lane.get("kind") == "ticket" and path_kind == "out_of_repo":
            if not writer.get("keeper_env"):
                errors.append(f"schema[{name}]: agent+ticket out_of_repo writer needs `keeper_env`")
    return errors


# ── B: the drain writer exists ────────────────────────────────────────────────
def check_writer_exists(root: Path, entries: dict) -> list[str]:
    errors: list[str] = []
    if not (root / DRAIN_SCRIPT).exists():
        errors.append(f"writer-exists: drain script {DRAIN_SCRIPT} missing")
    if "board" in entries and not (root / BOARD_ENGINE).exists():
        errors.append(f"writer-exists: board engine {BOARD_ENGINE} missing")
    return errors


# ── C: the lane exists (PENDING-tolerant) ─────────────────────────────────────
def check_lane_exists(root: Path, entries: dict) -> list[str]:
    errors: list[str] = []
    if "memory" in entries:
        submit_cli = root / MEMORY_SUBMIT_CLI
        engine = root / MEMORY_ENGINE
        if not submit_cli.exists() and not engine.exists():
            print("covenant[memory]: lane PENDING (files not yet landed)")
        else:
            if submit_cli.exists():
                try:
                    compile(_read(submit_cli), str(submit_cli), "exec")
                except SyntaxError as exc:
                    errors.append(f"lane[memory]: {MEMORY_SUBMIT_CLI} does not compile: {exc}")
            else:
                errors.append(f"lane[memory]: engine present but submit CLI {MEMORY_SUBMIT_CLI} missing")
            if engine.exists():
                text = _read(engine)
                for func in MEMORY_ENGINE_FUNCS:
                    if f"def {func}" not in text:
                        errors.append(f"lane[memory]: {MEMORY_ENGINE} does not define {func}")
            else:
                errors.append(f"lane[memory]: submit CLI present but engine {MEMORY_ENGINE} missing")
    if "board" in entries:
        engine = root / BOARD_ENGINE
        if engine.exists():
            text = _read(engine)
            for func in BOARD_SUBMIT_FUNCS:
                if f"def {func}" not in text:
                    errors.append(f"lane[board]: {BOARD_ENGINE} does not define {func}")
    return errors


# ── D: no other writer touches the MEMORY surface ─────────────────────────────
def _mentions_memory_token(node: ast.AST | None) -> bool:
    """True iff the unparsed expression references a memory-dir path token — so a write is
    flagged only when its TARGET is a memory path, never when the module merely reads one."""
    if node is None:
        return False
    try:
        expr = ast.unparse(node)
    except Exception:
        return False
    return any(token in expr for token in MEMORY_WRITE_TOKENS)


def _writes_memory_path(tree: ast.AST) -> bool:
    """True iff a write_text/write_bytes/open(...,'w'|'a') targets a memory path.

    The signal is the WRITE CALL'S TARGET, not the whole module: `x.write_text(...)` where the
    receiver `x` references a memory token, or `open(<memory path>, 'w')`. This deliberately does
    NOT flag a module that only READS a memory path (evocator.py, session-orient.py) while writing
    an unrelated file (FLAME.md, a digest, a JSON view)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in WRITE_CALLS:
            if _mentions_memory_token(func.value):
                return True
        elif isinstance(func, ast.Attribute) and func.attr == "open" and _has_write_mode(node):
            # <path>.open('w'...) — the receiver is the target.
            if _mentions_memory_token(func.value):
                return True
        elif isinstance(func, ast.Name) and func.id == "open" and _has_write_mode(node):
            # open(<path>, 'w'...) — the first positional arg is the target.
            if node.args and _mentions_memory_token(node.args[0]):
                return True
    return False


def _has_write_mode(node: ast.Call) -> bool:
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and any(m in arg.value for m in ("w", "a")):
            return True
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            if any(m in kw.value.value for m in ("w", "a")):
                return True
    return False


def check_no_other_writer(scan_root: Path) -> list[str]:
    errors: list[str] = []
    allow = set(MEMORY_WRITER_ALLOWLIST)
    tolerated = set(MEMORY_READONLY_TOLERATED)
    for subdir in SCAN_SUBDIRS:
        base = scan_root / subdir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = _rel(path, scan_root)
            if rel in allow:
                continue
            try:
                tree = ast.parse(_read(path), filename=str(path))
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            if _writes_memory_path(tree):
                # Read-only summoners are tolerated unless they GAIN a write call — which the
                # scan just detected, so even a tolerated file is flagged here.
                label = "read-only summoner gained a memory write" if rel in tolerated else "unlisted memory writer"
                errors.append(f"no-other-writer: {rel} ({label}) — only {sorted(allow)} may write the memory surface")
    return errors


# ── E: enforcement parity (ratchet-gated by `armed`) ──────────────────────────
def check_enforcement(root: Path, entries: dict) -> list[str]:
    errors: list[str] = []
    for name, entry in entries.items():
        enforcement = entry.get("enforcement") or {}
        armed = bool(enforcement.get("armed"))
        hook = enforcement.get("hook")
        if not armed:
            if hook:
                print(f"covenant[{name}]: guard PENDING (unarmed)")
            continue
        # armed → the hook must exist AND be wired in settings.json under a PreToolUse Write|Edit.
        if not hook or not (root / hook).exists():
            errors.append(f"enforcement[{name}]: armed but hook {hook} missing")
        else:
            settings = root / ".claude" / "settings.json"
            if not settings.exists():
                errors.append(f"enforcement[{name}]: armed but .claude/settings.json missing")
            else:
                text = _read(settings)
                if Path(hook).name not in text:
                    errors.append(f"enforcement[{name}]: armed hook {hook} not referenced in settings.json")
                elif "PreToolUse" not in text or not ("Write" in text and "Edit" in text):
                    errors.append(f"enforcement[{name}]: hook not under a PreToolUse Write|Edit matcher")
        # Declared gate/sensor ids: verify only if the registry already holds them.
        for kind, registry_rel, block in (
            ("gate", "institutio/governance/gates.yaml", "gates"),
            ("sensor", "institutio/governance/sensors.yaml", "sensors"),
        ):
            ident = enforcement.get(kind)
            if not ident:
                continue
            registry = root / registry_rel
            if registry.exists() and f"{ident}:" in _read(registry):
                continue
            if armed:
                errors.append(f"enforcement[{name}]: armed but {kind} id {ident!r} absent from {registry_rel}")
    return errors


# ── F: out-of-repo CI safety (never fail for absence) ─────────────────────────
def check_out_of_repo_safety(entries: dict) -> list[str]:
    for name, entry in entries.items():
        if entry.get("path_kind") != "out_of_repo":
            continue
        memdir = resolve_memory_dir()
        if not memdir.exists():
            print(f"covenant[{name}]: out-of-repo dir absent — schema-only")
    return []


# ── G: doc parity ─────────────────────────────────────────────────────────────
def check_doc_parity(root: Path, entries: dict) -> list[str]:
    doc = root / COVENANT_DOC
    if not doc.exists():
        return [f"doc: missing charter {COVENANT_DOC}"]
    text = _read(doc)
    errors: list[str] = []
    for name, entry in entries.items():
        locator = entry.get("path") or entry.get("path_env")
        if locator and locator not in text:
            errors.append(f"doc[{name}]: charter does not name path/path_env {locator}")
        writer = (entry.get("sole_writer") or {}).get("identity")
        if writer and writer not in text:
            errors.append(f"doc[{name}]: charter does not name sole writer {writer}")
        submit = (entry.get("lane") or {}).get("submit")
        if submit and submit not in text:
            errors.append(f"doc[{name}]: charter does not name lane submit command")
    return errors


def check_all(root: Path = ROOT, scan_root: Path | None = None) -> list[str]:
    entries = covenant_entries()
    errors = check_schema(entries)
    # A hard schema break makes the rest meaningless; stop and report it.
    if errors:
        return errors
    errors.extend(check_writer_exists(root, entries))
    errors.extend(check_lane_exists(root, entries))
    errors.extend(check_no_other_writer(scan_root or root))
    errors.extend(check_enforcement(root, entries))
    errors.extend(check_out_of_repo_safety(entries))
    errors.extend(check_doc_parity(root, entries))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record-keeper covenant drift predicate.")
    parser.add_argument(
        "--scan-root",
        type=Path,
        default=ROOT,
        help="root the no-other-writer scan walks (default: repo root; tests point it at a fixture)",
    )
    args = parser.parse_args(argv)
    errors = check_all(ROOT, scan_root=args.scan_root)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print(f"record-keeper covenant verified: {len(covenant_entries())} surfaces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
