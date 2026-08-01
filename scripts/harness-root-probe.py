#!/usr/bin/env python3
"""Sense the Claude Code harness: is its runtime root where we think, and is plan mode working?

Two assertions, one probe:

1. **Root liveness.** The resolved harness root actually holds transcripts. A root that exists but
   is empty *while a sibling candidate holds many* is the signature of the harness relocating its
   tree — exactly what happened when it moved from ``~/.claude`` to ``<repo>/.agent-runtime/claude``
   and ten limen surfaces went blind at once without a single check going red.

2. **Plan-mode fault signatures**, read structurally out of the transcripts themselves:

   - ``A`` — an ``ExitPlanMode`` call whose ``tool_result`` came back ``is_error``. The loud fault
     the operator sees as "You are not in plan mode".
   - ``B`` — a file mutation while the session's last recorded ``permissionMode`` is ``plan``,
     excluding the session's own plan file (plan-file writes are legitimate in plan mode). This is
     the *dangerous* half: it means the read-only guarantee silently stopped holding.
   - ``C`` — one plan slug written to both a shared-checkout path and a ``.claude/worktrees/`` path
     in a single session: the plan-path shadow that makes the approval dialog serve a stale plan.

Signatures match on JSON structure, never on error text — substring matching also catches sessions
that merely *discuss* the error, which produced three false positives when this was prototyped.

Read-only. Never mutates transcripts. Exits non-zero when the root looks relocated or a fault is
seen in the window; the sensor entry runs it at ``advisory`` severity so the beat stays fail-open.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen import harness_paths

MUTATING_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
PLAN_DIR_MARKER = "/claude/plans/"
WORKTREE_MARKER = "/.claude/worktrees/"


def _iter_rows(path: Path):
    """Yield parsed JSON rows, skipping unparseable lines.

    Transcripts are appended live by another process, so a truncated final line is normal rather
    than exceptional — never let one bad line lose a whole session.
    """

    try:
        with path.open(errors="replace") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    except OSError:
        return


def scan_transcript(path: Path) -> dict:
    """Structural fault detection over one transcript."""

    tool_names: dict[str, str] = {}
    mode: str | None = None
    model: str | None = None
    approved = False
    plan_slug_paths: dict[str, set[str]] = {}
    findings: dict[str, list] = {"A": [], "B": [], "C": []}
    models: Counter = Counter()

    for row in _iter_rows(path):
        if row.get("permissionMode"):
            mode = row["permissionMode"]
        message = row.get("message") or {}
        if message.get("model"):
            model = message["model"]
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "tool_use":
                name = block.get("name")
                tool_names[block.get("id")] = name
                target = str((block.get("input") or {}).get("file_path", ""))
                if PLAN_DIR_MARKER in target:
                    slug = Path(target).name
                    scope = "worktree" if WORKTREE_MARKER in target else "shared"
                    plan_slug_paths.setdefault(slug, set()).add(scope)
                elif name in MUTATING_TOOLS and mode == "plan" and not approved:
                    findings["B"].append({"ts": row.get("timestamp"), "tool": name, "target": target, "model": model})
            elif kind == "tool_result":
                name = tool_names.get(block.get("tool_use_id"))
                if name != "ExitPlanMode":
                    continue
                if block.get("is_error"):
                    findings["A"].append({"ts": row.get("timestamp"), "model": model})
                    models[(model or "unknown", "fail")] += 1
                else:
                    approved = True
                    models[(model or "unknown", "ok")] += 1

    for slug, scopes in plan_slug_paths.items():
        if len(scopes) > 1:
            findings["C"].append({"slug": slug, "scopes": sorted(scopes)})

    return {"findings": findings, "models": models}


def scan(root: Path, days: int, max_files: int) -> dict:
    """Scan the newest transcripts under ``root``, newest first, bounded by age and count."""

    projects = root / "projects"
    if not projects.is_dir():
        return {"scanned": 0, "A": [], "B": [], "C": [], "by_model": {}}

    cutoff = time.time() - days * 86400 if days > 0 else 0.0
    try:
        candidates = [p for p in projects.glob("*/*.jsonl") if p.is_file() and p.stat().st_mtime >= cutoff]
    except OSError:
        candidates = []
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    candidates = candidates[:max_files] if max_files > 0 else candidates

    out: dict = {"scanned": 0, "A": [], "B": [], "C": [], "by_model": {}}
    totals: Counter = Counter()
    for path in candidates:
        result = scan_transcript(path)
        out["scanned"] += 1
        for key in ("A", "B", "C"):
            for item in result["findings"][key]:
                out[key].append({**item, "session": path.stem[:12]})
        totals.update(result["models"])
    out["by_model"] = {f"{model}:{status}": count for (model, status), count in sorted(totals.items())}
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=int(os.environ.get("LIMEN_HARNESS_PROBE_DAYS", "7")))
    parser.add_argument("--max-files", type=int, default=int(os.environ.get("LIMEN_HARNESS_PROBE_MAX_FILES", "60")))
    parser.add_argument("--json", action="store_true", help="emit the full report as JSON")
    parser.add_argument("--root-only", action="store_true", help="check root liveness, skip the transcript scan")
    args = parser.parse_args()

    info = harness_paths.liveness()
    resolved = Path(info["resolved"])
    best_elsewhere = max(
        (row["transcripts"] for row in info["candidates"] if row["root"] != info["resolved"]),
        default=0,
    )
    relocated = not info["resolved_live"] and best_elsewhere > 0

    report: dict = {"root": info, "relocated": relocated}
    if not args.root_only:
        report["scan"] = scan(resolved, args.days, args.max_files)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 1 if relocated or _faults(report) else 0

    print(f"harness root: {info['resolved']}  (live={info['resolved_live']})")
    for row in info["candidates"]:
        mark = "*" if row["root"] == info["resolved"] else " "
        print(f"  {mark} {row['transcripts']:>5} transcripts  exists={row['exists']!s:<5} {row['root']}")
    if relocated:
        print(
            f"RELOCATED: resolved root holds no transcripts but a candidate holds {best_elsewhere}. "
            f"Set {harness_paths.HARNESS_ROOT_ENV} or teach limen.harness_paths the new layout."
        )

    if args.root_only:
        return 1 if relocated else 0

    found = report["scan"]
    print(f"\nscanned {found['scanned']} transcript(s), last {args.days}d")
    print(f"  A plan-exit rejected        : {len(found['A'])}")
    print(f"  B mutation while mode=plan  : {len(found['B'])}   <- read-only guarantee")
    print(f"  C worktree plan shadow      : {len(found['C'])}")
    if found["by_model"]:
        print("  ExitPlanMode by model:")
        for key, count in found["by_model"].items():
            print(f"      {key:<32} {count}")
    for item in found["B"]:
        print(f"  ! B {item['ts']} {item['tool']} -> {item['target']}")

    return 1 if relocated or _faults(report) else 0


def _faults(report: dict) -> bool:
    scan_result = report.get("scan")
    if not scan_result:
        return False
    return bool(scan_result["A"] or scan_result["B"] or scan_result["C"])


if __name__ == "__main__":
    raise SystemExit(main())
