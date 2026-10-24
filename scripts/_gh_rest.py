#!/usr/bin/env python3
"""_gh_rest.py — the REST read path for GitHub facts when GraphQL is unavailable.

Claude Code cloud sessions reach GitHub through a proxy that answers every GraphQL call with
``HTTP 403: GitHub GraphQL is not available from Claude Code sessions; use the REST API``.
`gh pr view`, `gh pr checks`, `gh issue view` and `gh api graphql` are all GraphQL underneath, so
every predicate built on them reads "cannot read PR" in the one environment where most merging
happens (gap G4, docs/plans/2026-10-17-tmb-acceptance-gaps.md).

This module derives the SAME facts over REST and presents them in the SAME shape
`gh pr view --json number,title,url,state,isDraft,mergeStateStatus,baseRefName,headRefName,
headRefOid,files,statusCheckRollup` produces, so the caller's verdict logic does not fork:
exactly one set of rules judges the PR whichever transport carried the facts.

Read-only by construction. Every call is a GET through ``gh api``; nothing here can merge, label,
comment or otherwise change GitHub, and the effect paths (``gh pr merge``, ``gh pr edit``) are
deliberately NOT given a REST twin: the queue-free merge contract forbids a merge-method fallback.

Fail toward caution: any call that fails, any malformed payload, and any file list that GitHub
truncated raises ``ReadError``. The caller treats that as "could not look" — never as a verdict.

CLI (each prints one fact on stdout; a failure prints a diagnostic on stderr and exits 1):
    _gh_rest.py snapshot --pr N [--repo OWNER/NAME]       # gh-pr-view-shaped JSON
    _gh_rest.py head --pr N [--repo OWNER/NAME]           # exact head SHA
    _gh_rest.py current-pr [--repo OWNER/NAME] [--branch B]  # open PR number for a branch ('' if none)
    _gh_rest.py unresolved-threads --pr N [--repo OWNER/NAME]  # count of unresolved review threads
    _gh_rest.py issue-state --issue N [--repo OWNER/NAME]  # OPEN | CLOSED

Without ``--repo`` the endpoint carries gh's ``{owner}/{repo}`` placeholders, which gh fills from the
current directory's git remote with no network call (so no GraphQL).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from urllib.parse import quote

# REST `mergeable_state` -> GraphQL `mergeStateStatus` is the same enum, lower- vs upper-case.
_MERGE_STATES = frozenset({"CLEAN", "DIRTY", "BEHIND", "BLOCKED", "UNSTABLE", "HAS_HOOKS", "DRAFT", "UNKNOWN"})

_PAGE = "per_page=100"


class ReadError(Exception):
    """A GitHub fact could not be read or was malformed; the caller must not infer a verdict."""


def _gh(args: list[str], timeout: int = 60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout, check=False)


def _base(repo: str | None) -> str:
    return f"repos/{repo}" if repo else "repos/{owner}/{repo}"


def _decode_stream(text: str) -> list:
    """Every JSON value in ``text``.

    ``gh api --paginate`` emits one JSON document per page back to back (``[...][...]``), not one
    document, and ``--slurp`` is missing from older gh. Decoding the concatenation here works on both.
    """
    decoder = json.JSONDecoder()
    values: list = []
    index = 0
    while index < len(text):
        if text[index].isspace():
            index += 1
            continue
        try:
            value, index = decoder.raw_decode(text, index)
        except ValueError as exc:
            raise ReadError(f"unparseable GitHub response ({exc})") from exc
        values.append(value)
    return values


def _api(gh: Callable, endpoint: str, *, paginate: bool = False) -> list:
    args = ["api", *(["--paginate"] if paginate else []), endpoint]
    try:
        result = gh(args)
    except subprocess.TimeoutExpired as exc:
        raise ReadError(f"gh api {endpoint} timed out") from exc
    except OSError as exc:
        raise ReadError(f"gh api {endpoint} could not launch ({type(exc).__name__})") from exc
    if result.returncode != 0:
        detail = (getattr(result, "stderr", "") or getattr(result, "stdout", "") or "").strip()
        raise ReadError(detail or f"gh api {endpoint} failed (exit {result.returncode})")
    return _decode_stream(result.stdout or "")


def _one(values: list, endpoint: str) -> dict:
    if len(values) != 1 or not isinstance(values[0], dict):
        raise ReadError(f"unexpected response shape from {endpoint}")
    return values[0]


def _upper(value) -> str:
    return value.upper() if isinstance(value, str) else ""


def _pull(gh: Callable, base: str, number: int, *, tries: int, delay: float, sleep: Callable) -> dict:
    """The pull object, retrying while GitHub is still computing mergeability.

    GitHub documents ``mergeable: null`` as "not computed yet; a background job has started — poll".
    A one-shot read of a fresh PR therefore lands on UNKNOWN. A bounded retry resolves the common case;
    an exhausted retry still reports UNKNOWN, which the verdict logic treats as a transient HOLD.
    """
    endpoint = f"{base}/pulls/{number}"
    for attempt in range(max(tries, 1)):
        pull = _one(_api(gh, endpoint), endpoint)
        if pull.get("mergeable") is not None or pull.get("state") != "open":
            return pull
        if attempt + 1 < tries:
            sleep(delay)
    return pull


def _merge_state(pull: dict) -> str:
    state = _upper(pull.get("mergeable_state"))
    if pull.get("mergeable") is None and pull.get("state") == "open":
        return "UNKNOWN"  # never trust a stale-looking state while GitHub is still recomputing
    return state if state in _MERGE_STATES else "UNKNOWN"


def _pr_state(pull: dict) -> str:
    if pull.get("merged") is True or pull.get("merged_at"):
        return "MERGED"
    return "OPEN" if pull.get("state") == "open" else "CLOSED"


def _changed_files(gh: Callable, base: str, number: int, expected: object) -> list[dict]:
    endpoint = f"{base}/pulls/{number}/files?{_PAGE}"
    files: list[dict] = []
    for page in _api(gh, endpoint, paginate=True):
        if not isinstance(page, list):
            raise ReadError(f"unexpected response shape from {endpoint}")
        for entry in page:
            if not isinstance(entry, dict) or not isinstance(entry.get("filename"), str):
                raise ReadError(f"malformed file entry from {endpoint}")
            files.append({"path": entry["filename"]})
    # GitHub caps this listing at 3000 files. A truncated list would hide a deploy-trigger path
    # from the website guardrail, so an incomplete listing is unreadable, not "no deploy paths".
    if isinstance(expected, int) and len(files) < expected:
        raise ReadError(f"changed-file list truncated ({len(files)} of {expected}); cannot classify deploy paths")
    return files


def _rollup(gh: Callable, base: str, sha: str) -> list[dict]:
    """check runs + commit statuses for ``sha``, shaped like GraphQL ``statusCheckRollup`` nodes."""
    rollup: list[dict] = []

    runs_endpoint = f"{base}/commits/{sha}/check-runs?{_PAGE}"
    for page in _api(gh, runs_endpoint, paginate=True):
        runs = page.get("check_runs") if isinstance(page, dict) else None
        if not isinstance(runs, list):
            raise ReadError(f"unexpected response shape from {runs_endpoint}")
        for run in runs:
            if not isinstance(run, dict) or not isinstance(run.get("name"), str):
                raise ReadError(f"malformed check run from {runs_endpoint}")
            rollup.append(
                {
                    "__typename": "CheckRun",
                    "name": run["name"],
                    "status": _upper(run.get("status")),
                    "conclusion": _upper(run.get("conclusion")) or None,
                    "startedAt": run.get("started_at"),
                    "completedAt": run.get("completed_at"),
                }
            )

    status_endpoint = f"{base}/commits/{sha}/status?{_PAGE}"
    for page in _api(gh, status_endpoint, paginate=True):
        statuses = page.get("statuses") if isinstance(page, dict) else None
        if not isinstance(statuses, list):
            raise ReadError(f"unexpected response shape from {status_endpoint}")
        for status in statuses:
            if not isinstance(status, dict) or not isinstance(status.get("context"), str):
                raise ReadError(f"malformed commit status from {status_endpoint}")
            rollup.append(
                {
                    "__typename": "StatusContext",
                    "context": status["context"],
                    "state": _upper(status.get("state")),
                    "createdAt": status.get("created_at"),
                }
            )
    return rollup


def snapshot(
    repo: str | None,
    number: int,
    gh: Callable | None = None,
    *,
    tries: int | None = None,
    delay: float | None = None,
    sleep: Callable = time.sleep,
) -> dict:
    """The PR as ``gh pr view --json number,title,url,state,isDraft,mergeStateStatus,baseRefName,
    headRefName,headRefOid,files,statusCheckRollup`` would report it, derived over REST."""
    gh = gh or _gh
    tries = int(os.environ.get("LIMEN_GH_REST_MERGEABLE_TRIES", "3")) if tries is None else tries
    delay = float(os.environ.get("LIMEN_GH_REST_MERGEABLE_DELAY", "2")) if delay is None else delay
    base = _base(repo)
    pull = _pull(gh, base, number, tries=tries, delay=delay, sleep=sleep)
    head = pull.get("head")
    pr_base = pull.get("base")
    if not isinstance(head, dict) or not isinstance(pr_base, dict) or not isinstance(head.get("sha"), str):
        raise ReadError(f"malformed pull request payload for #{number}")
    sha = head["sha"]
    return {
        "number": pull.get("number", number),
        "title": pull.get("title") or "",
        "url": pull.get("html_url") or "",
        "state": _pr_state(pull),
        "isDraft": bool(pull.get("draft")),
        "mergeStateStatus": _merge_state(pull),
        "baseRefName": pr_base.get("ref") or "",
        "headRefName": head.get("ref") or "",
        "headRefOid": sha,
        "files": _changed_files(gh, base, number, pull.get("changed_files")),
        "statusCheckRollup": _rollup(gh, base, sha),
    }


def head_sha(repo: str | None, number: int, gh: Callable | None = None) -> str:
    gh = gh or _gh
    endpoint = f"{_base(repo)}/pulls/{number}"
    pull = _one(_api(gh, endpoint), endpoint)
    head = pull.get("head")
    sha = head.get("sha") if isinstance(head, dict) else None
    if not isinstance(sha, str) or not sha:
        raise ReadError(f"malformed pull request payload for #{number}")
    return sha


def current_branch() -> str:
    result = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, check=False)
    return result.stdout.strip()


def current_pr(repo: str | None, branch: str | None = None, gh: Callable | None = None) -> int | None:
    """Number of the open PR whose head is ``branch`` (default: the checked-out branch), or None."""
    gh = gh or _gh
    branch = branch or current_branch()
    if not branch:
        raise ReadError("no branch to look up (detached HEAD?)")
    owner = repo.split("/", 1)[0] if repo else "{owner}"
    head = f"{owner}:{quote(branch, safe='/')}"
    endpoint = f"{_base(repo)}/pulls?head={head}&state=open&per_page=2"
    for page in _api(gh, endpoint):
        if not isinstance(page, list):
            raise ReadError(f"unexpected response shape from {endpoint}")
        for entry in page:
            if isinstance(entry, dict) and isinstance(entry.get("number"), int):
                return entry["number"]
    return None


def unresolved_threads(repo: str | None, number: int, gh: Callable | None = None) -> int:
    """Unresolved review threads, via the CCR route (the GraphQL ``reviewThreads`` twin)."""
    gh = gh or _gh
    endpoint = f"{_base(repo)}/pulls/{number}/ccr/review_threads"
    values = _api(gh, endpoint)
    if len(values) != 1 or not isinstance(values[0], list):
        raise ReadError(f"unexpected response shape from {endpoint}")
    return sum(1 for thread in values[0] if isinstance(thread, dict) and thread.get("resolved") is False)


def issue_state(repo: str | None, number: int, gh: Callable | None = None) -> str:
    """``OPEN`` or ``CLOSED`` — the value ``gh issue view --json state`` reports."""
    gh = gh or _gh
    endpoint = f"{_base(repo)}/issues/{number}"
    state = _upper(_one(_api(gh, endpoint), endpoint).get("state"))
    if state not in {"OPEN", "CLOSED"}:
        raise ReadError(f"unexpected issue state from {endpoint}")
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, flag in (
        ("snapshot", "--pr"),
        ("head", "--pr"),
        ("unresolved-threads", "--pr"),
        ("issue-state", "--issue"),
    ):
        cmd = sub.add_parser(name)
        cmd.add_argument(flag, type=int, required=True)
        cmd.add_argument("--repo")
    cmd = sub.add_parser("current-pr")
    cmd.add_argument("--repo")
    cmd.add_argument("--branch")
    args = parser.parse_args(argv)

    try:
        if args.command == "snapshot":
            print(json.dumps(snapshot(args.repo, args.pr)))
        elif args.command == "head":
            print(head_sha(args.repo, args.pr))
        elif args.command == "current-pr":
            found = current_pr(args.repo, args.branch)
            print("" if found is None else found)
        elif args.command == "unresolved-threads":
            print(unresolved_threads(args.repo, args.pr))
        else:
            print(issue_state(args.repo, args.issue))
    except ReadError as exc:
        print(f"_gh_rest: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
