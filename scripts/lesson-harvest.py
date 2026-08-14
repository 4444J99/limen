#!/usr/bin/env python3
"""
lesson-harvest.py — the MECHANICAL half of /lesson-harvest (chats → durable lessons).

The operator's law is already prose (memory feedback-codify-every-session-lesson): every
discussion carries lessons, and a discussion that is not processed into a durable owner was
wasted. This organ is the deterministic substrate that makes "processed" a checkable state
instead of a memory: it enumerates sessions, keeps the durable cursor of which ones have
been harvested, and prints the honest backlog. The REASONING — reading a transcript and
extracting its lessons — belongs to the /lesson-harvest skill (the experience-audit ↔
experience-judge twin pattern; siblings: decorum-keeper, vendor-insights).

Division of labor:
  - THIS SCRIPT (deterministic): `--queue` (unprocessed sessions, newest first), `--mark`
    (stamp a session processed with its lesson owner refs), `--check` (backlog predicate).
  - THE SKILL (model-in-the-loop): pull bounded excerpts via
    `scripts/vendor-insights.py cat-session`, extract lessons, route each to an EXISTING
    terminus — censor/precedents.jsonl · his-hand-levers.json · memory/*.md · board task
    via the broker — then call `--mark`. Never a fifth substrate
    (PREC-2026-07-30-plan-decisions-dont-bind).

Store paths are imported from scripts/insight-cross-vendor-ingest.py (VENDOR_REGISTRY +
claude_estate_roots) — one source of truth; this organ never re-declares a path. Stores
are only ever LISTED here (filenames + sizes); transcript content is read exclusively by
the skill through vendor-insights.py's bounded `cat-session`.

The cursor ledger is TRACKED at censor/lesson-harvest.jsonl and is PII-clean by
construction: session ids (opaque uuids), vendor names, sanitized project labels
(basename only — never a /Users/... path), timestamps, and owner REFERENCES (a precedent
id, a lever id, a memory slug, a task id). Raw prompt/response text never lands here —
the same firewall as EVERY-ASK-LEDGER.md.

Usage:
  python3 scripts/lesson-harvest.py --queue [--vendor claude] [--limit 20]
  python3 scripts/lesson-harvest.py --mark <session-id> --vendor claude \
      --lessons '[{"owner_kind":"precedent","owner_ref":"PREC-2026-08-14-..."}]'
  python3 scripts/lesson-harvest.py --mark <session-id> --vendor claude --none-found
  python3 scripts/lesson-harvest.py --check

Exit codes: `--queue`/`--mark` 0 ok, 1 error. `--check`: 0 ⟺ zero unprocessed sessions
in scope (the Definition-of-Done fixed point), 1 backlog remains, 2 no store reachable.
Scope exclusions (vendors without an enumerator, archive-only history) are PRINTED, never
silently dropped.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
CURSOR = Path(os.environ.get("LIMEN_LESSON_HARVEST_CURSOR") or LIMEN_ROOT / "censor" / "lesson-harvest.jsonl")

OWNER_KINDS = {"precedent", "lever", "memory", "task", "existing"}


def _load_ingest_module():
    ingest_path = Path(__file__).resolve().parent / "insight-cross-vendor-ingest.py"
    spec = importlib.util.spec_from_file_location("insight_cross_vendor_ingest", ingest_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _project_label(project_dir: Path) -> str:
    """A PII-clean label for a claude project dir. The dir name flattens an absolute path
    (-Users-<name>-Workspace-limen), which leaks the username — keep only the last path
    component, the repo/worktree name."""
    return project_dir.name.rsplit("-", 1)[-1] or "unknown"


def _claude_sessions(mod) -> list[dict]:
    """Top-level session transcripts across every claude estate root. Subagent transcripts
    (<project>/<sid>/subagents/agent-*.jsonl) are children of their parent session and are
    deliberately NOT independent harvest units."""
    sessions: list[dict] = []
    for root in mod.claude_estate_roots():
        for project in sorted(p for p in root.iterdir() if p.is_dir()):
            if project.name == "memory":
                continue
            for jsonl in project.glob("*.jsonl"):
                try:
                    stat = jsonl.stat()
                except OSError:
                    continue
                sessions.append(
                    {
                        "sid": jsonl.stem,
                        "vendor": "claude",
                        "project": _project_label(project),
                        "mtime": stat.st_mtime,
                        "bytes": stat.st_size,
                    }
                )
    return sessions


# Vendor → enumerator. Only lanes with a top-level-session enumerator are IN SCOPE for the
# backlog predicate; every other registry vendor is reported as excluded so the cap is loud
# (codex's 707 rollout files need the parent-session grouping vendor-insights.py owns —
# extend by reusing that index rather than re-deriving the grouping here).
ENUMERATORS = {"claude": _claude_sessions}


def _load_cursor() -> dict[tuple[str, str], dict]:
    done: dict[tuple[str, str], dict] = {}
    if not CURSOR.exists():
        return done
    for line in CURSOR.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            print(f"WARN unparseable cursor line skipped: {line[:80]}", file=sys.stderr)
            continue
        done[(str(rec.get("vendor")), str(rec.get("sid")))] = rec
    return done


def _scope(mod, vendor: str | None):
    """(in-scope sessions, excluded-vendor names). Excluded = registry vendors we cannot yet
    enumerate — printed by every verb, never silently dropped."""
    vendors = [vendor] if vendor else sorted(mod.VENDOR_REGISTRY)
    sessions: list[dict] = []
    excluded: list[str] = []
    for name in vendors:
        enum = ENUMERATORS.get(name)
        if enum is None:
            excluded.append(name)
            continue
        sessions.extend(enum(mod))
    return sessions, excluded


def cmd_queue(vendor: str | None, limit: int) -> int:
    mod = _load_ingest_module()
    sessions, excluded = _scope(mod, vendor)
    done = _load_cursor()
    todo = [s for s in sessions if (s["vendor"], s["sid"]) not in done]
    todo.sort(key=lambda s: s["mtime"], reverse=True)
    for s in todo[:limit]:
        day = datetime.fromtimestamp(s["mtime"], tz=timezone.utc).date().isoformat()
        print(f"{s['vendor']}\t{s['sid']}\t{s['project']}\t{day}\t{s['bytes']}")
    if len(todo) > limit:
        print(f"# +{len(todo) - limit} more unprocessed (raise --limit)", file=sys.stderr)
    for name in excluded:
        print(f"# excluded vendor (no enumerator yet): {name}", file=sys.stderr)
    return 0


def cmd_mark(sid: str, vendor: str, lessons_json: str | None, none_found: bool) -> int:
    if bool(lessons_json) == none_found:
        print("ERROR: pass exactly one of --lessons or --none-found", file=sys.stderr)
        return 1
    lessons: list[dict] = []
    if lessons_json:
        try:
            lessons = json.loads(lessons_json)
        except ValueError as exc:
            print(f"ERROR: --lessons is not JSON: {exc}", file=sys.stderr)
            return 1
        if not isinstance(lessons, list) or not lessons:
            print("ERROR: --lessons must be a non-empty JSON array", file=sys.stderr)
            return 1
        for item in lessons:
            kind = item.get("owner_kind") if isinstance(item, dict) else None
            ref = item.get("owner_ref") if isinstance(item, dict) else None
            if kind not in OWNER_KINDS or not ref:
                print(
                    f"ERROR: each lesson needs owner_kind in {sorted(OWNER_KINDS)} and a non-empty owner_ref: {item}",
                    file=sys.stderr,
                )
                return 1
    if (vendor, sid) in _load_cursor():
        print(f"already marked: {vendor}/{sid} (idempotent no-op)")
        return 0
    rec = {
        "sid": sid,
        "vendor": vendor,
        "harvested_at": _now_iso(),
        "lessons": [{"owner_kind": it["owner_kind"], "owner_ref": it["owner_ref"]} for it in lessons],
        "none_found": none_found,
    }
    CURSOR.parent.mkdir(parents=True, exist_ok=True)
    with CURSOR.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"marked: {vendor}/{sid} — {len(lessons)} lesson(s)" + (" [none found]" if none_found else ""))
    return 0


def cmd_check() -> int:
    mod = _load_ingest_module()
    sessions, excluded = _scope(mod, None)
    if not sessions and not CURSOR.exists():
        print("lesson-harvest: no reachable session store and no cursor — cannot determine backlog")
        return 2
    done = _load_cursor()
    by_vendor: dict[str, list[int]] = {}
    for s in sessions:
        row = by_vendor.setdefault(s["vendor"], [0, 0])
        if (s["vendor"], s["sid"]) in done:
            row[1] += 1
        else:
            row[0] += 1
    remaining_total = 0
    for name, (remaining, processed) in sorted(by_vendor.items()):
        remaining_total += remaining
        print(f"{name}: {remaining} unprocessed / {processed} processed")
    for name in excluded:
        print(f"excluded (no enumerator yet — backlog unknown, NOT zero): {name}")
    stale = [key for key in done if key not in {(s["vendor"], s["sid"]) for s in sessions}]
    if stale:
        print(
            f"note: {len(stale)} cursor records reference sessions no longer on disk (rotated/archived) — kept as history"
        )
    print(f"TOTAL unprocessed in scope: {remaining_total}")
    return 0 if remaining_total == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--queue", action="store_true")
    mode.add_argument("--mark", metavar="SESSION_ID")
    mode.add_argument("--check", action="store_true")
    ap.add_argument("--vendor", help="restrict --queue to one vendor; required with --mark")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--lessons", help="JSON array of {owner_kind, owner_ref} for --mark")
    ap.add_argument("--none-found", action="store_true", help="mark processed with zero lessons")
    args = ap.parse_args()
    if args.queue:
        return cmd_queue(args.vendor, args.limit)
    if args.mark:
        if not args.vendor:
            print("ERROR: --mark requires --vendor", file=sys.stderr)
            return 1
        return cmd_mark(args.mark, args.vendor, args.lessons, args.none_found)
    return cmd_check()


if __name__ == "__main__":
    sys.exit(main())
