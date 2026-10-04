"""Complete custody proof-graph factory shared by real integration fixtures."""

import hashlib
import json

from limen.portable_custody import assemble_bundle
from limen.prima_materia import CustodyReceiptV2

OBSERVED = "2026-10-03T00:00:00+00:00"
RESTORED = "2026-10-03T01:00:00+00:00"
RETAINED = "2026-11-03T00:00:00+00:00"


def make_graph(*, session_id, scope_paths, now, native_entries=None):
    files, refs = {}, {}

    def put(value):
        raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
        digest = hashlib.sha256(raw).hexdigest()
        path = "evidence/" + digest
        files[path] = raw
        refs[digest] = {"evidence": path, "sha256": digest}
        return digest

    profile = put(b"fixture encryption profile")
    logical = put(
        {
            "schema": "limen.logical_capture.v1",
            "session_id": session_id,
            "scope_paths": scope_paths,
            "entries": {
                key: {".": {"type": "directory", "size": None, "content": None, "hardlink_group": None}}
                for key in scope_paths
            },
        }
    )
    native = put(
        {
            "schema": "limen.native_capture.v1",
            "session_id": session_id,
            "scope_paths": scope_paths,
            "entries": {
                key: {
                    ".": {
                        "measured": True,
                        "acl_measured": True,
                        "xattrs_measured": True,
                        "metadata": {
                            "type": "directory",
                            "mode": 0o755,
                            "uid": 501,
                            "gid": 20,
                            "mtime_ns": 1,
                            "birthtime_ns": 1,
                            "ctime_ns": 1,
                            "atime_ns": 1,
                            "flags": 0,
                            "nlink": 1,
                            "xattrs": {},
                            "acl": "absent",
                            "size": None,
                            "content": None,
                            "hardlink_group": None,
                        },
                    }
                }
                for key in scope_paths
            },
        }
    )
    if native_entries is not None:
        refs.pop(native)
        refs.pop(logical)
        native = put(
            {
                "schema": "limen.native_capture.v1",
                "session_id": session_id,
                "scope_paths": scope_paths,
                "entries": native_entries,
            }
        )
        logical = put(
            {
                "schema": "limen.logical_capture.v1",
                "session_id": session_id,
                "scope_paths": scope_paths,
                "entries": {
                    root: {
                        name: {key: entry["metadata"][key] for key in ("type", "size", "content", "hardlink_group")}
                        for name, entry in rows.items()
                    }
                    for root, rows in native_entries.items()
                },
            }
        )
    atoms = sum(len(rows) for rows in native_entries.values()) if native_entries is not None else len(scope_paths)
    artifact = {"artifact_id": "capturedArtifact01", "ciphertext_digest": "c" * 64, "ciphertext_bytes": 100}
    manifest = put(
        {
            "schema": "limen.ciphertext_manifest.v1",
            "session_id": session_id,
            "scope_paths": scope_paths,
            "artifacts": [artifact],
        }
    )
    captured = dict(artifact, manifest_digest=manifest)
    predicate = put(b"fixture full native restorer implementation")
    replicas, restorations = [], []
    for number, backend in enumerate(("github", "gdrive")):
        identifier = f"replicaIdentifier{number}"
        account = f"accountNamespace{number}"
        object_id = f"object{number}"
        revision = "revision1"
        readback = put(
            {
                "schema": "limen.replica_readback_observation.v1",
                "authenticated": True,
                "replica_id": identifier,
                "backend": backend,
                "account_namespace_id": account,
                "artifact_id": artifact["artifact_id"],
                "object_id": object_id,
                "revision": revision,
                "observed_at": OBSERVED,
                "ciphertext_sha256": artifact["ciphertext_digest"],
                "readback_sha256": artifact["ciphertext_digest"],
                "ciphertext_bytes": 100,
            }
        )
        retention = (
            put(
                {
                    "schema": "limen.replica_retention_observation.v1",
                    "authenticated": True,
                    "retention_enforced": True,
                    "replica_id": identifier,
                    "backend": backend,
                    "account_namespace_id": account,
                    "observed_at": OBSERVED,
                    "retention_until": RETAINED,
                    "generations": [{"object_id": object_id, "revision": revision}],
                }
            )
            if number
            else None
        )
        replicas.append(
            {
                "replica_id": identifier,
                "backend": backend,
                "account_namespace_id": account,
                "encryption_profile_digest": profile,
                "observed_at": OBSERVED,
                "retention_until": RETAINED if number else None,
                "retention_evidence_digest": retention,
                "artifacts": [
                    dict(
                        captured,
                        object_id=object_id,
                        revision=revision,
                        readback_digest=artifact["ciphertext_digest"],
                        readback_evidence_digest=readback,
                    )
                ],
            }
        )
        restored = put(
            {
                "schema": "limen.replica_restore_observation.v1",
                "session_id": session_id,
                "scope_paths": scope_paths,
                "replica_id": identifier,
                "restored_at": RESTORED,
                "logical_manifest_digest": logical,
                "native_metadata_digest": native,
                "logical_verified_entries": atoms,
                "native_verified_entries": atoms,
                "predicate_digest": predicate,
                "full_restore": True,
                "native_metadata_verified": True,
                "passed": True,
            }
        )
        restorations.append(
            {
                "replica_id": identifier,
                "restored_at": RESTORED,
                "logical_manifest_digest": logical,
                "native_metadata_digest": native,
                "source_atoms_verified": atoms,
                "predicate_digest": predicate,
                "evidence_digest": restored,
                "full_restore": True,
                "native_metadata_verified": True,
                "passed": True,
            }
        )
    receipt = CustodyReceiptV2.model_validate(
        {
            "custody_id": "custodyIdentifier01",
            "encryption_profile_digest": profile,
            "logical_manifest_digest": logical,
            "native_metadata_digest": native,
            "chunk_manifest_digests": [manifest],
            "captured_artifacts": [captured],
            "source_atoms": atoms,
            "replicas": replicas,
            "restoration_proofs": restorations,
        }
    )
    bundle = json.loads(
        assemble_bundle(
            receipt,
            session_id=session_id,
            scope_paths=scope_paths,
            supporting_evidence=refs,
            read_evidence=lambda packet: files[packet["evidence"]],
            now=now,
        )
    )
    return bundle, files


