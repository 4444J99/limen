#!/usr/bin/env python3
"""REVIEW-HARVEST predicate — a review finding must be CONSUMED, not merely received.

THE BLINDNESS THIS CLOSES. Two organs already look at review traffic and neither asks this
question:

  scripts/check-review-engine.py   "did >=2 agents REVIEW this PR?" — it counts distinct reviewer
                                   logins and never reads what they SAID. Liveness of the pipe,
                                   nothing about the payload.
  scripts/preflight-thread-state.py  "is there anything unread before I COMMENT?" — it gates an
                                   outbound write, not a merge.

So the estate can prove feedback ARRIVES and can prove it is read before it replies, and still has
no answer to "was any of it acted on?". Measured on 2026-08-07: six PRs (#2017, #2018, #2019, #2021,
#2023, #2024) carried agent reviews and all six merged. Copilot's review landed 2-3 minutes AFTER
the merge on three of them; on #2019 CodeRabbit posted three actionable comments and the PR merged
fourteen minutes later with all four threads unresolved. check-review-engine would have called
every one of those PRs green.

WHY NOT JUST BLOCK THE MERGE. Because that trade was already made, deliberately, and reversing it
costs more than it buys. scripts/merge-policy.sh counts only the checks branch protection actually
REQUIRES, precisely so an advisory check cannot hold a deliverable hostage (CLAUDE.md, Merge &
Branch Protocol; the 2026-07-24 insights lineage that produced the rule). Bot reviews are advisory
and they are SLOWER THAN THE MERGE — three of the six arrived after their PR was already in. A gate
that waits for them would stall a cadence that merged sixteen PRs in under an hour to catch findings
that mostly are not there yet. So this harvests AFTER the merge and never votes on it.

RESOLUTION STATE IS GITHUB-NATIVE — THERE IS NO LEDGER HERE, ON PURPOSE. GraphQL reviewThreads
carries isResolved and isOutdated per thread. That is the canonical surface: durable, visible in the
UI, clearable by a human with one click, and it survives this machine. Minting a local
acknowledgement file would fork parallel substrate for a fact GitHub already owns — and it would
answer "did an agent look?" rather than "was this dealt with?". preflight-thread-state.py's digest
ledger under logs/ is right for ITS job (a pre-send gate on one host, PII-sensitive) and wrong for
this one.

  isOutdated threads are NOT findings. The code they annotate has since changed, so the finding may
  no longer exist and nobody can act on a diff hunk that is gone. Letting them decay on their own is
  the difference between a gate that converges and a nag that accumulates.

EXIT CONTRACT (the predicate is the deliverable — CLAUDE.md, Definition of Done):
  0  no unresolved, non-outdated agent review thread on any sampled merged PR. Nothing owed.
  1  findings exist. Each is printed with PR, author, path and an excerpt, plus the exact command
     that closes it — so the next action is available without opening a browser.
  0  SKIP — offline, no `gh`, or the API is unreadable. Never a faked verdict, and never a red one
     either: "I could not look" is reported as a skip in the beat log, matching the sibling-organ
     contract in check-review-engine.py.

  python3 scripts/check-review-harvest.py                 # last 10 merged PRs on the conductor
  python3 scripts/check-review-harvest.py --sample 25     # widen the window
  python3 scripts/check-review-harvest.py --repo owner/x  # another repo (repeatable)
  python3 scripts/check-review-harvest.py --json          # machine-readable, for a doctor rung
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))

DEFAULT_REPO = "organvm/limen"
DEFAULT_SAMPLE = 10
# An excerpt, never the whole comment: findings print into a beat log that is read at a glance, and
# CodeRabbit bodies carry collapsed <details> blocks hundreds of lines long.
EXCERPT_CHARS = 140


def _agent_logins() -> frozenset[str]:
    """Import AGENT_LOGINS from the hyphenated sibling — one source of truth for "who is a reviewer".

    Copying the set would let the two organs disagree about what an agent IS, and they would then
    disagree silently: the engine would count a reviewer this predicate ignores, so a PR could read
    green on "was it reviewed" and green on "was it consumed" while a whole reviewer went unread.
    The spec_from_file_location dance is this repo's existing convention for hyphenated siblings
    (credential-wall.py, claude-workflow-guard.py, vendor-cancel-advisor.py, github-estate-census.py).
    """
    path = ROOT / "scripts" / "check-review-engine.py"
    try:
        spec = importlib.util.spec_from_file_location("_limen_review_engine", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"no loader for {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        logins = getattr(module, "AGENT_LOGINS", None)
        if not logins:
            raise ImportError("AGENT_LOGINS missing or empty")
        return frozenset(logins)
    except Exception as exc:  # pragma: no cover - only when the sibling is moved or broken
        raise SystemExit(f"review-harvest: cannot read AGENT_LOGINS from {path}: {exc}") from exc


def _gh(args: list[str], timeout: int = 45) -> subprocess.CompletedProcess:
    """Same shape as check-review-engine._gh: offline is a non-zero result, never an exception."""
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return subprocess.CompletedProcess(args, 1, "", "offline")
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    except Exception as exc:  # fail open — unreadable is SKIP, not red
        return subprocess.CompletedProcess(args, 1, "", str(exc))


_THREADS_QUERY = """
query($owner:String!, $name:String!, $number:Int!) {
  repository(owner:$owner, name:$name) {
    pullRequest(number:$number) {
      reviewThreads(first:100) {
        nodes {
          id
          isResolved
          isOutdated
          comments(first:1) {
            nodes { author { login } path body }
          }
        }
      }
    }
  }
}
"""


def merged_prs(repo: str, sample: int) -> list[int] | None:
    """Newest N MERGED PR numbers. None ⟺ unreadable (caller turns that into SKIP).

    Merged only: an open PR's unresolved threads are the normal state of a PR under review, not a
    finding. This predicate is about what survived the merge.
    """
    r = _gh(["pr", "list", "--repo", repo, "--state", "merged", "--limit", str(sample), "--json", "number"])
    if r.returncode != 0:
        return None
    try:
        return [int(row["number"]) for row in json.loads(r.stdout or "[]")]
    except (ValueError, KeyError, TypeError):
        return None


_MERGED_TOTAL_QUERY = """
query($owner:String!, $name:String!) {
  repository(owner:$owner, name:$name) { pullRequests(states:MERGED) { totalCount } }
}
"""


def merged_total(repo: str) -> int | None:
    """Exact count of merged PRs on the repo. None ⟺ unreadable.

    THE WINDOW SLIDES, AND THAT IS A TRUNCATION. `--sample N` takes the newest N merged PRs, so
    every merge pushes the oldest one out of scope — findings included. Caught by running this
    predicate on its own estate: the count fell 17 -> 11 while only 5 threads had been resolved,
    because three PRs carrying seven unresolved findings aged out underneath it as this session's
    own work merged. A number that shrinks because you looked at LESS reads exactly like progress,
    which is the silent-cap failure this predicate exists to catch one domain over.

    `totalCount` and not a list walk, for the reason the first version of this function got wrong:
    it counted `pr list --limit 1000` and reported "990 older" on a repo with 1394 merged PRs — the
    truncation reporter was itself truncated by its own cap, and the understated figure looked
    entirely plausible. One aggregate query is exact, cheaper, and has no ceiling to forget.
    """
    owner, _, name = repo.partition("/")
    r = _gh(["api", "graphql", "-f", f"query={_MERGED_TOTAL_QUERY}", "-F", f"owner={owner}", "-F", f"name={name}"])
    if r.returncode != 0:
        return None
    try:
        return int(json.loads(r.stdout)["data"]["repository"]["pullRequests"]["totalCount"])
    except (ValueError, KeyError, TypeError):
        return None


def unresolved_agent_threads(repo: str, number: int, agents: frozenset[str]) -> list[dict] | None:
    """Unresolved, non-outdated threads opened by a known agent. None ⟺ unreadable."""
    owner, _, name = repo.partition("/")
    r = _gh(
        [
            "api",
            "graphql",
            "-f",
            f"query={_THREADS_QUERY}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
            "-F",
            f"number={number}",
        ]
    )
    if r.returncode != 0:
        return None
    try:
        nodes = json.loads(r.stdout)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    except (ValueError, KeyError, TypeError):
        return None

    out: list[dict] = []
    for node in nodes or []:
        if node.get("isResolved") or node.get("isOutdated"):
            continue
        comments = ((node.get("comments") or {}).get("nodes")) or []
        if not comments:
            continue
        first = comments[0] or {}
        login = ((first.get("author") or {}).get("login")) or ""
        # GraphQL reports bot logins without the [bot] suffix that the REST API adds, and
        # AGENT_LOGINS is written in REST spelling. Accept either so a rename in one API does not
        # silently empty this predicate.
        if login not in agents and f"{login}[bot]" not in agents:
            continue
        body = " ".join((first.get("body") or "").split())
        out.append(
            {
                "pr": number,
                "thread_id": node.get("id") or "",
                "author": login,
                "path": first.get("path") or "(no path)",
                "excerpt": body[:EXCERPT_CHARS],
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="review-harvest: findings from agent reviews must be resolved, not merged past",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--repo", action="append", help=f"owner/repo to sample (repeatable); default {DEFAULT_REPO}")
    ap.add_argument(
        "--sample", type=int, default=DEFAULT_SAMPLE, help=f"newest N merged PRs per repo (default {DEFAULT_SAMPLE})"
    )
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    args = ap.parse_args(argv)

    repos = args.repo or [DEFAULT_REPO]
    agents = _agent_logins()

    findings: list[dict] = []
    checked = 0
    skipped: list[str] = []

    bounds: list[dict] = []

    for repo in repos:
        numbers = merged_prs(repo, args.sample)
        if numbers is None:
            skipped.append(f"{repo}: PR list unreadable")
            continue
        if numbers:
            total = merged_total(repo)
            older = None if total is None else max(0, total - len(numbers))
            bounds.append(
                {
                    "repo": repo,
                    "oldest_sampled": min(numbers),
                    "sampled": len(numbers),
                    "merged_total": total,
                    "older_unsampled": older,
                }
            )
        for number in numbers:
            threads = unresolved_agent_threads(repo, number, agents)
            if threads is None:
                skipped.append(f"{repo}#{number}: threads unreadable")
                continue
            checked += 1
            for thread in threads:
                findings.append({**thread, "repo": repo})

    if args.json:
        print(json.dumps({"checked": checked, "skipped": skipped, "bounds": bounds, "findings": findings}, indent=2))

    def _print_bounds() -> None:
        """Say what was NOT looked at, on every run — green or red.

        Without this the count is not comparable to itself across runs: merges slide the window, so
        the number can FALL because findings aged out rather than because anything was fixed. That
        reads as progress and is the opposite.
        """
        for b in bounds:
            older, total = b["older_unsampled"], b["merged_total"]
            head = f"  window: {b['sampled']} newest merged on {b['repo']}, down to #{b['oldest_sampled']}"
            if older is None:
                print(f"{head} — total merged UNREADABLE, so coverage is unknown, not total")
            elif older:
                print(f"{head} — {b['sampled']}/{total} merged PRs; {older} older NOT sampled (widen with --sample)")
            else:
                print(f"{head} — all {total} merged PRs sampled, coverage is total")

    # SKIP: nothing was readable at all. Report it as a skip, never as green-because-empty — the
    # two are indistinguishable in a count, and that is exactly the failure this estate has hit
    # before ("I found nothing" vs "I read nothing", CLAUDE.md Data Grounding).
    if checked == 0:
        if not args.json:
            print(f"~ review-harvest: SKIP — no PR readable ({'; '.join(skipped) or 'offline'})")
        return 0

    if findings:
        if not args.json:
            print(f"\n✗ review-harvest: {len(findings)} unresolved agent finding(s) on {checked} merged PR(s):\n")
            for f in findings:
                print(f"  {f['repo']}#{f['pr']} · {f['author']} · {f['path']}")
                print(f"      {f['excerpt']}")
                print(
                    "      resolve: gh api graphql -f query='mutation{resolveReviewThread"
                    f'(input:{{threadId:"{f["thread_id"]}"}}){{thread{{isResolved}}}}}}\''
                )
            print(
                "\n  These merged with the finding unread. Fix it and resolve the thread, or resolve it"
                "\n  with a reason — but do not leave it: an unresolved thread on a merged PR is a review"
                "\n  the estate paid for and never spent."
            )
            if skipped:
                print(f"  ({len(skipped)} unreadable, not counted: {'; '.join(skipped[:3])})")
            _print_bounds()
        return 1

    if not args.json:
        note = f" ({len(skipped)} unreadable)" if skipped else ""
        print(f"✓ review-harvest: {checked} merged PR(s), no unresolved agent findings{note}")
        _print_bounds()
    return 0


if __name__ == "__main__":
    sys.exit(main())
