"""Require complete portable custody and live equivalence before rebinding roots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from limen.native_equivalence import compare_native_manifests
from limen.portable_custody import PortableCustodyError, validate_bundle

SCHEMA = "limen.scope_lineage.v1"


def validate_lineage(
    payload: bytes,
    custody_payload: bytes,
    *,
    session_id: str,
    original_scope_paths: Mapping[str, str],
    current_scope_paths: Mapping[str, str],
    read_evidence: Callable[[dict], bytes],
    observe_current: Callable[[Mapping[str, str], int, int], bytes],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Validate every original root, never merely the roots that still resolve.

    The native observer receives exact atom and maximum-file-byte bounds derived
    from the authenticated source inventory. Production observers must acquire
    host admission and make a fresh, bounded, no-ignore observation. Evidence
    readers must require committed, unchanged, remotely durable records.
    Fresh comparison covers every relocated root. Unchanged roots remain in the
    full custody graph and ordinary scoped checks, not in a falsely expanded
    relocation claim. Missing/retired roots are not accepted by this contract.
    """
    record = json.loads(payload)
    if (
        not isinstance(record, dict)
        or record.get("schema") != SCHEMA
        or record.get("session_id") != session_id
        or record.get("original_scope_paths") != dict(original_scope_paths)
        or record.get("current_scope_paths") != dict(current_scope_paths)
        or record.get("custody_sha256") != hashlib.sha256(custody_payload).hexdigest()
        or record.get("disposition") != "relocated"
    ):
        raise PortableCustodyError("scope lineage binding is incomplete or inconsistent")
    receipt = validate_bundle(
        custody_payload,
        session_id=session_id,
        scope_paths=original_scope_paths,
        read_evidence=read_evidence,
        now=now,
    )
    if set(original_scope_paths) != set(current_scope_paths):
        raise PortableCustodyError("scope lineage original denominator differs")
    moved = {key for key in original_scope_paths if original_scope_paths[key] != current_scope_paths[key]}
    if not moved:
        raise PortableCustodyError("scope lineage has no relocated root")
    original_moved = {key: original_scope_paths[key] for key in sorted(moved)}
    current_moved = {key: current_scope_paths[key] for key in sorted(moved)}
    bundle = json.loads(custody_payload)
    original_packet = bundle["supporting_evidence"][receipt.native_metadata_digest]
    original = read_evidence(original_packet)
    if hashlib.sha256(original).hexdigest() != receipt.native_metadata_digest:
        raise PortableCustodyError("scope lineage original native evidence differs")
    current_packet = record.get("current_native")
    if not isinstance(current_packet, dict):
        raise PortableCustodyError("scope lineage destination inventory is absent")
    current = read_evidence(current_packet)
    if hashlib.sha256(current).hexdigest() != current_packet.get("sha256"):
        raise PortableCustodyError("scope lineage destination evidence differs")
    source = json.loads(original)
    projected_source = {
        **source,
        "scope_paths": original_moved,
        "entries": {key: source["entries"][key] for key in sorted(moved)},
    }
    comparison = compare_native_manifests(
        json.dumps(projected_source, sort_keys=True).encode(),
        current,
        session_id=session_id,
        original_scope_paths=original_moved,
        observed_scope_paths=current_moved,
    )
    maximum_file_bytes = max(
        (
            entry["metadata"]["size"]
            for rows in projected_source["entries"].values()
            for entry in rows.values()
            if entry["metadata"]["type"] == "file"
        ),
        default=0,
    )
    # Observe only after all committed custody and lineage evidence validates.
    live = observe_current(current_moved, comparison["atom_count"], maximum_file_bytes)
    live_comparison = compare_native_manifests(
        current,
        live,
        session_id=session_id,
        original_scope_paths=current_moved,
        observed_scope_paths=current_moved,
    )
    return {
        "schema": SCHEMA,
        "session_id": session_id,
        "original_scope_paths": dict(original_scope_paths),
        "current_scope_paths": dict(current_scope_paths),
        "custody_sha256": record["custody_sha256"],
        "original_native_sha256": receipt.native_metadata_digest,
        "committed_current_native_sha256": current_packet["sha256"],
        "live_native_sha256": live_comparison["observed_native_sha256"],
        "atom_count": comparison["atom_count"],
        "root_count": comparison["root_count"],
        "relocated_root_ids": sorted(moved),
        "relocation_verified": True,
        "retirement_authorized": False,
    }
