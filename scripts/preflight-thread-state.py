#!/usr/bin/env python3
"""preflight-thread-state.py — the ground-truth predicate behind the `github.comment` outbound gate.

WHAT IT ANSWERS: "what is ALREADY on this thread?" — read from the GitHub API, never from a local
artifact, a cached PR body, a review summary, or a previous turn's memory of the same thread.

WHY IT EXISTS: institutio/governance/outbound-effectors.yaml declares this file as the predicate for
`github.comment`, and until now it DID NOT EXIST. scripts/check-runner-coverage.py reported that as
finding C — "arming this effector would deny every matching command" — because the guard fails
CLOSED inside its match. The gate was therefore unarmable: a declared enforcement artifact whose
enforcement was impossible. That is the same declared-but-unwired class the coverage gate exists to
catch, one axis over.

Sibling of scripts/preflight-sent-state.py; same exit contract, same two-step acknowledgement, same
digest-only PII posture. Read that file first — the shape is deliberately identical, so a reviewer
learns one protocol, not two.

EXIT CONTRACT (this is what makes the gate a gate, not a checklist):
  0  the thread carries nothing unread — either it has no comments at all, or every comment below
     has been explicitly acknowledged via --acknowledge for that exact comment id.
  1  the thread carries comments you have not acknowledged. The gate denies. Each one is printed
     with author, age, and an excerpt, so the next decision is made WITH the thread in hand.
  77 the check could not run (no `gh`, not authenticated, no network, API error). SKIP — the gate
     still denies, because "I could not look" is not "there is nothing there".

WHY TWO STEPS. A one-step "did you read the thread?" is self-certifiable and demonstrably fails:
~/.claude/settings.json already carries exactly that question as advisory `additionalContext` on
`gh pr comment`, opening "AUDIT: Did you read the full PR thread ... BEFORE composing this
comment?". The model answers itself "yes" and proceeds. Acknowledgement here requires naming
specific comment ids that only the API can have told you about.

WHAT COUNTS AS A COMMENT. Three endpoints, namespaced so ids can never collide:
  issue:<id>          — the conversation timeline (works for PRs too; a PR *is* an issue)
  review:<id>         — a review's own body, plus its state (CHANGES_REQUESTED is printed loudly)
  reviewcomment:<id>  — an inline code comment on a diff hunk
Bots are labelled, never exempted. CLAUDE.md Rule #12 bans "merges with unanswered maintainer
comments"; a review left by a bot is still a comment a reply can talk over.

TRUNCATION IS REPORTED, NEVER SILENT. Pagination uses `gh api --paginate --slurp`; if that fails the
fallback is one page of 100 and the output says so. CLAUDE.md § Data Grounding requires the scope and
total record count to precede the first conclusion — a gate that silently sees 100 of 300 comments
is worse than no gate, because it PASSES on the strength of what it did not look at.

REPO RESOLUTION, AND A DELIBERATE FAIL-CLOSED HOLE. --repo wins, then GH_REPO, then `gh repo view`.
The guard's `{target}` substitution is a SINGLE string and outbound-effectors.yaml can only capture
one group, so a repo flag in the command text cannot be folded into the target. Rather than check
the AMBIENT repo's #N while the command names another repo's #N, the registry pattern is written so
that ANY repo flag (`--repo` or `-R`, either side of the number) yields no extractable target — and
the guard denies on an unextractable target by design. Cross-repo commenting is therefore denied
until the predicate is run by hand. That is the safe direction; see the registry's own note.

THREAT MODEL, STATED HONESTLY. This defends against a model self-certifying inside its own
reasoning. It does not defend against an operator who edits PATH, `gh`, or the ack file — no more
than LIMEN_ALLOW_UNVERIFIED_OUTBOUND does. The property being bought is that "I read the thread"
becomes an os.stat() plus a SHA-256 comparison instead of a sentence.

PII: acknowledgement markers live under logs/ (gitignored) and store the target DIGEST, never the
repo/number pair in the clear, matching preflight-sent-state.py. Comment bodies are printed to the
terminal for the reader and never written to disk.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACK_DIR = ROOT / "logs" / "preflight-acks"
PAGE_SIZE = 100
EXCERPT_CHARS = 600
GH_TIMEOUT_SECONDS = 45

SKIP = 77


def _target_digest(value: str) -> str:
    """Stable, content-free handle for a thread (also the ack filename).

    Mirrors preflight-sent-state.py._target_digest exactly — one hashing convention across the
    effector estate, so a reviewer never has to check whether two gates agree.
    """
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:16]


def _gh(args: list[str]) -> tuple[bool, str]:
    """Run `gh` read-only. Returns (ok, stdout-or-error). Never raises.

    `gh` is resolved from PATH rather than an env override on purpose: an env-named binary would be
    one more bypass surface on a gate whose entire value is that it cannot be talked past.
    """
    if shutil.which("gh") is None:
        return False, "the `gh` CLI is not on PATH"
    try:
        proc = subprocess.run(
            ["gh", *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"could not execute gh: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return False, detail[0] if detail else f"gh exited {proc.returncode}"
    return True, proc.stdout


def resolve_repo(explicit: str | None) -> tuple[str | None, str]:
    """(repo, reason). --repo, then GH_REPO, then the ambient checkout — the order `gh` itself uses."""
    for value, source in ((explicit, "--repo"), (os.environ.get("GH_REPO"), "GH_REPO")):
        if value and value.strip():
            candidate = value.strip()
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", candidate):
                return None, f"{source}={candidate} is not in owner/repo form"
            return candidate, f"{source}={candidate}"
    ok, out = _gh(["repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])
    if not ok:
        return None, f"could not resolve the ambient repo ({out}); pass --repo owner/repo"
    candidate = out.strip()
    if not candidate:
        return None, "the ambient repo resolved to an empty string; pass --repo owner/repo"
    return candidate, f"ambient checkout {candidate}"


def _api_list(endpoint: str) -> tuple[bool, list[dict], bool, str]:
    """Fetch a paginated list endpoint.

    Returns (ok, rows, truncated, detail). `--slurp` wraps pages into an array-of-arrays, so a
    successful slurp is flattened. If slurp is unavailable the fallback is ONE page and `truncated`
    reports it honestly rather than letting a partial read masquerade as the whole thread.
    """
    ok, out = _gh(["api", "--paginate", "--slurp", f"{endpoint}?per_page={PAGE_SIZE}"])
    if ok:
        try:
            payload = json.loads(out or "[]")
        except ValueError as exc:
            return False, [], False, f"unparseable response from {endpoint}: {exc}"
        rows: list[dict] = []
        for page in payload if isinstance(payload, list) else []:
            if isinstance(page, list):
                rows.extend(item for item in page if isinstance(item, dict))
            elif isinstance(page, dict):
                rows.append(page)
        return True, rows, False, ""

    slurp_error = out
    ok, out = _gh(["api", f"{endpoint}?per_page={PAGE_SIZE}"])
    if not ok:
        return False, [], False, out or slurp_error
    try:
        payload = json.loads(out or "[]")
    except ValueError as exc:
        return False, [], False, f"unparseable response from {endpoint}: {exc}"
    rows = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
    return True, rows, len(rows) >= PAGE_SIZE, ""


def _age(timestamp: str) -> str:
    try:
        when = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return timestamp or "unknown time"
    delta = datetime.now(UTC) - when
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{int(delta.total_seconds() // 60)}m ago"
    if hours < 48:
        return f"{int(hours)}h ago"
    return f"{int(hours // 24)}d ago"


def _excerpt(body: str | None) -> tuple[str, bool]:
    text = re.sub(r"\r\n?", "\n", (body or "")).strip()
    if len(text) <= EXCERPT_CHARS:
        return text, False
    return text[:EXCERPT_CHARS].rstrip(), True


def _actor(row: dict) -> tuple[str, bool]:
    user = row.get("user") or {}
    login = str(user.get("login") or "unknown")
    is_bot = str(user.get("type") or "").lower() == "bot" or login.endswith("[bot]")
    return login, is_bot


def collect_thread(repo: str, number: int) -> tuple[str, dict]:
    """Read the thread from the API. Returns (state, payload); state ∈ {ok, unavailable}."""
    ok, out = _gh(["api", f"repos/{repo}/issues/{number}"])
    if not ok:
        return "unavailable", {"detail": out}
    try:
        head = json.loads(out or "{}")
    except ValueError as exc:
        return "unavailable", {"detail": f"unparseable issue payload: {exc}"}
    if not isinstance(head, dict) or "number" not in head:
        return "unavailable", {"detail": f"{repo}#{number} did not resolve to a thread"}

    is_pr = bool(head.get("pull_request"))
    truncated: list[str] = []
    comments: list[dict] = []

    ok, rows, cut, detail = _api_list(f"repos/{repo}/issues/{number}/comments")
    if not ok:
        return "unavailable", {"detail": detail}
    if cut:
        truncated.append("conversation comments")
    for row in rows:
        login, is_bot = _actor(row)
        comments.append(
            {
                "identity": f"issue:{row.get('id')}",
                "kind": "comment",
                "author": login,
                "is_bot": is_bot,
                "created_at": str(row.get("created_at") or ""),
                "body": row.get("body"),
                "url": row.get("html_url"),
                "state": "",
            }
        )

    if is_pr:
        ok, rows, cut, detail = _api_list(f"repos/{repo}/pulls/{number}/reviews")
        if not ok:
            return "unavailable", {"detail": detail}
        if cut:
            truncated.append("reviews")
        for row in rows:
            login, is_bot = _actor(row)
            state = str(row.get("state") or "")
            # A PENDING review is not visible to anyone else yet, and an empty-bodied APPROVED
            # review carries no text to talk over. Everything else is a comment on the thread.
            if state.upper() == "PENDING":
                continue
            if not (row.get("body") or "").strip() and state.upper() not in {"CHANGES_REQUESTED"}:
                continue
            comments.append(
                {
                    "identity": f"review:{row.get('id')}",
                    "kind": "review",
                    "author": login,
                    "is_bot": is_bot,
                    "created_at": str(row.get("submitted_at") or ""),
                    "body": row.get("body"),
                    "url": row.get("html_url"),
                    "state": state,
                }
            )

        ok, rows, cut, detail = _api_list(f"repos/{repo}/pulls/{number}/comments")
        if not ok:
            return "unavailable", {"detail": detail}
        if cut:
            truncated.append("inline review comments")
        for row in rows:
            login, is_bot = _actor(row)
            where = row.get("path") or "?"
            comments.append(
                {
                    "identity": f"reviewcomment:{row.get('id')}",
                    "kind": f"inline on {where}",
                    "author": login,
                    "is_bot": is_bot,
                    "created_at": str(row.get("created_at") or ""),
                    "body": row.get("body"),
                    "url": row.get("html_url"),
                    "state": "",
                }
            )

    comments.sort(key=lambda row: row["created_at"])
    return "ok", {
        "title": str(head.get("title") or ""),
        "state": str(head.get("state") or "unknown"),
        "state_reason": str(head.get("state_reason") or ""),
        "is_pr": is_pr,
        "merged": bool((head.get("pull_request") or {}).get("merged_at")) if is_pr else False,
        "comments": comments,
        "truncated": truncated,
    }


def _ack_path(qualified: str) -> Path:
    return ACK_DIR / f"github.comment.{_target_digest(qualified)}.json"


def _load_acks(qualified: str) -> set[str]:
    try:
        payload = json.loads(_ack_path(qualified).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    known = payload.get("acknowledged_comment_ids")
    return set(known) if isinstance(known, list) else set()


def _write_acks(qualified: str, identities: set[str]) -> None:
    path = _ack_path(qualified)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "limen.preflight_ack.v1",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_digest": _target_digest(qualified),  # never the repo/number in the clear
        "acknowledged_comment_ids": sorted(identities),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _print_scope(repo: str, number: int, thread: dict) -> None:
    """Scope BEFORE conclusions — CLAUDE.md § Data Grounding."""
    kind = "PR" if thread["is_pr"] else "issue"
    status = thread["state"]
    if thread["merged"]:
        status = "MERGED"
    elif thread["state_reason"]:
        status = f"{status} ({thread['state_reason']})"
    print(f"  thread:  {repo}#{number} [{kind}, {status}] {thread['title'][:70]}")
    print(f"  records: {len(thread['comments'])} comment(s) read from the API")
    print(f"  digest:  {_target_digest(f'{repo}#{number}')}")
    if thread["truncated"]:
        print(
            "  WARNING: pagination fell back to a single page for "
            f"{', '.join(thread['truncated'])} — this is a PARTIAL read of the thread. "
            "Upgrade `gh` (--slurp) before trusting a PASS here."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--number", required=True, type=int, help="the PR or issue number about to be commented on")
    parser.add_argument("--repo", default=None, help="owner/repo (default: GH_REPO, then the ambient checkout)")
    parser.add_argument(
        "--acknowledge",
        action="store_true",
        help="record that every comment printed below has been READ; only then can the gate pass",
    )
    args = parser.parse_args()

    if args.number <= 0:
        print(f"preflight-thread-state: SKIP — {args.number} is not a valid thread number.")
        return SKIP

    repo, reason = resolve_repo(args.repo)
    if repo is None:
        print(f"preflight-thread-state: SKIP — {reason}")
        print("  'I could not look' is not 'there is nothing there'; the gate stays closed.")
        return SKIP

    state, thread = collect_thread(repo, args.number)
    if state == "unavailable":
        print(f"preflight-thread-state: SKIP — could not read {repo}#{args.number}.")
        print(f"  reason: {thread.get('detail', 'unknown')}")
        print(f"  resolved via: {reason}")
        print("  'I could not look' is not 'there is nothing there'; the gate stays closed.")
        print("  Check: gh auth status, network reachability, and that the number exists.")
        return SKIP

    comments = thread["comments"]

    if not comments:
        print("preflight-thread-state: PASS — nothing on this thread to talk over.")
        _print_scope(repo, args.number, thread)
        return 0

    qualified = f"{repo}#{args.number}"
    acknowledged = _load_acks(qualified)
    outstanding = [row for row in comments if row["identity"] not in acknowledged]

    if args.acknowledge:
        _write_acks(qualified, acknowledged | {row["identity"] for row in comments})
        print(f"preflight-thread-state: acknowledged {len(comments)} comment(s) on {qualified}.")
        print("  Re-run WITHOUT --acknowledge to mint the PASS receipt the gate requires.")
        return 0

    if not outstanding:
        print(f"preflight-thread-state: PASS — {len(comments)} comment(s), all previously acknowledged.")
        _print_scope(repo, args.number, thread)
        return 0

    print(f"preflight-thread-state: FAIL — {len(outstanding)} comment(s) on this thread, UNREAD.")
    _print_scope(repo, args.number, thread)
    if thread["merged"]:
        print("  NOTE: this PR is already MERGED — a new comment here may be commenting on a closed decision.")
    print("  You are about to reply into a conversation you have not read. Read it first:")
    for row in outstanding:
        marker = " [BOT]" if row["is_bot"] else ""
        state = f" ({row['state']})" if row["state"] else ""
        print("")
        print(f"    · {row['author']}{marker} — {row['kind']}{state}, {_age(row['created_at'])}")
        print(f"      {row['identity']}  {row['url'] or ''}")
        body, cut = _excerpt(row["body"])
        for line in (body or "(empty body)").splitlines():
            print(f"      | {line}")
        if cut:
            print(f"      | … truncated at {EXCERPT_CHARS} chars — open the URL for the rest")
    print("")
    print("  If a comment is still the right move, acknowledge these explicitly:")
    print(f"    python3 scripts/preflight-thread-state.py --number {args.number} --repo {repo} --acknowledge")
    return 1


if __name__ == "__main__":
    sys.exit(main())
