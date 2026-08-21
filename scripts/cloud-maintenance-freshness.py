#!/usr/bin/env python3
"""Require a recent successful exact-head cloud-maintenance receipt."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from typing import Any


def _parse_timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def latest_success(repo: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            "cloud-maintenance.yml",
            "--status",
            "success",
            "--event",
            "workflow_dispatch",
            "--limit",
            "1",
            "--json",
            "databaseId,headSha,updatedAt,url",
        ],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "gh run list failed").strip())
    rows = json.loads(completed.stdout or "[]")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("no successful cloud-maintenance workflow receipt")
    row = rows[0]
    if not isinstance(row, dict) or not row.get("updatedAt") or not row.get("url"):
        raise RuntimeError("latest cloud-maintenance receipt is malformed")
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="organvm/limen")
    parser.add_argument("--max-age-seconds", type=int, default=21600)
    args = parser.parse_args()
    try:
        receipt = latest_success(args.repo)
        age = (dt.datetime.now(dt.timezone.utc) - _parse_timestamp(str(receipt["updatedAt"]))).total_seconds()
        if age < 0 or age > args.max_age_seconds:
            raise RuntimeError(f"latest successful cloud receipt is stale ({int(age)}s)")
    except Exception as exc:
        print(f"cloud-maintenance-freshness: FAIL — {exc}", file=sys.stderr)
        return 1
    print(
        "cloud-maintenance-freshness: OK "
        f"run={receipt.get('databaseId')} head={receipt.get('headSha')} age_seconds={int(age)} "
        f"url={receipt.get('url')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
