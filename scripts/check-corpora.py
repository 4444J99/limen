#!/usr/bin/env python3
"""CORPORA registry drift-predicate — hold institutio/governance/corpora.yaml to the disk.

The corpus locations are declared data (corpora.yaml). This is their drift-check, the
corpora-domain twin of check-gates.py / check-sensors.py / check-params.py. Exit 0 ⟺ the
registry agrees with what is actually on disk and with the one resolver:

  A schema        — every corpus row carries store/provider/kind/owner/note and valid enums;
                    every store carries root/remote/owner/note.
  B roots exist   — every declared store root resolves to a real directory.
  C disk parity   — every corpus-shaped directory on disk has a row, and every declared row
                    that claims to be populated actually is. This is the check that would
                    have caught the Perplexity drift: a directory CCE does not declare, and
                    which every declared-ids-only consumer therefore dropped in silence.
  D resolver sole — nothing outside scripts/corpus_resolve.py hardcodes a corpus root. A
                    second copy of "where the corpora live" is how both original bugs
                    survived: two consumers, two copies, both wrong the same way.
  E freshness     — re-derived from the store's own federation summary. Advisory by default
                    (a stale corpus is a fact, not a build break); fatal under --strict.

  python3 scripts/check-corpora.py            # gate (CI): exit 1 on real drift
  python3 scripts/check-corpora.py --strict   # also fail on stale corpora
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference_state
from reference_state import ReferenceResolver

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "corpora.yaml"
RESOLVER = ROOT / "scripts" / "corpus_resolve.py"
BASELINE = ROOT / "institutio" / "governance" / "corpus-root-literals-baseline.txt"

VALID_KIND = {"session-memory", "raw-archive", "atom-stream", "brainstorm-extract"}

# Directories under a store root that are infrastructure, not corpora.
NON_CORPUS_DIRS = {".git", "federation", "reports", "state", "source-drop"}

# Consumers allowed to name a corpus root literally. Everything else must import the
# resolver; a literal anywhere else is a second source of truth.
RESOLVER_EXEMPT = {"scripts/corpus_resolve.py", "scripts/check-corpora.py"}

FAILURES: list[str] = []
ADVISORIES: list[str] = []


def fail(check: str, msg: str) -> None:
    FAILURES.append(f"{check}: {msg}")


def advise(check: str, msg: str) -> None:
    ADVISORIES.append(f"{check}: {msg}")


def load_baseline() -> set[str]:
    """Grandfathered `<path>::<literal>` keys — new ones fail, this set only shrinks.

    Only the line terminator is stripped. A literal may legitimately end in a
    space (a markdown fragment does), and stripping it broke the round-trip so
    an entry could never match what it grandfathered.
    """
    if not BASELINE.is_file():
        return set()
    return {line for line in BASELINE.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")}


def expand(path: str) -> Path:
    return Path(path).expanduser()


def check_a_schema(doc: dict) -> None:
    for name, store in (doc.get("stores") or {}).items():
        for field in ("root", "remote", "owner", "note"):
            if not store.get(field):
                fail("A", f"store {name!r} missing required field {field!r}")
    for cid, row in (doc.get("corpora") or {}).items():
        for field in ("store", "provider", "kind", "owner", "note"):
            if not row.get(field):
                fail("A", f"corpus {cid!r} missing required field {field!r}")
        kind = row.get("kind")
        if kind and kind not in VALID_KIND:
            fail("A", f"corpus {cid!r} has invalid kind {kind!r} (valid: {sorted(VALID_KIND)})")
        store = row.get("store")
        if store and store not in (doc.get("stores") or {}):
            fail("A", f"corpus {cid!r} references undeclared store {store!r}")


def check_b_roots(doc: dict) -> dict[str, Path]:
    """Resolve store roots, deriving absence severity from the CUSTODY axis.

    This used to key off `on_host = any(root.is_dir())` and degrade a missing root to an
    ADVISORY whenever no declared store happened to be on disk. The 2026-07-27 evacuation
    archived every store at once, so that branch became permanent: a store safely archived
    with two verified copies and a store somebody deleted read IDENTICALLY, and the check
    stayed green. Green through absence.

    The verdict now comes from `reference_state.ReferenceResolver` — the single resolver
    the three axes share (see convergence.yaml `reference-liveness`) — which distinguishes:

      ok / archived      accounted for: present, or receipts prove two verified copies on
                         independent devices. Reported, never failed.
      unaccounted        absent, provably so here, and NOTHING declares where it went.
                         This is a REAL failure and the reason the axis exists.
      unverifiable-here  a CI runner with no ~/Workspace. Absence of evidence stays a host
                         fact, never drift — the one part of the old behaviour that was right.
    """
    roots: dict[str, Path] = {}
    for name, store in (doc.get("stores") or {}).items():
        roots[name] = expand(str(store.get("root", "")))

    resolver = ReferenceResolver()
    forced_host = os.environ.get("LIMEN_CORPORA_HOST") == "1"
    for name, store in (doc.get("stores") or {}).items():
        root = roots[name]
        if root.is_dir():
            continue
        res = resolver.resolve(str(store.get("root", "")))
        if res.state == reference_state.UNACCOUNTED:
            fail("B", f"store {name!r} root does not exist and is UNACCOUNTED: {root} — {res.detail}")
        elif res.state == reference_state.ARCHIVED:
            advise("B", f"store {name!r} root is archived off-host: {res.detail}")
        elif forced_host:
            # LIMEN_CORPORA_HOST=1 asserts this machine CAN prove absence, so an
            # unverifiable verdict here is the caller contradicting the evidence.
            fail("B", f"store {name!r} root does not exist: {root} (LIMEN_CORPORA_HOST=1 asserts absence is provable)")
        else:
            advise("B", f"store {name!r} root not resolvable here: {res.detail}")
    return roots


def check_c_disk_parity(doc: dict, roots: dict[str, Path]) -> None:
    corpora = doc.get("corpora") or {}

    # every declared row that lives at a store root directory actually exists
    for cid, row in corpora.items():
        root = roots.get(str(row.get("store")))
        if root is None or not root.is_dir():
            continue
        target = root / row["path"] if row.get("path") else root / cid
        if not target.exists():
            fail("C", f"corpus {cid!r} declared but absent on disk: {target}")

    # every corpus-shaped directory on disk has a row  ← the Perplexity catch
    declared_dirs = {cid for cid, row in corpora.items() if not row.get("path")}
    for store_name, root in roots.items():
        if not root.is_dir():
            continue
        # only stores whose corpora are top-level dirs participate
        if not any(r.get("store") == store_name and not r.get("path") for r in corpora.values()):
            continue
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith(".") or child.name in NON_CORPUS_DIRS:
                continue
            if child.name not in declared_dirs:
                fail(
                    "C",
                    f"corpus directory on disk with no registry row: {store_name}/{child.name} "
                    "— an undeclared corpus is invisible to every declared-ids-only consumer",
                )

    # a row claiming a CCE id different from its directory name must say so explicitly
    for cid, row in corpora.items():
        undeclared_row = row.get("cce_declared") is False and row.get("provider") != "multi" and not row.get("path")
        if undeclared_row and not row.get("cce_id") and not row.get("note"):
            fail("C", f"corpus {cid!r} is not CCE-declared but records no cce_id and no note")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """id() of every Constant node that is a docstring, so prose is never flagged."""
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            out.add(id(body[0].value))
    return out


def collect_root_literals(doc: dict) -> set[str]:
    """Every `<path>::<literal>` naming a corpus root outside the resolver."""
    dirnames = [Path(str(s.get("root", ""))).name for s in (doc.get("stores") or {}).values()]
    dirnames = [d for d in dirnames if d]
    found: set[str] = set()
    if not dirnames:
        return found
    for path in sorted(ROOT.glob("scripts/*.py")) + sorted(ROOT.glob("organs/**/*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in RESOLVER_EXEMPT:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        docstrings = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            if any(d in node.value for d in dirnames):
                found.add(f"{rel}::{node.value}")
    return found


def check_d_resolver_sole(doc: dict, baseline: set[str]) -> None:
    """No second copy of 'where the corpora live'.

    Parsed, not grepped: a corpus root named in a docstring or comment is
    documentation, while the same name in a live string literal is a second
    source of truth. Line-matching cannot tell those apart and reported ten
    prose mentions as violations.

    Existing violations are grandfathered via the baseline file (the
    undeclared-params-baseline.txt pattern) — new ones fail, the old set only
    shrinks. Converting a consumer means deleting its line from the baseline.
    """
    dirnames = [Path(str(s.get("root", ""))).name for s in (doc.get("stores") or {}).values()]
    dirnames = [d for d in dirnames if d]
    if not dirnames:
        return

    for path in sorted(ROOT.glob("scripts/*.py")) + sorted(ROOT.glob("organs/**/*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in RESOLVER_EXEMPT:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue
        docstrings = _docstring_nodes(tree)
        # Key on the literal's VALUE, not its line. A line number is a position,
        # and any edit above shifts it — baselining by line makes an unrelated
        # insertion look like a new violation (observed while testing this very
        # check). The literal itself is stable under refactoring.
        hits: dict[str, int] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docstrings:
                continue
            if any(d in node.value for d in dirnames):
                hits.setdefault(node.value, node.lineno)
        for literal, lineno in sorted(hits.items()):
            key = f"{rel}::{literal}"
            if key in baseline:
                continue
            fail(
                "D",
                f"{rel}:{lineno} hardcodes a corpus root in a string literal "
                f"({literal!r}) — import scripts/corpus_resolve.py instead",
            )


def check_e_freshness(doc: dict, roots: dict[str, Path], strict: bool) -> None:
    for store_name, root in roots.items():
        summary = root / "federation" / "corpora-summary.json"
        if not summary.is_file():
            continue
        try:
            rows = json.loads(summary.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            advise("E", f"{store_name}: federation summary unreadable ({exc})")
            continue
        for row in rows if isinstance(rows, list) else []:
            state = row.get("source_freshness_state")
            cid = row.get("corpus_id", "?")
            if state and state not in ("fresh", "not_applicable"):
                msg = f"{cid}: source_freshness_state={state} — re-run the provider import"
                (fail if strict else advise)("E", msg)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true", help="treat stale corpora as failures")
    ap.add_argument("--update-baseline", action="store_true", help="rewrite the baseline from current state")
    args = ap.parse_args(argv)

    if not REGISTRY.is_file():
        print(f"FAILED: check-corpora — registry missing at {REGISTRY}")
        return 1
    try:
        doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"FAILED: check-corpora — cannot parse {REGISTRY}: {exc}")
        return 1

    if not RESOLVER.is_file():
        fail("D", f"the single resolver is missing: {RESOLVER}")

    if args.update_baseline:
        # Re-derive the grandfathered set from current state. Only ever run
        # deliberately: it can only be honest if every entry is a real, known
        # duplicate awaiting conversion.
        keys = sorted(collect_root_literals(doc))
        BASELINE.write_text(
            "# Corpus-root string literals awaiting conversion to scripts/corpus_resolve.py.\n"
            "# Format: <path>::<literal>  — keyed on the literal, never a line number, so an\n"
            "# unrelated edit above cannot masquerade as a new violation.\n"
            "# Ratchet: new literals fail check-corpora D; this list only shrinks.\n"
            "# Convert a consumer, then delete its lines here.\n" + "".join(f"{k}\n" for k in keys),
            encoding="utf-8",
        )
        print(f"wrote {BASELINE} ({len(keys)} grandfathered literals)")
        return 0

    check_a_schema(doc)
    roots = check_b_roots(doc)
    check_c_disk_parity(doc, roots)
    check_d_resolver_sole(doc, load_baseline())
    check_e_freshness(doc, roots, args.strict)

    for note in ADVISORIES:
        print(f"  ↑ {note}")
    if FAILURES:
        print(f"FAILED: check-corpora — {len(FAILURES)} drift(s)")
        for f in FAILURES:
            print(f"  ✗ {f}")
        return 1

    n_corpora = len(doc.get("corpora") or {})
    n_stores = len(doc.get("stores") or {})
    n_unpop = len(doc.get("unpopulated") or [])
    print(
        f"OK: check-corpora — {n_corpora} corpora across {n_stores} stores, "
        f"{n_unpop} declared-but-unpopulated, checks A-E clean"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
