#!/usr/bin/env python3
"""Prove that a governed measurement document is written only by its keeper.

`tasks.yaml` has had custody for a long time: a sole logical writer, GitHub SHA
compare-and-swap, a stable publication branch, and ``scripts/task-writer-audit.py`` to catch a
new bypass writer *before* it can race the projection. Every other document that records durable
truth had a convention and nothing enforcing it — and the difference is not theoretical.
``docs/IDEAL-FORMS-LEDGER.md`` records that five of the six observations in the open-PR debt
series were side effects of unrelated feature PRs that happened to regenerate the ledger, and
that the series stopped when that unrelated work did.

This is deliberately NOT a second copy of the board audit, because a measurement series does not
have the board's problem. Live state is *raced*, so its predicate must answer "who wins". An
append-only series is *diluted*, so its predicate answers three narrower questions, one per check:

    A. Did anything other than the keeper commit this file?      (dilution — the recorded defect)
    B. Can anything other than the declared roles touch it?      (the next dilution, pre-empted)
    C. Is every committed row a distinct, correctly-ordered census?  (integrity of the series)

Check C deserves a note. It is the *write*-side twin of a defect that was found on the read side:
``pr-debt-trend.py --series`` counted a live uncommitted working copy as a second observation, and
because ``--check`` windows back from the newest row, that phantom shifted the measurement window
and reported +182 from a 1111 baseline when the truth was +234 from 1059. The reader is fixed. C
holds the written series to the same invariant so a future writer cannot reintroduce it from the
other end.

Usage::

    python3 scripts/check-ledger-custody.py            # exit 0 iff custody holds
    python3 scripts/check-ledger-custody.py --list      # print the governed estate, check nothing

Registry: ``institutio/governance/ledger-custody.yaml``. Adding a governed document is one entry
there; no path is hardcoded here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
REGISTRY_REL = "institutio/governance/ledger-custody.yaml"

# Where a writer could plausibly live. Tests are excluded on purpose: a test that writes a
# fixture ledger into a tmp_path is exercising the keeper, not competing with it, and the
# custody question is about production code paths.
SOURCE_ROOTS = ("scripts", "cli/src", "mcp/src", "web/api", "web/worker/src")
EXCLUDED_PARTS = {"test", "tests", "__pycache__", "node_modules", ".venv", "dist", "build"}
SOURCE_SUFFIXES = {".py", ".sh", ".bash", ".js", ".mjs", ".ts"}


def git(*args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", *args], cwd=str(ROOT), capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout


def load_registry() -> dict[str, Any]:
    path = ROOT / REGISTRY_REL
    if not path.is_file():
        sys.stdout.write(f"check-ledger-custody: FAIL — registry missing at {REGISTRY_REL}\n")
        raise SystemExit(1)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ledgers = data.get("ledgers") or {}
    if not isinstance(ledgers, dict) or not ledgers:
        sys.stdout.write(f"check-ledger-custody: FAIL — {REGISTRY_REL} declares no ledgers\n")
        raise SystemExit(1)
    return ledgers


def load_baseline(rel: str | None) -> set[tuple[str, str]]:
    """Baselined (sha, ledger-id) pairs. A missing file is an empty baseline, not an error."""
    if not rel:
        return set()
    path = ROOT / rel
    if not path.is_file():
        return set()
    out: set[tuple[str, str]] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            out.add((parts[0], parts[1]))
    return out


def commits_touching(rel_path: str) -> list[tuple[str, str]]:
    rc, out = git("log", "--format=%H%x00%s", "--", rel_path)
    if rc != 0:
        return []
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        if "\x00" not in line:
            continue
        sha, subject = line.split("\x00", 1)
        rows.append((sha.strip(), subject.strip()))
    return rows


def blob_at(sha: str, rel_path: str) -> dict[str, Any] | None:
    rc, out = git("show", f"{sha}:{rel_path}")
    if rc != 0:
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def source_files() -> list[Path]:
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            if EXCLUDED_PARTS & set(path.relative_to(ROOT).parts):
                continue
            files.append(path)
    return files


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def check_a_passengers(ledger_id: str, spec: dict[str, Any], baseline: set[tuple[str, str]]) -> list[str]:
    """Every commit touching the ledger is a keeper ship, or is baselined history."""
    pattern = spec.get("commit_subject")
    if not pattern:
        return [f"[A] {ledger_id}: registry declares no commit_subject — custody is unverifiable"]
    subject_re = re.compile(pattern)
    findings: list[str] = []
    for sha, subject in commits_touching(spec["path"]):
        if (sha, ledger_id) in baseline:
            continue
        if not subject_re.search(subject):
            findings.append(
                f"[A] {ledger_id}: {sha[:8]} carried the ledger as a passenger — {subject!r}\n"
                f"        the keeper ({spec['keeper']}) is the only thing that may commit it;\n"
                f"        revert the passenger and let the keeper ship the observation"
            )
    return findings


def check_b_touchers(ledger_id: str, spec: dict[str, Any]) -> list[str]:
    """Only declared roles may name the ledger path in production source."""
    declared = {spec["keeper"], spec["producer"], *(spec.get("readers") or [])}
    declared.add("scripts/check-ledger-custody.py")
    needle = spec["path"]
    findings: list[str] = []
    for path in source_files():
        relpath = rel(path)
        if relpath in declared:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if needle in text:
            findings.append(
                f"[B] {ledger_id}: undeclared toucher {relpath}\n"
                f"        declare it in {REGISTRY_REL} (as a reader) or stop it touching the file"
            )
    return findings


def check_c_series(ledger_id: str, spec: dict[str, Any], baseline: set[tuple[str, str]]) -> list[str]:
    """Non-baselined committed rows are distinct and strictly ordered by the ledger's own clock."""
    series_key = spec.get("series_key")
    if not series_key:
        return []
    rows = commits_touching(spec["path"])
    rows.reverse()  # git log is newest-first; walk forward in time
    findings: list[str] = []
    seen: dict[str, str] = {}
    previous: tuple[str, str] | None = None
    for sha, _subject in rows:
        baselined = (sha, ledger_id) in baseline
        data = blob_at(sha, spec["path"])
        if data is None:
            if not baselined:
                findings.append(f"[C] {ledger_id}: {sha[:8]} committed an unreadable ledger")
            continue
        stamp = data.get(series_key)
        if not isinstance(stamp, str) or not stamp:
            # Pre-keeper commits may predate the field; that is history, not a live violation.
            continue
        if baselined:
            # Baselining suppresses findings against immutable history; it must not erase
            # that row from the ordering state used to judge every fresh successor.
            seen.setdefault(stamp, sha)
            previous = (sha, stamp)
            continue
        if stamp in seen:
            findings.append(
                f"[C] {ledger_id}: {sha[:8]} re-ships the census already committed as "
                f"{seen[stamp][:8]} ({series_key}={stamp}) — two rows, one observation"
            )
        elif previous and stamp <= previous[1]:
            findings.append(
                f"[C] {ledger_id}: {sha[:8]} carries {series_key}={stamp}, not later than "
                f"{previous[0][:8]}'s {previous[1]} — the series is out of order"
            )
        seen.setdefault(stamp, sha)
        previous = (sha, stamp)
    return findings


