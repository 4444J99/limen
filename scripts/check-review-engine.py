#!/usr/bin/env python3
"""check-review-engine.py — the review engine's liveness predicate: every recent PR carries
multi-agent feedback.

Exit 0 ⟺ each sampled PR (opened after the engine's arming) has reviews/comments from at least
--min-agents DISTINCT known review agents. This is the fleet-rollout exit bar (estate.yaml
integrations, category review): before arming it reads honestly red — that red IS the owed work.

Samples the --repo list (default: the conductor + the canary) rather than a whole-org search:
bounded, deterministic, rate-limit-friendly (the estate budget floor is 15% headroom). Offline /
unreadable → SKIP exit 0 (the sibling-organ contract — never a faked verdict).

  python3 scripts/check-review-engine.py                    # conductor + canary, last 5 PRs each
  python3 scripts/check-review-engine.py --repo organvm/organvm-scrutator --sample 3
  python3 scripts/check-review-engine.py --since 2026-07-17 # only PRs created after the arming date
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

# The known review-agent logins (GitHub actor names as they appear on reviews/issue comments).
# github-actions is deliberately EXCLUDED — that is our own fanout requester, not a reviewer.
AGENT_LOGINS = {
    "coderabbitai[bot]",
    "gemini-code-assist[bot]",
    "claude[bot]",
    "claude",
    "chatgpt-codex-connector[bot]",
    "copilot-pull-request-reviewer[bot]",
    "sourcery-ai[bot]",
    "qodo-merge-pro[bot]",
    "llamapreview[bot]",
}

DEFAULT_REPOS = ["organvm/limen", "organvm/organvm-scrutator"]


def _gh(args: list[str], timeout: int = 45) -> subprocess.CompletedProcess:
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return subprocess.CompletedProcess(args, 1, "", "offline")
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    except Exception as e:  # fail open
        return subprocess.CompletedProcess(args, 1, "", str(e))


def pr_agents(repo: str, number: int) -> set[str] | None:
    """Distinct known agent logins among a PR's reviews + issue comments. None ⟺ unreadable."""
    actors: set[str] = set()
    r = _gh(["api", f"/repos/{repo}/pulls/{number}/reviews", "--paginate", "--jq", ".[].user.login"])
    if r.returncode != 0:
        return None
    actors |= {ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()}
    c = _gh(["api", f"/repos/{repo}/issues/{number}/comments", "--paginate", "--jq", ".[].user.login"])
    if c.returncode != 0:
        return None
    actors |= {ln.strip() for ln in (c.stdout or "").splitlines() if ln.strip()}
    return {a for a in actors if a in AGENT_LOGINS}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="review-engine liveness: recent PRs carry multi-agent feedback")
    ap.add_argument("--repo", action="append", help="owner/repo to sample (repeatable); default conductor+canary")
    ap.add_argument("--sample", type=int, default=5, help="newest N PRs per repo (default 5)")
    ap.add_argument("--min-agents", type=int, default=2, help="distinct agent reviewers required per PR (default 2)")
    ap.add_argument("--since", default="", help="only PRs created on/after this ISO date (the arming date)")
    args = ap.parse_args(argv)

    repos = args.repo or DEFAULT_REPOS
    gaps: list[str] = []
    checked = 0
    for repo in repos:
        r = _gh(
            [
                "api",
                f"/repos/{repo}/pulls?state=all&sort=created&direction=desc&per_page={args.sample}",
                "--jq",
                ".[] | {number, created_at, draft}",
            ]
        )
        if r.returncode != 0:
            print(f"~ SKIP {repo}: PRs unreadable (offline or no access)")
            continue
        for ln in (r.stdout or "").splitlines():
            try:
                pr = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if pr.get("draft"):
                continue
            if args.since and str(pr.get("created_at", ""))[:10] < args.since:
                continue
            num = int(pr["number"])
            agents = pr_agents(repo, num)
            if agents is None:
                print(f"~ SKIP {repo}#{num}: reviews unreadable")
                continue
            checked += 1
            if len(agents) < args.min_agents:
                gaps.append(f"{repo}#{num}: {len(agents)} agent reviewer(s) {sorted(agents) or '[]'}")
            else:
                print(f"✓ {repo}#{num}: {sorted(agents)}")

    if not checked:
        print("check-review-engine: SKIP — no PRs sampled (offline, empty window, or --since excludes all)")
        return 0
    if gaps:
        print(f"\n✗ check-review-engine: {len(gaps)}/{checked} PR(s) below {args.min_agents} agent reviews:")
        for g in gaps:
            print(f"   {g}")
        print("   (arming order: install the review apps on organvm — levers #933/#934/gemini — then fan out the workflows)")
        return 1
    print(f"✓ check-review-engine: all {checked} sampled PR(s) carry ≥{args.min_agents} agent reviews")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
