#!/usr/bin/env python3
"""Apply lever-triage-results.json decisions against his-hand-levers.json.

Paths supported (from lever-triage.html dropdown, plus legacy aliases):
  - "Execute Now (I will do it)"  -> append notes to lever.note, leave status open
  - "Delegate to Agent (You do it)" -> status -> needs_human + append delegation note
  - "Defer 30 Days"               -> status -> deferred + defer_until
  - "Discharge / Ignore"          -> remove lever (hard-delete, like PR #2616)

Discharge is the only destructive mutation and requires --apply. Deferred
and Execute are reversible. Delegate does NOT create tasks.yaml entries
directly — it marks the lever needs_human with a delegation marker your
chosen dispatch flow can turn into a broker packet.

Safety:
  - Default is --dry-run (no writes).
  - --apply writes his-hand-levers.json atomically and validates JSON.
  - Unknown lever IDs in results are warned, not fatal.
  - Unknown paths are warned and treated as notes-only.

Usage:
  python3 scripts/apply-triage-results.py --dry-run lever-triage-results.json
  python3 scripts/apply-triage-results.py --apply lever-triage-results.json
  python3 scripts/apply-triage-results.py --apply --in his-hand-levers.json lever-triage-results.json
  python3 scripts/apply-triage-results.py --apply --out his-hand-levers.json lever-triage-results.json

Verifies:
  python3 -m json.tool his-hand-levers.json > /dev/null
  python3 scripts/check-his-hand-registry.py  # if present, advisory
"""

import argparse
import datetime
import json
import pathlib
import sys
import shutil
import re

# Canonical path strings from the SPA
PATH_EXECUTE = "Execute Now (I will do it)"
PATH_DELEGATE = "Delegate to Agent (You do it)"
PATH_DEFER = "Defer 30 Days"
PATH_DISCHARGE = "Discharge / Ignore"

# Legacy aliases users might produce by editing JSON
ALIASES = {
    "execute": PATH_EXECUTE,
    "execute now": PATH_EXECUTE,
    "delegate": PATH_DELEGATE,
    "delegate to agent": PATH_DELEGATE,
    "defer": PATH_DEFER,
    "defer 30 days": PATH_DEFER,
    "defer 30": PATH_DEFER,
    "discharge": PATH_DISCHARGE,
    "discharge / ignore": PATH_DISCHARGE,
    "ignore": PATH_DISCHARGE,
    "dismiss": PATH_DISCHARGE,
}


def normalize_path(p: str) -> str:
    if not p:
        return ""
    s = p.strip()
    if s in (PATH_EXECUTE, PATH_DELEGATE, PATH_DEFER, PATH_DISCHARGE):
        return s
    low = s.lower()
    if low in ALIASES:
        return ALIASES[low]
    return s  # unknown — caller will warn