def describe(ledger_id: str, spec: dict[str, Any]) -> str:
    readers = ", ".join(spec.get("readers") or []) or "(none)"
    return (
        f"{ledger_id}\n"
        f"  path     {spec['path']}\n"
        f"  keeper   {spec['keeper']}\n"
        f"  producer {spec['producer']}\n"
        f"  readers  {readers}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the governed estate and exit 0")
    args = parser.parse_args()

    ledgers = load_registry()

    if args.list:
        sys.stdout.write(f"governed ledgers ({len(ledgers)}) — {REGISTRY_REL}\n\n")
        for ledger_id, spec in sorted(ledgers.items()):
            sys.stdout.write(describe(ledger_id, spec) + "\n")
        return 0

    findings: list[str] = []
    for ledger_id, spec in sorted(ledgers.items()):
        missing = [k for k in ("path", "keeper", "producer") if not spec.get(k)]
        if missing:
            findings.append(f"[R] {ledger_id}: registry entry missing {', '.join(missing)}")
            continue
        baseline = load_baseline(spec.get("baseline"))
        findings.extend(check_a_passengers(ledger_id, spec, baseline))
        findings.extend(check_b_touchers(ledger_id, spec))
        findings.extend(check_c_series(ledger_id, spec, baseline))

    if findings:
        sys.stdout.write(f"check-ledger-custody: FAIL — {len(findings)} finding(s)\n\n")
        for finding in findings:
            sys.stdout.write(f"  {finding}\n")
        sys.stdout.write("\n  custody means the document has a keeper, not merely a convention.\n")
        return 1

    count = len(ledgers)
    sys.stdout.write(
        f"check-ledger-custody: OK — {count} governed ledger(s); "
        "every commit is a keeper ship, every toucher is declared, every row is a distinct census\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
