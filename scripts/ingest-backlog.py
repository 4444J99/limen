#!/usr/bin/env python3
"""ingest-backlog — release STAGED Studium expansion tasks into the live fleet queue, SAFELY.

The Studium's breadth (per-work music deepening, film companions, corpus fetches) is staged in
studium/expansion-backlog.yaml under a release-hold. This is the SANCTIONED funnel that merges the
CONTENT-class tasks into the daemon-contended tasks.yaml as a re-emitting C_FEED voice:

  * LOCKLESS + atomic — exactly like the sibling generate-backlog / generate-revenue-backlog voices.
    The daemon does NOT hold the queue lock across a beat, so taking queue_lock here would only STARVE
    this voice (it times out under live contention and skips every beat — the tasks never land). It
    re-reads fresh right before the write, then atomic-saves (temp file -> os.replace).
  * IDEMPOTENT + SELF-HEALING — only NEW task ids are appended, so it runs every beat as a no-op once
    seeded; if a long concurrent dispatch save ever clobbers the rows, the next beat simply re-adds
    them. (A one-shot lock-guarded apply was the bug; a re-emitting voice is the cure.)

It respects the backlog's OWN internal gates: only the content-authoring sections are released
(deepening — MINUS the in-flight odyssey — plus corpus_gaps and film.first_pass). The his-gate
sections (community / community_interaction / analysis / tier2_staged / Letterboxd posting) and any
row carrying a `gate:` field are NEVER released here.

Read-only by default (prints exactly what it WOULD add). With --apply it appends losslessly + atomically.
Never dispatches; the live daemon (autonomy mode "dispatch") routes the new tasks on its own beats.

PRECONDITION (executability): the fleet executes a task by cloning the repo's DEFAULT branch. These
content tasks need the studium/ scaffold (canon.yaml, the book-01 templates, scripts/studium-validate.py)
to be present on that branch. If the scaffold is not yet on origin/main, releasing these tasks would
seed dead-end work — get the scaffold onto the clone target FIRST (the studium go-live merge).

Usage:
  python3 scripts/ingest-backlog.py                                   # dry-run vs $LIMEN_ROOT/tasks.yaml
  python3 scripts/ingest-backlog.py --tasks ~/Workspace/limen/tasks.yaml --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("pyyaml required", file=sys.stderr)
    raise SystemExit(2)

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "cli" / "src"))
from limen.io import load_limen_file  # noqa: E402
from limen.intake import contract_fields, github_pr_contract  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import submit_task_upsert  # noqa: E402

SRC_DEFAULT = HERE / "studium" / "expansion-backlog.yaml"
# the Studium lives in this repo; the fleet authors arcs into studium/ and opens a PR here.
REPO = os.environ.get("LIMEN_STUDIUM_REPO", "organvm/limen")
# in-flight elsewhere (lane 1 authors the Odyssey directly this session) — never double-release it.
EXCLUDE_IDS = {"studium-deepen-odyssey"}


def content_tasks(doc: dict) -> list[dict]:
    """Only the CONTENT-authoring sections. Skip any row carrying a `gate:` (his-go), the
    excluded ids, and the his-gate sections entirely (community/community_interaction/analysis/
    tier2_staged are simply never read here). Order + dedupe by id."""
    rows: list[dict] = []
    rows += (doc.get("deepening") or {}).get("tasks", []) or []
    rows += (doc.get("corpus_gaps") or {}).get("tasks", []) or []
    rows += ((doc.get("film") or {}).get("first_pass") or {}).get("tasks", []) or []
    seen: set[str] = set()
    clean: list[dict] = []
    for t in rows:
        if not isinstance(t, dict):
            continue
        tid = (t.get("id") or "").strip()
        if not tid or tid in EXCLUDE_IDS or tid in seen:
            continue
        if t.get("gate"):  # a his-go row that slipped into a content section — never release
            continue
        seen.add(tid)
        clean.append(t)
    return clean


def to_task(t: dict, stamp: str) -> Task:
    tid = t["id"]
    title = t.get("title", tid)
    checklist = t.get("checklist")
    ctx = (f"STUDIUM content task (staged in studium/expansion-backlog.yaml, released to the fleet). "
           f"{title}. ")
    if checklist:
        ctx += (f"The authoritative division checklist (which divisions are done [check] vs todo) is "
                f"{checklist}. Author the NEXT BOUNDED BATCH of undone divisions (a handful per PR, "
                f"NOT all at once) as force-matched arcs + mirrored essays in the Iliad gold-standard "
                f"format (see studium/music/iliad/ + studium/essays/iliad/ and studium/music/<work>/PLAN.md). ")
    ctx += ("Acceptance: scripts/studium-validate.py must PASS (every force in studium/dominant-force.yaml; "
            "force_arc equals the ordered track forces; no intra-arc duplicate pieces). One green PR.")
    return Task(
        id=tid,
        title=title,
        repo=REPO,
        type="content",
        target_agent="any",  # routable — route.py distributes to a live, capable lane
        priority="medium",
        budget_cost=1,
        status="open",
        labels=["studium", "content", "expansion-backlog"],
        context=ctx,
        **contract_fields(github_pr_contract(REPO, tid)),
        created=stamp,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(SRC_DEFAULT))
    ap.add_argument(
        "--tasks",
        default=os.environ.get(
            "LIMEN_TASKS",
            str(Path(os.path.expanduser(os.environ.get("LIMEN_ROOT", "~/Workspace/limen"))) / "tasks.yaml"),
        ),
    )
    ap.add_argument("--apply", action="store_true", help="append to tasks.yaml losslessly (atomic, re-emitting)")
    args = ap.parse_args()

    src = Path(os.path.expanduser(args.source))
    doc = yaml.safe_load(src.read_text()) or {}
    staged = content_tasks(doc)
    stamp = date.today().isoformat()
    candidates = [to_task(t, stamp) for t in staged]
    path = Path(os.path.expanduser(args.tasks))

    if not args.apply:
        try:
            existing = {t.id for t in load_limen_file(path).tasks}
        except Exception as e:  # read-only dry-run must never break
            existing = set()
            print(f"(could not read {path}: {e})", file=sys.stderr)
        new = [t for t in candidates if t.id not in existing]
        print(f"# ingest-backlog DRY-RUN: {len(candidates)} content tasks staged; {len(new)} NEW "
              f"(not already in queue), {len(candidates) - len(new)} already present.")
        print(f"# source: {src}")
        print(f"# target: {path}  (repo={REPO})\n")
        print("| new task id | title |")
        print("|---|---|")
        for t in new:
            print(f"| {t.id} | {t.title} |")
        print(f"\ndry-run — re-run with --apply to append {len(new)} tasks (lossless atomic, re-emitting).")
        return 0

    # APPLY — lockless + atomic, exactly like the generate-revenue-backlog / generate-backlog voices it
    # runs beside in the C_FEED block. The daemon does NOT hold the queue lock across a beat, so taking
    # queue_lock here only STARVES this voice: under live contention it times out and skips EVERY beat,
    # so the tasks never land (observed live — "queue busy ... skipped" each beat). Instead, re-read
    # fresh right before the write (pick up ids a sibling added this beat, never double-land), extend,
    # and atomic-save. NEVER skip on contention: the id-dedupe makes this idempotent, so if a long
    # concurrent dispatch save ever clobbers, the next C_FEED beat simply re-adds (self-healing — the
    # "never a silent no" invariant; a one-shot lock-guarded apply was the bug, a re-emitting voice is
    # the cure).
    fresh = load_limen_file(path)  # fresh re-read right before the write (dedup only; read never clobbers)
    existing = {t.id for t in fresh.tasks}
    new = [t for t in candidates if t.id not in existing]
    if not new:
        print("nothing new — every staged content task already in the queue (idempotent no-op).")
        return 0

    # TABVLARIVS producer path (Step 2.1). When LIMEN_TICKETS_PRODUCE=1 this voice stops writing
    session_id = os.environ.get("LIMEN_SESSION_ID", "ingest-backlog")
    for task in new:
        submit_task_upsert(path, task, agent="ingest-backlog", session_id=session_id)
    print(
        f"submitted {len(new)} Studium content upsert tickets to the keeper's inbox "
        f"(TABVLARIVS folds them onto {path} next beat; never dispatched here)."
    )
    for t in new:
        print(f"  + {t.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
