#!/usr/bin/env python3
"""plans-lifecycle-audit.py — the missing lifecycle for plan documents.

tasks.yaml has one: open -> dispatched -> in_progress -> done -> archived, with heal-dispatch.py
as its healer. Plans have never had an equivalent — docs/plans/ (+ the per-agent scratch
directories ~/.claude/plans and ~/.codex/plans) are pure append-only bookkeeping (CLAUDE.md's own
"Settling a session stream" section says as much: a claiming commit must change something OUTSIDE
docs/{plans,continuations}/, because "bookkeeping records an outcome, it cannot produce one"), and
nothing has ever swept a plan back OUT once its work has settled. Measured 2026-08-05 by
plans-orphan-audit: stale open plans rose 685 -> 718 (+33) in one day. That is not a spike, it is
the expected shape of a corpus with an intake and no drain.

Three corpora, two different lifecycles:
  * ~/.claude/plans, ~/.codex/plans — untracked, per-agent scratch (not in this repo, not in any
    repo). A stale entry here costs nothing to move and nothing to lose; --apply MAY archive these.
  * docs/plans/ — git-tracked. A file here can only be relocated through the normal branch/PR
    flow (CLAUDE.md: "do session work in a worktree, never in the live checkout"; "Confine edits
    to your worktree + branch"). This organ never writes there under --apply — REPORT-ONLY,
    always, for every entry in this corpus. Archiving a git-tracked plan is a human-reviewed PR,
    not a beat action.

"Stale" = last-modified older than --stale-days (default 30; a plan is a working document, not a
receipt the beat rewrites hourly, so a human timescale is the honest default; env
LIMEN_PLANS_STALE_DAYS). This is a coarse, defensible first cut — age alone, no attempt to parse
whether the plan's own work settled — because false negatives (a genuinely stale plan not yet
flagged) cost nothing and false positives (a live plan wrongly archived) would, and --apply only
ever MOVES a file into a same-directory `archive/` subfolder — it NEVER deletes. A human who
disagrees with an archived candidate moves it back; nothing is destroyed, so there is no
audit-vs-instant-archive judgment call worth encoding here yet — the corpus gets a chance to prove
the heuristic wrong before anything sharper is built on top of it.

Usage:
  python3 scripts/plans-lifecycle-audit.py            # report only; never writes
  python3 scripts/plans-lifecycle-audit.py --apply     # archive stale untracked-corpus entries
  python3 scripts/plans-lifecycle-audit.py --json      # machine-readable report
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
DEFAULT_STALE_DAYS = int(os.environ.get("LIMEN_PLANS_STALE_DAYS", "30"))

# (label, path, archivable) — archivable=False marks a git-tracked corpus this organ only reports
# on; archivable=True marks untracked per-agent scratch --apply may move entries out of.
CORPORA: tuple[tuple[str, Path, bool], ...] = (
    ("claude-plans", Path(os.environ.get("LIMEN_CLAUDE_PLANS_DIR", Path.home() / ".claude" / "plans")), True),
    ("codex-plans", Path(os.environ.get("LIMEN_CODEX_PLANS_DIR", Path.home() / ".codex" / "plans")), True),
    ("docs-plans", ROOT / "docs" / "plans", False),
)

ARCHIVE_DIRNAME = "archive"


@dataclass
class CorpusReport:
    label: str
    path: str
    archivable: bool
    present: bool
    total: int = 0
    stale: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)


def _plan_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.md") if p.is_file() and ARCHIVE_DIRNAME not in p.relative_to(base).parts)


def _is_stale(path: Path, *, now: float, stale_seconds: float) -> bool:
    try:
        return (now - path.stat().st_mtime) >= stale_seconds
    except OSError:
        return False


def audit(*, apply: bool, stale_days: int) -> list[CorpusReport]:
    now = time.time()
    stale_seconds = stale_days * 86400
    reports: list[CorpusReport] = []

    for label, base, archivable in CORPORA:
        report = CorpusReport(label=label, path=str(base), archivable=archivable, present=base.is_dir())
        if not report.present:
            reports.append(report)
            continue

        files = _plan_files(base)
        report.total = len(files)
        for plan_file in files:
            if not _is_stale(plan_file, now=now, stale_seconds=stale_seconds):
                continue
            rel = str(plan_file.relative_to(base))
            report.stale.append(rel)
            if apply and archivable:
                dest = base / ARCHIVE_DIRNAME / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(plan_file), str(dest))
                    report.archived.append(rel)
                except OSError as exc:
                    print(f"plans-lifecycle-audit: could not archive {plan_file}: {exc}", file=sys.stderr)

        reports.append(report)

    return reports


def _print_human(reports: list[CorpusReport], *, apply: bool, stale_days: int) -> None:
    print(f"plans-lifecycle-audit: stale threshold {stale_days}d")
    for report in reports:
        if not report.present:
            print(f"  {report.label}: absent ({report.path})")
            continue
        verb = "archived" if apply and report.archivable else "would archive" if report.archivable else "report-only"
        acted = len(report.archived) if apply and report.archivable else len(report.stale)
        print(f"  {report.label}: {report.total} plan(s), {len(report.stale)} stale, {verb} {acted}")
        if not report.archivable and report.stale:
            print(f"    git-tracked — relocate via a normal branch/PR, not this organ's --apply")
        for rel in report.stale[:5]:
            print(f"    - {rel}")
        if len(report.stale) > 5:
            print(f"    ... and {len(report.stale) - 5} more")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--apply", action="store_true", help="archive stale entries in untracked corpora (never docs/plans/)"
    )
    ap.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    ap.add_argument("--json", action="store_true", help="emit a machine-readable report instead of text")
    args = ap.parse_args(argv)

    reports = audit(apply=args.apply, stale_days=args.stale_days)

    if args.json:
        print(
            json.dumps(
                {
                    "stale_days": args.stale_days,
                    "applied": args.apply,
                    "corpora": [
                        {
                            "label": r.label,
                            "path": r.path,
                            "archivable": r.archivable,
                            "present": r.present,
                            "total": r.total,
                            "stale_count": len(r.stale),
                            "stale": r.stale,
                            "archived": r.archived,
                        }
                        for r in reports
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        _print_human(reports, apply=args.apply, stale_days=args.stale_days)

    return 0


if __name__ == "__main__":
    sys.exit(main())
