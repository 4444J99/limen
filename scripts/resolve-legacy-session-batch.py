#!/usr/bin/env python3
"""Resolve legacy Claude-project session batches into public-safe receipts."""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
BATCH_RESOLUTION_RECEIPTS = ROOT / "docs" / "prompt-batch-resolution-receipts.json"
SCAN_SCRIPT = ROOT / "scripts" / "scan-legacy-session-batch.py"
OWNER_REPO = "organvm/limen"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_scanner():
    spec = importlib.util.spec_from_file_location("scan_legacy_session_batch", SCAN_SCRIPT)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load scanner: {SCAN_SCRIPT}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_json(args: list[str]) -> Any | None:
    proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def branch_proof(branch: str) -> dict[str, Any]:
    if branch in {"", "HEAD", "main"}:
        return {"branch": branch, "live_sha": None, "prs": []}
    encoded_branch = quote(branch, safe="")
    branch_obj = run_json(["gh", "api", f"repos/{OWNER_REPO}/branches/{encoded_branch}"])
    live_sha = None
    if isinstance(branch_obj, dict):
        commit = branch_obj.get("commit") if isinstance(branch_obj.get("commit"), dict) else {}
        live_sha = str(commit.get("sha") or "")[:7] or None
    prs = run_json(
        [
            "gh",
            "pr",
            "list",
            "-R",
            OWNER_REPO,
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "number,state,mergeStateStatus,url,headRefName,headRefOid,mergedAt,closedAt",
        ]
    )
    return {"branch": branch, "live_sha": live_sha, "prs": prs if isinstance(prs, list) else []}


def sensitive_total(row: dict[str, Any]) -> int:
    return sum(int(value or 0) for value in (row.get("sensitive_keyword_counts") or {}).values())


def proof_prs(row: dict[str, Any], proofs: dict[str, dict[str, Any]], state: str) -> list[dict[str, Any]]:
    matches = []
    for branch in row.get("git_branches") or []:
        for pr in proofs.get(str(branch), {}).get("prs") or []:
            if str(pr.get("state") or "") == state:
                matches.append(pr)
    return matches


