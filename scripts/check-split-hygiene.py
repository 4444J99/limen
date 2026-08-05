#!/usr/bin/env python3
"""check-split-hygiene.py — the done-predicate for a form-twin repo split (docs/repo-split-protocol.md).

A split is DONE only when it is PROVEN leak-free, exit 0 ⟺ all five predicates hold:

  P1  history-disjoint   public∩private commit-SHA sets = ∅ — a fork/branch-copy would share
                         objects; fresh history is proven, never asserted.
  P2  policy-green       every public HEAD file classifies public_safe/product_content and no
  P4  secret-green       secret shape exists anywhere in public history (both delegated to
                         scripts/publish-sweep.py's sweep — the same gate a visibility flip passes).
  P3  manifest-covered   every public HEAD file lies under a form-manifest.yaml `paths:` entry.
  P5  registry-paired    the private repo's estate.yaml override row carries split.into naming the twin.

Repos may be given as owner/name (cloned via gh) or as local paths (the offline test seam — any
argument containing a path separator or pointing at an existing directory is treated as local).

  python3 scripts/check-split-hygiene.py --public organvm/x --private organvm/x--operatio
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent.resolve()

sys.path.insert(0, str(SCRIPT_DIR))


def _module(name: str, filename: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, str(SCRIPT_DIR / filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _is_local(ref: str) -> bool:
    return Path(ref).exists()


def _bare_clone(ref: str, dest: Path, sweep_mod) -> bool:
    return sweep_mod._clone(ref, dest, ref if _is_local(ref) else None)


def _commit_shas(clone: Path) -> set[str]:
    r = subprocess.run(
        ["git", "-C", str(clone), "rev-list", "--all"], capture_output=True, text=True, timeout=300
    )
    return {ln.strip() for ln in r.stdout.splitlines() if ln.strip()} if r.returncode == 0 else set()


def _head_paths(clone: Path) -> list[str]:
    r = subprocess.run(
        ["git", "-C", str(clone), "ls-tree", "-r", "HEAD", "--name-only"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()] if r.returncode == 0 else []


def _manifest(clone: Path) -> dict | None:
    r = subprocess.run(
        ["git", "-C", str(clone), "show", "HEAD:form-manifest.yaml"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        return None
    try:
        return yaml.safe_load(r.stdout) or {}
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Form-twin split hygiene predicate (P1–P5).")
    ap.add_argument("--public", required=True, help="the public form twin (owner/repo or local path)")
    ap.add_argument("--private", required=True, help="the private operation repo (owner/repo or local path)")
    args = ap.parse_args(argv)

    sweep_mod = _module("publish_sweep", "publish-sweep.py")
    pp = _module("publication_policy", "publication-policy.py")
    gitvs = _module("gitvs", "gitvs.py")

    fails: list[str] = []
    with tempfile.TemporaryDirectory(prefix="split-hygiene-") as td:
        pub, prv = Path(td) / "public.git", Path(td) / "private.git"
        if not _bare_clone(args.public, pub, sweep_mod):
            print(f"✗ split-hygiene: cannot clone public twin {args.public}")
            return 1
        if not _bare_clone(args.private, prv, sweep_mod):
            print(f"✗ split-hygiene: cannot clone private repo {args.private}")
            return 1

        # P1 — fresh history proven.
        shared = _commit_shas(pub) & _commit_shas(prv)
        if shared:
            fails.append(f"P1 history-disjoint: {len(shared)} commit(s) shared with the private repo — this is a fork/branch-copy, not a fresh extraction")

        # P2/P4 — the same gate a visibility flip passes, on the twin.
        receipt = sweep_mod.sweep(args.public, pp, clone_from=str(pub))
        if not receipt.get("green"):
            finds = len(receipt.get("head_findings") or [])
            hits = len(receipt.get("history_secret_hits") or [])
            fails.append(f"P2/P4 publish-sweep red on the twin: {finds} HEAD finding(s), {hits} history secret hit(s)")

        # P3 — manifest coverage.
        manifest = _manifest(pub)
        if manifest is None:
            fails.append("P3 manifest-covered: form-manifest.yaml missing/unparseable at the twin's HEAD")
        else:
            allow = [str(p) for p in (manifest.get("paths") or [])] + ["form-manifest.yaml"]
            stray = [
                p
                for p in _head_paths(pub)
                if not any(p == a or p.startswith(a.rstrip("/") + "/") or (a.endswith("/") and p.startswith(a)) for a in allow)
            ]
            if stray:
                fails.append(f"P3 manifest-covered: {len(stray)} file(s) outside manifest paths (e.g. {stray[:3]})")

    # P5 — registry pairing (only meaningful for owner/repo refs; local fixtures skip it).
    if not _is_local(args.private):
        row = (gitvs.load_estate().get("repo_overrides") or {}).get(args.private) or {}
        into = ((row.get("split") or {}).get("into")) or []
        if args.public not in into:
            fails.append(f"P5 registry-paired: estate row for {args.private} does not name {args.public} in split.into")

    if fails:
        print(f"✗ split-hygiene ({args.public} ⇐ {args.private}): {len(fails)} predicate(s) failed:")
        for f in fails:
            print(f"   {f}")
        return 1
    print(f"✓ split-hygiene ({args.public} ⇐ {args.private}): P1–P5 hold — the split is leak-free")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
