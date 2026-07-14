#!/usr/bin/env python3
"""generate-organ-backlog — feed idle capacity INSTITUTION-BUILDING work (the VLTIMA organs).

The diagnosis (2026-06-23): the fleet runs at ~25-33% of capacity; the binding constraint is the
SUPPLY of high-value work, not capacity. Meanwhile the user has eight-plus half-built INSTITUTIONS
(legal, financial, education, media, governance, consulting, artist, social, health) — the pillars the
rich have behind them and he wants rebuilt as AI-run organs ("the prosthesis for human weakness"; his
own term: VLTIMA MATERIA). The idle horsepower and the unfinished organs are the same problem from two
ends. This converts the institutional census (organ-ladder.json) into bounded, dispatchable build
tasks so every beat drives every organ toward its next maturity band.

Sibling of generate-revenue-backlog.py — SAME safety contract: identity DERIVED from organ-ladder.json
(never pinned); read-only by default (prints a plan); with --apply it appends `open` tasks via the
limen schema (validated, atomic, fresh re-read before write) so it can't clobber a concurrent dispatch
write; never dispatches; floor-gated + id-deduped + capped (bounded, no flood). Organ artifacts are
authored into the limen repo under organs/<pillar>/ (the proven Studium home) so dispatch never hits a
dead clone.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.capacity import select_lanes  # noqa: E402
from limen.io import load_limen_file, queue_lock, save_limen_file  # noqa: E402
from limen.intake import contract_fields, github_pr_contract  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import submit_task_upsert  # noqa: E402

# Maturity bands that still have build work. mature(>=90) is self-running — no generated tasks.
_BUILD_STAGES = {"scaffold", "building", "maturing"}

# A task is "organ-class" (counts toward the organ floor) if it carries any of these labels.
_ORGAN_LABELS = {"organ", "institution", "vltima"}

# statuses that mean a (repo,lever) is already being worked — never duplicate those.
_ACTIVE = {"open", "dispatched", "in_progress", "needs_human", "failed_blocked"}

# Per-band institution levers. {pillar}/{organ}/{rival}/{macro}/{micro}/{domain_map}/{first_artifact}/
# {home}/{repo} are filled per organ from organ-ladder.json. key = labels[0] (the per-(repo,lever)
# dedup handle scoped by pillar); the organ win-classes are appended. Every lever AUTHORS into
# {repo}:{home} so the clone target always exists.
_SCAFFOLD_LEVERS = [
    ("organ-kernel", "critical",
     "Map the VLTIMA 5-primitive kernel to the {pillar} organ",
     "In {repo}, author {home}KERNEL.md: map the domain-neutral kernel (Member - Mandate - Standing - "
     "Standard - Governance) onto the {pillar} domain ({domain_map}). State the organ's purpose as an "
     "institutional prosthesis, its MACRO deployment ({macro}) and its MICRO deployment ({micro}). "
     "Generic + nameless underneath, his instance on top. One PR, no lorem."),
    ("organ-charter", "critical",
     "Charter the {pillar} organ as an institution rivaling {rival}",
     "In {repo} {home}, write CHARTER.md: the org-chart of AI roles (the 'virtual firm/team'), the "
     "workflows it runs, its inputs/outputs, and exactly how it gives one person the institutional "
     "weight of {rival}. Concrete and buildable. No invented capabilities."),
    ("organ-firstslice", "high",
     "Build the first working vertical slice of the {pillar} organ",
     "In {repo} {home}, deliver one real end-to-end artifact the organ produces: {first_artifact}. A "
     "tangible proof the institution works for ONE real case. One PR; tested where it is code; drafts "
     "only for anything outbound (his hand on send/sign)."),
]
_BUILDING_LEVERS = [
    ("organ-deepen", "high",
     "Deepen the {pillar} organ toward a usable institution",
     "In {repo} {home} (and reference its product repo where relevant), close the single highest-leverage "
     "gap between the current scaffold and something a real person could RELY ON for {pillar}. Ship "
     "{first_artifact} if not yet done, else the next gap. One focused PR."),
    ("organ-selffeed", "high",
     "Wire the {pillar} organ to advance autonomously",
     "Make the {pillar} organ self-feeding like the revenue/studium voices: bump its maturity in "
     "organ-ladder.json as slices land, and add/extend a beat or generator hook so the conductor keeps "
     "driving it without a human in the loop. Keep it lockless + idempotent."),
]
_MATURING_LEVERS = [
    ("organ-face", "high",
     "Make the {pillar} organ's macro + micro face excellent",
     "In {repo} {home}, author the polished MACRO face ({macro} — the platform anyone can hold) AND the "
     "MICRO instance ({micro} — his own), grounded in what the organ actually does. Real copy, ready to "
     "show. One PR."),
    ("organ-operationalize", "medium",
     "Operationalize {pillar} governance (rules as checks)",
     "Turn the {pillar} organ's rules into executable/checkable form (mirror cvrsvs-honorvm): a small "
     "validator or checklist that PROVES the institution runs correctly. One PR, green."),
]


def _ladder_path() -> Path:
    root = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
    return Path(os.environ.get("LIMEN_ORGAN_LADDER", str(root / "organ-ladder.json")))


def _organs() -> list[dict]:
    """Active organs from organ-ladder.json, build-stage only, ranked. [] on any error (the generator
    must never break the feed beat)."""
    try:
        data = json.loads(_ladder_path().read_text())
    except Exception as e:  # noqa: BLE001
        print(f"  organ-ladder unreadable ({e}) — nothing to generate.", file=sys.stderr)
        return []
    orgs = [o for o in (data.get("organs") or [])
            if isinstance(o, dict) and o.get("repo") and (o.get("stage") in _BUILD_STAGES)]
    orgs.sort(key=lambda o: o.get("rank", 999))
    return orgs


def _avg_headroom_pct() -> float | None:
    """Average live per-vendor headroom (0-100) from logs/usage.json, or None. Full tank => lift the
    organ floor (same accelerator the revenue/coverage generators use) so a full tank can't sit idle
    for lack of institution work."""
    fpath = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)) / "logs" / "usage.json"
    try:
        vendors = (json.loads(fpath.read_text()) or {}).get("vendors", {})
        hs = [v["headroom_pct"] for v in vendors.values()
              if isinstance(v, dict) and isinstance(v.get("headroom_pct"), (int, float))]
        return sum(hs) / len(hs) if hs else None
    except Exception:
        return None


def _levers_for(stage: str):
    if stage == "scaffold":
        return _SCAFFOLD_LEVERS
    if stage == "maturing":
        return _MATURING_LEVERS
    return _BUILDING_LEVERS


def _fmt(o: dict) -> dict:
    return {
        "pillar": o.get("pillar", "?"),
        "organ": o.get("organ", o.get("pillar", "?")),
        "repo": o["repo"],
        "home": o.get("home", f"organs/{o.get('pillar','x')}/"),
        "rival": o.get("rival", "a top-tier institution"),
        "macro": o.get("macro", "a platform anyone can hold"),
        "micro": o.get("micro", "his own instance"),
        "domain_map": o.get("domain_map", "Member/Mandate/Standing/Standard/Governance"),
        "first_artifact": o.get("first_artifact", "one real end-to-end artifact"),
    }


def _plan(tasks: list[Task], floor_base: int, max_new: int, board: object | None = None) -> tuple[list[Task], dict]:
    """Compute the organ tasks to add. Pure (no I/O side effects). Returns (new_tasks, info)."""
    try:
        from limen.dispatch import _down_lanes
        dead = _down_lanes()
    except Exception:
        dead = set()
    dispatch_lanes = set(select_lanes(os.environ.get("LIMEN_DISPATCH_LANES", "auto"), board, down_lanes=dead)) | {"any"}

    def routable(t: Task) -> bool:
        lane = t.target_agent or "any"
        return lane in dispatch_lanes and lane not in dead

    open_org = sum(
        1 for t in tasks
        if t.status == "open" and routable(t)
        and (set(t.labels or []) & _ORGAN_LABELS)
    )
    floor = floor_base
    avg_hr = _avg_headroom_pct()
    if avg_hr is not None and avg_hr >= 50:
        floor = int(round(floor_base * (1 + min(2.0, (avg_hr - 50) / 25))))
    info = {"open_org": open_org, "floor": floor, "avg_hr": avg_hr}
    if open_org >= floor:
        return [], info
    need = min(floor - open_org, max_new)

    orgs = _organs()
    if not orgs:
        info["no_organs"] = True
        return [], info

    existing = {t.id for t in tasks}
    lever_keys = {k for k, *_ in (_SCAFFOLD_LEVERS + _BUILDING_LEVERS + _MATURING_LEVERS)}
    # dedup handle is (pillar, lever) — many organs share one repo (organvm/limen), so scope by pillar.
    active_pairs = set()
    for t in tasks:
        if t.status in _ACTIVE and t.labels and t.labels[0] in lever_keys:
            pillar = next((lab.split(":", 1)[1] for lab in t.labels if lab.startswith("pillar:")), t.repo)
            active_pairs.add((pillar, t.labels[0]))
    # feed least-loaded pillars first so we spread institution work, not pile it on rank 1.
    load = Counter(
        next((lab.split(":", 1)[1] for lab in (t.labels or []) if lab.startswith("pillar:")), None)
        for t in tasks if t.status in _ACTIVE
    )

    stamp = date.today().isoformat()
    mmdd = date.today().strftime("%m%d")
    new: list[Task] = []
    max_levers = max(len(_SCAFFOLD_LEVERS), len(_BUILDING_LEVERS), len(_MATURING_LEVERS))
    for lever_idx in range(max_levers):
        if len(new) >= need:
            break
        for org in sorted(orgs, key=lambda o: load.get(o.get("pillar"), 0)):
            if len(new) >= need:
                break
            levers = _levers_for(org["stage"])
            if lever_idx >= len(levers):
                continue
            key, prio, title, ctx = levers[lever_idx]
            pillar = org.get("pillar", org["repo"])
            if (pillar, key) in active_pairs:
                continue
            tid = f"ORG-{pillar}-{key}-{mmdd}"
            if tid in existing:
                continue
            existing.add(tid)
            active_pairs.add((pillar, key))
            fmt = _fmt(org)
            note = org.get("note", "")
            new.append(Task(
                id=tid, title=title.format(**fmt), repo=org["repo"], type="content",
                target_agent="any", priority=prio, budget_cost=2, status="open",
                # labels[0] = lever key (dedup handle); pillar:<x> scopes dedup; rest = organ win-classes.
                labels=[key, f"pillar:{pillar}", "organ", "institution", "vltima", "generated"], urls=[],
                context=ctx.format(**fmt)
                + (f" CONSTRAINT: {note}." if note else "")
                + f" [organ-backlog {stamp}: rank {org.get('rank','?')}, maturity {org.get('maturity','?')}% "
                  f"stage {org['stage']} — convert idle fleet capacity into institutional weight (VLTIMA).]",
                **contract_fields(github_pr_contract(org["repo"], tid)),
                depends_on=[], created=stamp, dispatch_log=[],
            ))
    return new, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--floor", type=int, default=int(os.environ.get("LIMEN_ORGAN_FLOOR", "9")),
                    help="keep at least this many routable OPEN organ-class tasks; generate up to it")
    ap.add_argument("--max-new", type=int, default=int(os.environ.get("LIMEN_ORGAN_MAX", "9")),
                    help="hard cap on tasks generated in one run (anti-flood)")
    ap.add_argument("--apply", action="store_true",
                    help="append to tasks.yaml (validated, atomic, fresh re-read before write)")
    args = ap.parse_args()

    path = Path(args.tasks)
    lf = load_limen_file(path)
    new, info = _plan(lf.tasks, args.floor, args.max_new, lf)

    hr = info.get("avg_hr")
    print(f"# generate-organ-backlog: open-organ={info['open_org']} floor={info['floor']} "
          f"(base {args.floor}, avg headroom {hr if hr is None else round(hr)}%)")
    if info.get("no_organs"):
        print("no build-stage organs in organ-ladder.json — nothing to generate.")
        return 0
    if info["open_org"] >= info["floor"]:
        print(f"organ queue healthy: {info['open_org']} >= {info['floor']} — nothing to generate.")
        return 0
    if not new:
        print("(every (pillar,lever) is already active — nothing new to generate.)")
        return 0

    print(f"-> generating {len(new)} organ-class tasks across "
          f"{len(set(t.labels[1] for t in new))} pillars (cap {args.max_new})\n")
    print("| new task id | pillar/repo | prio | lever |")
    print("|---|---|---|---|")
    for t in new:
        print(f"| {t.id} | {t.repo} | {t.priority} | {t.labels[0]} |")

    if not args.apply:
        print(f"\ndry-run — re-run with --apply to append {len(new)} tasks.")
        return 0

    # APPLY: the WHOLE read-modify-write under the shared queue_lock (the same mkdir-mutex the heartbeat
    # and dispatchers hold) so a manual run can never torn-write with a concurrent daemon dispatch save.
    # Fresh read UNDER the lock; only NEW ids appended (idempotent). NEVER a silent dead-stop on a busy
    # lock: the floor-gate makes the next beat self-correct, so we report + exit non-zero, never swallow.
    with queue_lock(path) as got:
        if not got:
            print("\nqueue busy (lock timeout) — skipped; re-run (self-corrects, never racing the daemon).")
            return 1
        fresh = load_limen_file(path)
        have = {t.id for t in fresh.tasks}
        to_add = [t for t in new if t.id not in have]
        if not to_add:
            print("\n(all planned tasks already present after fresh re-read — nothing applied.)")
            return 0
        # TABVLARIVS producer path (Step 2.1). LIMEN_TICKETS_PRODUCE=1 → submit each fresh-deduped task
        # as an upsert ticket instead of writing tasks.yaml directly; the keeper folds them next beat.
        # Default OFF keeps the legacy validated append. submit_ticket is itself lock-free (os.link).
        if os.environ.get("LIMEN_TICKETS_PRODUCE") == "1":
            session_id = os.environ.get("LIMEN_SESSION_ID", "generate-organ-backlog")
            for t in to_add:
                submit_task_upsert(path, t, agent="generate-organ-backlog", session_id=session_id)
            print(f"\nsubmitted {len(to_add)} organ upsert tickets to the keeper's inbox (folds onto {path} next beat).")
            return 0
        fresh.tasks.extend(to_add)
        save_limen_file(path, fresh)
    print(f"\napplied: appended {len(to_add)} organ tasks -> {path} (route+dispatch separately).")
    for t in to_add:
        print(f"  + {t.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
