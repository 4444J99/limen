"""Every portable contract hash must resolve to its complete scope-bound proof."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime

import pytest

from limen.portable_custody import PortableCustodyError, assemble_bundle, validate_bundle
from limen.prima_materia import CustodyReceiptV2

SID = "portable-session"
SCOPES = {"first": "a" * 64, "second": "b" * 64}
NOW = datetime(2026, 10, 3, 2, tzinfo=UTC)
OBSERVED = "2026-10-03T00:00:00+00:00"
RESTORED = "2026-10-03T01:00:00+00:00"
RETAINED = "2026-11-03T00:00:00+00:00"


@pytest.fixture
def graph():
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
            "session_id": SID,
            "scope_paths": SCOPES,
            "entries": {
                key: {".": {"type": "directory", "size": None, "content": None, "hardlink_group": None}}
                for key in SCOPES
            },
        }
    )
    native = put(
        {
            "schema": "limen.native_capture.v1",
            "session_id": SID,
            "scope_paths": SCOPES,
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
                for key in SCOPES
            },
        }
    )
    artifact = {"artifact_id": "capturedArtifact01", "ciphertext_digest": "c" * 64, "ciphertext_bytes": 100}
    manifest = put(
        {"schema": "limen.ciphertext_manifest.v1", "session_id": SID, "scope_paths": SCOPES, "artifacts": [artifact]}
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
                "session_id": SID,
                "scope_paths": SCOPES,
                "replica_id": identifier,
                "restored_at": RESTORED,
                "logical_manifest_digest": logical,
                "native_metadata_digest": native,
                "logical_verified_entries": 2,
                "native_verified_entries": 2,
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
                "source_atoms_verified": 2,
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
            "source_atoms": 2,
            "replicas": replicas,
            "restoration_proofs": restorations,
        }
    )
    bundle = json.loads(
        assemble_bundle(
            receipt,
            session_id=SID,
            scope_paths=SCOPES,
            supporting_evidence=refs,
            read_evidence=lambda packet: files[packet["evidence"]],
            now=NOW,
        )
    )
    return bundle, files


def validate(bundle, files, **changes):
    return validate_bundle(
        json.dumps(bundle).encode(),
        session_id=changes.get("session_id", SID),
        scope_paths=changes.get("scope_paths", SCOPES),
        now=changes.get("now", NOW),
        read_evidence=lambda packet: files[packet["evidence"]],
    )


def replace_record(bundle, files, old_digest, mutation):
    """Rehash an honestly changed record, not just corrupt its committed bytes."""
    old_packet = bundle["supporting_evidence"].pop(old_digest)
    record = json.loads(files[old_packet["evidence"]])
    mutation(record)
    raw = json.dumps(record, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path = "evidence/" + digest
    files[path] = raw
    bundle["supporting_evidence"][digest] = {"evidence": path, "sha256": digest}
    return digest


def test_complete_bundle_is_read_only_and_idempotent(graph):
    bundle, files = graph
    before = deepcopy(files)
    assert validate(bundle, files) == validate(bundle, files)
    assert files == before


@pytest.mark.parametrize("failure", ["session", "scope", "missing_record", "wrong_bytes", "extra_record", "expired"])
def test_complete_contract_does_not_replace_proof_graph(graph, failure):
    bundle, files = graph
    changes = {}
    if failure == "session":
        changes["session_id"] = "another-session"
    elif failure == "scope":
        changes["scope_paths"] = {"first": SCOPES["first"]}
    elif failure == "missing_record":
        bundle["supporting_evidence"].pop(bundle["custody_receipt"]["native_metadata_digest"])
    elif failure == "wrong_bytes":
        files[next(iter(files))] += b"changed"
    elif failure == "extra_record":
        bundle["supporting_evidence"]["e" * 64] = {"evidence": "unused", "sha256": "e" * 64}
    else:
        changes["now"] = datetime(2026, 12, 3, tzinfo=UTC)
    with pytest.raises(PortableCustodyError):
        validate(bundle, files, **changes)


@pytest.mark.parametrize(
    "field,value",
    [
        ("authenticated", False),
        ("authenticated", 1),
        ("revision", "different"),
        ("backend", "physical"),
        ("account_namespace_id", "anotherAccount"),
        ("ciphertext_bytes", 99),
        ("readback_sha256", "0" * 64),
        ("observed_at", RESTORED),
    ],
)
def test_rehashed_readback_must_still_match_exact_capture(graph, field, value):
    bundle, files = graph
    artifact = bundle["custody_receipt"]["replicas"][0]["artifacts"][0]
    artifact["readback_evidence_digest"] = replace_record(
        bundle, files, artifact["readback_evidence_digest"], lambda row: row.update({field: value})
    )
    with pytest.raises(PortableCustodyError):
        validate(bundle, files)


@pytest.mark.parametrize(
    "field,value",
    [
        ("passed", False),
        ("full_restore", False),
        ("native_metadata_verified", False),
        ("native_verified_entries", 1),
        ("logical_verified_entries", 1),
        ("scope_paths", {"first": SCOPES["first"]}),
        ("session_id", "another-session"),
        ("restored_at", OBSERVED),
    ],
)
def test_full_restore_cannot_be_relabelled_from_partial_report(graph, field, value):
    bundle, files = graph
    proof = bundle["custody_receipt"]["restoration_proofs"][0]
    proof["evidence_digest"] = replace_record(
        bundle, files, proof["evidence_digest"], lambda row: row.update({field: value})
    )
    with pytest.raises(PortableCustodyError):
        validate(bundle, files)


@pytest.mark.parametrize(
    "field,value",
    [
        ("authenticated", False),
        ("retention_enforced", False),
        ("generations", []),
        ("account_namespace_id", "anotherAccount"),
        ("retention_until", RESTORED),
    ],
)
def test_retention_covers_every_exact_generation(graph, field, value):
    bundle, files = graph
    replica = bundle["custody_receipt"]["replicas"][1]
    replica["retention_evidence_digest"] = replace_record(
        bundle, files, replica["retention_evidence_digest"], lambda row: row.update({field: value})
    )
    with pytest.raises(PortableCustodyError):
        validate(bundle, files)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda entry: entry.pop("metadata"),
        lambda entry: entry["metadata"].pop("ctime_ns"),
        lambda entry: entry["metadata"].update(acl="unmeasured"),
        lambda entry: entry["metadata"].update(mode=True),
        lambda entry: entry["metadata"].update(xattrs={"user.attr": "not-a-digest"}),
        lambda entry: entry["metadata"].update(type="special"),
        lambda entry: entry.update(acl_measured=False),
        lambda entry: entry.update(xattrs_measured=False),
    ],
)
def test_measured_flag_does_not_replace_native_readings(graph, mutation):
    bundle, files = graph
    receipt = bundle["custody_receipt"]
    # Even a valid contract whose native digest was honestly updated is not
    # accepted without the actual capture fields and matching restore records.
    old = receipt["native_metadata_digest"]
    new = replace_record(bundle, files, old, lambda row: mutation(row["entries"]["first"]["."]))
    receipt["native_metadata_digest"] = new
    for proof in receipt["restoration_proofs"]:
        proof["native_metadata_digest"] = new
    with pytest.raises(PortableCustodyError):
        validate(bundle, files)
