"""Assemble and consume committed, scope-bound portable custody evidence.

The v2 model is a contract, not an observation. This layer requires the actual
capture, authenticated readback, retention and full-restoration records behind
every digest. It does not upload, restore, authorize deletion or mint evidence.
Provider observers and native restorers remain responsible for those records.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from limen.prima_materia import CustodyReceiptV2

SCHEMA = "limen.portable_custody_evidence.v1"
DIGEST = re.compile(r"[a-f0-9]{64}")


class PortableCustodyError(ValueError):
    """A referenced observation is absent, inconsistent or incomplete."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise PortableCustodyError(reason)


def _time(value: Any) -> datetime:
    _require(isinstance(value, str), "observation timestamp is missing")
    result = datetime.fromisoformat(value)
    _require(result.tzinfo is not None, "observation timestamp has no timezone")
    return result


def _matches(record: dict, expected: dict) -> bool:
    return all(type(record.get(key)) is type(value) and record[key] == value for key, value in expected.items())


def _relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and str(path) == value


def _native_entry(entry: Any) -> dict:
    _require(isinstance(entry, dict) and entry.get("measured") is True, "native capture is unmeasured")
    _require(
        entry.get("acl_measured") is True and entry.get("xattrs_measured") is True,
        "native ACL or xattr capture is unmeasured",
    )
    metadata = entry.get("metadata")
    fields = {
        "type",
        "mode",
        "uid",
        "gid",
        "mtime_ns",
        "birthtime_ns",
        "atime_ns",
        "ctime_ns",
        "flags",
        "xattrs",
        "acl",
        "hardlink_group",
        "size",
        "content",
    }
    _require(isinstance(metadata, dict) and set(metadata) == fields, "complete native metadata readings are required")
    _require(metadata["type"] in {"file", "directory", "symlink"}, "native file type is unsupported")
    _require(
        all(
            type(metadata[key]) is int
            for key in ("mode", "uid", "gid", "mtime_ns", "birthtime_ns", "atime_ns", "ctime_ns", "flags")
        ),
        "native numeric metadata readings are malformed",
    )
    _require(
        0 <= metadata["mode"] <= 0o7777 and metadata["uid"] >= 0 and metadata["gid"] >= 0,
        "native ownership or mode is malformed",
    )
    attrs = metadata["xattrs"]
    _require(
        isinstance(attrs, dict)
        and all(
            isinstance(key, str) and key and isinstance(value, str) and DIGEST.fullmatch(value)
            for key, value in attrs.items()
        ),
        "native xattr digest readings are malformed",
    )
    acl = metadata["acl"]
    _require(
        isinstance(acl, str) and (acl == "absent" or DIGEST.fullmatch(acl) is not None),
        "native ACL reading is malformed or unmeasured",
    )
    _require(
        metadata["hardlink_group"] is None or _relative(metadata["hardlink_group"]),
        "native hardlink membership is malformed",
    )
    if metadata["type"] == "file":
        _require(type(metadata["size"]) is int and metadata["size"] >= 0, "native file size is unmeasured")
    else:
        _require(
            metadata["size"] is None and metadata["hardlink_group"] is None, "native non-file metadata is malformed"
        )
    content = metadata["content"]
    _require(
        content is None
        if metadata["type"] == "directory"
        else isinstance(content, str) and DIGEST.fullmatch(content) is not None,
        "native content or symlink-target digest is unmeasured",
    )
    return metadata


