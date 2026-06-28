#!/usr/bin/env python3
"""Promote prompt-priority batches into durable owner/review receipts.

This script consumes the redacted prompt priority map and existing preservation
receipts. It does not read source session files or prompt text. The public doc is
the operator queue; the ignored JSON keeps the complete batch-to-session/hash map.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIORITY_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
ATTACK_INDEX = PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
PRESERVATION_RECEIPTS = ROOT / "docs" / "worktree-preservation-receipts.json"
DOC_PATH = ROOT / "docs" / "prompt-batch-review-ledger.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"

RECORDED_STATUSES = {
    "owner-recorded",
    "non-source-recorded",
    "superseded-recorded",
}

STATUS_ORDER = {
    "owner-recorded": 0,
    "non-source-recorded": 1,
    "superseded-recorded": 2,
    "needs-packetization": 3,
    "needs-private-review": 4,
    "needs-remote-proof": 5,
    "needs-owner-route": 6,
    "parked-secret": 7,
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def band_rank(band: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "parked": 4}.get(band, 5)


def receipt_by_root(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for receipt in data.get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        root = receipt.get("root") or receipt.get("id")
        if root:
            receipts[str(root)] = receipt
    return receipts


def attack_by_id(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in data.get("ranked_paths") or []:
        if not isinstance(item, dict):
            continue
        path_id = item.get("id")
        if path_id:
            rows[str(path_id)] = item
    return rows


def status_for_batch(batch: dict[str, Any], receipts: list[dict[str, Any]]) -> str:
    lane = str(batch.get("lane") or "")
    worktrees = batch.get("worktrees") or {}
    if lane == "parked-secret":
        return "parked-secret"
    if worktrees and len(receipts) == len(worktrees):
        receipt_lanes = {str(receipt.get("lane") or "") for receipt in receipts}
        receipt_statuses = {str(receipt.get("status") or "") for receipt in receipts}
        if receipt_lanes == {"documented-residue"} or receipt_statuses <= {
            "cache_only_residue",
            "empty_generated_residue",
        }:
            return "non-source-recorded"
        if "superseded_on_origin_main" in receipt_statuses:
            return "superseded-recorded"
        return "owner-recorded"
    if lane == "stalled-review":
        return "needs-packetization"
    if lane in {"remote-proof", "remote-close"}:
        return "needs-remote-proof"
    if lane in {"legacy-session-review", "historical-worktree-review", "hash-review", "family"}:
        return "needs-private-review"
    return "needs-owner-route"


def evidence_summary(
    batch: dict[str, Any],
    receipts: list[dict[str, Any]],
    attacks: list[dict[str, Any]],
) -> dict[str, Any]:
    repos = sorted({str(receipt.get("repo")) for receipt in receipts if receipt.get("repo")})
    receipt_statuses = Counter(str(receipt.get("status") or "unknown") for receipt in receipts)
    attack_scores = [int(item.get("score") or 0) for item in attacks]
    private_receipts = sorted(
        str(receipt.get("private_receipt"))
        for receipt in receipts
        if receipt.get("private_receipt")
    )
    return {
        "owner_repos": repos,
        "receipt_statuses": dict(receipt_statuses.most_common()),
        "preservation_receipts": private_receipts,
        "attack_score_max": max(attack_scores) if attack_scores else None,
        "attack_path_ids": [str(item.get("id")) for item in attacks if item.get("id")],
        "worktrees": sorted((batch.get("worktrees") or {}).keys()),
    }


def gate_for_status(status: str) -> str:
    if status == "owner-recorded":
        return "not dispatchable: owner classification remains before cleanup, PR creation, or delegation"
    if status == "non-source-recorded":
        return "not dispatchable: recorded as non-source residue; reclaim only after operator acceptance"
    if status == "superseded-recorded":
        return "not dispatchable: recorded as superseded by remote/default; reclaim only after operator acceptance"
    if status == "needs-packetization":
        return "codex packetization needed before delegation"
    if status == "needs-private-review":
        return "private review needed; do not paste raw prompt/session material"
    if status == "needs-remote-proof":
        return "remote/default proof needed before local reclaim or delegation"
    if status == "parked-secret":
        return "parked: auth/secret lane requires explicit scoped setup task"
    return "owner route missing"


def build_snapshot(limit: int) -> dict[str, Any]:
    priority = load_json(PRIORITY_INDEX)
    receipt_map = receipt_by_root(load_json(PRESERVATION_RECEIPTS))
    attacks = attack_by_id(load_json(ATTACK_INDEX))
    batches = []
    for batch in priority.get("review_batches") or []:
        if not isinstance(batch, dict):
            continue
        worktree_names = sorted((batch.get("worktrees") or {}).keys())
        receipts = [receipt_map[root] for root in worktree_names if root in receipt_map]
        attack_rows = [attacks[root] for root in worktree_names if root in attacks]
        status = status_for_batch(batch, receipts)
        evidence = evidence_summary(batch, receipts, attack_rows)
        batches.append(
            {
                "id": batch.get("id"),
                "band": batch.get("band"),
                "lane": batch.get("lane"),
                "status": status,
                "gate": gate_for_status(status),
                "session_count": int(batch.get("session_count") or 0),
                "prompt_events": int(batch.get("prompt_events") or 0),
                "unique_prompt_hashes": int(batch.get("unique_prompt_hashes") or 0),
                "max_score": int(batch.get("max_score") or 0),
                "avg_score": batch.get("avg_score"),
                "next_action": batch.get("next_action") or "",
                "sources": batch.get("sources") or {},
                "families": batch.get("families") or {},
                "worktrees": batch.get("worktrees") or {},
                "session_keys": batch.get("session_keys") or [],
                "prompt_hashes": batch.get("prompt_hashes") or [],
                "evidence": evidence,
            }
        )
    batches.sort(
        key=lambda item: (
            STATUS_ORDER.get(str(item["status"]), 99),
            band_rank(str(item["band"])),
            -int(item["max_score"]),
            str(item["id"]),
        )
    )
    status_counts = Counter(str(item["status"]) for item in batches)
    lane_counts = Counter(str(item["lane"]) for item in batches)
    recorded = [item for item in batches if item["status"] in RECORDED_STATUSES]
    queue = [item for item in batches if item["status"] not in RECORDED_STATUSES and item["status"] != "parked-secret"]
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return {
        "generated_at": now,
        "inputs": {
            "prompt_priority_map": {"path": str(PRIORITY_INDEX), "present": bool(priority)},
            "session_attack_paths": {"path": str(ATTACK_INDEX), "present": bool(attacks)},
            "worktree_preservation_receipts": {
                "path": str(PRESERVATION_RECEIPTS),
                "present": bool(receipt_map),
            },
        },
        "coverage": {
            "priority_batches": len(priority.get("review_batches") or []),
            "review_batches": len(batches),
            "recorded_batches": len(recorded),
            "open_review_batches": len(queue),
            "parked_secret_batches": int(status_counts.get("parked-secret", 0)),
            "prompt_events": sum(int(item["prompt_events"]) for item in batches),
            "unique_prompt_hash_refs": sum(int(item["unique_prompt_hashes"]) for item in batches),
            "preservation_receipts": len(receipt_map),
        },
        "counts": {
            "statuses": dict(status_counts.most_common()),
            "lanes": dict(lane_counts.most_common()),
        },
        "recorded_batches": recorded,
        "review_queue": queue,
        "batches": batches,
        "private_index": str(PRIVATE_INDEX),
    }


def render_counts(counter: dict[str, int]) -> str:
    return ", ".join(f"`{key}` {value}" for key, value in counter.items()) or "none"


def render_owner_repos(repos: list[str]) -> str:
    return ", ".join(f"`{repo}`" for repo in repos) if repos else "none"


def render_markdown(snapshot: dict[str, Any], *, limit: int) -> str:
    coverage = snapshot["coverage"]
    recorded = snapshot["recorded_batches"][:limit]
    queue = snapshot["review_queue"][:limit]
    lines = [
        "# Prompt Batch Review Ledger",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- Review batches are promoted by owner receipt, not by exposing raw prompt/session text.",
        "- `owner-recorded`, `non-source-recorded`, and `superseded-recorded` batches have durable evidence but can still require an owner decision before cleanup or delegation.",
        "- `needs-*` batches are the next work queue; they require private review, packetization, remote proof, or owner routing before dispatch.",
        "- `parked-secret` remains parked unless a scoped account/setup task explicitly activates it.",
        "",
        "## Coverage",
        "",
        f"- Priority batches read: `{coverage.get('priority_batches', 0)}`.",
        f"- Review batches recorded: `{coverage.get('review_batches', 0)}`.",
        f"- Batches with durable owner/non-source/supersession evidence: `{coverage.get('recorded_batches', 0)}`.",
        f"- Open review batches: `{coverage.get('open_review_batches', 0)}`.",
        f"- Parked secret batches: `{coverage.get('parked_secret_batches', 0)}`.",
        f"- Prompt events represented: `{coverage.get('prompt_events', 0)}`.",
        f"- Preservation receipts available: `{coverage.get('preservation_receipts', 0)}`.",
        f"- Status mix: {render_counts(snapshot['counts']['statuses'])}.",
        f"- Lane mix: {render_counts(snapshot['counts']['lanes'])}.",
        "",
        "## Recorded Batches",
        "",
        "| Rank | Batch | Status | Band | Lane | Events | Owner Repos | Evidence | Gate |",
        "|---:|---|---|---|---|---:|---|---|---|",
    ]
    for rank, batch in enumerate(recorded, start=1):
        evidence = batch["evidence"]
        receipt_bits = render_counts(evidence.get("receipt_statuses") or {})
        lines.append(
            f"| {rank} | `{batch['id']}` | `{batch['status']}` | `{batch['band']}` | `{batch['lane']}` | "
            f"{batch['prompt_events']} | {render_owner_repos(evidence.get('owner_repos') or [])} | "
            f"{receipt_bits} | {batch['gate']} |"
        )
    if not recorded:
        lines.append("| 0 | none | n/a | n/a | n/a | 0 | none | none | n/a |")

    lines += [
        "",
        "## Next Review Queue",
        "",
        "| Rank | Batch | Status | Band | Lane | Sessions | Events | Dominant Mix | Next Action |",
        "|---:|---|---|---|---|---:|---:|---|---|",
    ]
    for rank, batch in enumerate(queue, start=1):
        source_bits = ", ".join(f"{key} {value}" for key, value in (batch.get("sources") or {}).items()) or "none"
        family_bits = ", ".join(f"{key} {value}" for key, value in (batch.get("families") or {}).items()) or "none"
        lines.append(
            f"| {rank} | `{batch['id']}` | `{batch['status']}` | `{batch['band']}` | `{batch['lane']}` | "
            f"{batch['session_count']} | {batch['prompt_events']} | sources {source_bits}; families {family_bits} | "
            f"{batch['next_action']} |"
        )
    if not queue:
        lines.append("| 0 | none | n/a | n/a | n/a | 0 | 0 | none | n/a |")

    lines += [
        "",
        "## Private Output",
        "",
        f"- Prompt batch review private index: `{relpath(PRIVATE_INDEX)}`.",
        "- The private index keeps batch membership, session keys, prompt hashes, private receipt paths, and owner routing evidence; it contains no prompt text.",
        "",
        "## Commands",
        "",
        "- Refresh prerequisites: `python3 scripts/prompt-priority-map.py --write && python3 scripts/session-attack-paths.py --write`",
        "- Refresh this review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`",
        "- Show a wider tracked slice: `python3 scripts/prompt-batch-review-ledger.py --write --limit 60`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a redacted prompt batch review ledger.")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    parser.add_argument("--limit", type=int, default=30, help="batches to show per tracked section")
    args = parser.parse_args()

    snapshot = build_snapshot(limit=max(1, args.limit))
    markdown = render_markdown(snapshot, limit=max(1, args.limit))
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = (
        "prompt-batch-review-ledger: "
        f"{snapshot['coverage']['review_batches']} batches, "
        f"{snapshot['coverage']['recorded_batches']} recorded, "
        f"{snapshot['coverage']['open_review_batches']} open"
    )
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
