#!/usr/bin/env python3
"""Promote prompt-priority batches into durable owner/review receipts.

This script consumes the redacted prompt priority map and existing preservation
receipts. It does not read source session files or prompt text. The public doc is
the operator queue; the ignored JSON keeps the complete batch-to-session/hash map.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PRIORITY_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
ATTACK_INDEX = PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
PRESERVATION_RECEIPTS = ROOT / "docs" / "worktree-preservation-receipts.json"
PACKET_RESOLUTION_RECEIPTS = ROOT / "docs" / "prompt-packet-resolution-receipts.json"
BATCH_RESOLUTION_RECEIPTS = ROOT / "docs" / "prompt-batch-resolution-receipts.json"
DOC_PATH = ROOT / "docs" / "prompt-batch-review-ledger.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-batch-review-ledger.json"

RECORDED_STATUSES = {
    "owner-recorded",
    "non-source-recorded",
    "superseded-recorded",
}

RECORDED_PACKET_STATUSES = RECORDED_STATUSES | {"current-state-recorded"}

CORPUS_DISPOSITIONS = {
    "unassessed",
    "not_done",
    "partial",
    "done",
    "blocked",
    "superseded",
}

RESOLVED_DISPOSITIONS = {"done", "superseded"}

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

CANONICAL_OWNER = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class BatchAuthorityError(RuntimeError):
    """The priority input crossed or omitted the legacy compatibility boundary."""


def priority_review_batches(priority: dict[str, Any]) -> list[dict[str, Any]]:
    control = priority.get("control")
    if not isinstance(control, dict):
        raise BatchAuthorityError("priority map lacks prompt-atom control authority")
    if (
        control.get("authority") != "prompt_atom_projection"
        or control.get("healthy") is not True
        or control.get("governing_unit") != "atom_id"
    ):
        raise BatchAuthorityError("priority map control authority is not prompt_atom_projection")
    if control.get("legacy_can_override") is not False:
        raise BatchAuthorityError("priority map does not explicitly deny legacy override")
    projection_digest = str(control.get("projection_digest") or "")
    private_check = control.get("private_check")
    if (
        not SHA256.fullmatch(projection_digest)
        or not isinstance(private_check, dict)
        or private_check.get("result") != "pass"
        or private_check.get("projection_digest") != projection_digest
    ):
        raise BatchAuthorityError("priority map lacks a hash-matched private atom check")
    compatibility = priority.get("legacy_compatibility")
    if not isinstance(compatibility, dict):
        raise BatchAuthorityError("priority map lacks explicit legacy_compatibility boundary")
    if (
        compatibility.get("authoritative") is not False
        or compatibility.get("governs_execution") is not False
        or not str(compatibility.get("reason") or "").strip()
    ):
        raise BatchAuthorityError("legacy compatibility boundary is incomplete")
    raw_batches = compatibility.get("review_batches")
    if not isinstance(raw_batches, list) or any(not isinstance(row, dict) for row in raw_batches):
        raise BatchAuthorityError("legacy_compatibility.review_batches must be an object list")
    batches = [dict(row) for row in raw_batches]
    for row in batches:
        if row.get("authority") != "legacy_compatibility_only" or row.get("governs_execution") is not False:
            raise BatchAuthorityError("legacy review batch lacks its non-authority boundary")
    return batches


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


def packet_receipts_by_source_batch(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    receipts: dict[str, list[dict[str, Any]]] = {}
    for receipt in data.get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        source_batch = receipt.get("source_batch")
        if source_batch:
            receipts.setdefault(str(source_batch), []).append(receipt)
    return receipts


def batch_resolution_lookup(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for receipt in data.get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        batch_id = receipt.get("batch") or receipt.get("batch_id") or receipt.get("id")
        if batch_id:
            receipts[str(batch_id)] = receipt
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


def packet_receipts_cover_batch(batch: dict[str, Any], packet_receipts: list[dict[str, Any]]) -> bool:
    if str(batch.get("lane") or "") != "stalled-review" or not packet_receipts:
        return False
    batch_families = {str(family) for family in (batch.get("families") or {}).keys()}
    receipt_families = {str(receipt.get("family") or "") for receipt in packet_receipts}
    receipt_statuses = {str(receipt.get("status") or "") for receipt in packet_receipts}
    return bool(batch_families) and batch_families <= receipt_families and receipt_statuses <= RECORDED_PACKET_STATUSES


def status_for_batch(
    batch: dict[str, Any],
    receipts: list[dict[str, Any]],
    packet_receipts: list[dict[str, Any]],
    batch_resolution: dict[str, Any] | None,
) -> str:
    lane = str(batch.get("lane") or "")
    worktrees = batch.get("worktrees") or {}
    if lane == "parked-secret":
        return "parked-secret"
    if batch_resolution and str(batch_resolution.get("status") or "") in RECORDED_STATUSES:
        return str(batch_resolution.get("status"))
    if packet_receipts_cover_batch(batch, packet_receipts):
        packet_statuses = {str(receipt.get("status") or "") for receipt in packet_receipts}
        if packet_statuses == {"non-source-recorded"}:
            return "non-source-recorded"
        if packet_statuses <= {"superseded-recorded", "non-source-recorded"}:
            return "superseded-recorded"
        return "owner-recorded"
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


def row_disposition(row: dict[str, Any]) -> str:
    """Return the analytic prompt-corpus disposition for an evidence row.

    Legacy receipts predate dispositions. They remain readable, but missing or
    invalid values fail closed as ``unassessed`` instead of being promoted from
    a custody/evidence status such as ``owner-recorded``.
    """

    disposition = str(row.get("disposition") or "unassessed")
    return disposition if disposition in CORPUS_DISPOSITIONS else "unassessed"


def _row_subject(row: dict[str, Any]) -> str:
    return str(row.get("root") or row.get("atom_id") or row.get("packet") or row.get("id") or "").strip()


def _proof_owner(row: dict[str, Any], outcome: dict[str, Any]) -> str:
    row_owner = str(row.get("repo") or row.get("owner") or "").strip()
    receipt_owner = str(outcome.get("owner") or "").strip()
    if not CANONICAL_OWNER.fullmatch(row_owner) or receipt_owner != row_owner:
        return ""
    return row_owner


def _github_proof_valid(
    kind: str,
    owner: str,
    outcome: dict[str, Any],
) -> bool:
    commit_sha = str(outcome.get("commit_sha") or "")
    if not SHA1.fullmatch(commit_sha) or outcome.get("reachable") is not True:
        return False
    parsed = urlsplit(str(outcome.get("ref") or ""))
    if parsed.scheme != "https" or parsed.netloc != "github.com":
        return False
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or "/".join(parts[:2]) != owner:
        return False
    if kind == "github_pr":
        return parts[2] == "pull" and parts[3].isdigit() and outcome.get("state") == "merged"
    return parts[2] == "commit" and parts[3] == commit_sha


def _predicate_proof_valid(outcome: dict[str, Any]) -> bool:
    relative = str(outcome.get("path") or outcome.get("ref") or "").strip()
    if not relative or Path(relative).is_absolute():
        return False
    root = ROOT.resolve()
    candidate = (root / relative).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return False
    claimed = str(outcome.get("sha256") or "")
    if not SHA256.fullmatch(claimed):
        return False
    try:
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
    except OSError:
        return False
    return actual == claimed and bool(str(outcome.get("predicate") or "").strip())


def terminal_proof_valid(row: dict[str, Any], outcome: dict[str, Any]) -> bool:
    subject = _row_subject(row)
    owner = _proof_owner(row, outcome)
    if not subject or not owner:
        return False
    if str(outcome.get("subject") or "") != subject:
        return False
    if str(outcome.get("subject_hash") or "") != hashlib.sha256(subject.encode()).hexdigest():
        return False
    if str(outcome.get("result") or "").strip().lower() != "pass":
        return False
    kind = str(outcome.get("kind") or "")
    if kind in {"github_pr", "github_commit"}:
        return _github_proof_valid(kind, owner, outcome)
    if kind == "predicate_receipt":
        return _predicate_proof_valid(outcome)
    return False


def row_has_terminal_outcome(row: dict[str, Any]) -> bool:
    """True only when an explicit terminal disposition has machine evidence."""

    disposition = row_disposition(row)
    if disposition not in RESOLVED_DISPOSITIONS:
        return False
    outcome = row.get("outcome_receipt")
    if not isinstance(outcome, dict):
        return False
    if not terminal_proof_valid(row, outcome):
        return False
    if disposition == "done":
        return bool(str(outcome.get("predicate") or "").strip())
    return bool(str(row.get("superseded_by") or "").strip() or str(outcome.get("successor") or "").strip())


def resolution_for_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute completion independently from the receipt's evidence status."""

    disposition_counts = Counter(row_disposition(row) for row in rows)
    unresolved = [
        {
            "root": str(row.get("root") or row.get("id") or row.get("packet") or "unknown"),
            "status": str(row.get("status") or "unknown"),
            "disposition": row_disposition(row),
        }
        for row in rows
        if not row_has_terminal_outcome(row)
    ]
    return {
        "complete": bool(rows) and not unresolved,
        "row_count": len(rows),
        "resolved_row_count": len(rows) - len(unresolved),
        "unresolved_root_count": len(unresolved),
        "disposition_counts": dict(disposition_counts.most_common()),
        "unresolved_roots": unresolved,
        "coverage_complete": False,
        "missing_expected_ids": [],
    }


