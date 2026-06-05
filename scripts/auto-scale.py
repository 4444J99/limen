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

import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
import yaml

TASKS_FILE = Path(__file__).resolve().parent.parent / "tasks.yaml"
ORGS = ["a-organvm", "organvm-i-theoria"]
DEFAULT_DEPTH = 100


def main() -> int:
    token = os.getenv("GITHUB_TOKEN")  # allow-secret — env read, no literal
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 1
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }

    data = yaml.safe_load(TASKS_FILE.read_text()) or {}
    tasks = data.get("tasks") or []
    depth = ((data.get("portal") or {}).get("budget") or {}).get("daily", DEFAULT_DEPTH)

    if len(tasks) >= depth:
        print(f"Task depth {len(tasks)} already at or above {depth}.")
        return 0

    needed = depth - len(tasks)
    print(f"Fetching up to {needed} tasks...")

    existing_urls = {u for t in tasks for u in (t.get("urls") or [])}
    next_num = 1 + max(
        (
            int(m.group(1))
            for t in tasks
            if (m := re.match(r"LIMEN-(\d+)$", t.get("id", "")))
        ),
        default=0,
    )

    today = date.today().isoformat()
    new_tasks = []
    for org in ORGS:
        page = 1
        while needed > 0:
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
            for issue in items:
                if needed <= 0:
                    break
                url = issue["html_url"]
                if url in existing_urls:
                    continue
                # html_url shape: https://github.com/<owner>/<repo>/issues/<n>
                owner_repo = "/".join(url.split("/")[3:5])
                new_tasks.append(
                    {
                        "id": f"LIMEN-{next_num:03d}",
                        "title": issue["title"],
                        "repo": owner_repo,
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
                    }
                )
                existing_urls.add(url)
                next_num += 1
                needed -= 1
            page += 1

    tasks.extend(new_tasks)
    data["tasks"] = tasks
    TASKS_FILE.write_text(yaml.dump(data, sort_keys=False, allow_unicode=True))
    print(f"Added {len(new_tasks)} new tasks. Total: {len(tasks)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
