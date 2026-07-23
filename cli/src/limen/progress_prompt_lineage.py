"""Normalize prompt atoms and exact estate receipts into a progress source."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from limen.progress_source_registry import REPORT_SCHEMA

SCHEMA = "limen.progress-prompt-lineage.v1"
SOURCE_ID = "prompt-lineage"
AUTHORITY_SCHEMA = "limen.prompt-authority-seal.v1"
ATOM_KINDS = frozenset({"ask", "correction", "constraint", "acceptance_criterion", "human_gate"})
DISPOSITIONS = frozenset({"unassessed", "not_done", "partial", "blocked", "done", "superseded"})
TERMINAL_DISPOSITIONS = frozenset({"done", "superseded"})
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _authority_state(seal: dict[str, Any]) -> tuple[bool, int | None, int | None, list[str]]:
    failures: list[str] = []
    if seal.get("schema") != AUTHORITY_SCHEMA:
        failures.append("unsupported-prompt-authority-seal")
    claimed_hash = seal.get("content_hash")
    material = {key: value for key, value in seal.items() if key != "content_hash"}
    if not isinstance(claimed_hash, str) or claimed_hash != _canonical_sha256(material):
        failures.append("prompt-authority-seal-hash-mismatch")
    scope = _object(seal.get("scope"))
    totals = _object(seal.get("totals"))
    coverage = _object(seal.get("coverage"))
    expected_atoms = _nonnegative_int(coverage.get("atoms"))
    expected_unresolved = _nonnegative_int(coverage.get("current_unresolved_atoms"))
    if expected_atoms is None:
        failures.append("authority-atom-count-missing")
    if expected_unresolved is None:
        failures.append("authority-unresolved-count-missing")
    zero_fields = ("pending", "errors", "unsupported", "unresolved", "adapter_gaps", "validation_errors")
    exact = bool(
        seal.get("authority_ready") is True
        and seal.get("validation_ok") is True
        and scope.get("scope") == "all"
        and scope.get("target_scope") == "all"
        and scope.get("all_baseline_complete") is True
        and all(totals.get(field) == 0 for field in zero_fields)
    )
    if not exact:
        failures.append("prompt-authority-not-exact-all-all")
    return exact and not failures, expected_atoms, expected_unresolved, failures


def _passing_evidence(item: Any) -> bool:
    return bool(
        isinstance(item, dict)
        and str(item.get("ref") or "").strip()
        and str(item.get("predicate") or "").strip()
        and str(item.get("result") or "").lower() == "pass"
        and str(item.get("verified_at") or "").strip()
    )


def _reconciliation_rows(
    reconciliation: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not isinstance(reconciliation, dict):
        return {}, ["estate-reconciliation-missing"]
    control = _object(reconciliation.get("control"))
    private_check = _object(control.get("private_check"))
    failures: list[str] = []
    if not (
        control.get("authority") == "prompt_atom_projection"
        and control.get("source_scope") == "all"
        and control.get("target_scope") == "all"
        and control.get("matching") == "exact_atom_id_only"
        and control.get("read_only") is True
        and control.get("estate_mutations") == 0
        and private_check.get("result") == "pass"
    ):
        failures.append("estate-reconciliation-authority-invalid")
    rows: dict[str, dict[str, Any]] = {}
    for raw in reconciliation.get("atom_reconciliation") or []:
        if not isinstance(raw, dict) or not SAFE_ID.fullmatch(str(raw.get("atom_id") or "")):
            failures.append("estate-reconciliation-row-invalid")
            continue
        atom_id = str(raw["atom_id"])
        if atom_id in rows:
            failures.append(f"{atom_id}:duplicate-estate-reconciliation")
            continue
        rows[atom_id] = raw
    coverage = _object(reconciliation.get("coverage"))
    declared = _nonnegative_int(coverage.get("unresolved_atom_ids"))
    if declared is None or declared != len(rows):
        failures.append("estate-reconciliation-count-mismatch")
    return rows, failures


def _receipt_links(row: dict[str, Any] | None) -> dict[str, list[str]]:
    links: dict[str, list[str]] = {"tasks": [], "pull_requests": [], "worktrees": []}
    if row is None:
        return links
    for owner in row.get("owner_receipts") or []:
        if not isinstance(owner, dict):
            continue
        for receipt in owner.get("receipts") or []:
            if not isinstance(receipt, dict):
                continue
            receipt_id = str(receipt.get("receipt_id") or "")
            surface = str(receipt.get("surface") or "")
            if receipt_id and surface == "task":
                links["tasks"].append(receipt_id)
            elif receipt_id and surface == "pull_request":
                links["pull_requests"].append(receipt_id)
            elif receipt_id and surface == "worktree":
                links["worktrees"].append(receipt_id)
    return {key: sorted(set(values)) for key, values in links.items()}


def _normalize_atom(
    atom: dict[str, Any],
    reconciliation: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    failures: list[str] = []
    atom_id = str(atom.get("atom_id") or "")
    lineage_id = str(atom.get("lineage_id") or "")
    kind = str(atom.get("kind") or "")
    if not SAFE_ID.fullmatch(atom_id):
        return None, ["atom-identity-invalid"]
    if not SAFE_ID.fullmatch(lineage_id):
        failures.append(f"{atom_id}:lineage-identity-invalid")
    if kind not in ATOM_KINDS:
        failures.append(f"{atom_id}:kind-invalid")
    predecessor_ids = sorted({str(value) for value in atom.get("predecessor_ids") or [] if str(value)})
    if kind == "correction" and not predecessor_ids:
        failures.append(f"{atom_id}:correction-missing-predecessor")

    outcome = _object(atom.get("outcome"))
    disposition = str(outcome.get("disposition") or "unassessed")
    if disposition not in DISPOSITIONS:
        failures.append(f"{atom_id}:disposition-invalid")
    evidence = [item for item in outcome.get("evidence") or [] if isinstance(item, dict)]
    verified = [item for item in evidence if _passing_evidence(item)]
    if disposition in {"done", "partial", "superseded"} and not verified:
        failures.append(f"{atom_id}:closure-without-verified-predicate")
    owner = str(outcome.get("owner") or atom.get("owner") or "unassigned")
    successor = str(outcome.get("successor_atom_id") or "") or None
    if disposition == "superseded" and successor is None:
        failures.append(f"{atom_id}:supersession-successor-missing")
    blocker: dict[str, str] | None = None
    if disposition == "blocked":
        gate = str(outcome.get("gate") or "")
        next_command = str(outcome.get("next_command") or "")
        if not owner or owner == "unassigned" or not gate or not next_command:
            failures.append(f"{atom_id}:blocker-route-incomplete")
        blocker = {"owner": owner, "gate": gate, "next_command": next_command}

    links = _receipt_links(reconciliation)
    evidence_refs = sorted({str(item.get("ref")) for item in evidence if item.get("ref")})
    predicates = sorted({str(item.get("predicate")) for item in evidence if item.get("predicate")})
    receipt_count = sum(len(values) for values in links.values()) + len(evidence_refs)
    return (
        {
            "leaf_id": atom_id,
            "kind": kind,
            "authority": str(atom.get("authority") or "unknown"),
            "lineage_id": lineage_id,
            "predecessor_ids": predecessor_ids,
            "is_current_intent": atom.get("is_current_intent") is True,
            "disposition": disposition,
            "owner": owner,
            "owner_route": str(atom.get("owner_route") or "unrouted"),
            "task_receipts": links["tasks"],
            "pull_request_receipts": links["pull_requests"],
            "worktree_receipts": links["worktrees"],
            "durable_receipts": evidence_refs,
            "predicates": predicates,
            "verified_outcome": bool(verified),
            "verified_at": sorted({str(item.get("verified_at")) for item in verified if item.get("verified_at")}),
            "superseded_by": successor,
            "blocker": blocker,
            "receipt_count": receipt_count,
            "unmatched": receipt_count == 0,
        },
        failures,
    )


def _tracked_leaf(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "leaf_key": sha256(str(row["leaf_id"]).encode()).hexdigest(),
        "kind": row["kind"],
        "authority": row["authority"],
        "is_current_intent": row["is_current_intent"],
        "disposition": row["disposition"],
        "has_task_receipt": bool(row["task_receipts"]),
        "has_pull_request_receipt": bool(row["pull_request_receipts"]),
        "has_durable_receipt": bool(row["durable_receipts"]),
        "verified_outcome": row["verified_outcome"],
        "superseded": row["superseded_by"] is not None,
        "blocked": row["blocker"] is not None,
        "unmatched": row["unmatched"],
    }


def build_prompt_lineage_source(
    authority_seal: dict[str, Any],
    atoms: Sequence[dict[str, Any]],
    estate_reconciliation: dict[str, Any] | None,
    *,
    generated_at: datetime | None = None,
    input_failures: Sequence[str] = (),
    public_limit: int = 256,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build full private facts and a bounded, prompt-text-free tracked projection."""

    if public_limit < 0:
        raise ValueError("public_limit must be non-negative")
    authority_exact, expected_atoms, expected_unresolved, failures = _authority_state(authority_seal)
    failures.extend(f"input-failure-{sha256(str(value).encode()).hexdigest()}" for value in input_failures)
    reconciliation_rows: dict[str, dict[str, Any]] = {}
    if authority_exact:
        reconciliation_rows, reconciliation_failures = _reconciliation_rows(estate_reconciliation)
        failures.extend(reconciliation_failures)

    leaves: list[dict[str, Any]] = []
    atom_ids: set[str] = set()
    for atom in atoms:
        atom_id = str(atom.get("atom_id") or "") if isinstance(atom, dict) else ""
        if atom_id in atom_ids:
            failures.append(f"{atom_id}:duplicate-atom")
            continue
        atom_ids.add(atom_id)
        row, row_failures = _normalize_atom(
            atom if isinstance(atom, dict) else {},
            reconciliation_rows.get(atom_id),
        )
        failures.extend(row_failures)
        if row is not None:
            leaves.append(row)
    leaves.sort(key=lambda row: str(row["leaf_id"]))

    if authority_exact and expected_atoms != len(leaves):
        failures.append("prompt-authority-atom-count-not-reconciled")
    leaf_ids = {str(row["leaf_id"]) for row in leaves}
    for row in leaves:
        for predecessor in row["predecessor_ids"]:
            if predecessor not in leaf_ids:
                failures.append(f"{row['leaf_id']}:predecessor-does-not-resolve")
        successor = row["superseded_by"]
        if successor is not None and successor not in leaf_ids:
            failures.append(f"{row['leaf_id']}:successor-does-not-resolve")

    unresolved_ids = {
        str(row["leaf_id"])
        for row in leaves
        if row["is_current_intent"] and row["disposition"] not in TERMINAL_DISPOSITIONS
    }
    if authority_exact and expected_unresolved != len(unresolved_ids):
        failures.append("prompt-authority-unresolved-count-not-reconciled")
    if authority_exact and set(reconciliation_rows) != unresolved_ids:
        failures.append("estate-reconciliation-unresolved-set-mismatch")

    failures = sorted(set(failures))
    exhaustive = authority_exact and not failures
    observed = (generated_at or datetime.now(UTC)).astimezone(UTC)
    content_sha256 = _canonical_sha256(leaves)
    source_report = {
        "schema": REPORT_SCHEMA,
        "source_id": SOURCE_ID,
        "cursor": {
            "authority_scope": (authority_seal.get("scope") or {}).get("scope"),
            "authority_ready": authority_seal.get("authority_ready") is True,
            "expected_atom_count": expected_atoms,
            "known_atom_count": len(leaves),
            "expected_current_unresolved_count": expected_unresolved,
            "known_current_unresolved_count": len(unresolved_ids),
            "reconciled_current_unresolved_count": len(reconciliation_rows),
            "failure_count": len(failures),
        },
        "exhaustive": exhaustive,
        "generated_at": observed.isoformat().replace("+00:00", "Z"),
        "content_sha256": content_sha256,
        "semantic_status": "ready" if exhaustive else "partial",
        "normalized_leaf_count": len(leaves),
    }
    kind_counts = Counter(str(row["kind"]) for row in leaves)
    disposition_counts = Counter(str(row["disposition"]) for row in leaves)
    summary = {
        "authority_ready": authority_seal.get("authority_ready") is True,
        "expected_atom_count": expected_atoms,
        "known_atom_count": len(leaves),
        "current_unresolved_count": len(unresolved_ids),
        "matched_atom_count": sum(not bool(row["unmatched"]) for row in leaves),
        "unmatched_atom_count": sum(bool(row["unmatched"]) for row in leaves),
        "verified_outcome_count": sum(bool(row["verified_outcome"]) for row in leaves),
        "correction_count": kind_counts.get("correction", 0),
        "kind_counts": dict(sorted(kind_counts.items())),
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "failure_count": len(failures),
    }
    full = {
        "schema": SCHEMA,
        "source_report": source_report,
        "summary": summary,
        "failures": failures,
        "leaves": leaves,
    }
    public_rows = [_tracked_leaf(row) for row in leaves[:public_limit]]
    tracked = {
        "schema": SCHEMA,
        "source_report": source_report,
        "summary": summary,
        "failure_reasons": failures,
        "leaves": public_rows,
        "tracked_leaf_limit": public_limit,
        "tracked_leaf_count": len(public_rows),
        "tracked_leaf_truncated_count": max(0, len(leaves) - len(public_rows)),
    }
    return full, tracked