def require_expected_coverage(
    resolution: dict[str, Any],
    *,
    expected_ids: set[str],
    covered_ids: set[str],
) -> dict[str, Any]:
    """Require a terminal outcome for every declared child, not a convenient subset."""

    missing = sorted(expected_ids - covered_ids)
    resolution["coverage_complete"] = bool(expected_ids) and not missing
    resolution["missing_expected_ids"] = missing
    if missing:
        resolution["unresolved_roots"].extend(
            {
                "root": child_id,
                "status": "missing_child_outcome",
                "disposition": "unassessed",
            }
            for child_id in missing
        )
        resolution["unresolved_root_count"] = len(resolution["unresolved_roots"])
    resolution["complete"] = bool(resolution.get("complete") and resolution.get("coverage_complete"))
    return resolution


def resolution_for_batch(
    batch: dict[str, Any],
    receipts: list[dict[str, Any]],
    packet_receipts: list[dict[str, Any]],
    batch_resolution: dict[str, Any] | None,
) -> dict[str, Any]:
    """Project the strongest available evidence rows into completion truth.

    Evidence/custody classifications and work completion are separate axes. A
    writer cannot close a batch by setting only a top-level recorded status.
    """

    if batch_resolution:
        roots = [row for row in (batch_resolution.get("roots") or []) if isinstance(row, dict)]
        expected_roots = {str(value) for value in (batch.get("worktrees") or {}).keys()}
        if expected_roots:
            return require_expected_coverage(
                resolution_for_rows(roots),
                expected_ids=expected_roots,
                covered_ids={str(row.get("root") or row.get("id") or "") for row in roots},
            )
        atom_rows = [row for row in (batch_resolution.get("atom_outcomes") or []) if isinstance(row, dict)]
        expected_atoms = {
            str(value) for value in (batch_resolution.get("expected_atom_ids") or batch.get("atom_ids") or [])
        }
        return require_expected_coverage(
            resolution_for_rows(atom_rows),
            expected_ids=expected_atoms,
            covered_ids={str(row.get("atom_id") or "") for row in atom_rows},
        )
    if packet_receipts_cover_batch(batch, packet_receipts):
        # Packet evidence preserves custody but does not yet enumerate every ask atom.
        return resolution_for_rows(packet_receipts)
    worktrees = batch.get("worktrees") or {}
    if worktrees and len(receipts) == len(worktrees):
        return require_expected_coverage(
            resolution_for_rows(receipts),
            expected_ids={str(value) for value in worktrees.keys()},
            covered_ids={str(row.get("root") or row.get("id") or "") for row in receipts},
        )
    return resolution_for_rows([])