def make_retirement(bundle, files, *, session_id, scope_paths, retired_root_ids):
    """Return a complete retirement graph, preserving all original scope IDs."""
    custody = json.dumps(bundle).encode()
    binding = {
        "session_id": session_id,
        "scope_paths": scope_paths,
        "custody_sha256": hashlib.sha256(custody).hexdigest(),
    }

    def put(value):
        raw = json.dumps(value, sort_keys=True).encode()
        digest = hashlib.sha256(raw).hexdigest()
        path = "evidence/" + digest
        files[path] = raw
        return {"evidence": path, "sha256": digest}

    dependencies = {
        "schema": "limen.scope_retirement_dependencies.v1",
        **binding,
        "observed_at": "2026-10-03T01:15:00+00:00",
        "scope_root_ids": sorted(scope_paths),
        "retired_root_ids": sorted(retired_root_ids),
        "observation_complete": True,
        "git_store_consumers": [],
        "external_consumers": [],
    }
    execution = {
        "schema": "limen.scope_retirement_execution.v1",
        **binding,
        "executed_at": "2026-10-03T01:30:00+00:00",
        "exit_code": 0,
        "absence_measured": True,
        "retired_root_ids": sorted(retired_root_ids),
        "dependencies": put(dependencies),
    }
    record = {
        "schema": "limen.scope_retirement.v1",
        **binding,
        "retired_root_ids": sorted(retired_root_ids),
        "executions": [put(execution)],
    }
    return record, custody, dependencies, execution, put
