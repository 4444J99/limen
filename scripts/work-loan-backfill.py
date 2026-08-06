#!/usr/bin/env python3
"""Work-loan backfill organ: convert loan-less open tasks into dispatchable packets.

Gauge + effector for the candidate-starvation cut of the 07-19 starvation: 738/829 open
tasks fail WorkLoanV1 readiness, so even an open dispatch valve finds ~8 jules candidates.
This organ derives the missing loan fields mechanically (limen.work_loan_backfill) under
the declarative quality bar of docs/repo-predicates.yaml, and submits each enrichment as
a preconditioned TABVLARIVS ticket — the keeper folds it, this process never writes the
board. Refusals are COUNTED with reasons, never silent; the refusal census is the honest
statement of what still needs a model/human authoring pass.

Dry-run (census-only) by default: LIMEN_WORK_LOAN_BACKFILL_APPLY=1 or --apply arms.
Bounded per run (--limit, default 25 — the jules-supply per_run_cap, bounding tasks.yaml
churn through the single-writer queue). Exclusions the pure module cannot see: chronic
non-progress tasks (dispatch.chronic_dispatch_reason), needs-human labels, partner lanes
(limen.partition_lanes.heuristics_may_promote).

Exit 0 always in dry-run; exit 0 when armed (minting is progress, an empty mintable set
is a fixed point). Advisory exit 1 only when armed minting fails to submit.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from limen.dispatch import chronic_dispatch_reason  # noqa: E402
from limen.estate import append_aliases, load_estate_cache  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.partition_lanes import heuristics_may_promote  # noqa: E402
from limen.tabularius import INTENT_UPSERT, Ticket, new_ticket_id, submit_ticket  # noqa: E402
from limen.work_loan_backfill import derive_loan_patch, load_repo_predicates  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
REGISTRY = Path(os.environ.get("LIMEN_REPO_PREDICATES", str(ROOT / "docs" / "repo-predicates.yaml")))
RECEIPTS = Path(os.environ.get("LIMEN_WORK_LOAN_BACKFILL_RECEIPTS", str(ROOT / "logs" / "work-loan-backfill.jsonl")))
ESTATE_CACHE = Path(os.environ.get("LIMEN_ESTATE_REPOS_CACHE", str(ROOT / "logs" / "estate-repos.json")))
ESTATE_TTL_HOURS = float(os.environ.get("LIMEN_ESTATE_CACHE_TTL_HOURS", "24") or 24)

_EXCLUDED_LABELS = {"needs-human", "operator-paused"}


def _probe_aliases(board, estate):
    """Follow GitHub transfer/rename redirects for board repos the roster doesn't know.

    The board records the path a task was FILED under; a transferred repo leaves those
    rows pointing at a redirect stub GitHub still answers for. One `gh repo view` per
    unique unknown name (bounded by LIMEN_ESTATE_ALIAS_PROBE_MAX) recovers the canonical
    path; hits are folded into the cache (limen.estate.append_aliases) so the next run
    pays nothing. Returns the estate with the new aliases applied.
    """
    import dataclasses

    limit = int(os.environ.get("LIMEN_ESTATE_ALIAS_PROBE_MAX", "40") or 40)
    unknown: list[str] = []
    seen: set[str] = set()
    for task in board.tasks:
        repo = str(task.repo or "").strip()
        if not repo or task.status != "open" or repo in seen:
            continue
        seen.add(repo)
        if "/" in repo and estate.resolve(repo) is None:
            unknown.append(repo)
    found: dict[str, str] = {}
    for repo in unknown[:limit]:
        try:
            proc = subprocess.run(
                ["gh", "repo", "view", repo, "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        canonical = proc.stdout.strip()
        if proc.returncode != 0 or not canonical or canonical == repo:
            continue
        if canonical in estate.repos:
            found[repo] = canonical
    if found:
        append_aliases(ESTATE_CACHE, found)
        estate = dataclasses.replace(estate, aliases={**estate.aliases, **found})
    skipped = max(0, len(unknown) - limit)
    if skipped:
        print(f"  work-loan-backfill: alias probe capped — {skipped} unknown repo name(s) deferred to the next run")
    return estate


def _load_estate(now: datetime):
    """Hot cache first; one bounded refresh attempt when the cache is absent/stale.

    Returns None on refresh failure — the pure module then falls back to registry-only
    membership, so a network outage NARROWS supply to the value tier, never inverts it.
    """
    estate = load_estate_cache(ESTATE_CACHE, now=now, ttl_hours=ESTATE_TTL_HOURS)
    if estate is not None:
        return estate
    if os.environ.get("LIMEN_ESTATE_REFRESH", "1") != "1":
        return None
    refresher = Path(__file__).resolve().parent / "estate-repos-refresh.py"
    try:
        subprocess.run([sys.executable, str(refresher)], capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    return load_estate_cache(ESTATE_CACHE, now=now, ttl_hours=ESTATE_TTL_HOURS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_WORK_LOAN_BACKFILL_LIMIT", "25")))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    armed = args.apply or os.environ.get("LIMEN_WORK_LOAN_BACKFILL_APPLY", "0") == "1"

    board = load_limen_file(TASKS)
    registry = load_repo_predicates(REGISTRY)
    now = datetime.now(timezone.utc)
    estate = _load_estate(now)
    if estate is not None:
        estate = _probe_aliases(board, estate)

    reasons: dict[str, int] = {}
    minted = 0
    failures = 0
    rows = []
    for task in board.tasks:
        if minted >= args.limit and armed:
            break
        if task.status != "open":
            continue
        labels = {str(label).strip().lower() for label in (task.labels or [])}
        if labels & _EXCLUDED_LABELS:
            reasons["excluded:label"] = reasons.get("excluded:label", 0) + 1
            continue
        if task.repo and not heuristics_may_promote(task.repo):
            reasons["excluded:partner-lane"] = reasons.get("excluded:partner-lane", 0) + 1
            continue
        if chronic_dispatch_reason(task):
            reasons["excluded:chronic"] = reasons.get("excluded:chronic", 0) + 1
            continue
        patch, reason = derive_loan_patch(task, registry, estate)
        if patch is None:
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        reasons["mintable"] = reasons.get("mintable", 0) + 1
        if not armed:
            continue
        if minted >= args.limit:
            continue
        ticket = Ticket(
            ticket_id=new_ticket_id("work-loan-backfill"),
            timestamp=now,
            agent="claude",
            session_id="work-loan-backfill-organ",
            intent=INTENT_UPSERT,
            task_id=task.id,
            patch=patch,
            # optimistic guard: only enrich a task that is STILL open when the keeper folds it
            precondition={"status": "open"},
        )
        try:
            submit_ticket(TASKS, ticket)
        except Exception as exc:  # noqa: BLE001 — one bad ticket must not stop the batch
            failures += 1
            rows.append({"ts": now.isoformat(timespec="seconds"), "task": task.id, "outcome": f"failed: {exc}"[:200]})
            continue
        minted += 1
        rows.append(
            {
                "ts": now.isoformat(timespec="seconds"),
                "task": task.id,
                "outcome": "minted",
                "fields": sorted(patch),
            }
        )

    try:
        RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
        with open(RECEIPTS, "a") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")
    except OSError:
        pass

    census = " ".join(f"{key}={value}" for key, value in sorted(reasons.items()))
    mode = "APPLY" if armed else "DRY-RUN"
    scope = f"estate={len(estate.live_members())}" if estate is not None else "estate=absent(registry-only)"
    print(f"  work-loan-backfill: {mode} {scope} minted={minted} failures={failures} {census}")
    if reasons.get("unmintable:repo-not-in-predicate-registry"):
        print(
            "  work-loan-backfill: estate evidence is ABSENT so only docs/repo-predicates.yaml admits — "
            "run scripts/estate-repos-refresh.py (or check gh auth) to restore estate-wide underwriting"
        )
    return 1 if (armed and failures and not minted) else 0


if __name__ == "__main__":
    raise SystemExit(main())