def evidence_summary(
    batch: dict[str, Any],
    receipts: list[dict[str, Any]],
    packet_receipts: list[dict[str, Any]],
    batch_resolution: dict[str, Any] | None,
    attacks: list[dict[str, Any]],
    resolution: dict[str, Any],
) -> dict[str, Any]:
    repos = sorted({str(receipt.get("repo")) for receipt in receipts if receipt.get("repo")})
    receipt_statuses = Counter(str(receipt.get("status") or "unknown") for receipt in receipts)
    packet_statuses = Counter(str(receipt.get("status") or "unknown") for receipt in packet_receipts)
    batch_roots = [root for root in (batch_resolution or {}).get("roots") or [] if isinstance(root, dict)]
    batch_root_statuses = Counter(str(root.get("status") or "unknown") for root in batch_roots)
    batch_repos = sorted({str(root.get("repo")) for root in batch_roots if root.get("repo")})
    attack_scores = [int(item.get("score") or 0) for item in attacks]
    private_receipts = sorted(
        str(receipt.get("private_receipt")) for receipt in receipts if receipt.get("private_receipt")
    )
    return {
        "owner_repos": repos,
        "receipt_statuses": dict(receipt_statuses.most_common()),
        "packet_receipt_statuses": dict(packet_statuses.most_common()),
        "packet_receipts": sorted(
            str(receipt.get("packet") or "") for receipt in packet_receipts if receipt.get("packet")
        ),
        "batch_resolution_status": str((batch_resolution or {}).get("status") or ""),
        "batch_root_statuses": dict(batch_root_statuses.most_common()),
        "batch_root_repos": batch_repos,
        "resolution_complete": bool(resolution.get("complete")),
        "resolution_row_count": int(resolution.get("row_count") or 0),
        "resolved_row_count": int(resolution.get("resolved_row_count") or 0),
        "unresolved_root_count": int(resolution.get("unresolved_root_count") or 0),
        "disposition_counts": resolution.get("disposition_counts") or {},
        "unresolved_roots": resolution.get("unresolved_roots") or [],
        "preservation_receipts": private_receipts,
        "attack_score_max": max(attack_scores) if attack_scores else None,
        "attack_path_ids": [str(item.get("id")) for item in attacks if item.get("id")],
        "worktrees": sorted((batch.get("worktrees") or {}).keys()),
    }


