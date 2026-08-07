#!/usr/bin/env python3
"""owner-route-drain.py — drain the blocked jules owner-route PR estate, with receipts.

308 jules-authored PRs sit open and lifecycle:blocked (23.8% of estate PR debt): launched,
landed, never routed to a merge decision. This organ walks that cohort on a rotating cursor
and gives each PR exactly one disposition from limen.owner_route_drain.classify:

  MERGE          only on merge-policy.sh exit 0, re-run adjacent to the effect with the exact
                 head pinned (the website guardrail stays merge-policy's verdict).
  SUPERSEDE      a merged sibling carries the task's value — close with the pointer + label.
  CLOSE          trivial diff or aged-out red — close with the reason as a comment.
  ROUTE_TO_HEAL  real value needing repair — DO NOTHING here; self-heal.py owns that writer.
  SKIP           leave alone.

Posture:
  * dry-run by default; --apply or LIMEN_OWNER_ROUTE_DRAIN_APPLY=1 arms mutations.
  * classification-only under logs/AUTONOMY_PAUSED regardless of arming (the GITVS task's
    own pause clause: never mutate PRs while a pause marker exists).
  * bounded: --limit verdicts/run (default 15), --merge-limit merges/run (default 5).
  * every verdict appends one receipt row to logs/owner-route-drain.jsonl, applied or not.

Enumeration is live via gh search (author app/google-labs-jules plus "[limen jules" titles);
the privacy-redacted PR-debt ledger under docs/ is the scoreboard, never the worklist.
"""

# NB: the PR-debt ledger's filename is deliberately not spelled out in the docstring above, and
# this note lives in comments rather than in that docstring. Both are gate-shaped, and the pair
# is a small lesson in how two audits in this estate read source.
#
# check-ledger-custody.py's B-check asserts that only declared roles NAME the ledger path in a
# production source file, matching the raw substring over the whole file — docstrings included.
# So a sentence stating this organ does NOT use the ledger reads to that gate exactly like code
# that writes it, and naming it turned main red the moment #1881 landed beside #1880. Declaring
# this file a `reader` was the other way out and it would have been false: nothing here opens
# that document; receipts go to logs/owner-route-drain.jsonl.
#
# direct-main-writer-audit.py then draws the line one step further in: it skips lines starting
# with `#` but NOT docstring lines, so an explanation of the first gate, written as prose, trips
# the second — which is exactly what happened to the first cut of this note. Hence a comment.
#
# Issue #1905 carries the real fix for the class: teach a gate to read code, not text.

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts/ for _pr_scan
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))

from _pr_scan import enumerate_open_prs, rotating_window  # noqa: E402
from limen.owner_route_drain import CLOSE, MERGE, ROUTE_TO_HEAL, SUPERSEDE, Verdict, classify, task_family  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]
RECEIPTS = ROOT / "logs" / "owner-route-drain.jsonl"
CURSOR = ROOT / "logs" / ".pr-scan-cursor.owner-route"
POLICY = ROOT / "scripts" / "merge-policy.sh"
PAUSE_MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"
JULES_AUTHOR = os.environ.get("LIMEN_JULES_PR_AUTHOR", "app/google-labs-jules")
JULES_TITLE_MARK = "[limen jules"


def gh(args, timeout=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)


def _pr_facts(repo: str, num: int) -> dict | None:
    r = gh(
        [
            "pr",
            "view",
            str(num),
            "-R",
            repo,
            "--json",
            "state,isDraft,mergeable,mergeStateStatus,statusCheckRollup,labels,createdAt,"
            "headRefOid,headRefName,title,author,baseRefName",
        ],
        timeout=40,
    )
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except (TypeError, ValueError):
        return None


def _is_trivial(repo: str, num: int) -> bool:
    """Empty or pure-reformat diff (merge-drain's value gate, same conservatism: errors -> False)."""
    r = gh(["pr", "diff", str(num), "-R", repo], timeout=60)
    if r.returncode != 0:
        return False
    added, removed = [], []
    for ln in r.stdout.splitlines():
        if ln.startswith(
            (
                "+++",
                "---",
                "diff ",
                "index ",
                "@@",
                "old mode",
                "new mode",
                "similarity",
                "rename",
                "deleted file",
                "new file",
                "Binary",
            )
        ):
            continue
        if ln.startswith("+"):
            added.append(ln[1:].strip())
        elif ln.startswith("-"):
            removed.append(ln[1:].strip())
    if not added and not removed:
        return True
    return sorted(x for x in added if x) == sorted(x for x in removed if x)


def _merged_sibling(repo: str, num: int, family: str | None) -> str | None:
    """URL of an already-MERGED PR in the same repo carrying this task family, if any."""
    if not family:
        return None
    r = gh(
        [
            "search",
            "prs",
            "--repo",
            repo,
            "--state",
            "merged",
            "--limit",
            "5",
            "--json",
            "number,url,title",
            str(family),
        ],
        timeout=40,
    )
    if r.returncode != 0:
        return None
    try:
        rows = json.loads(r.stdout or "[]")
    except (TypeError, ValueError):
        return None
    for row in rows:
        if row.get("number") == num:
            continue
        if family in str(row.get("title") or ""):
            return str(row.get("url") or "") or None
    return None


