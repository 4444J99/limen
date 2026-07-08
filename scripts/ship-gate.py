#!/usr/bin/env python3
"""ship-gate.py — product-facing "done" requires a reachable external artifact.

The gap this closes (retro 2026-06-24→07-08, findings 4 + gap-model): 101 creative
asks produced code-complete organs, merged PRs, and receipts — and nothing a user
could reach. MONETA's deployed URL returned nothing (curl 000) while every internal
predicate read green. The drift predictor was structural: anything whose deliverable
is an ARMED BEHAVIOR drifts unless a gate demands the artifact itself.

The predicate: a product-facing claim of "done" is satisfied ONLY by a reachable
external artifact — a deployed URL returning 200, a served artifact still carrying
its rail, a posted link, a booked event id. Never a merged PR alone, never a
receipt, never a filed lever (PREC-2026-07-08-armed-valve-outcome).

Two rungs:
  • SURFACES — spec/ship-surfaces.json registers each product's user-reachable
    artifact; every entry is probed (http_200 / http_contains). A dark artifact
    is a RED product, whatever the board says.
  • TASKS — every `done`/`archived` task labelled ``product-facing`` (updated in
    the last --since days) must carry at least one reachable http(s) artifact in
    its ``urls`` or its last dispatch_log result. No artifact → RED.

Exit codes: 0 = all green; 1 = any RED (with --check).
Stamps logs/ship-gate.json. CI runs the fixture test only (network is the beat's
job — metabolize.sh wires the live probe).

Usage:
  python3 scripts/ship-gate.py                 # report + stamp
  python3 scripts/ship-gate.py --check         # gate mode
  python3 scripts/ship-gate.py --task ID       # gate one task's done-claim
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))
sys.path.insert(0, str(SCRIPT_ROOT / "cli" / "src"))

URL_RE = re.compile(r"https?://[^\s\"'<>\])]+")
PR_URL_RE = re.compile(r"github\.com/[^/]+/[^/]+/pull/\d+")
LABEL = "product-facing"


def probe(url, needle=None, timeout=10):
    """(ok, note). curl-000-equivalent (unreachable) is False, never an exception."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "limen-ship-gate"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if needle is not None:
                body = resp.read(4_000_000).decode("utf-8", errors="replace")
                ok = needle in body
                return ok, f"{resp.status}, rail {'present' if ok else 'STRIPPED'}"
            return 200 <= resp.status < 300, str(resp.status)
    except Exception as exc:  # noqa: BLE001 — unreachable IS the finding
        return False, f"unreachable ({type(exc).__name__})"


def surface_rung(registry):
    rows = []
    for s in registry.get("surfaces", []):
        ok, note = probe(s["url"], s.get("needle"))
        rows.append(dict(rung="surface", id=s["id"], ok=ok, note=note, url=s["url"], what=s.get("what", "")))
    return rows


def task_artifacts(task):
    """Candidate artifact URLs from a task: urls[] + last dispatch_log result text.

    A PR url is NOT an artifact (a merged PR alone never satisfies the gate).
    """
    candidates = []
    for u in task.urls or []:
        candidates.append(str(u))
    log = task.dispatch_log or []
    if log:
        last = log[-1]
        blob = json.dumps(last.model_dump() if hasattr(last, "model_dump") else str(last), default=str)
        candidates.extend(URL_RE.findall(blob))
    seen, out = set(), []
    for u in candidates:
        u = u.rstrip(".,;:")
        if PR_URL_RE.search(u) or "github.com" in u and "/pull/" in u:
            continue
        if u.startswith("http") and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def task_rung(tasks, since_days, only_id=None, probe_cap=20):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=since_days)
    rows, probes = [], 0
    for t in tasks:
        if only_id and t.id != only_id:
            continue
        if not only_id:
            if t.status not in ("done", "archived") or LABEL not in (t.labels or []):
                continue
            upd = str(getattr(t, "updated", "") or "")
            try:
                when = datetime.datetime.fromisoformat(upd.replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=datetime.timezone.utc)
                if when < cutoff:
                    continue
            except ValueError:
                pass  # unparsable updated → still audited; a dark artifact must not hide behind a bad date
        arts = task_artifacts(t)
        if not arts:
            rows.append(dict(rung="task", id=t.id, ok=False, note="no external artifact on a product-facing done claim", url="", what=t.title[:80]))
            continue
        ok_any, notes = False, []
        for u in arts[:3]:
            if probes >= probe_cap:
                notes.append("probe cap reached")
                break
            probes += 1
            ok, note = probe(u)
            notes.append(f"{u} → {note}")
            if ok:
                ok_any = True
                break
        rows.append(dict(rung="task", id=t.id, ok=ok_any, note="; ".join(notes), url=arts[0], what=t.title[:80]))
    return rows


def stamp(rows, path):
    payload = dict(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        red=[r["id"] for r in rows if not r["ok"]],
        green=sum(1 for r in rows if r["ok"]),
        rows=rows,
    )
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=1) + "\n")
    except OSError as exc:
        print(f"  (stamp skipped: {exc})", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Product-facing done requires a reachable external artifact.")
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 on any RED")
    ap.add_argument("--task", help="gate a single task id's done-claim (ignores label/status filters)")
    ap.add_argument("--since", type=int, default=14, help="only audit done tasks updated in the last N days")
    ap.add_argument("--surfaces", default=str(SCRIPT_ROOT / "spec" / "ship-surfaces.json"))
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", str(ROOT / "tasks.yaml")))
    ap.add_argument("--no-tasks", action="store_true", help="surfaces rung only (skip the board)")
    ap.add_argument("--stamp", default=str(ROOT / "logs" / "ship-gate.json"))
    args = ap.parse_args(argv)

    registry = json.loads(Path(args.surfaces).read_text())
    rows = surface_rung(registry) if not args.task else []

    if not args.no_tasks:
        try:
            from limen.io import load_limen_file  # noqa: PLC0415 — deferred so --no-tasks never needs the package

            lf = load_limen_file(Path(args.tasks))
            rows += task_rung(lf.tasks, args.since, only_id=args.task)
        except Exception as exc:  # noqa: BLE001 — a broken board read must surface, not crash the beat
            rows.append(dict(rung="task", id="_board", ok=False, note=f"board unreadable: {exc}", url="", what=""))

    stamp(rows, args.stamp)

    red = [r for r in rows if not r["ok"]]
    for r in rows:
        mark = "ok " if r["ok"] else "RED"
        if not r["ok"]:
            print(f"  {mark} [{r['rung']}] {r['id']}: {r['note']}" + (f" — {r['what']}" if r["what"] else ""))
    print(f"ship-gate: {len(rows) - len(red)} green, {len(red)} red")

    if args.check and red:
        print("ship-gate: RED — a product-facing done-claim has no reachable artifact: "
              + ", ".join(r["id"] for r in red), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