def gate_for_status(status: str, resolution: dict[str, Any]) -> str:
    if resolution.get("complete"):
        return "resolved: every evidence row has a verified terminal outcome receipt"
    unresolved = int(resolution.get("unresolved_root_count") or 0)
    if status == "owner-recorded":
        return f"evidence recorded, not complete: {unresolved or 'all'} row(s) require disposition and outcome proof"
    if status == "non-source-recorded":
        return f"non-source evidence recorded, not complete: {unresolved or 'all'} row(s) require terminal proof"
    if status == "superseded-recorded":
        return f"supersession evidence recorded, not complete: {unresolved or 'all'} row(s) require successor proof"
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
    review_batches = priority_review_batches(priority)
    receipt_map = receipt_by_root(load_json(PRESERVATION_RECEIPTS))
    packet_receipts = packet_receipts_by_source_batch(load_json(PACKET_RESOLUTION_RECEIPTS))
    batch_resolutions = batch_resolution_lookup(load_json(BATCH_RESOLUTION_RECEIPTS))
    attacks = attack_by_id(load_json(ATTACK_INDEX))
    batches = []
    for batch in review_batches:
        worktree_names = sorted((batch.get("worktrees") or {}).keys())
        receipts = [receipt_map[root] for root in worktree_names if root in receipt_map]
        batch_packet_receipts = packet_receipts.get(str(batch.get("id") or ""), [])
        batch_resolution = batch_resolutions.get(str(batch.get("id") or ""))
        attack_rows = [attacks[root] for root in worktree_names if root in attacks]
        status = status_for_batch(batch, receipts, batch_packet_receipts, batch_resolution)
        resolution = resolution_for_batch(batch, receipts, batch_packet_receipts, batch_resolution)
        evidence = evidence_summary(
            batch,
            receipts,
            batch_packet_receipts,
            batch_resolution,
            attack_rows,
            resolution,
        )
        batches.append(
            {
                "id": batch.get("id"),
                "band": batch.get("band"),
                "lane": batch.get("lane"),
                "status": status,
                "resolution_complete": bool(resolution.get("complete")),
                "gate": gate_for_status(status, resolution),
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
    closed = [item for item in batches if item["resolution_complete"]]
    queue = [item for item in batches if not item["resolution_complete"] and item["status"] != "parked-secret"]
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
            "packet_resolution_receipts": {
                "path": str(PACKET_RESOLUTION_RECEIPTS),
                "present": bool(packet_receipts),
            },
            "batch_resolution_receipts": {
                "path": str(BATCH_RESOLUTION_RECEIPTS),
                "present": bool(batch_resolutions),
            },
        },
        "coverage": {
            "priority_batches": len(review_batches),
            "review_batches": len(batches),
            "recorded_batches": len(recorded),
            "closed_batches": len(closed),
            "recorded_unresolved_batches": sum(1 for item in recorded if not item["resolution_complete"]),
            "open_review_batches": len(queue),
            "parked_secret_batches": int(status_counts.get("parked-secret", 0)),
            "prompt_events": sum(int(item["prompt_events"]) for item in batches),
            "unique_prompt_hash_refs": sum(int(item["unique_prompt_hashes"]) for item in batches),
            "preservation_receipts": len(receipt_map),
            "packet_resolution_receipts": sum(len(rows) for rows in packet_receipts.values()),
            "batch_resolution_receipts": len(batch_resolutions),
        },
        "counts": {
            "statuses": dict(status_counts.most_common()),
            "lanes": dict(lane_counts.most_common()),
        },
        "control": {
            "authority": "prompt_atom_projection",
            "governing_unit": "atom_id",
            "legacy_compatibility_only": True,
        },
        "recorded_batches": recorded,
        "closed_batches": closed,
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
        "- Evidence status and work completion are separate axes. A recorded receipt never closes a batch by itself.",
        "- A batch closes only when every evidence row has `done` or `superseded` disposition plus a passing outcome receipt.",
        "- Recorded-but-unresolved and `needs-*` batches remain in the review queue until their residual asks are proved or owner-routed.",
        "- `parked-secret` remains parked unless a scoped account/setup task explicitly activates it.",
        "",
        "## Coverage",
        "",
        f"- Priority batches read: `{coverage.get('priority_batches', 0)}`.",
        f"- Review batches recorded: `{coverage.get('review_batches', 0)}`.",
        f"- Batches with durable owner/non-source/supersession evidence: `{coverage.get('recorded_batches', 0)}`.",
        f"- Batches with verified terminal outcomes: `{coverage.get('closed_batches', 0)}`.",
        f"- Recorded but unresolved batches: `{coverage.get('recorded_unresolved_batches', 0)}`.",
        f"- Open review batches: `{coverage.get('open_review_batches', 0)}`.",
        f"- Parked secret batches: `{coverage.get('parked_secret_batches', 0)}`.",
        f"- Prompt events represented: `{coverage.get('prompt_events', 0)}`.",
        f"- Preservation receipts available: `{coverage.get('preservation_receipts', 0)}`.",
        f"- Packet resolution receipts available: `{coverage.get('packet_resolution_receipts', 0)}`.",
        f"- Batch resolution receipts available: `{coverage.get('batch_resolution_receipts', 0)}`.",
        f"- Status mix: {render_counts(snapshot['counts']['statuses'])}.",
        f"- Lane mix: {render_counts(snapshot['counts']['lanes'])}.",
        "",
        "## Recorded Batches",
        "",
        "| Rank | Batch | Evidence Status | Complete | Band | Lane | Events | Owner Repos | Evidence | Gate |",
        "|---:|---|---|---|---|---|---:|---|---|---|",
    ]
    for rank, batch in enumerate(recorded, start=1):
        evidence = batch["evidence"]
        if evidence.get("batch_root_statuses"):
            receipt_bits = f"batch roots {render_counts(evidence.get('batch_root_statuses') or {})}"
        elif evidence.get("packet_receipt_statuses"):
            receipt_bits = f"packets {render_counts(evidence.get('packet_receipt_statuses') or {})}"
        else:
            receipt_bits = render_counts(evidence.get("receipt_statuses") or {})
        owner_repos = evidence.get("batch_root_repos") or evidence.get("owner_repos") or []
        lines.append(
            f"| {rank} | `{batch['id']}` | `{batch['status']}` | `{str(batch['resolution_complete']).lower()}` | "
            f"`{batch['band']}` | `{batch['lane']}` | "
            f"{batch['prompt_events']} | {render_owner_repos(owner_repos)} | "
            f"{receipt_bits} | {batch['gate']} |"
        )
    if not recorded:
        lines.append("| 0 | none | n/a | false | n/a | n/a | 0 | none | none | n/a |")

    lines += [
        "",
        "## Next Review Queue",
        "",
        "| Rank | Batch | Evidence Status | Unresolved | Band | Lane | Sessions | Events | Dominant Mix | Next Action |",
        "|---:|---|---|---:|---|---|---:|---:|---|---|",
    ]
    for rank, batch in enumerate(queue, start=1):
        source_bits = ", ".join(f"{key} {value}" for key, value in (batch.get("sources") or {}).items()) or "none"
        family_bits = ", ".join(f"{key} {value}" for key, value in (batch.get("families") or {}).items()) or "none"
        lines.append(
            f"| {rank} | `{batch['id']}` | `{batch['status']}` | "
            f"{batch['evidence'].get('unresolved_root_count', 0)} | `{batch['band']}` | `{batch['lane']}` | "
            f"{batch['session_count']} | {batch['prompt_events']} | sources {source_bits}; families {family_bits} | "
            f"{batch['next_action']} |"
        )
    if not queue:
        lines.append("| 0 | none | n/a | 0 | n/a | n/a | 0 | 0 | none | n/a |")

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
        "- Refresh prompt packet ledger: `python3 scripts/prompt-packet-ledger.py --write`",
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

    try:
        snapshot = build_snapshot(limit=max(1, args.limit))
    except BatchAuthorityError as exc:
        print(f"prompt-batch-review-ledger: BLOCKED — {exc}")
        return 2
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
