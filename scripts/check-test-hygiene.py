#!/usr/bin/env python3
"""Test-hygiene gate — keep the suite order-independent so main's pr-gate can't silently go red.

The gap this closes (2026-07-10): non-hermetic tests broke the REQUIRED ``pr-gate`` for every PR. A
helper in ``cli/tests/test_async_dispatch.py`` wrote ``os.environ`` DIRECTLY (not via ``monkeypatch``,
which auto-reverts), leaking ``LIMEN_WORKTREE_DEBT_GATE=0`` process-wide and disabling the lifecycle
debt gate for later files when CI ran ``pytest web/api/tests cli/tests`` (web/api first). It passed
locally by test order and failed only in CI. The fix was an autouse ``os.environ`` snapshot/restore
fixture in a per-root ``conftest.py`` (#870). This gate makes that fix DURABLE and ratchets the
pattern:

1. CONFTEST GUARD (hard): every test root (``cli/tests``, ``web/api/tests``) must have a
   ``conftest.py`` whose autouse fixture restores ``os.environ`` — so the isolation can't be silently
   deleted, reviving the leak class.
2. DIRECT-WRITE RATCHET (hard): no NEW direct ``os.environ`` writes / ``setdefault`` / ``update`` /
   ``os.putenv`` in test files beyond the committed baseline (AST-detected, so comments/strings/``==``
   never false-match). Existing safe writes are grandfathered; new ones must use ``monkeypatch``.
   This is exactly the ``scripts/check-params.py`` ratchet pattern, one domain over.

  python3 scripts/check-test-hygiene.py            # gate (CI): exit 1 on violation
  python3 scripts/check-test-hygiene.py --update    # rewrite the baseline to current (after folding)
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_ROOTS = ("cli/tests", "web/api/tests")
BASELINE = ROOT / "institutio" / "governance" / "test-hygiene-baseline.txt"


def _is_os_environ(node: ast.AST) -> bool:
    """True for an ``os.environ`` attribute or a bare ``environ`` name (from-import)."""
    if isinstance(node, ast.Attribute) and node.attr == "environ":
        return isinstance(node.value, ast.Name) and node.value.id == "os"
    return isinstance(node, ast.Name) and node.id == "environ"


def _key_literal(sub: ast.Subscript) -> str:
    """The subscript key if it's a string literal (``os.environ["FOO"]`` -> FOO), else ``*``."""
    idx = sub.slice
    if isinstance(idx, ast.Constant) and isinstance(idx.value, str):
        return idx.value
    return "*"


class _Visitor(ast.NodeVisitor):
    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        self.hits: list[str] = []  # stable keys: "<relpath>::<envkey-or-callname>"

    def _record(self, key: str) -> None:
        self.hits.append(f"{self.relpath}::{key}")

    def visit_Assign(self, node: ast.Assign) -> None:
        for tgt in node.targets:
            if isinstance(tgt, ast.Subscript) and _is_os_environ(tgt.value):
                self._record(_key_literal(tgt))
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Subscript) and _is_os_environ(node.target.value):
            self._record(_key_literal(node.target))
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        fn = node.func
        if isinstance(fn, ast.Attribute):
            # os.environ.setdefault(...) / os.environ.update(...)
            if fn.attr in {"setdefault", "update"} and _is_os_environ(fn.value):
                self._record(f"environ.{fn.attr}")
            # os.putenv(...)
            elif fn.attr == "putenv" and isinstance(fn.value, ast.Name) and fn.value.id == "os":
                self._record("os.putenv")
        self.generic_visit(node)


def scan_direct_writes(root: Path = ROOT) -> set[str]:
    found: set[str] = set()
    for rel in TEST_ROOTS:
        base = root / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("test_*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError):
                continue
            v = _Visitor(str(path.relative_to(root)))
            v.visit(tree)
            found.update(v.hits)
    return found


def _conftest_restores_environ(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return (
        "autouse=True" in text
        and "os.environ" in text
        and ("os.environ.clear()" in text or "os.environ.update" in text)
    )


def conftest_gaps(root: Path = ROOT) -> list[str]:
    gaps = []
    for rel in TEST_ROOTS:
        cf = root / rel / "conftest.py"
        if not cf.exists():
            gaps.append(f"{rel}/conftest.py MISSING (no env-isolation fixture)")
        elif not _conftest_restores_environ(cf):
            gaps.append(f"{rel}/conftest.py present but has no autouse os.environ restore fixture")
    return gaps


def load_baseline(baseline: Path = BASELINE) -> set[str]:
    if not baseline.exists():
        return set()
    return {
        ln.strip() for ln in baseline.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")
    }


def write_baseline(entries: set[str], baseline: Path = BASELINE) -> None:
    header = (
        "# Grandfathered direct os.environ writes in tests (test-hygiene ratchet).\n"
        "# New entries here mean a NEW direct write slipped in — prefer pytest's monkeypatch.\n"
        "# Regenerate with: python3 scripts/check-test-hygiene.py --update\n"
    )
    baseline.write_text(header + "".join(f"{e}\n" for e in sorted(entries)), encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="test-hygiene gate")
    ap.add_argument("--update", action="store_true", help="rewrite the direct-write baseline to current")
    ap.add_argument("--root", default=None, help="repo root to scan (default: this repo; for tests)")
    ap.add_argument("--baseline", default=None, help="baseline file path (default: governance baseline)")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else ROOT
    baseline_path = (
        Path(args.baseline) if args.baseline else (root / "institutio" / "governance" / "test-hygiene-baseline.txt")
    )

    current = scan_direct_writes(root)
    if args.update:
        write_baseline(current, baseline_path)
        print(f"test-hygiene: baseline rewritten — {len(current)} grandfathered direct write(s).")
        return 0

    gaps = conftest_gaps(root)
    baseline = load_baseline(baseline_path)
    new_writes = current - baseline

    if not gaps and not new_writes:
        print(
            f"check-test-hygiene: OK — env-isolation conftest present in {len(TEST_ROOTS)} test root(s); "
            f"{len(current)} grandfathered direct write(s), 0 new."
        )
        return 0

    if gaps:
        print("TEST-HYGIENE GATE: env-isolation conftest missing/incomplete —")
        for g in gaps:
            print(f"  ✗ {g}")
    if new_writes:
        print("TEST-HYGIENE GATE: new direct os.environ write(s) in tests — use monkeypatch, or")
        print("  fold into the baseline via --update if intentional:")
        for w in sorted(new_writes):
            print(f"  ✗ {w}")
    print("FAILED: check-test-hygiene")
    return 1


if __name__ == "__main__":
    sys.exit(main())
