#!/usr/bin/env python3
"""generate-seo-backlog — convert the SEO audit's gap list into bounded fleet tasks.

The public estate is the inbound-traffic surface; seo-audit.py scores every governed public repo
against its class README standard (portal-v1 rungs) and repo-metadata-sync converges the metadata
half. What remains — READMEs below standard, unseeded portal repos — is PER-REPO EDITORIAL WORK,
and that ships as tasks.yaml tasks the fleet consumes (the generate-revenue-backlog pattern), never
as one mega-session.

Reads logs/seo-audit.json (the sweep artifact) + value-repos.json (priority). Emits, bounded:
  SEO-<slug>-readme-<mmdd>   README below its class standard — context embeds the failed rungs and
                             the literal done-predicate (seo-audit.py --repo X --check exits 0).
  SEO-<slug>-seed-<mmdd>     a portal-class repo with no seed in positioning-seeds.json or
                             seo-seeds.yaml — author the judgment layer first (garbage-in guard).

Read-only by default; --apply appends via the validated queue path. Floor-gated + deduped + capped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.intake import contract_fields, github_pr_contract  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import submit_task_upsert  # noqa: E402

# Artifacts + registries resolve from the SCRIPT'S OWN TREE (they are written/committed beside this
# code — the gitvs ROOT convention); only the task board stays env-resolved (LIMEN_TASKS/cwd), since
# the beat genuinely feeds the live board from wherever it runs.
ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "logs" / "seo-audit.json"
TRAFFIC = ROOT / "logs" / "observatory" / "traffic.jsonl"

_SEO_LABELS = {"seo", "product"}
_ACTIVE = {"open", "dispatched", "in_progress", "needs_human", "failed_blocked"}
_LEVER_KEYS = {"seo-readme", "seo-seed"}


def _audit() -> dict:
    try:
        return json.loads(AUDIT.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _value_rank() -> dict[str, int]:
    try:
        repos = json.loads((ROOT / "value-repos.json").read_text()).get("repos") or []
        return {r: i for i, r in enumerate(repos)}
    except Exception:
        return {}


def _traffic_seen() -> dict[str, int]:
    """Latest MEASURED 14-day unique-visitor count per repo from the traffic ledger
    (scripts/traffic-collect.py). A repo whose newest snapshot is a 403/error (`views._error`,
    i.e. unmeasured) is omitted — it stays neutral (static value rank), never mistaken for unseen.
    Missing/empty ledger -> {} -> the plan sort collapses to the static value rank (correct-when-empty).
    """
    latest: dict[str, tuple[str, int]] = {}  # repo -> (date, uniques); newest snapshot wins
    try:
        lines = TRAFFIC.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        repo, v = e.get("repo"), e.get("views")
        if not repo or not isinstance(v, dict) or "_error" in v:
            continue
        u = v.get("uniques")
        if not isinstance(u, int) or isinstance(u, bool):
            continue
        date_s = e.get("date") or ""
        prev = latest.get(repo)
        if prev is None or date_s >= prev[0]:
            latest[repo] = (date_s, u)
    return {repo: u for repo, (_d, u) in latest.items()}


def _seeded() -> set[str]:
    out: set[str] = set()
    try:
        out |= set((json.loads((ROOT / "positioning-seeds.json").read_text()).get("repos") or {}).keys())
    except Exception:
        pass
    try:
        seo = yaml.safe_load((ROOT / "institutio" / "github" / "seo-seeds.yaml").read_text()) or {}
        out |= set((seo.get("repos") or {}).keys())
    except Exception:
        pass
    return out


def _plan(tasks: list[Task], floor: int, max_new: int) -> tuple[list[Task], dict]:
    audit = _audit()
    repos = audit.get("repos") or {}
    if not repos:
        return [], {"no_audit": True}
    open_seo = sum(1 for t in tasks if t.status == "open" and (set(t.labels or []) & _SEO_LABELS))
    info = {"open_seo": open_seo, "floor": floor, "audited": audit.get("audited")}
    if open_seo >= floor:
        return [], info
    need = min(floor - open_seo, max_new)

    rank = _value_rank()
    seen = _traffic_seen()
    seeded = _seeded()
    existing = {t.id for t in tasks}
    active_pairs = {
        (t.repo, t.labels[0])
        for t in tasks
        if t.repo and t.labels and t.labels[0] in _LEVER_KEYS and t.status in (_ACTIVE | {"done", "archived"})
    }

    # Target the actually-UNSEEN first: a value-repo with a MEASURED 0 unique visitors is the
    # funnel's DISCOVERY bottleneck made concrete, so it sorts ahead of better-seen repos; within a
    # visibility tier the static value rank still holds. Correct-when-empty: no traffic ledger ->
    # seen == {} -> every repo is tier 1 -> the sort collapses to the pure value rank (prior behavior).
    def _order(repo: str) -> tuple[int, int]:
        return (0 if seen.get(repo) == 0 else 1, rank.get(repo, 999))

    # work items: seed-authoring first for unseeded portal repos, then failing READMEs — each lane
    # ordered unseen-then-value-rank.
    items: list[tuple[str, str, dict]] = []
    for repo, r in sorted(repos.items(), key=lambda kv: _order(kv[0])):
        if r.get("standard") == "portal" and repo not in seeded:
            items.append(("seo-seed", repo, r))
    for repo, r in sorted(repos.items(), key=lambda kv: _order(kv[0])):
        if not r.get("pass"):
            items.append(("seo-readme", repo, r))

    stamp = date.today().isoformat()
    mmdd = date.today().strftime("%m%d")
    new: list[Task] = []
    for key, repo, r in items:
        if len(new) >= need:
            break
        if (repo, key) in active_pairs:
            continue
        slug = repo.replace("/", "-").lower()
        tid = f"SEO-{slug}-{key.split('-', 1)[1]}-{mmdd}"
        if tid in existing:
            continue
        existing.add(tid)
        active_pairs.add((repo, key))
        misses = sorted(k for k, v in (r.get("rungs") or {}).items() if not v)
        if key == "seo-seed":
            title = f"Author the SEO/positioning seed for {repo}"
            ctx = (
                f"{repo} is portal-class (the SEO lure tier) but has no judgment seed in "
                "positioning-seeds.json or institutio/github/seo-seeds.yaml. Draft one: run "
                f"`python3 scripts/repo-metadata-sync.py --suggest` for a starting row, curate the "
                "buyer-search description (≤350 chars, no prices) and topics (≤20, lowercase-hyphen), "
                "and land it in seo-seeds.yaml by PR. Done ⟺ `python3 scripts/seo-audit.py --doctor` "
                "exits 0 with the row present."
            )
            prio = "high"
        else:
            title = f"Bring {repo}'s README to its {r.get('standard')} SEO standard"
            ctx = (
                f"{repo} fails rungs {', '.join(misses)} of the {r.get('standard')} README standard "
                "(S1 single H1 · S2 80-600-char value-prop first paragraph · S3 badge · S4 quickstart "
                "heading · S5 architecture heading · S6 estate backlink · S7 contact CTA · S10 no "
                "prices). Fix the README in a normal PR on that repo — real copy from what the code "
                "actually does, no invented features, NO price/currency tokens. Done ⟺ "
                f"`python3 scripts/seo-audit.py --repo {repo} --check` exits 0."
            )
            prio = "high" if repo in rank else "medium"
        new.append(
            Task(
                id=tid,
                title=title,
                repo=repo,
                type="code",
                target_agent="any",
                priority=prio,
                budget_cost=1,
                status="open",
                labels=[key, "seo", "product", "generated"],
                urls=[],
                context=ctx + f" [seo-backlog {stamp}]",
                **contract_fields(github_pr_contract(repo, tid)),
                depends_on=[],
                created=stamp,
                dispatch_log=[],
            )
        )
    return new, info


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--floor", type=int, default=int(os.environ.get("LIMEN_SEO_FLOOR", "6")))
    ap.add_argument("--max-new", type=int, default=int(os.environ.get("LIMEN_SEO_MAX", "6")))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    path = Path(args.tasks)
    lf = load_limen_file(path)
    new, info = _plan(lf.tasks, args.floor, args.max_new)

    if info.get("no_audit"):
        print("# generate-seo-backlog: no sweep artifact (run seo-audit.py --sweep first) — nothing to generate.")
        return 0
    print(f"# generate-seo-backlog: open-seo={info['open_seo']} floor={info['floor']} audited={info['audited']}")
    if not new:
        print("seo queue healthy or every (repo,lever) active — nothing to generate.")
        return 0
    print(f"-> generating {len(new)} seo tasks (cap {args.max_new})")
    for t in new:
        print(f"| {t.id} | {t.repo} | {t.priority} | {t.labels[0]} |")
    if not args.apply:
        print(f"\ndry-run — re-run with --apply to append {len(new)} tasks.")
        return 0
    fresh = load_limen_file(path)
    have = {t.id for t in fresh.tasks}
    to_add = [t for t in new if t.id not in have]
    if not to_add:
        print("\n(all planned tasks already present after fresh re-read — nothing applied.)")
        return 0
    session_id = os.environ.get("LIMEN_SESSION_ID", "generate-seo-backlog")
    for task in to_add:
        submit_task_upsert(path, task, agent="generate-seo-backlog", session_id=session_id)
    print(f"\nsubmitted {len(to_add)} seo upsert tickets to the keeper's inbox.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