def validate_bundle(
    payload: bytes,
    *,
    session_id: str,
    scope_paths: Mapping[str, str],
    read_evidence: Callable[[dict], bytes],
    now: datetime | None = None,
) -> CustodyReceiptV2:
    """Check the full evidence graph against the original session denominator.

    ``read_evidence`` must resolve the packet from the inspected committed owner,
    never an untracked path or URL. It may also enforce unchanged working bytes.
    No output includes provider credentials, native paths or captured metadata.
    """
    now = now or datetime.now(UTC)
    _require(now.tzinfo is not None, "verification time has no timezone")
    bundle = json.loads(payload)
    _require(isinstance(bundle, dict) and bundle.get("schema") == SCHEMA, "portable evidence schema mismatch")
    _require(bundle.get("session_id") == session_id, "portable custody session mismatch")
    _require(bundle.get("scope_paths") == dict(scope_paths), "portable custody original scope mismatch")
    _require(bool(scope_paths), "portable custody has no original scope")
    _require(
        all(isinstance(value, str) and DIGEST.fullmatch(value) for value in scope_paths.values()),
        "portable custody original path identity is malformed",
    )
    receipt = CustodyReceiptV2.model_validate(bundle.get("custody_receipt"))
    references = bundle.get("supporting_evidence")
    _require(isinstance(references, dict), "portable supporting evidence is missing")
    used: set[str] = set()

    def content(digest: str) -> bytes:
        packet = references.get(digest)
        _require(isinstance(packet, dict) and packet.get("sha256") == digest, "supporting evidence is absent")
        raw = read_evidence(packet)
        _require(hashlib.sha256(raw).hexdigest() == digest, "supporting evidence digest mismatch")
        used.add(digest)
        return raw

    def record(digest: str, schema: str) -> dict:
        value = json.loads(content(digest))
        _require(isinstance(value, dict) and value.get("schema") == schema, "observation schema mismatch")
        return value

    # The capture-time encryption profile must exist, not just agree with other
    # self-declared hashes. Never print or copy its bytes into the report.
    content(receipt.encryption_profile_digest)
    logical = record(receipt.logical_manifest_digest, "limen.logical_capture.v1")
    native = record(receipt.native_metadata_digest, "limen.native_capture.v1")
    memberships = []
    for manifest in (logical, native):
        _require(manifest.get("session_id") == session_id, "capture session mismatch")
        _require(manifest.get("scope_paths") == dict(scope_paths), "capture original scope mismatch")
        entries = manifest.get("entries")
        _require(isinstance(entries, dict) and set(entries) == set(scope_paths), "capture scope denominator mismatch")
        _require(
            all(isinstance(rows, dict) and rows for rows in entries.values()), "capture root is empty or unmeasured"
        )
        membership = {(root, name) for root, rows in entries.items() for name in rows}
        _require(all(_relative(name) for _, name in membership), "capture member path is malformed")
        _require(len(membership) == receipt.source_atoms, "capture atom denominator mismatch")
        memberships.append(membership)
    _require(memberships[0] == memberships[1], "logical and native capture membership differs")
    for root, rows in native["entries"].items():
        for name, entry in rows.items():
            metadata = _native_entry(entry)
            projection = {key: metadata[key] for key in ("type", "size", "content", "hardlink_group")}
            _require(
                logical["entries"][root][name] == projection, "logical capture differs from native content readings"
            )
    captured = [artifact.model_dump(mode="json") for artifact in receipt.captured_artifacts]
    for digest in receipt.chunk_manifest_digests:
        manifest = record(digest, "limen.ciphertext_manifest.v1")
        _require(manifest.get("session_id") == session_id, "ciphertext capture session mismatch")
        _require(manifest.get("scope_paths") == dict(scope_paths), "ciphertext capture original scope mismatch")
        # A manifest cannot embed its own digest; compare its remaining fields.
        expected = [
            {key: value for key, value in row.items() if key != "manifest_digest"}
            for row in captured
            if row["manifest_digest"] == digest
        ]
        _require(manifest.get("artifacts") == expected, "ciphertext capture denominator mismatch")
    for replica in receipt.replicas:
        _require(replica.observed_at <= now, "replica observation is future-dated")
        for artifact in replica.artifacts:
            observed = record(artifact.readback_evidence_digest, "limen.replica_readback_observation.v1")
            expected = {
                "authenticated": True,
                "replica_id": replica.replica_id,
                "backend": replica.backend,
                "account_namespace_id": replica.account_namespace_id,
                "artifact_id": artifact.artifact_id,
                "object_id": artifact.object_id,
                "revision": artifact.revision,
                "ciphertext_sha256": artifact.ciphertext_digest,
                "readback_sha256": artifact.readback_digest,
                "ciphertext_bytes": artifact.ciphertext_bytes,
            }
            _require(_matches(observed, expected), "authenticated exact-generation readback mismatch")
            _require(_time(observed.get("observed_at")) == replica.observed_at, "readback observation time mismatch")
        if replica.retention_evidence_digest is not None:
            retained = record(replica.retention_evidence_digest, "limen.replica_retention_observation.v1")
            generations = [
                {"object_id": artifact.object_id, "revision": artifact.revision} for artifact in replica.artifacts
            ]
            _require(
                retained.get("authenticated") is True
                and retained.get("retention_enforced") is True
                and retained.get("replica_id") == replica.replica_id
                and retained.get("backend") == replica.backend
                and retained.get("account_namespace_id") == replica.account_namespace_id
                and retained.get("generations") == generations,
                "retention does not cover every authenticated generation",
            )
            _require(_time(retained.get("retention_until")) == replica.retention_until, "retention horizon mismatch")
            _require(_time(retained.get("observed_at")) == replica.observed_at, "retention observation time mismatch")
    _require(
        any(replica.retention_until is not None and replica.retention_until > now for replica in receipt.replicas),
        "restore-tested retained custody has expired",
    )
    for proof in receipt.restoration_proofs:
        _require(proof.restored_at <= now, "full restoration is future-dated")
        content(proof.predicate_digest)
        observed = record(proof.evidence_digest, "limen.replica_restore_observation.v1")
        expected = {
            "replica_id": proof.replica_id,
            "logical_manifest_digest": receipt.logical_manifest_digest,
            "native_metadata_digest": receipt.native_metadata_digest,
            "logical_verified_entries": receipt.source_atoms,
            "native_verified_entries": receipt.source_atoms,
            "predicate_digest": proof.predicate_digest,
            "full_restore": True,
            "native_metadata_verified": True,
            "passed": True,
            "scope_paths": dict(scope_paths),
            "session_id": session_id,
        }
        _require(_matches(observed, expected), "full native restoration observation mismatch")
        _require(_time(observed.get("restored_at")) == proof.restored_at, "full restoration time mismatch")
    _require(set(references) == used, "supporting evidence has unattributed records")
    return receipt


def assemble_bundle(
    receipt: CustodyReceiptV2,
    *,
    session_id: str,
    scope_paths: Mapping[str, str],
    supporting_evidence: Mapping[str, dict],
    read_evidence: Callable[[dict], bytes],
    now: datetime | None = None,
) -> bytes:
    """Produce a bundle only from an already complete, verified evidence graph."""
    payload = json.dumps(
        {
            "schema": SCHEMA,
            "session_id": session_id,
            "scope_paths": dict(scope_paths),
            "custody_receipt": receipt.model_dump(mode="json"),
            "supporting_evidence": dict(supporting_evidence),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    validate_bundle(payload, session_id=session_id, scope_paths=scope_paths, read_evidence=read_evidence, now=now)
    return payload
