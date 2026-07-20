#!/usr/bin/env python3
"""discover-value — the organ that ends repo STARVATION.

"Non-value repo" is a dumbass category: if a repo has no *visible* value, discovering its value IS the
work. Value is an OUTPUT of the fleet, not a precondition for spending on it. generate-backlog only does
build-out levers on repos whose value is ALREADY ranked (value-repos.json) — so without this organ every
un-ranked repo sits dark and the fleet idles at a full tank (the overnight idle bug).

This organ guarantees NO repo stays dark: for every org repo that is neither ranked nor already under
discovery, it emits ONE concrete DISCOVERY task — a real reasoning job for a thinking lane (codex/claude/
opencode) that (1) reads what the repo is, (2) finds its latent value / first revenue-or-utility step,
(3) EITHER proposes a concrete first task AND promotes the repo into value-repos.json (so the ranked tier
GROWS — discover-then-rank), OR marks it archival with a one-paragraph thesis. Ranked and archival
terminal dispositions live in value-discovery-dispositions.json, so board compaction cannot make a
completed thesis look dark again. So idle capacity burns on discovery, and value-repos.json becomes the
OUTPUT of the fleet, continuously re-ranked.

Anti-flood: ONE discovery task per dark repo (never 6 busywork levers), least-covered first, hard --max-new
cap. Headroom-aware: when the fleet tank is full (high aggregate headroom) it raises the discovery floor so
more dark repos get covered per window — the accelerator that burns each window toward the reserve drops.
Read-only by default (prints a plan); --apply appends via the limen schema (validated, atomic). Never
dispatches. Fail-open: any error → generate nothing rather than crash the feed beat. ([[no-never-happens-again]])
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.io import load_limen_file  # noqa: E402
from limen.intake import contract_fields, github_pr_contract, is_durable_receipt_target  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import submit_task_upsert  # noqa: E402

# Thinking lanes — discovery is reasoning work, so route it to the lanes that reason best, round-robin.
_THINK_LANES = ["codex", "claude", "opencode"]
# statuses that mean a repo is already getting attention — don't re-discover or double up.
_ACTIVE = {"open", "dispatched", "in_progress", "needs_human", "failed_blocked"}
_DISCOVER_PREFIX = "DISCOVER-"
_DISPOSITION_SCHEMA = "limen.value_discovery_dispositions.v1"

_THESIS = (
    "DISCOVER the latent value of {repo}. This repo currently has NO ranked value — your job is to find it "
    "(value is discovered, never assumed absent). Steps: (1) Read the repo — what it is, its real "
    "entrypoints/exports, what it already does. (2) Identify its highest latent value: a concrete product, "
    "revenue path, reusable asset, or capability the rest of the estate could use — be specific and honest. "
    "(3) DECIDE: if there is real value, write a one-paragraph value thesis to DISCOVERY.md AND open a PR "
    'that ALSO appends "{repo}" to value-repos.json (promote it into the ranked tier so build-out can '
    "follow) AND name the single best concrete first task; if it is genuinely archival, write the thesis "
    "saying so (so it is never re-discovered) — do NOT promote it. Keep any build green. Output the thesis."
)


def _is_candidate(full: str) -> bool:
    """Skip infra/meta/example/contrib names; everything else is a discovery candidate (a repo is
    never pre-judged valueless — discovery decides)."""
    n = full.split("/")[-1]
    if n.startswith("_") or n == ".github" or n.endswith("--superproject"):
        return False
    if n.startswith(("example-", "art-from--", "contrib--")):
        return False
    return True


def _org_repos() -> list[str]:
    """Every non-fork, non-archived repo in the org(s) (LIMEN_ORGS, default organvm). Excludes
    infra/meta/site names. [] on any error so the feed beat never breaks. (Mirrors generate-backlog.)
    LIMEN_DISCOVER_REPOS (comma-sep) overrides the live source — a manual seam + the test injection."""
    override = [r.strip() for r in os.environ.get("LIMEN_DISCOVER_REPOS", "").split(",") if r.strip()]
    if override:
        return [r for r in override if _is_candidate(r)]
    orgs = [o.strip() for o in os.environ.get("LIMEN_ORGS", "organvm").split(",") if o.strip()]
    out: list[str] = []
    for org in orgs:
        try:
            r = subprocess.run(
                [
                    "gh",
                    "api",
                    f"/orgs/{org}/repos",
                    "--paginate",
                    "--jq",
                    ".[] | select(.fork==false and .archived==false) | .full_name",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode == 0:
                out += [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
        except Exception:
            pass
    return [r for r in out if _is_candidate(r)]


def _ranked_repos() -> set[str]:
    """The already-DISCOVERED + ranked tier (value-repos.json / env). These have value already; skip
    them — build-out (generate-backlog) covers them. Same source generate-backlog reads as its gate."""
    repos: set[str] = {r.strip() for r in os.environ.get("LIMEN_VALUE_REPOS", "").split(",") if r.strip()}
    fpath = os.environ.get(
        "LIMEN_VALUE_REPOS_FILE",
        str(Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)) / "value-repos.json"),
    )
    try:
        data = json.loads(Path(fpath).read_text())
        for r in data.get("repos", []):
            repos.add(r if isinstance(r, str) else (r.get("repo") or ""))
    except Exception:
        pass
    repos.discard("")
    return repos


def _dispositioned_repos(ranked: set[str]) -> set[str]:
    """Repos with a durable ranked/archival discovery decision.

    The board is an active-state projection and may archive or compact terminal discovery tasks. The
    tracked disposition ledger is therefore the durable anti-rediscovery contract. Malformed rows are
    ignored rather than allowed to suppress work.
    """

    root = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
    path = Path(
        os.environ.get(
            "LIMEN_VALUE_DISCOVERY_DISPOSITIONS_FILE",
            root / "value-discovery-dispositions.json",
        )
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return set()
    if not isinstance(payload, dict) or payload.get("schema_version") != _DISPOSITION_SCHEMA:
        return set()
    rows = payload.get("dispositions")
    if not isinstance(rows, list):
        return set()
    # Uniqueness is a ledger property, not a property of the rows that happen to
    # validate.  Count every named row first so a malformed/conflicting duplicate
    # cannot hide behind the one valid row and suppress discovery.
    seen = Counter(
        str(row.get("repo") or "").strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("repo") or "").strip()
    )
    valid: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        repo = str(row.get("repo") or "").strip()
        disposition = row.get("disposition")
        receipt = str(row.get("receipt") or "").strip()
        if not repo or disposition not in {"ranked", "archival"}:
            continue
        if seen[repo] != 1 or not is_durable_receipt_target(receipt):
            continue
        if (disposition == "ranked") != (repo in ranked):
            continue
        valid.add(repo)
    return valid


def _avg_headroom_pct() -> float | None:
    """Average live per-vendor headroom from logs/usage.json (0–100), or None if unreadable. High
    headroom = a full tank ⇒ raise the discovery floor so idle capacity burns on covering dark repos."""
    fpath = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)) / "logs" / "usage.json"
    try:
        vendors = (json.loads(fpath.read_text()) or {}).get("vendors", {})
        hs = [
            v["headroom_pct"]
            for v in vendors.values()
            if isinstance(v, dict) and isinstance(v.get("headroom_pct"), (int, float))
        ]
        return sum(hs) / len(hs) if hs else None
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument(
        "--floor",
        type=int,
        default=int(os.environ.get("LIMEN_DISCOVER_FLOOR", "12")),
        help="keep up to this many discovery tasks open; headroom scales it up when the tank is full",
    )
    ap.add_argument(
        "--max-new",
        type=int,
        default=int(os.environ.get("LIMEN_DISCOVER_MAX", "12")),
        help="hard cap on discovery tasks generated in one run (anti-flood)",
    )
    ap.add_argument("--apply", action="store_true", help="append to tasks.yaml (validated, atomic)")
    args = ap.parse_args()

    path = Path(args.tasks)
    lf = load_limen_file(path)
    tasks = lf.tasks

    # Headroom accelerator: a full tank (avg headroom well above the 15% reserve) lifts the floor up to
    # 3x so more dark repos get covered per window; a near-empty tank keeps it at the base (don't pile on).
    floor = args.floor
    avg_hr = _avg_headroom_pct()
    if avg_hr is not None and avg_hr >= 50:
        floor = int(round(args.floor * (1 + min(2.0, (avg_hr - 50) / 25))))  # 50%→1x … 100%→3x

    open_discover = sum(1 for t in tasks if t.status == "open" and (t.id or "").startswith(_DISCOVER_PREFIX))
    if open_discover >= floor:
        print(
            f"discovery healthy: open-discover={open_discover} >= floor={floor} "
            f"(avg headroom {avg_hr if avg_hr is None else round(avg_hr)}%) — nothing to discover."
        )
        return 0
    need = min(floor - open_discover, args.max_new)

    org = _org_repos()
    if not org:
        print("no candidate repos (org API unreachable) — nothing to discover.")
        return 0

    ranked = _ranked_repos()
    dispositioned = _dispositioned_repos(ranked)
    # already covered = ranked, durably dispositioned, OR has active work (don't double up).
    busy = {t.repo for t in tasks if t.status in _ACTIVE and t.repo}
    dark = [r for r in org if r not in ranked and r not in dispositioned and r not in busy]
    if not dark:
        print(f"no dark repos: all {len(org)} org repos are ranked, dispositioned, or already under work.")
        return 0

    # least-covered first: repos with the fewest total tasks ever (most neglected) get discovered first.
    seen = Counter(t.repo for t in tasks if t.repo)
    dark.sort(key=lambda r: seen.get(r, 0))

    existing = {t.id for t in tasks}
    stamp = date.today().isoformat()
    new: list[Task] = []
    for i, repo in enumerate(dark):
        if len(new) >= need:
            break
        slug = repo.replace("/", "-").lower()
        tid = f"{_DISCOVER_PREFIX}{slug}"
        if tid in existing:
            continue
        existing.add(tid)
        lane = _THINK_LANES[i % len(_THINK_LANES)]
        new.append(
            Task(
                id=tid,
                title=f"Discover the latent value of {repo}",
                repo=repo,
                type="research",
                target_agent=lane,
                priority="medium",
                budget_cost=1,
                status="open",
                labels=["discover", "value-discovery"],
                urls=[],
                context=_THESIS.format(repo=repo) + f" [auto-discovery {stamp}; no repo stays dark]",
                **contract_fields(github_pr_contract(repo, tid)),
                depends_on=[],
                created=stamp,
                dispatch_log=[],
            )
        )

    print(
        f"# discover-value: open-discover={open_discover} floor={floor} "
        f"(avg headroom {avg_hr if avg_hr is None else round(avg_hr)}%) -> {len(new)} new "
        f"across {len(dark)} dark repos (cap {args.max_new})\n"
    )
    print("| discovery task | repo | lane |")
    print("|---|---|---|")
    for t in new:
        print(f"| {t.id} | {t.repo} | {t.target_agent} |")

    if not new:
        print("\n(nothing new to discover)")
        return 0
    if args.apply:
        session_id = os.environ.get("LIMEN_SESSION_ID", "discover-value")
        for task in new:
            submit_task_upsert(path, task, agent="discover-value", session_id=session_id)
        print(
            f"\nsubmitted {len(new)} discovery upsert tickets to the keeper's inbox "
            f"(folds onto {path} next beat)."
        )
    else:
        print(f"\ndry-run — re-run with --apply to append {len(new)} discovery tasks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