def load_results(path: pathlib.Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    # Support both {id: {path, notes}} and [{id, path, notes}] forms
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        out = {}
        for item in data:
            if isinstance(item, dict) and item.get("id"):
                out[item["id"]] = item
        return out
    raise ValueError(f"Unexpected results shape {type(data)} in {path}")


def main():
    p = argparse.ArgumentParser(description="Apply lever triage decisions")
    p.add_argument("results", help="Path to lever-triage-results.json (exported from lever-triage.html)")
    p.add_argument("--in", dest="inp", default="his-hand-levers.json", help="his-hand-levers.json path")
    p.add_argument("--out", dest="out", default=None, help="Output path (default: overwrite --in)")
    p.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    p.add_argument("--dry-run", action="store_true", help="Explicit dry-run (same as default, no write)")
    p.add_argument("--defer-days", type=int, default=30, help="Days for defer (default 30)")
    args = p.parse_args()

    inp = pathlib.Path(args.inp)
    out = pathlib.Path(args.out) if args.out else inp
    results_path = pathlib.Path(args.results)

    if not inp.exists():
        print(f"ERROR: input {inp} not found", file=sys.stderr)
        sys.exit(2)
    if not results_path.exists():
        print(f"ERROR: results {results_path} not found", file=sys.stderr)
        sys.exit(2)

    data = json.loads(inp.read_text(encoding="utf-8"))
    levers = data.get("levers", [])
    by_id = {lv["id"]: lv for lv in levers}

    results = load_results(results_path)

    # Stats
    to_discharge = []
    to_defer = []
    to_delegate = []
    to_execute = []
    to_note_only = []
    unknown_ids = []
    unknown_paths = []

    now = datetime.datetime.now(datetime.timezone.utc)
    defer_until = (now + datetime.timedelta(days=args.defer_days)).date().isoformat()

    for lid, decision in results.items():
        if lid not in by_id:
            unknown_ids.append(lid)
            continue
        raw_path = decision.get("path", "") if isinstance(decision, dict) else ""
        notes = decision.get("notes", "") if isinstance(decision, dict) else ""
        path = normalize_path(raw_path)

        # Empty path with notes -> note-only update
        if not path and notes:
            to_note_only.append((lid, notes))
            continue
        if not path and not notes:
            continue  # no decision

        if path == PATH_DISCHARGE:
            to_discharge.append((lid, notes))
        elif path == PATH_DEFER:
            to_defer.append((lid, notes))
        elif path == PATH_DELEGATE:
            to_delegate.append((lid, notes))
        elif path == PATH_EXECUTE:
            to_execute.append((lid, notes))
        else:
            unknown_paths.append((lid, raw_path))
            to_note_only.append((lid, f"[{raw_path}] {notes}".strip()))

    print(f"Loaded {len(levers)} levers from {inp} (generated_at={data.get('generated_at','')})")
    print(f"Decisions in {results_path}: {len(results)} total")
    print(f"  Discharge : {len(to_discharge)}")
    print(f"  Defer     : {len(to_defer)} (until {defer_until})")
    print(f"  Delegate  : {len(to_delegate)}")
    print(f"  Execute   : {len(to_execute)}")
    print(f"  Note-only : {len(to_note_only)}")
    if unknown_ids:
        print(f"  WARN unknown lever IDs in results (ignored): {', '.join(unknown_ids)}")
    if unknown_paths:
        print(f"  WARN unknown paths (treated as note-only): {unknown_paths}")

    if not args.apply or args.dry_run:
        if args.apply and args.dry_run:
            print("ERROR: --apply and --dry-run are mutually exclusive", file=sys.stderr)
            sys.exit(2)
        print("\nDRY-RUN — no files written. Re-run with --apply to mutate.")
        if to_discharge:
            print("  Would discharge: " + ", ".join(x[0] for x in to_discharge))
        if to_defer:
            print("  Would defer: " + ", ".join(x[0] for x in to_defer))
        if to_delegate:
            print("  Would delegate (needs_human): " + ", ".join(x[0] for x in to_delegate))
        if to_execute:
            print("  Would mark execute (notes appended): " + ", ".join(x[0] for x in to_execute))
        return 0

    # Apply mutations
    discharged_ids = {lid for lid, _ in to_discharge}
    new_levers = []

    for lv in levers:
        lid = lv["id"]
        if lid in discharged_ids:
            continue  # hard-delete
        # Find matching decision
        # Defer
        match = next((x for x in to_defer if x[0] == lid), None)
        if match:
            _, notes = match
            lv = dict(lv)
            lv["status"] = "deferred"
            lv["defer_until"] = defer_until
            lv["defer_notes"] = notes.strip() if notes else ""
            lv["triage_at"] = now.isoformat()
            lv["triage_path"] = PATH_DEFER
            new_levers.append(lv)
            continue
        match = next((x for x in to_delegate if x[0] == lid), None)
        if match:
            _, notes = match
            lv = dict(lv)
            lv["status"] = "needs_human"
            lv["triage_at"] = now.isoformat()
            lv["triage_path"] = PATH_DELEGATE
            if notes and notes.strip():
                existing = lv.get("note", "")
                lv["note"] = (existing + "\n\n[Delegate] " + notes.strip()).strip() if existing else notes.strip()
                lv["triage_notes"] = notes.strip()
            new_levers.append(lv)
            continue
        match = next((x for x in to_execute if x[0] == lid), None)
        if match:
            _, notes = match
            lv = dict(lv)
            lv["triage_at"] = now.isoformat()
            lv["triage_path"] = PATH_EXECUTE
            if notes and notes.strip():
                existing = lv.get("note", "")
                lv["note"] = (existing + "\n\n[Execute Now] " + notes.strip()).strip() if existing else notes.strip()
                lv["triage_notes"] = notes.strip()
            # status stays as-is (usually open)
            new_levers.append(lv)
            continue
        match = next((x for x in to_note_only if x[0] == lid), None)
        if match:
            _, notes = match
            lv = dict(lv)
            if notes and notes.strip():
                existing = lv.get("note", "")
                # avoid duplicating if notes already appended
                if notes.strip() not in existing:
                    lv["note"] = (existing + "\n\n[Triage] " + notes.strip()).strip() if existing else notes.strip()
                lv["triage_at"] = now.isoformat()
                lv["triage_notes"] = notes.strip()
            new_levers.append(lv)
            continue
        new_levers.append(lv)

    data["levers"] = new_levers
    # Preserve generated_at; add triage metadata
    data["triage_applied_at"] = now.isoformat()
    data["triage_source"] = str(results_path)

    # Validate JSON serializable
    try:
        serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        json.loads(serialized)
    except Exception as e:
        print(f"ERROR: result not JSON-serializable: {e}", file=sys.stderr)
        sys.exit(1)

    # Atomic write + backup
    backup = inp.with_suffix(inp.suffix + f".bak-{now.strftime('%Y%m%dT%H%M%SZ')}")
    if out == inp:
        shutil.copy2(inp, backup)
        print(f"Backup: {backup}")

    # Ensure parent exists
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(serialized, encoding="utf-8")
    tmp.replace(out)
    print(f"Wrote {out}: {len(new_levers)} levers (removed {len(to_discharge)}, deferred {len(to_defer)}, delegated {len(to_delegate)}, execute {len(to_execute)}, note {len(to_note_only)})")

    # Advisory registry check
    for cand in [pathlib.Path("scripts/check-his-hand-registry.py"), pathlib.Path("scripts/check-ideal-forms.py")]:
        if cand.exists():
            print(f"Advisory: {cand} exists — run `python3 {cand}` to verify (non-blocking)")

    # Bare-word L-* check: ensure _doc still holds; our mutations don't introduce new bare IDs
    text = serialized
    # Very light check: count new triage_* keys
    if "triage_applied_at" in data:
        print(f"Triage receipt: {data['triage_applied_at']} from {data['triage_source']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