def _policy_cleared(repo: str, num: int, expected_head: str) -> tuple[bool, int]:
    """merge-policy.sh is the ONE merge authority; exit 0 with the exact head is the only green."""
    try:
        r = subprocess.run(
            [str(POLICY), str(num), "--repo", repo, "--expected-head", expected_head],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, -1
    return r.returncode == 0, r.returncode


def _receipt(row: dict) -> None:
    try:
        RECEIPTS.parent.mkdir(parents=True, exist_ok=True)
        with open(RECEIPTS, "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass


def _apply_merge(repo: str, num: int, expected_head: str) -> str:
    cleared, exit_code = _policy_cleared(repo, num, expected_head)
    if not cleared:
        return f"policy-refused(exit {exit_code})"
    r = gh(
        ["pr", "merge", str(num), "-R", repo, "--squash", "--auto", "--match-head-commit", expected_head],
        timeout=90,
    )
    return "merged-or-queued" if r.returncode == 0 else f"merge-failed: {(r.stderr or '').strip()[:120]}"


def _apply_supersede(repo: str, num: int, reason: str) -> str:
    gh(["pr", "comment", str(num), "-R", repo, "--body", f"owner-route-drain: {reason}"], timeout=40)
    gh(["pr", "edit", str(num), "-R", repo, "--add-label", "lifecycle:superseded"], timeout=40)
    r = gh(["pr", "close", str(num), "-R", repo], timeout=40)
    return "closed-superseded" if r.returncode == 0 else f"close-failed: {(r.stderr or '').strip()[:120]}"


def _apply_close(repo: str, num: int, reason: str) -> str:
    gh(["pr", "comment", str(num), "-R", repo, "--body", f"owner-route-drain: {reason}"], timeout=40)
    r = gh(["pr", "close", str(num), "-R", repo], timeout=40)
    return "closed" if r.returncode == 0 else f"close-failed: {(r.stderr or '').strip()[:120]}"


def _enumerate_jules_prs(max_total: int) -> list[tuple[str, int]]:
    by_author = enumerate_open_prs(OWNERS, gh, max_total=max_total, want_url=False, author=JULES_AUTHOR)
    # The limen-landed cohort carries "[limen jules …]" titles under other authors — a
    # title search is the only cheap way to sweep it in.
    retitled: list[tuple[str, int]] = []
    r = gh(
        [
            "search",
            "prs",
            "--state",
            "open",
            "--limit",
            str(max_total),
            *sum([["--owner", o] for o in OWNERS], []),
            "--json",
            "number,repository,title",
            JULES_TITLE_MARK,
        ],
        timeout=60,
    )
    if r.returncode == 0:
        try:
            for row in json.loads(r.stdout or "[]"):
                title = str(row.get("title") or "")
                if JULES_TITLE_MARK in title:
                    retitled.append((row["repository"]["nameWithOwner"], row["number"]))
        except (KeyError, TypeError, ValueError):
            pass
    return sorted(set(by_author) | set(retitled))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=int(os.environ.get("LIMEN_OWNER_ROUTE_LIMIT", "15")))
    parser.add_argument("--merge-limit", type=int, default=int(os.environ.get("LIMEN_OWNER_ROUTE_MERGE_LIMIT", "5")))
    parser.add_argument("--max-age-days", type=int, default=int(os.environ.get("LIMEN_OWNER_ROUTE_MAX_AGE_DAYS", "45")))
    parser.add_argument("--scan-max", type=int, default=500)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="force dry-run even when the env valve is armed")
    args = parser.parse_args()

    armed = args.apply or os.environ.get("LIMEN_OWNER_ROUTE_DRAIN_APPLY", "0") == "1"
    if args.dry_run:
        armed = False
    paused = PAUSE_MARKER.exists()
    if paused and armed:
        print("  owner-route-drain: AUTONOMY_PAUSED present — classification-only this run")
        armed = False

    now = datetime.now(timezone.utc)
    cohort = _enumerate_jules_prs(args.scan_max)
    if not cohort:
        print("  owner-route-drain: no open jules-authored PRs found (or gh unavailable)")
        return 0
    window = rotating_window(cohort, args.limit, str(CURSOR), persist=armed)

    counts: dict[str, int] = {}
    merges_done = 0
    for repo, num in window:
        facts = _pr_facts(repo, num)
        if facts is None:
            verdict = Verdict("skip", "gh view failed")
        else:
            family = task_family(str(facts.get("title") or ""), str(facts.get("headRefName") or ""))
            verdict = classify(
                facts,
                now=now,
                max_age_days=args.max_age_days,
                merged_sibling=_merged_sibling(repo, num, family),
                is_trivial=_is_trivial(repo, num),
            )
        outcome = "dry-run"
        if armed:
            if verdict.action == MERGE:
                if merges_done < args.merge_limit:
                    outcome = _apply_merge(repo, num, str(facts.get("headRefOid") or ""))
                    if outcome == "merged-or-queued":
                        merges_done += 1
                else:
                    outcome = "merge-limit-reached"
            elif verdict.action == SUPERSEDE:
                outcome = _apply_supersede(repo, num, verdict.reason)
            elif verdict.action == CLOSE:
                outcome = _apply_close(repo, num, verdict.reason)
            else:
                outcome = "no-action"
        counts[verdict.action] = counts.get(verdict.action, 0) + 1
        _receipt(
            {
                "ts": now.isoformat(timespec="seconds"),
                "repo": repo,
                "pr": num,
                "verdict": verdict.action,
                "reason": verdict.reason,
                "applied": armed,
                "outcome": outcome,
                "paused": paused,
            }
        )
        print(f"  owner-route-drain: {repo}#{num} -> {verdict.action} ({verdict.reason[:90]}) [{outcome}]")

    summary = " ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    mode = "APPLY" if armed else ("PAUSED" if paused else "DRY-RUN")
    print(f"  owner-route-drain: {mode} cohort={len(cohort)} window={len(window)} {summary}")
    heal_backlog = counts.get(ROUTE_TO_HEAL, 0)
    if heal_backlog:
        print(f"  owner-route-drain: {heal_backlog} route-to-heal PRs — self-heal.py owns their repair tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
