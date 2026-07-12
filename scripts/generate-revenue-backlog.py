#!/usr/bin/env python3
"""generate-revenue-backlog — feed idle WIN-CLASS capacity REVENUE work, not busywork.

The diagnosis (2026-06-23): the daemon is healthy and spending correctly, but the queue is 100%
generated test-coverage/build-out maintenance — ZERO revenue-class. So codex/claude/agy (the proven
earners) and every expiring token window get fed busywork; the binding constraint on "use all tokens
toward August income" is the SUPPLY of real product work, not capacity or pacing.

`revenue-ladder.json` already ranks the products + their stage toward a first paying dollar, but
NOTHING converts that into dispatchable tasks — it just sits in JSON. generate-backlog.py only emits
6 templated maintenance levers (coverage/CI/docs/security/simplify/typing). This closes that gap:
it reads the ladder and emits a small, bounded set of REVENUE-CLASS tasks per active product, labeled
so they ride the accelerator on the win-class lanes and outrank test-coverage.

Identity is DERIVED from revenue-ladder.json (stage + whose_hand + first_dollar_path), never pinned.
Account creation (Ko-fi/Sponsors/LemonSqueezy) is genuinely his hand and is NOT emitted as a task;
everything that BUILDS the funnel and ships the products IS — so the funnel is live the instant he
creates the accounts.

Read-only by default (prints a plan). With --apply it appends `open` tasks via the limen schema
(validated) under the canonical queue lock (so it can't clobber a concurrent dispatch write). Never
dispatches. Floor-gated + id-deduped + capped: bounded, no flood.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.capacity import select_lanes  # noqa: E402
from limen.io import load_limen_file, save_limen_file  # noqa: E402
from limen.intake import contract_fields, github_pr_contract  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import submit_task_upsert  # noqa: E402

# Stages that still have build work between here and a paying dollar. live/monetized are already
# earning — don't generate build tasks for them.
_BUILD_STAGES = {"building", "deploy-ready"}

# A task is "revenue-class" (counts toward the revenue floor) if it carries any of these labels.
# These are the ledger win_classes for codex/claude/agy, so they also ride the dispatch accelerator.
_REVENUE_LABELS = {"revenue", "product", "ship-order"}

# statuses that mean a (repo,lever) is already being worked — never duplicate those.
_ACTIVE = {"open", "dispatched", "in_progress", "needs_human"}

# Per-stage revenue levers. (key, priority, title, context-template). {product}/{repo}/{path} filled
# per product. key = labels[0] (the per-(repo,lever) dedup handle); the win-class labels are appended.
# deploy-ready (e.g. the Exporter): the FUNNEL is the work — make the donate/Pro path live so the only
# remaining step is the his-hand account creation.
_DEPLOY_READY_LEVERS = [
    ("revenue-funding", "critical",
     "Stage the donation funnel for {product}",
     "In {repo}, add .github/FUNDING.yml (ko_fi + github sponsors entries — use the owner handle; if "
     "the exact Ko-fi slug isn't known yet, leave a single clearly-marked TODO) AND a concise "
     "'Support / Sponsor' section in the README linking both. Goal: the moment the accounts exist the "
     "donate path is ALREADY live. Tasteful, no nagware. Open a PR, keep the build green."),
    ("revenue-pro-tier", "critical",
     "Make the Pro-tier checkout merge-ready for {product}",
     "In {repo}, rebase the stacked Pro-tier / LemonSqueezy checkout PRs onto the default branch, "
     "resolve conflicts, and get every check green so the ONLY remaining step is pasting "
     "LEMONSQUEEZY_STORE_ID. Don't invent product scope — just unblock what's already built ({path})."),
    ("revenue-landing", "high",
     "Ship a landing page for {product}",
     "Create a single deploy-ready product page for {product} in {repo} (docs/ or a gh-pages-ready "
     "index) explaining the real value and linking install + the donation/Pro options. Real copy "
     "derived from what the product ACTUALLY does — no lorem, no invented features."),
    ("revenue-launch-post", "high",
     "Draft the build-in-public launch post for {product}",
     "Write a ready-to-post launch announcement for {product} (Show HN + Reddit + X variants), grounded "
     "in what it ACTUALLY does and its real users. Save as marketing/launch-post.md in {repo}. No hype, "
     "no invented metrics."),
]
# building: ship the product toward deploy-ready + close the gap to a payable feature — revenue-labeled
# so it outranks generic test-coverage and feeds the accelerator on the earner lanes.
_BUILDING_LEVERS = [
    ("revenue-ship", "high",
     "Drive {product} to deploy-ready",
     "In {repo}, clear the concrete blockers between the current state and a DEPLOYABLE product: get "
     "open PRs green + merged, fix the critical path, confirm the app runs end-to-end. Output: a "
     "deploy-ready build + a short DEPLOY.md listing exactly what remains."),
    ("revenue-readiness", "high",
     "First-paying-customer readiness pass on {product}",
     "In {repo}, find the single highest-leverage gap between the current product and something a "
     "stranger would pay for (first-dollar path: {path}) and close it with a real, tested change. "
     "One focused PR; keep CI green."),
]

# Deploy-ready funnel levers create durable artifacts. Once one lands, a later date suffix should not
# regenerate the same work just because the revenue floor has capacity again.
_COMPLETED_DEDUP_STATUSES = {"done", "archived"}
_COMPLETED_DEDUP_LEVERS = {k for k, *_ in _DEPLOY_READY_LEVERS}


def _ladder_path() -> Path:
    root = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
    return Path(os.environ.get("LIMEN_REVENUE_LADDER", str(root / "revenue-ladder.json")))


def _positive_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _products() -> list[dict]:
    """Active products from revenue-ladder.json, build-stage only, ranked. [] on any error (the
    generator must never break the feed beat)."""
    try:
        data = json.loads(_ladder_path().read_text())
    except Exception as e:  # noqa: BLE001
        print(f"  revenue-ladder unreadable ({e}) — nothing to generate.", file=sys.stderr)
        return []
    if not isinstance(data, dict):
        print(f"  revenue-ladder root is {type(data).__name__}, not a mapping — nothing to generate.", file=sys.stderr)
        return []
    raw_products = data.get("products") or []
    if not isinstance(raw_products, list):
        print(f"  revenue-ladder products is {type(raw_products).__name__}, not a list — nothing to generate.", file=sys.stderr)
        return []
    prods = [p for p in raw_products
             if isinstance(p, dict) and p.get("repo") and (p.get("stage") in _BUILD_STAGES)]
    prods.sort(key=lambda p: p.get("rank", 999))
    return prods


def _avg_headroom_pct() -> float | None:
    """Average live per-vendor headroom (0–100) from logs/usage.json, or None. Full tank ⇒ lift the
    revenue floor (same accelerator generate-backlog + discover-value use) so a full tank can't sit
    idle for lack of revenue work."""
    fpath = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)) / "logs" / "usage.json"
    try:
        vendors = (json.loads(fpath.read_text()) or {}).get("vendors", {})
        hs = [
            h
            for v in vendors.values()
            if isinstance(v, dict)
            for h in [_finite_float(v.get("headroom_pct"))]
            if h is not None
        ]
        return sum(hs) / len(hs) if hs else None
    except Exception:
        return None


def _levers_for(stage: str):
    return _DEPLOY_READY_LEVERS if stage == "deploy-ready" else _BUILDING_LEVERS


def _plan(tasks: list[Task], floor_base: int, max_new: int, board: object | None = None) -> tuple[list[Task], dict]:
    """Compute the revenue tasks to add. Pure (no I/O side effects). Returns (new_tasks, info)."""
    try:
        from limen.dispatch import _down_lanes
        dead = _down_lanes()
    except Exception:
        dead = set()
    dispatch_lanes = set(select_lanes(os.environ.get("LIMEN_DISPATCH_LANES", "auto"), board, down_lanes=dead)) | {"any"}

    def routable(t: Task) -> bool:
        lane = t.target_agent or "any"
        return lane in dispatch_lanes and lane not in dead

    open_rev = sum(
        1 for t in tasks
        if t.status == "open" and routable(t)
        and (set(t.labels or []) & _REVENUE_LABELS)
    )
    floor = floor_base
    avg_hr = _avg_headroom_pct()
    if avg_hr is not None and avg_hr >= 50:
        floor = int(round(floor_base * (1 + min(2.0, (avg_hr - 50) / 25))))
    info = {"open_rev": open_rev, "floor": floor, "avg_hr": avg_hr}
    if open_rev >= floor:
        return [], info
    need = min(floor - open_rev, max_new)

    prods = _products()
    if not prods:
        info["no_products"] = True
        return [], info

    existing = {t.id for t in tasks}
    lever_keys = {k for k, *_ in (_DEPLOY_READY_LEVERS + _BUILDING_LEVERS)}
    active_pairs = {
        (t.repo, t.labels[0])
        for t in tasks
        if t.repo
        and t.labels
        and t.labels[0] in lever_keys
        and (t.status in _ACTIVE or (t.status in _COMPLETED_DEDUP_STATUSES and t.labels[0] in _COMPLETED_DEDUP_LEVERS))
    }
    # feed least-loaded products first so we spread revenue work, not pile it on rank 1.
    load = Counter(t.repo for t in tasks if t.status in _ACTIVE and t.repo)

    stamp = date.today().isoformat()
    mmdd = date.today().strftime("%m%d")
    new: list[Task] = []
    # round-robin lever-index across products (ranked), so each product gets its #1 lever before any
    # gets its #2 — the nearest-dollar funnel work lands first.
    max_levers = max(len(_DEPLOY_READY_LEVERS), len(_BUILDING_LEVERS))
    for lever_idx in range(max_levers):
        if len(new) >= need:
            break
        for prod in sorted(prods, key=lambda p: load.get(p["repo"], 0)):
            if len(new) >= need:
                break
            levers = _levers_for(prod["stage"])
            if lever_idx >= len(levers):
                continue
            key, prio, title, ctx = levers[lever_idx]
            repo = prod["repo"]
            if (repo, key) in active_pairs:
                continue
            slug = repo.replace("/", "-").lower()
            tid = f"REV-{slug}-{key}-{mmdd}"
            if tid in existing:
                continue
            existing.add(tid)
            active_pairs.add((repo, key))
            product = prod.get("product", repo)
            path = prod.get("first_dollar_path") or prod.get("next_action") or "the paid tier"
            fmt = {"product": product, "repo": repo, "path": path}
            new.append(Task(
                id=tid, title=title.format(**fmt), repo=repo, type="code",
                target_agent="any", priority=prio, budget_cost=2, status="open",
                # labels[0] = lever key (dedup handle); the rest are win-classes (ride the accelerator).
                labels=[key, "revenue", "product", "ship-order", "generated"], urls=[],
                context=ctx.format(**fmt)
                + f" [revenue-backlog {stamp}: rank {prod.get('rank','?')}, stage {prod['stage']} — "
                  f"spend tokens on income, not busywork]",
                **contract_fields(github_pr_contract(repo, tid)),
                depends_on=[], created=stamp, dispatch_log=[],
            ))
    return new, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--floor", type=int, default=_positive_int(os.environ.get("LIMEN_REVENUE_FLOOR"), 12),
                    help="keep at least this many routable OPEN revenue-class tasks; generate up to it")
    ap.add_argument("--max-new", type=int, default=_positive_int(os.environ.get("LIMEN_REVENUE_MAX"), 12),
                    help="hard cap on tasks generated in one run (anti-flood)")
    ap.add_argument("--apply", action="store_true",
                    help="append to tasks.yaml (validated, atomic, under the queue lock)")
    args = ap.parse_args()

    path = Path(args.tasks)
    lf = load_limen_file(path)
    new, info = _plan(lf.tasks, args.floor, args.max_new, lf)

    hr = info.get("avg_hr")
    print(f"# generate-revenue-backlog: open-revenue={info['open_rev']} floor={info['floor']} "
          f"(base {args.floor}, avg headroom {hr if hr is None else round(hr)}%)")
    if info.get("no_products"):
        print("no active build-stage products in revenue-ladder.json — nothing to generate.")
        return 0
    if info["open_rev"] >= info["floor"]:
        print(f"revenue queue healthy: {info['open_rev']} >= {info['floor']} — nothing to generate.")
        return 0
    if not new:
        print("(every (product,lever) is already active — nothing new to generate.)")
        return 0

    print(f"-> generating {len(new)} revenue-class tasks across "
          f"{len(set(t.repo for t in new))} products (cap {args.max_new})\n")
    print("| new task id | product/repo | prio | lever |")
    print("|---|---|---|---|")
    for t in new:
        print(f"| {t.id} | {t.repo} | {t.priority} | {t.labels[0]} |")

    if not args.apply:
        print(f"\ndry-run — re-run with --apply to append {len(new)} tasks.")
        return 0

    # Apply lockless + atomic, exactly like the sibling generate-backlog voice it runs beside in the
    # C_FEED block (sequential within the beat; later loaders preserve these). Re-read fresh right
    # before the write so we pick up tasks an earlier sibling (mine-backlog) added this beat and never
    # double-land an id. NEVER skip on contention: the floor-gate makes this idempotent, so if a long
    # concurrent dispatch save ever clobbers, the next C_FEED beat simply re-adds (self-healing — no
    # silent "no").
    fresh = load_limen_file(path)
    have = {t.id for t in fresh.tasks}
    to_add = [t for t in new if t.id not in have]
    if not to_add:
        print("\n(all planned tasks already present after fresh re-read — nothing applied.)")
        return 0
    # TABVLARIVS producer path (Step 2.1). LIMEN_TICKETS_PRODUCE=1 → submit each fresh-deduped task as
    # an upsert ticket instead of writing tasks.yaml directly; the keeper folds them next beat. Default
    # OFF keeps the legacy validated append. `to_add` is already fresh-deduped, so no id clobbers.
    if os.environ.get("LIMEN_TICKETS_PRODUCE") == "1":
        session_id = os.environ.get("LIMEN_SESSION_ID", "generate-revenue-backlog")
        for t in to_add:
            submit_task_upsert(path, t, agent="generate-revenue-backlog", session_id=session_id)
        print(f"\nsubmitted {len(to_add)} revenue upsert tickets to the keeper's inbox (folds onto {path} next beat).")
        return 0
    fresh.tasks.extend(to_add)
    save_limen_file(path, fresh)
    print(f"\napplied: appended {len(to_add)} revenue tasks -> {path} (route+dispatch separately).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
