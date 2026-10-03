#!/usr/bin/env python3
"""Read-only, repository-qualified issue/PR/branch triage; never closes or deletes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "limen.remote_estate_triage.v1"
SAFETY_ISSUES = {2776, 2537, 2355}
RECOVERY_ISSUES = {2739, 2740, 2741, 2742, 2743, 2744, 2745, 685, 2614}
CONTROL_ISSUES = {2760, 2763, 2751, 2752, 2753, 2680, 2664, 2374, 2413}
PRIORITY_PRS = {2777: 0, 2780: 0, 2826: 0, 2778: 0, 2672: 0, 2676: 0,
                2823: 1, 2825: 1, 2802: 1, 2805: 1, 2799: 1, 2828: 1}


def run(args: list[str], *, timeout: int = 90) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed ({result.returncode}); no effects applied")
    return result.stdout


def api(endpoint: str) -> list[dict]:
    pages = json.loads(run(["gh", "api", "--paginate", "--slurp", endpoint]))
    return [item for page in pages for item in page] if pages and isinstance(pages[0], list) else pages


def issue_category(number: int, labels: list[str]) -> tuple[str, int]:
    # A label is a routing observation, not proof of a genuine external gate.
    if number in SAFETY_ISSUES:
        return "safety-evidence-review", 0
    if "credential" in labels:
        return "credential-owner-recheck", 2
    if "needs-human" in labels:
        return "human-gate-owner-recheck", 2
    if number in RECOVERY_ISSUES:
        return "remote-first-recovery", 1
    if number in CONTROL_ISSUES:
        return "control-acceptance", 2
    if "program:production-systems" in labels:
        return "program-dependency-review", 3
    return "intent-and-evidence-review", 2


def pr_category(number: int, labels: list[str], body: str, *, dirty: bool | None,
                empty: bool) -> str:
    if dirty:
        return "active-local-edit-review"
    if number == 2777 or re.search(r"leave this PR unmerged|must not merge|human review before merging", body, re.I):
        return "explicit-review-hold"
    if "lifecycle:preservation" in labels:
        return "preservation-only"
    if empty:
        return "empty-comparison-lineage-review"
    if re.search(r"heavy verification.*(?:75|denied)|admission.*denied|full.*verification.*unproven|awaits admitted", body, re.I):
        return "verification-admission-review"
    return "exact-head-verification-review"


def branch_category(name: str, *, protected: bool, local: bool, open_pr: int | None,
                    ancestor: bool, historical_pr: int | None) -> str:
    if protected or name == "main" or name.startswith("tabularius/"):
        return "protected-trunk-or-service"
    if name.startswith("preserve/"):
        return "intentional-preservation"
    if local:
        return "local-worktree-owner-review"
    if open_pr:
        return "open-pr-owned"
    if ancestor:
        return "ancestry-proven-review-custody-required"
    if historical_pr:
        return "historical-pr-successor-review"
    return "unique-owner-review-required"


def oid(sha: str) -> dict[str, str]:
    return {"abbreviation": sha[:12], "sha256": hashlib.sha256(sha.encode()).hexdigest()}


def references(body: str, numbers: set[int]) -> list[int]:
    # Related references are never promoted into dependencies or completion proof.
    return sorted({int(n) for n in re.findall(r"(?<![A-Za-z0-9])#(\d+)", body) if int(n) in numbers})


def collect(repository: str, source: Path, review_anchor: str) -> dict:
    metadata = json.loads(run(["gh", "api", f"repos/{repository}"]))
    if metadata["private"] or metadata["id"] != 1255213941 or metadata["full_name"].lower() != repository.lower():
        raise RuntimeError("public canonical repository identity required")
    started = datetime.now(timezone.utc).isoformat()
    raw = api(f"repos/{repository}/issues?state=open&per_page=100")
    prs = api(f"repos/{repository}/pulls?state=open&per_page=100")
    branches = api(f"repos/{repository}/branches?per_page=100")
    historical = api(f"repos/{repository}/pulls?state=closed&per_page=100&sort=updated&direction=desc")
    issues = [i for i in raw if "pull_request" not in i]
    if len(raw) != len(issues) + len(prs):
        raise RuntimeError("open issue/PR snapshot changed during enumeration; reconcile delta")
    numbers = {i["number"] for i in issues}
    main = next(b["commit"]["sha"] for b in branches if b["name"] == metadata["default_branch"])
    local = {}
    porcelain = run(["git", "-C", str(source), "worktree", "list", "--porcelain"])
    for block in porcelain.strip().split("\n\n"):
        lines = block.splitlines()
        for line in lines:
            if line.startswith("branch refs/heads/"):
                local[line.removeprefix("branch refs/heads/")] = lines[0].removeprefix("worktree ")
    issue_rows = []
    for i in issues:
        labels = [l["name"] for l in i["labels"]]
        category, priority = issue_category(i["number"], labels)
        issue_rows.append({"number": i["number"], "owner_url": i["html_url"], "labels": labels,
                           "category": category, "priority_tier": priority,
                           "github_assignees": [a["login"] for a in i["assignees"]],
                           "related_open_issues": references(i["body"] or "", numbers),
                           "updated_at": i["updated_at"], "completion_proven": False,
                           "next_command": f"gh issue view {i['number']} --repo {repository}"})

    def inspect_pr(p: dict) -> dict:
        n = p["number"]
        files = api(f"repos/{repository}/pulls/{n}/files?per_page=100")
        reviews = api(f"repos/{repository}/pulls/{n}/reviews?per_page=100")
        dirty = None
        if p["head"]["ref"] in local:
            dirty = bool(run(["git", "-C", local[p["head"]["ref"]], "status", "--porcelain", "--untracked-files=normal"], timeout=20))
        labels = [l["name"] for l in p["labels"]]
        category = pr_category(n, labels, p["body"] or "", dirty=dirty, empty=not files)
        return {"number": n, "owner_url": p["html_url"], "head": oid(p["head"]["sha"]),
                "branch": p["head"]["ref"], "draft": p["draft"], "labels": labels,
                "category": category, "priority_tier": PRIORITY_PRS.get(n, 2),
                "related_open_issues": references(p["body"] or "", numbers),
                "changed_paths": [f["filename"] for f in files],
                "local_worktree": p["head"]["ref"] in local, "local_dirty": dirty,
                "review_counts": dict(Counter(r["state"] for r in reviews)),
                "exact_head_review_count": sum(r["commit_id"] == p["head"]["sha"] for r in reviews),
                "verification_proven_by_this_audit": False,
                "next_command": f"gh pr view {n} --repo {repository}"}

    with ThreadPoolExecutor(max_workers=3) as executor:
        pr_rows = list(executor.map(inspect_pr, prs))
    open_prs = {p["head"]["ref"]: p["number"] for p in prs}
    history = {}
    for p in historical:
        history.setdefault(p["head"]["ref"], p)
    branch_rows = []
    for b in branches:
        name, sha = b["name"], b["commit"]["sha"]
        proof = subprocess.run(["git", "-C", str(source), "merge-base", "--is-ancestor", sha, main], capture_output=True, timeout=20)
        ancestor = proof.returncode == 0
        h = history.get(name)
        category = branch_category(name, protected=b["protected"], local=name in local,
                                   open_pr=open_prs.get(name), ancestor=ancestor,
                                   historical_pr=h["number"] if h else None)
        owner = f"https://github.com/{repository}/pull/{open_prs[name]}" if name in open_prs else f"https://github.com/{repository}/issues/2614"
        branch_rows.append({"name": name, "tip": oid(sha), "category": category,
                            "owner_url": owner, "owner_basis": "open-pr" if name in open_prs else "branch-reconciliation-owner",
                            "open_pr": open_prs.get(name), "historical_pr": h["number"] if h else None,
                            "historical_pr_merged": bool(h["merged_at"]) if h else None,
                            "ancestor_of_snapshot_main": ancestor, "ancestry_available": proof.returncode in (0, 1),
                            "local_worktree": name in local, "deletion_eligible": False})
    return {"schema": SCHEMA, "repository": repository, "repository_id": metadata["id"],
            "review_anchor": review_anchor, "collection_started_at": started,
            "observed_at": datetime.now(timezone.utc).isoformat(), "snapshot_main": oid(main),
            "counts": {"issues": len(issue_rows), "prs": len(pr_rows), "branches": len(branch_rows),
                       "historical_prs_inspected": len(historical)},
            "coverage": "routing-complete; acceptance-and-custody-not-certified",
            "issues": issue_rows, "prs": pr_rows, "branches": branch_rows,
            "effects": {"merges": 0, "closures": 0, "deletions": 0, "task_transitions": 0}}


def check(snapshot: dict) -> None:
    if snapshot.get("schema") != SCHEMA:
        raise ValueError("unsupported schema")
    if snapshot.get("repository_id") != 1255213941:
        raise ValueError("wrong repository identity")
    owner_prefix = f"https://github.com/{snapshot['repository']}/"
    for key, identifier in (("issues", "number"), ("prs", "number"), ("branches", "name")):
        rows = snapshot[key]
        if len(rows) != snapshot["counts"][key] or len({r[identifier] for r in rows}) != len(rows):
            raise ValueError(f"missing or duplicate {key} coverage")
        if any(not r.get("owner_url") or not r.get("category") for r in rows):
            raise ValueError(f"missing {key} owner or disposition")
        if any(not r["owner_url"].startswith(owner_prefix) for r in rows):
            raise ValueError(f"foreign {key} owner")
        if any(any(k in r for k in ("body", "title", "local_path", "headRefOid")) for r in rows):
            raise ValueError(f"raw source metadata in public {key} projection")
    if any(r["deletion_eligible"] for r in snapshot["branches"]):
        raise ValueError("triage cannot certify deletion")
    if any(r["completion_proven"] for r in snapshot["issues"]):
        raise ValueError("routing cannot certify completion")
    if any(r["verification_proven_by_this_audit"] for r in snapshot["prs"]):
        raise ValueError("inspection cannot certify verification")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="4444J99/limen")
    parser.add_argument("--source", type=Path, default=Path.cwd())
    parser.add_argument("--review-anchor")
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    if args.check:
        check(json.loads(args.check.read_text()))
        print("PASS: complete owner-linked routing; no invented completion or deletion authority")
        return
    if not args.review_anchor:
        parser.error("--review-anchor must name the last human review point")
    snapshot = collect(args.repo, args.source, args.review_anchor)
    check(snapshot)
    print(json.dumps(snapshot, separators=(",", ":")))


if __name__ == "__main__":
    main()
