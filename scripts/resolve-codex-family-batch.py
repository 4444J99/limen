#!/usr/bin/env python3
"""Resolve Codex session-lifecycle family batches into public-safe receipts.

The resolver reads only redacted/private metadata indexes and public GitHub
state. It does not open source session JSONL files or write raw prompt,
assistant, tool-result, account, credential, billing, health, or secret text.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIORITY_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
SESSION_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
BATCH_RESOLUTION_RECEIPTS = ROOT / "docs" / "prompt-batch-resolution-receipts.json"

LOCAL_WORKTREE_BASES = [
    Path("/Users/4jp/Workspace/.limen-worktrees"),
    ROOT / ".worktrees",
    ROOT / ".claude" / "worktrees",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def run_json(args: list[str]) -> tuple[Any | None, str]:
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if proc.returncode != 0:
        return None, proc.stderr.strip()
    text = proc.stdout.strip()
    if not text:
        return None, ""
    try:
        return json.loads(text), ""
    except ValueError as exc:
        return None, f"could not parse JSON from {' '.join(args[:3])}: {exc}"


def batch_by_id(priority: dict[str, Any], batch_id: str) -> dict[str, Any]:
    for batch in priority.get("review_batches") or []:
        if isinstance(batch, dict) and batch.get("id") == batch_id:
            return batch
    raise SystemExit(f"batch not found: {batch_id}")


def sessions_by_key(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("session_key")): row
        for row in index.get("sessions") or []
        if isinstance(row, dict) and row.get("session_key")
    }


def repo_candidates(root: str) -> list[str]:
    if root.startswith("limen-"):
        return ["organvm/limen"]
    if "session-meta" in root:
        return ["organvm/session-meta", "4444J99/session-meta"]
    if "domus-genoma" in root:
        return ["organvm/domus-genoma", "4444J99/domus-genoma"]
    if "organvm-corpvs-testamentvm" in root:
        return ["organvm/organvm-corpvs-testamentvm", "a-organvm/organvm-corpvs-testamentvm"]
    if "organvm-engine" in root:
        return ["organvm/organvm-engine"]
    if "the-invisible-ledger" in root:
        return ["organvm/the-invisible-ledger", "a-organvm/the-invisible-ledger"]
    if "scale-threshold-emergence" in root:
        return ["organvm/scale-threshold-emergence"]
    if "peer-audited--behavioral-blockchain" in root:
        return ["organvm/peer-audited--behavioral-blockchain", "a-organvm/peer-audited--behavioral-blockchain"]
    if "vi-koinonia-github" in root:
        return ["organvm-vi-koinonia/.github", "organvm/dot-github--koinonia"]
    if ".github" in root or "--github" in root or "dot-github" in root:
        return ["organvm-i-theoria/.github", "organvm/dot-github--theoria", "organvm/.github"]
    if "rules-system-bound" in root:
        return ["organvm-i-theoria/rules-system-bound", "organvm/rules-system-bound"]
    if root.startswith("rev-styx-") or "styx-" in root:
        return ["organvm/styx-behavioral-economics-theory", "organvm-i-theoria/styx-behavioral-economics-theory"]
    if "_agent" in root:
        return ["organvm/_agent"]
    return []


def resolve_repo(root: str) -> tuple[str | None, list[str]]:
    attempted = repo_candidates(root)
    for repo in attempted:
        obj, _err = run_json(["gh", "repo", "view", repo, "--json", "nameWithOwner,url"])
        if isinstance(obj, dict) and obj.get("nameWithOwner"):
            return str(obj["nameWithOwner"]), attempted
    return None, attempted


def local_worktree_hits(root: str) -> list[str]:
    hits = []
    for base in LOCAL_WORKTREE_BASES:
        candidate = base / root
        if candidate.exists():
            hits.append(str(candidate))
    return hits


def branch_state(repo: str, branch: str) -> dict[str, Any] | None:
    encoded_branch = quote(branch, safe="")
    obj, _err = run_json(["gh", "api", f"repos/{repo}/branches/{encoded_branch}"])
    if not isinstance(obj, dict):
        return None
    commit = obj.get("commit") if isinstance(obj.get("commit"), dict) else {}
    sha = commit.get("sha") if isinstance(commit, dict) else None
    return {"name": obj.get("name") or branch, "sha": sha} if sha else {"name": obj.get("name") or branch}


def exact_prs(repo: str, branch: str) -> list[dict[str, Any]]:
    obj, _err = run_json(
        [
            "gh",
            "pr",
            "list",
            "-R",
            repo,
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "number,state,mergeStateStatus,url,headRefName,headRefOid,mergedAt,closedAt",
        ]
    )
    if isinstance(obj, list):
        return [row for row in obj if isinstance(row, dict)]
    return []


def broad_pr_hit_count(repo: str, root: str) -> int:
    obj, _err = run_json(
        [
            "gh",
            "search",
            "prs",
            root,
            "-R",
            repo,
            "--json",
            "number,state,url,title,repository",
            "--limit",
            "10",
        ]
    )
    if isinstance(obj, list):
        return len(obj)
    return 0


def choose_pr(prs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not prs:
        return None
    state_rank = {"OPEN": 0, "MERGED": 1, "CLOSED": 2}
    return sorted(prs, key=lambda row: (state_rank.get(str(row.get("state")), 9), int(row.get("number") or 0)))[0]


def predicate_for(repo: str | None) -> str:
    if repo == "organvm/limen":
        return "bash scripts/verify-whole.sh after branch rehydration"
    if repo == "organvm/session-meta":
        return "session-meta issue/PR review predicate after branch rehydration"
    return "GitHub issue/PR review predicate after branch rehydration"


def classify_root(root: str, session_key: str, family: str, session: dict[str, Any] | None) -> dict[str, Any]:
    branch = f"limen/{root}"
    source_exists = bool(session and Path(str(session.get("path") or "")).exists())
    row: dict[str, Any] = {
        "root": root,
        "session_key": session_key,
        "family": family,
        "source_exists": source_exists,
        "prompt_event_count": int((session or {}).get("prompt_event_count") or 0),
        "unique_prompt_hashes": len(set((session or {}).get("prompt_hashes") or [])),
        "branch": branch,
    }

    hits = local_worktree_hits(root)
    if hits:
        row["local_worktree_hits"] = hits

    repo, attempted = resolve_repo(root)
    if attempted:
        row["repo_candidates"] = attempted
    if not repo:
        row.update(
            {
                "status": "needs_owner_route",
                "evidence": "No inferred owner repository resolved through gh repo view.",
                "next_action": "Add an owner repo route before rehydration or delegation.",
            }
        )
        return row

    row["repo"] = repo
    branch_info = branch_state(repo, branch)
    prs = exact_prs(repo, branch)
    pr = choose_pr(prs)
    broad_hits = 0 if pr else broad_pr_hit_count(repo, root)
    if broad_hits:
        row["non_exact_broad_pr_hits"] = broad_hits

    if branch_info and branch_info.get("sha"):
        row["branch_sha"] = str(branch_info["sha"])[:7]

    if pr:
        pr_state = str(pr.get("state") or "UNKNOWN")
        row["pr"] = str(pr.get("url"))
        if pr.get("headRefOid") and not row.get("branch_sha"):
            row["branch_sha"] = str(pr["headRefOid"])[:7]
        if pr_state == "OPEN":
            merge_state = str(pr.get("mergeStateStatus") or "UNKNOWN")
            row["status"] = "remote_pr_preserved"
            row["evidence"] = (
                f"Remote branch {'exists at ' + row['branch_sha'] if row.get('branch_sha') else 'was not confirmed live'}; "
                f"GitHub PR #{pr.get('number')} is OPEN with merge state {merge_state}."
            )
            row["next_action"] = f"Review PR #{pr.get('number')} freshness/checks/conflicts, then merge or supersede by a named PR."
        elif pr_state == "MERGED":
            row["status"] = "remote_pr_merged"
            row["evidence"] = f"No live branch remains; matching PR #{pr.get('number')} is MERGED."
            row["next_action"] = "No local root to preserve; rely on merged PR history unless a later owner packet identifies missing value."
        else:
            row["status"] = "closed_pr_recorded_no_branch" if not branch_info else "closed_pr_recorded_with_branch"
            branch_text = "No live branch remains" if not branch_info else "A live branch still exists"
            row["evidence"] = f"{branch_text}; matching PR #{pr.get('number')} is CLOSED and unmerged."
            row["next_action"] = "Treat the closed PR as historical unless a later owner packet identifies missing value."
        return row

    if branch_info:
        row["status"] = "remote_branch_preserved"
        row["evidence"] = (
            f"Remote branch exists at {row.get('branch_sha', 'unknown sha')}; no exact-head PR was found."
        )
        row["next_action"] = "Inspect the remote branch and either open, merge, supersede, or delete it with an owner receipt."
        return row

    row["status"] = "owner_repo_routed_absent_branch"
    if broad_hits:
        row["evidence"] = (
            "Owner repo resolves; no matching local root, remote branch, or exact-head PR was found. "
            f"Broader same-repo PR search returned {broad_hits} non-exact hit(s), not an exact receipt."
        )
    else:
        row["evidence"] = (
            "Owner repo resolves; no matching local root, remote branch, exact-head PR, or broader PR-search hit was found."
        )
    row["predicate"] = predicate_for(repo)
    row["next_action"] = (
        "Do not rehydrate unless a later owner packet identifies the missing delta, live branch or PR, and narrow predicate."
    )
    return row


def build_receipt(batch_id: str) -> dict[str, Any]:
    priority = load_json(PRIORITY_INDEX)
    sessions = sessions_by_key(load_json(SESSION_INDEX))
    batch = batch_by_id(priority, batch_id)
    if batch.get("lane") != "family":
        raise SystemExit(f"{batch_id} is lane {batch.get('lane')!r}, not family")

    family_counts = batch.get("families") or {}
    family = next(iter(family_counts.keys()), "session_lifecycle")
    roots = []
    for session_key in batch.get("session_keys") or []:
        key = str(session_key)
        session = sessions.get(key)
        root = str((session or {}).get("worktree_slug") or f"session-{key}")
        roots.append(classify_root(root, key, str(family), session))

    status_counts = Counter(str(row.get("status") or "unknown") for row in roots)
    source_exists = sum(1 for row in roots if row.get("source_exists"))
    unique_roots = {str(row.get("root")) for row in roots}
    local_hit_count = sum(1 for row in roots if row.get("local_worktree_hits"))
    repo_count = sum(1 for row in roots if row.get("repo"))
    open_prs = [
        f"{row['repo']}#{str(row['pr']).rsplit('/', 1)[-1]} {row.get('branch_sha', 'unknown')}"
        for row in roots
        if row.get("status") == "remote_pr_preserved" and row.get("repo") and row.get("pr")
    ]
    closed_prs = [
        f"{row['repo']}#{str(row['pr']).rsplit('/', 1)[-1]}"
        for row in roots
        if str(row.get("status", "")).startswith("closed_pr") and row.get("repo") and row.get("pr")
    ]
    non_exact = [
        f"{row['root']} ({row['non_exact_broad_pr_hits']} non-exact broad hit(s))"
        for row in roots
        if row.get("non_exact_broad_pr_hits")
    ]

    evidence = [
        (
            f"private redacted batch metadata listed {len(roots)} Codex-session family items "
            f"across {len(unique_roots)} unique roots, all classified as {family}"
        ),
        f"{source_exists} of {len(roots)} private source JSONL files existed under ~/.codex/sessions at review time",
        (
            "review used only metadata fields: root slug, session key, source existence, owner repo inference, "
            "prompt-event counts, hash counts, family label, and public GitHub branch/PR state"
        ),
    ]
    if local_hit_count:
        evidence.append(f"{local_hit_count} exact local root directories still existed under the checked worktree roots")
    else:
        evidence.append(
            "no exact local root directory existed for any root under /Users/4jp/Workspace/.limen-worktrees, "
            "/Users/4jp/Workspace/limen/.worktrees, or /Users/4jp/Workspace/limen/.claude/worktrees at review time"
        )
    evidence.append(
        f"gh repo view resolved owner repositories for {repo_count} of {len(roots)} inferred roots after repository redirects"
    )
    evidence.append(
        "gh api branch lookup, gh pr list --head limen/<root> --state all, and bounded gh search prs checks found "
        f"{status_counts.get('remote_pr_merged', 0)} exact merged PR receipts, "
        f"{status_counts.get('remote_pr_preserved', 0)} exact open PR receipts with live branches, "
        f"{status_counts.get('closed_pr_recorded_no_branch', 0) + status_counts.get('closed_pr_recorded_with_branch', 0)} closed-unmerged PR receipt(s), "
        f"{status_counts.get('remote_branch_preserved', 0)} live branch receipt(s) without exact PRs, and "
        f"{status_counts.get('owner_repo_routed_absent_branch', 0)} source-session row(s) without exact branch/PR"
    )
    if open_prs:
        evidence.append("open PRs preserved for owner review: " + ", ".join(open_prs))
    if closed_prs:
        evidence.append("closed PRs recorded as historical: " + ", ".join(closed_prs))
    if non_exact:
        evidence.append("non-exact broad PR hits were recorded but not treated as exact receipts for: " + ", ".join(non_exact))
    evidence.append(
        "no raw user, assistant, last-prompt, credential, account, billing, financial, health, or secret text was copied into this tracked receipt"
    )

    return {
        "generated_at": utc_now(),
        "batch": batch_id,
        "band": batch.get("band"),
        "lane": batch.get("lane"),
        "status": "owner-recorded",
        "classification": (
            "Codex session-lifecycle family batch mapped to merged PR receipts, preserved open PRs, "
            "live branch receipts, closed PR receipts, and absent owner routes"
        ),
        "session_count": int(batch.get("session_count") or len(roots)),
        "prompt_events": int(batch.get("prompt_events") or 0),
        "unique_prompt_hashes": int(batch.get("unique_prompt_hashes") or 0),
        "evidence": evidence,
        "next_action": (
            "Review preserved open PRs or live branches before merge, supersession, or deletion. "
            "Rely on merged PR history for landed roots and treat closed PRs as historical. "
            "Treat absent roots as lifecycle-closed owner routes; do not rehydrate unless a later packet names "
            "the missing delta, live branch or PR, owner repo, and narrow predicate."
        ),
        "roots": roots,
    }


def append_receipt(receipt: dict[str, Any], *, replace: bool) -> None:
    data = load_json(BATCH_RESOLUTION_RECEIPTS)
    receipts = [row for row in data.get("receipts") or [] if isinstance(row, dict)]
    batch_id = str(receipt.get("batch"))
    existing = [row for row in receipts if str(row.get("batch") or row.get("batch_id") or row.get("id")) == batch_id]
    if existing and not replace:
        raise SystemExit(f"receipt already exists for {batch_id}; pass --replace to update it")
    receipts = [row for row in receipts if str(row.get("batch") or row.get("batch_id") or row.get("id")) != batch_id]
    receipts.append(receipt)
    data["generated_at"] = utc_now()
    data["receipts"] = receipts
    write_json(BATCH_RESOLUTION_RECEIPTS, data)


def receipt_exists(batch_id: str) -> bool:
    data = load_json(BATCH_RESOLUTION_RECEIPTS)
    for row in data.get("receipts") or []:
        if isinstance(row, dict) and str(row.get("batch") or row.get("batch_id") or row.get("id")) == batch_id:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve a Codex family prompt batch into a public-safe receipt.")
    parser.add_argument("batch_id")
    parser.add_argument("--write", action="store_true", help="append the receipt to docs/prompt-batch-resolution-receipts.json")
    parser.add_argument("--replace", action="store_true", help="replace an existing receipt for the same batch")
    args = parser.parse_args()

    if args.write and not args.replace and receipt_exists(args.batch_id):
        raise SystemExit(f"receipt already exists for {args.batch_id}; pass --replace to update it")
    receipt = build_receipt(args.batch_id)
    if args.write:
        append_receipt(receipt, replace=args.replace)
        print(f"wrote receipt for {args.batch_id} to {BATCH_RESOLUTION_RECEIPTS}")
    else:
        json.dump(receipt, sys.stdout, indent=2, sort_keys=True)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
