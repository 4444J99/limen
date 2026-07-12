#!/usr/bin/env python3
"""auto-scale — top up tasks.yaml to the portal's daily budget depth from open
jules-ready issues across the organ orgs.

Runs in CI every 4h (.github/workflows/auto-scale.yml); safe to run locally.
Requires GITHUB_TOKEN; writes only tasks.yaml, emitting SCHEMA.md §2.2 entries.

Provenance: originally committed to the 4444J99/_limen governance repo as an
inline workflow blob written against a bare-list tasks.yaml schema; routed here
and adapted to the dict schema 2026-06-05 (see _limen
decisions/2026-06-05-charter-restoration.md).
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
import yaml

# Producers never write tasks.yaml directly; they submit upsert tickets and Tabularius seals the
# projection. The auto-scale workflow runs scripts/tabularius-organ.py after this producer.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.intake import contract_fields, github_issue_contract
from limen.tabularius import pending_task_ids, pending_upsert_patches, submit_task_upsert

TASKS_FILE = Path(__file__).resolve().parent.parent / "tasks.yaml"
# Post-move: all repos were consolidated into the single `organvm` org (was
# a-organvm + organvm-i..vii + meta-organvm, now emptied). Derive from env so a
# future re-home is a config change, not a code edit.
ORGS = [o.strip() for o in os.environ.get("LIMEN_ORGS", "organvm").split(",") if o.strip()]
DEFAULT_DEPTH = 100
MAX_PAGES_PER_ORG = 10


def _load_board() -> dict:
    return yaml.safe_load(TASKS_FILE.read_text()) or {}


def _tasks(data: dict) -> list[dict]:
    return data.get("tasks") or []


def _depth(data: dict) -> int:
    return ((data.get("portal") or {}).get("budget") or {}).get("daily", DEFAULT_DEPTH)


def _existing_urls(tasks: list[dict]) -> set[str]:
    return {u for t in tasks for u in (t.get("urls") or [])}


def _pending_urls() -> set[str]:
    return {u for patch in pending_upsert_patches(TASKS_FILE) for u in (patch.get("urls") or [])}


def _next_task_num(tasks: list[dict]) -> int:
    pending_ids = pending_task_ids(TASKS_FILE)
    return 1 + max(
        (
            int(m.group(1))
            for tid in [*(t.get("id", "") for t in tasks), *pending_ids]
            if (m := re.match(r"LIMEN-(\d+)$", tid))
        ),
        default=0,
    )


def _allowed_repos() -> set[str]:
    """Value tier — the ONLY repos worth auto-scaling work for (revenue/conductor). Source of truth
    is value-repos.json at LIMEN_ROOT (or LIMEN_VALUE_REPOS_FILE) + LIMEN_VALUE_REPOS env. Empty=unset."""
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


def main() -> int:
    token = os.getenv("GITHUB_TOKEN")  # allow-secret — env read, no literal
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 1
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    data = _load_board()
    tasks = _tasks(data)
    depth = _depth(data)

    if len(tasks) >= depth:
        print(f"Task depth {len(tasks)} already at or above {depth}.")
        return 0

    needed = depth - len(tasks)
    print(f"Fetching up to {needed} tasks...")

    existing_urls = _existing_urls(tasks) | _pending_urls()

    today = date.today().isoformat()
    candidates = []
    for org in ORGS:
        page = 1
        seen_search_urls: set[str] = set()
        while needed > 0 and page <= MAX_PAGES_PER_ORG:
            resp = requests.get(
                "https://api.github.com/search/issues",
                params={
                    "q": f"org:{org} is:issue is:open label:jules-ready",
                    "per_page": 100,
                    "page": page,
                },
                headers=headers,
                timeout=30,
            )
            if resp.status_code != 200:
                print(f"Search failed for {org} (page {page}): HTTP {resp.status_code}", file=sys.stderr)
                break
            items = resp.json().get("items", [])
            if not items:
                break
            page_urls = {issue.get("html_url") for issue in items if issue.get("html_url")}
            if page_urls and page_urls <= seen_search_urls:
                print(f"Search for {org} repeated page {page}; stopping pagination", file=sys.stderr)
                break
            seen_search_urls.update(page_urls)
            for issue in items:
                if needed <= 0:
                    break
                url = issue["html_url"]
                if url in existing_urls:
                    continue
                # html_url shape: https://github.com/<owner>/<repo>/issues/<n>
                owner_repo = "/".join(url.split("/")[3:5])
                candidates.append({"title": issue["title"], "repo": owner_repo, "url": url})
                existing_urls.add(url)
                needed -= 1
            page += 1
        if needed > 0 and page > MAX_PAGES_PER_ORG:
            print(f"Search for {org} stopped at page cap {MAX_PAGES_PER_ORG}", file=sys.stderr)

    # VALUE-TIER GATE: only auto-scale work for revenue/conductor repos (never the dead estate).
    allowed = _allowed_repos()
    if allowed:
        before = len(candidates)
        candidates = [c for c in candidates if c.get("repo") in allowed]
        print(f"  value-tier gate: {before} mined → {len(candidates)} in tier")

    data = _load_board()
    tasks = _tasks(data)
    pending_ids = pending_task_ids(TASKS_FILE)
    remaining = max(0, _depth(data) - len(tasks) - len(pending_ids))
    if remaining <= 0:
        print(f"Task depth {len(tasks)} plus {len(pending_ids)} pending already at or above {_depth(data)} after refresh.")
        return 0
    existing_urls = _existing_urls(tasks) | _pending_urls()
    next_num = _next_task_num(tasks)
    new_tasks = []
    for candidate in candidates:
        if len(new_tasks) >= remaining:
            break
        url = candidate["url"]
        if url in existing_urls:
            continue
        new_tasks.append(
            {
                "id": f"LIMEN-{next_num:03d}",
                "title": candidate["title"],
                "repo": candidate["repo"],
                "type": "code",
                "target_agent": "jules",
                "priority": "medium",
                "budget_cost": 1,
                # SCHEMA.md §2.3: the state machine starts at `open`;
                # `dispatched` requires an agent claim (+ dispatch_log).
                "status": "open",
                "labels": ["jules-ready"],
                "urls": [url],
                "created": today,
                "updated": today,
                **contract_fields(github_issue_contract(candidate["repo"], url.rsplit("/", 1)[-1])),
            }
        )
        existing_urls.add(url)
        next_num += 1
    session_id = os.environ.get("LIMEN_SESSION_ID", "auto-scale")
    for task in new_tasks:
        submit_task_upsert(TASKS_FILE, task, agent="auto-scale", session_id=session_id)
    print(f"Submitted {len(new_tasks)} task upsert ticket(s). Total after keeper fold: {len(tasks) + len(pending_ids) + len(new_tasks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
