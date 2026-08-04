#!/usr/bin/env python3
"""
repo-genesis — mint a repository by predicate, never by hand.

There was no repo-scaffolding path in this estate at all (`gh repo create` appears twice,
both one-offs); repos appeared by hand and were classified after the fact, and
IF-AMALGAMATION records what that produced: duplicates accreting faster than they merge.
This tool is the gate the estate never had. A repo exists because a predicate said so —
and the predicate refuses far more often than it mints.

The unit of a brainstorm is an ATOM in the extract registry (IF-LEARNING-ENGINE's
subject/cartridge contract, generalized). A repo is minted only when an atom needs what
only a repo provides — its own deploy surface, collaborator grant, or visibility boundary
— and has the demand evidence to prove it (review-before-rails, the constellation
program's own rule).

Gates, all of which must pass:

  G1 evidence    — a non-empty demand-evidence reference (an extract path, dossier path,
                   or CONST-/IRF id). "I want it" is not evidence; a reviewed
                   conversation record is.
  G2 name        — `scripts/nomenclator.py --check <name>` clears the naming canon.
  G3 class       — the name resolves to a declared estate.yaml class; an explicit
                   repo_overrides judgment wins before broad globs. `--class` pins
                   the expected result (never class J / unclassified).
  G4 seed        — at least one brainstorm extract or seed document to found the repo
                   with; an empty repo is a vacuum, not a genesis.

On mint (without --dry-run): creates the private repo, pushes the seed material
(extracts under brainstorms/, a seed.yaml, a README stub), and appends the estate.yaml
repo_overrides row LOCALLY — the row still lands by PR through the normal branch flow,
never pushed directly (the estate contract: rows land by PR, never auto-written).
Visibility is NOT a flag here: estate.yaml classes own it (IF-PUBLICATION-ESTATE).

Usage:
  scripts/repo-genesis.py --name the-consulate--intake \\
      --class operation_private \\
      --evidence "brainstorm-extracts/chatgpt-local-session-memory/threads/042-….md" \\
      --seed-extract <path> [--seed-extract <path> …] --why "…" --dry-run
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ESTATE = ROOT / "institutio" / "github" / "estate.yaml"
NOMENCLATOR = ROOT / "scripts" / "nomenclator.py"
DEFAULT_ORG = "organvm"


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def gate_evidence(evidence: str) -> tuple[bool, str]:
    ev = (evidence or "").strip()
    if not ev:
        return False, "G1 evidence: none supplied — review-before-rails means a reviewed record, not intent"
    p = Path(ev).expanduser()
    if p.exists():
        return True, f"G1 evidence: file exists ({ev})"
    if ev.startswith(("CONST-", "IRF-", "L-")):
        return True, f"G1 evidence: registry id ({ev})"
    return False, f"G1 evidence: {ev!r} is neither an existing file nor a registry id"


def gate_name(name: str) -> tuple[bool, str]:
    if not NOMENCLATOR.is_file():
        return False, "G2 name: scripts/nomenclator.py missing"
    proc = run([sys.executable, str(NOMENCLATOR), "--check", name], cwd=ROOT)
    ok = proc.returncode == 0
    detail = (proc.stdout or proc.stderr).strip().splitlines()
    return ok, f"G2 name: {'clears' if ok else 'REJECTED by'} the canon ({detail[-1] if detail else name})"


def gate_class(full_name: str, expected_class: str | None = None) -> tuple[bool, str]:
    doc = yaml.safe_load(ESTATE.read_text(encoding="utf-8")) or {}
    classes = doc.get("classes") or {}
    override = (doc.get("repo_overrides") or {}).get(full_name)
    resolved: str | None = None
    source = ""
    if isinstance(override, dict) and override.get("class"):
        resolved = str(override["class"])
        source = "explicit override"
        if resolved not in classes:
            return False, f"G3 class: {full_name} override names undeclared class {resolved!r}"
    else:
        for cls_name, cls in classes.items():
            for glob in cls.get("match") or cls.get("globs") or []:
                if fnmatch.fnmatch(full_name, glob):
                    resolved = str(cls_name)
                    source = f"glob {glob!r}"
                    break
            if resolved:
                break
    if resolved is None:
        return False, f"G3 class: {full_name} matches no declared estate.yaml class — would land as class J"
    if expected_class and resolved != expected_class:
        return False, f"G3 class: {full_name} resolves to {resolved!r}, expected {expected_class!r} ({source})"
    return True, f"G3 class: {full_name} → class {resolved!r} ({source})"


def gate_seed(paths: list[str]) -> tuple[bool, str]:
    if not paths:
        return False, "G4 seed: no seed material — an empty repo is a vacuum, not a genesis"
    missing = [p for p in paths if not Path(p).expanduser().is_file()]
    if missing:
        return False, f"G4 seed: missing seed file(s): {missing}"
    return True, f"G4 seed: {len(paths)} founding document(s)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", required=True, help="bare repo name (org fixed)")
    ap.add_argument("--org", default=DEFAULT_ORG)
    ap.add_argument("--class", dest="expected_class", help="required estate class for this repository")
    ap.add_argument("--evidence", required=True, help="demand-evidence file path or registry id")
    ap.add_argument("--seed-extract", action="append", default=[], help="founding document(s); repeatable")
    ap.add_argument("--why", required=True, help="the one-line why for the estate override row")
    ap.add_argument("--dry-run", action="store_true", help="evaluate the gates, mint nothing")
    args = ap.parse_args()

    full = f"{args.org}/{args.name}"
    results = [
        gate_evidence(args.evidence),
        gate_name(args.name),
        gate_class(full, args.expected_class),
        gate_seed(args.seed_extract),
    ]
    ok = all(r[0] for r in results)
    for passed, msg in results:
        print(f"  {'✓' if passed else '✗'} {msg}")
    if not ok:
        print(f"\nREFUSED: {full} — {sum(1 for r in results if not r[0])} gate(s) failed. Nothing minted.")
        return 2
    if args.dry_run:
        print(f"\nCLEARED (dry run): {full} passes all four gates. Re-run without --dry-run to mint.")
        return 0

    # ── mint, one motion ──
    if run(["gh", "repo", "view", full]).returncode == 0:
        print(f"REFUSED: {full} already exists — genesis never overwrites.")
        return 2
    proc = run(["gh", "repo", "create", full, "--private"])
    if proc.returncode != 0:
        print(f"FAILED: gh repo create — {proc.stderr.strip()}")
        return 1

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        run(["git", "init", "-q", "-b", "main"], cwd=wd)
        (wd / "README.md").write_text(
            f"# {args.name}\n\nFounded by repo-genesis from demand evidence: `{args.evidence}`.\n"
            f"Seed brainstorms under `brainstorms/`.\n",
            encoding="utf-8",
        )
        (wd / "seed.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": "1.0",
                    "repo": full,
                    "genesis": {"tool": "scripts/repo-genesis.py", "evidence": args.evidence, "why": args.why},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        bdir = wd / "brainstorms"
        bdir.mkdir()
        for p in args.seed_extract:
            src = Path(p).expanduser()
            (bdir / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        run(["git", "add", "-A"], cwd=wd)
        run(["git", "commit", "-q", "-m", f"genesis: {args.name} — seeded by repo-genesis ({args.evidence})"], cwd=wd)
        run(["git", "remote", "add", "origin", f"https://github.com/{full}.git"], cwd=wd)
        push = run(["git", "push", "-q", "origin", "main"], cwd=wd)
        if push.returncode != 0:
            print(f"FAILED: seed push — {push.stderr.strip()}")
            return 1

    estate = yaml.safe_load(ESTATE.read_text(encoding="utf-8")) or {}
    if full in (estate.get("repo_overrides") or {}):
        registry_detail = "predeclared estate override retained"
    else:
        # Backward-compatible staging for callers that did not predeclare a judgment. New
        # genesis packets should commit an explicit override before minting so G3 cannot be
        # decided by a broad fallthrough glob.
        with ESTATE.open("a", encoding="utf-8") as fh:
            fh.write(
                f"\n# repo-genesis {args.name}: pending PR review — move into repo_overrides on merge\n"
                f"# {full}: {{why: {args.why!r}, genesis_evidence: {args.evidence!r}}}\n"
            )
        registry_detail = "estate row staged locally; commit + PR it"
    print(f"\nMINTED: https://github.com/{full} (private) — {registry_detail}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