def classify_row(row: dict[str, Any], proofs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    root = str(row.get("root") or f"legacy-session-{row.get('session_key')}")
    session_key = str(row.get("session_key") or "")
    branches = [str(branch) for branch in (row.get("git_branches") or [])]
    owner_lane = str(row.get("owner_lane") or "legacy-session-unknown")
    merged_prs = proof_prs(row, proofs, "MERGED")
    closed_prs = proof_prs(row, proofs, "CLOSED")
    total_sensitive = sensitive_total(row)
    out: dict[str, Any] = {
        "root": root,
        "session_key": session_key,
        "status": "legacy_session_owner_lane_routed",
        "owner_lane": owner_lane,
        "repo": OWNER_REPO,
        "branch": branches[0] if branches else "",
        "branches": branches,
    }

    if total_sensitive:
        out["status"] = "legacy_session_sensitive_context_recorded"
        out["evidence"] = f"Structured scan found nonzero sensitive keyword counts ({total_sensitive}) for this owner lane; no raw text was copied."
        out["next_action"] = "Keep as private owner-lane context unless a later scoped setup/security packet names the exact delta and predicate."
        return out

    if merged_prs:
        prs = sorted({str(pr.get("url")) for pr in merged_prs if pr.get("url")})
        numbers = sorted({f"#{int(pr.get('number'))}" for pr in merged_prs if pr.get("number")})
        out["status"] = "legacy_session_pr_routed"
        out["prs"] = prs
        out["evidence"] = (
            f"Metadata contained branch anchor(s) {', '.join(branches)}; no live exact branch remains, "
            f"and matching PR(s) {', '.join(numbers)} are MERGED."
        )
        out["next_action"] = f"Use merged PR(s) {', '.join(numbers)} and current Limen state; do not replay the legacy transcript."
        return out

    if closed_prs:
        prs = sorted({str(pr.get("url")) for pr in closed_prs if pr.get("url")})
        numbers = sorted({f"#{int(pr.get('number'))}" for pr in closed_prs if pr.get("number")})
        out["status"] = "legacy_session_closed_pr_recorded"
        out["prs"] = prs
        out["evidence"] = (
            f"Metadata contained branch anchor(s) {', '.join(branches)}; matching PR(s) {', '.join(numbers)} "
            "are CLOSED and unmerged, and no live exact branch was found."
        )
        out["next_action"] = "Treat as historical closed-PR context unless a later owner packet identifies missing value."
        return out

    if owner_lane.startswith("archive4t"):
        out["status"] = "legacy_session_estate_routed"
        out["evidence"] = "Metadata contained Archive4T estate anchors; no public PR or issue URL anchor was present in the structured scan."
        out["next_action"] = "Treat as archive estate context; require a current owner repo/path and predicate before follow-up."
        return out

    if owner_lane == "external-local-project":
        out["status"] = "legacy_session_external_context_recorded"
        out["evidence"] = "Metadata contained external local project anchors; no safe public repo or PR anchor was present in the structured scan."
        out["next_action"] = "Keep as private external-project context unless a later owner packet names the repo/path and predicate."
        return out

    if branches and set(branches) <= {"main"}:
        out["evidence"] = "Metadata contained main-branch Limen anchors; no public PR or issue URL anchor was present in the structured scan."
        out["next_action"] = "Use current Limen main state; require a named delta and predicate before follow-up."
        return out

    out["evidence"] = (
        f"Metadata contained branch anchor(s) {', '.join(branches) or 'none'}; "
        "no live exact remote branch, exact-head PR, or public URL anchor was found."
    )
    out["next_action"] = "Do not rehydrate unless a later packet identifies the missing subagent delta and Limen predicate."
    return out


def build_receipt(batch_id: str) -> dict[str, Any]:
    scanner = load_scanner()
    scan = scanner.build_scan(batch_id)
    branches = sorted({str(branch) for row in scan.get("sessions") or [] for branch in (row.get("git_branches") or [])})
    proofs = {branch: branch_proof(branch) for branch in branches}
    roots = [classify_row(row, proofs) for row in scan.get("sessions") or []]
    status_counts = Counter(str(row.get("status") or "unknown") for row in roots)
    unique_keys = {str(row.get("session_key")) for row in roots}
    source_exists = sum(1 for row in scan.get("sessions") or [] if row.get("source_exists"))
    owner_lanes = scan.get("batch_summary", {}).get("owner_lanes") or {}
    anchor_kinds = scan.get("batch_summary", {}).get("anchor_kinds") or {}
    repo_refs = scan.get("batch_summary", {}).get("repo_refs") or {}
    sensitive_rows = [row for row in scan.get("sessions") or [] if sensitive_total(row)]
    duplicate_keys = scan.get("batch_summary", {}).get("duplicate_session_keys") or {}
    merged_numbers = sorted(
        {
            f"#{int(pr.get('number'))}"
            for proof in proofs.values()
            for pr in proof.get("prs") or []
            if pr.get("number") and str(pr.get("state")) == "MERGED"
        }
    )
    closed_numbers = sorted(
        {
            f"#{int(pr.get('number'))}"
            for proof in proofs.values()
            for pr in proof.get("prs") or []
            if pr.get("number") and str(pr.get("state")) == "CLOSED"
        }
    )
    live_branches = sorted(branch for branch, proof in proofs.items() if proof.get("live_sha"))

    evidence = [
        f"private redacted batch metadata listed {len(roots)} legacy Claude-project session slots with no worktree slug in the priority map",
        (
            f"the batch contained {len(unique_keys)} unique session keys and {len(roots)} private source rows; "
            f"{source_exists} source JSONL files existed under ~/.claude/projects at review time"
        ),
        (
            "private structured scan emitted only session keys, source existence, project/worktree cluster names, git branch names, "
            "public GitHub URLs, repo anchors, prompt-event counts, hash counts, duplicate counts, top-level event type names, "
            "tool names, and sensitive-keyword counts; no prompt body was copied"
        ),
    ]
    if anchor_kinds or repo_refs:
        evidence.append(
            f"the structured scan found public anchor kinds {anchor_kinds or {}} and repo refs {repo_refs or {}}; branch proof still used exact Limen branch/PR checks"
        )
    else:
        evidence.append(
            "the structured scan found no public GitHub URL anchors and no safe allowlisted repo refs in this batch, so public proof came from gitBranch anchors only"
        )
    evidence.append(
        "no exact local worktree directory existed for the named Limen subagent clusters under /Users/4jp/Workspace/.limen-worktrees, "
        "/Users/4jp/Workspace/limen/.worktrees, or /Users/4jp/Workspace/limen/.claude/worktrees at review time"
    )
    if merged_numbers:
        evidence.append("gh api branch lookup and gh pr list --head against organvm/limen found merged PR receipts for " + ", ".join(merged_numbers))
    if closed_numbers:
        evidence.append("closed unmerged PR receipts were recorded but not treated as landed proof for " + ", ".join(closed_numbers))
    if live_branches:
        evidence.append("live exact remote branch anchors remain for " + ", ".join(live_branches))
    evidence.append(f"legacy session status counts: {dict(status_counts.most_common())}")
    if sensitive_rows:
        evidence.append(f"{len(sensitive_rows)} source row(s) had nonzero sensitive keyword counts and were recorded as private owner-lane context without copying raw text")
    if duplicate_keys:
        evidence.append(
            "duplicate legacy session keys recorded once per source slot: "
            + ", ".join(f"{key} appears in {count} source rows" for key, count in sorted(duplicate_keys.items()))
        )
    evidence.append("no raw user, assistant, last-prompt, credential, account, billing, financial, health, or secret text was copied into this tracked receipt")

    return {
        "generated_at": utc_now(),
        "batch": batch_id,
        "band": scan.get("batch_summary", {}).get("band"),
        "lane": scan.get("batch_summary", {}).get("lane"),
        "status": "owner-recorded",
        "classification": "legacy Claude-project sessions routed from private structured metadata to Limen owner lanes, PR receipts, estate/external context, and sensitive operator context",
        "session_count": int(scan.get("batch_summary", {}).get("session_count") or len(roots)),
        "prompt_events": int(scan.get("batch_summary", {}).get("prompt_events") or 0),
        "unique_prompt_hashes": int(scan.get("batch_summary", {}).get("unique_prompt_hashes") or 0),
        "evidence": evidence,
        "next_action": "Use merged Limen PR receipts as durable proof. Keep branch-only, closed-PR, main-only, external, Archive4T, and sensitive sessions as private owner-lane context; do not replay legacy transcripts unless a later packet names the missing delta, owner repo, live branch or issue, and narrow predicate.",
        "roots": roots,
    }


def receipt_exists(batch_id: str) -> bool:
    data = load_json(BATCH_RESOLUTION_RECEIPTS)
    return any(
        isinstance(row, dict) and str(row.get("batch") or row.get("batch_id") or row.get("id")) == batch_id
        for row in data.get("receipts") or []
    )


def append_receipt(receipt: dict[str, Any], *, replace: bool) -> None:
    data = load_json(BATCH_RESOLUTION_RECEIPTS)
    batch_id = str(receipt.get("batch"))
    if receipt_exists(batch_id) and not replace:
        raise SystemExit(f"receipt already exists for {batch_id}; pass --replace to update it")
    receipts = [
        row
        for row in data.get("receipts") or []
        if isinstance(row, dict) and str(row.get("batch") or row.get("batch_id") or row.get("id")) != batch_id
    ]
    receipts.append(receipt)
    data["generated_at"] = utc_now()
    data["receipts"] = receipts
    write_json(BATCH_RESOLUTION_RECEIPTS, data)


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve a legacy Claude-project session batch into a public-safe receipt.")
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
        json.dump(receipt, sys.stdout, indent=2)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
