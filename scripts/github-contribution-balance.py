#!/usr/bin/env python3
"""Read-only GitHub contribution balance report.

The goal is not to farm profile activity. It is to keep real work from landing
as commit-only residue when the healthier shape is issue -> PR -> review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


TARGETS = {
    "commits_max_share": 0.60,
    "issues_min_share": 0.15,
    "pull_requests_min_share": 0.15,
    "reviews_min_share": 0.10,
}

GRAPHQL_FIELDS = {
    "commits": "totalCommitContributions",
    "issues": "totalIssueContributions",
    "pull_requests": "totalPullRequestContributions",
    "reviews": "totalPullRequestReviewContributions",
}


def _date_arg(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from exc


def default_window() -> tuple[dt.date, dt.date]:
    today = dt.datetime.now(dt.UTC).date()
    return today - dt.timedelta(days=365), today


def _at_start(day: dt.date) -> str:
    return f"{day.isoformat()}T00:00:00Z"


def _at_end(day: dt.date) -> str:
    return f"{day.isoformat()}T23:59:59Z"


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def normalize_counts(payload: dict[str, Any]) -> dict[str, int]:
    """Accept this script's JSON, a raw GraphQL response, or a direct counts map."""
    if isinstance(payload.get("counts"), dict):
        source = payload["counts"]
    else:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        user = data.get("viewer") or data.get("user") if isinstance(data, dict) else {}
        collection = user.get("contributionsCollection") if isinstance(user, dict) else {}
        source = collection if isinstance(collection, dict) and collection else payload

    counts: dict[str, int] = {}
    for key, graphql_key in GRAPHQL_FIELDS.items():
        raw = source.get(key, source.get(graphql_key, 0)) if isinstance(source, dict) else 0
        counts[key] = int(raw or 0)
    return counts


def shares(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    if total <= 0:
        return {key: 0.0 for key in GRAPHQL_FIELDS}
    return {key: counts.get(key, 0) / total for key in GRAPHQL_FIELDS}


def balance_actions(counts: dict[str, int], targets: dict[str, float] | None = None) -> list[dict[str, Any]]:
    targets = targets or TARGETS
    mix = shares(counts)
    actions: list[dict[str, Any]] = []

    def add(lane: str, current: float, target: float, message: str) -> None:
        actions.append(
            {
                "lane": lane,
                "current_share": round(current, 4),
                "target_share": round(target, 4),
                "deficit": round(max(target - current, current - target), 4),
                "action": message,
            }
        )

    if mix["reviews"] < targets["reviews_min_share"]:
        add(
            "reviews",
            mix["reviews"],
            targets["reviews_min_share"],
            "Review an existing PR with a substantive approval, request-change, or comment receipt before new feature work.",
        )
    if mix["issues"] < targets["issues_min_share"]:
        add(
            "issues",
            mix["issues"],
            targets["issues_min_share"],
            "Open or refresh a real issue with acceptance criteria for the next unresolved work unit.",
        )
    if mix["pull_requests"] < targets["pull_requests_min_share"]:
        add(
            "pull_requests",
            mix["pull_requests"],
            targets["pull_requests_min_share"],
            "Package the next implementation behind a branch and PR instead of direct-to-main feature commits.",
        )
    if mix["commits"] > targets["commits_max_share"]:
        add(
            "commits",
            mix["commits"],
            targets["commits_max_share"],
            "Keep commits inside PRs; reserve direct main commits for daemon board snapshots and narrow owner receipts.",
        )
    actions.sort(key=lambda item: (item["lane"] != "reviews", -float(item["deficit"]), item["lane"]))
    return actions


def build_report(
    counts: dict[str, int],
    *,
    login: str,
    from_date: dt.date | None,
    to_date: dt.date | None,
    targets: dict[str, float] | None = None,
) -> dict[str, Any]:
    targets = targets or TARGETS
    actions = balance_actions(counts, targets)
    return {
        "generated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "login": login,
        "window": {
            "from": from_date.isoformat() if from_date else "",
            "to": to_date.isoformat() if to_date else "",
        },
        "counts": counts,
        "shares": {key: round(value, 4) for key, value in shares(counts).items()},
        "targets": targets,
        "status": "needs_balance" if actions else "balanced",
        "next_action": actions[0]["action"] if actions else "Mix is within target; keep running issue -> PR -> review for meaningful work.",
        "actions": actions,
    }


def query_github(login: str | None, from_date: dt.date, to_date: dt.date) -> tuple[str, dict[str, int]]:
    if login:
        query = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
    }
  }
}
"""
        args = [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"login={login}",
            "-F",
            f"from={_at_start(from_date)}",
            "-F",
            f"to={_at_end(to_date)}",
        ]
    else:
        query = """
query($from: DateTime!, $to: DateTime!) {
  viewer {
    login
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
    }
  }
}
"""
        args = [
            "gh",
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"from={_at_start(from_date)}",
            "-F",
            f"to={_at_end(to_date)}",
        ]

    proc = subprocess.run(args, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "gh api graphql failed")
    payload = json.loads(proc.stdout)
    data = payload.get("data", {})
    subject = data.get("user") or data.get("viewer") or {}
    resolved_login = str(subject.get("login") or login or "")
    return resolved_login, normalize_counts(payload)


def format_report(report: dict[str, Any]) -> str:
    counts = report["counts"]
    mix = report["shares"]
    total = sum(int(v) for v in counts.values())
    lines = [
        f"github-contribution-balance: {report['status']}",
        f"login: {report['login'] or 'unknown'}",
        f"window: {report['window']['from']}..{report['window']['to']}",
        (
            "mix: "
            f"commits {mix['commits']:.1%}, "
            f"issues {mix['issues']:.1%}, "
            f"pull_requests {mix['pull_requests']:.1%}, "
            f"reviews {mix['reviews']:.1%} ({total} total)"
        ),
        f"next: {report['next_action']}",
    ]
    if report["actions"]:
        lines.append("owed:")
        for action in report["actions"]:
            lines.append(
                f"- {action['lane']}: {action['current_share']:.1%} -> "
                f"{action['target_share']:.1%}; {action['action']}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    start, end = default_window()
    parser = argparse.ArgumentParser(description="Report the authentic GitHub issue/PR/review/commit balance.")
    parser.add_argument("--login", help="GitHub login; omitted means the authenticated gh viewer")
    parser.add_argument("--from", dest="from_date", type=_date_arg, default=start, help="window start, YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", type=_date_arg, default=end, help="window end, YYYY-MM-DD")
    parser.add_argument("--from-json", type=Path, help="read a saved report or GraphQL response instead of calling gh")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    try:
        if args.from_json:
            payload = load_json(args.from_json)
            counts = normalize_counts(payload)
            login = str(payload.get("login") or args.login or "")
        else:
            login, counts = query_github(args.login, args.from_date, args.to_date)
    except Exception as exc:
        print(f"github-contribution-balance: unavailable: {exc}", file=sys.stderr)
        return 2

    report = build_report(counts, login=login, from_date=args.from_date, to_date=args.to_date)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
