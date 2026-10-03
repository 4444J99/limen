"""Remote custody must not require or impersonate mounted devices."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from limen.prima_materia import CustodyReceiptV2


def receipt():
    replicas = []
    proofs = []
    for number, backend in enumerate(("github", "gdrive")):
        identifier = f"replicaIdentifier{number}"
        replicas.append(
            {
                "replica_id": identifier,
                "backend": backend,
                "account_namespace_id": f"accountNamespace{number}",
                "encryption_profile_digest": "a" * 64,
                "observed_at": "2026-10-03T00:00:00+00:00",
                "retention_until": "2026-11-03T00:00:00+00:00" if number else None,
                "retention_evidence_digest": "b" * 64 if number else None,
                "artifacts": [
                    {
                        "artifact_id": "capturedArtifact01",
                        "manifest_digest": "c" * 64,
                        "ciphertext_digest": "d" * 64,
                        "ciphertext_bytes": 100,
                        "object_id": f"object{number}",
                        "revision": "revision1",
                        "readback_digest": "d" * 64,
                        "readback_evidence_digest": "e" * 64,
                    }
                ],
            }
        )
        proofs.append(
            {
                "replica_id": identifier,
                "restored_at": "2026-10-03T01:00:00+00:00",
                "logical_manifest_digest": "f" * 64,
                "native_metadata_digest": "1" * 64,
                "source_atoms_verified": 10,
                "predicate_digest": "2" * 64,
                "evidence_digest": "3" * 64,
                "full_restore": True,
                "native_metadata_verified": True,
                "passed": True,
            }
        )
    return {
        "custody_id": "custodyIdentifier01",
        "encryption_profile_digest": "a" * 64,
        "chunk_manifest_digests": ["c" * 64],
        "captured_artifacts": [
            {
                "artifact_id": "capturedArtifact01",
                "manifest_digest": "c" * 64,
                "ciphertext_digest": "d" * 64,
                "ciphertext_bytes": 100,
            }
        ],
        "logical_manifest_digest": "f" * 64,
        "native_metadata_digest": "1" * 64,
        "source_atoms": 10,
        "replicas": replicas,
        "restoration_proofs": proofs,
    }


def test_two_remote_vendors_without_device_ids():
    result = CustodyReceiptV2.model_validate(receipt())
    assert all(replica.device_id is None for replica in result.replicas)
    assert CustodyReceiptV2.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["replicas"][1].update(backend="github"),
        lambda r: r["replicas"][0]["artifacts"][0].update(artifact_id="differentArtifact01"),
        lambda r: r["replicas"][0].update(device_id="fakeDeviceIdentifier"),
        lambda r: r["replicas"][0]["artifacts"][0].update(readback_digest="0" * 64),
        lambda r: r["replicas"][0]["artifacts"][0].update(object_id="https://provider/object?token=secret"),  # allow-secret
        lambda r: r["replicas"][1]["artifacts"][0].update(ciphertext_bytes=99),
        lambda r: r["replicas"][1].update(encryption_profile_digest="0" * 64),
        lambda r: r["replicas"][1]["artifacts"][0].update(manifest_digest="0" * 64),
        lambda r: r["replicas"][1].update(retention_until=None, retention_evidence_digest=None),
        lambda r: r["restoration_proofs"][1].update(source_atoms_verified=9),
        lambda r: r["restoration_proofs"][1].update(native_metadata_digest="0" * 64),
        lambda r: r["restoration_proofs"][1].update(native_metadata_verified=False),
        lambda r: r["restoration_proofs"][1].update(full_restore=False),
        lambda r: r["restoration_proofs"].pop(),
        lambda r: r["restoration_proofs"][1].update(restored_at="2026-10-02T00:00:00+00:00"),
    ],
)
def test_incomplete_or_correlated_custody_is_rejected(mutation):
    value = deepcopy(receipt())
    mutation(value)
    with pytest.raises(ValidationError):
        CustodyReceiptV2.model_validate(value)


def test_physical_and_remote_pair_uses_real_device_identity():
    value = receipt()
    value["replicas"][1].update(backend="physical", device_id="physicalDeviceIdentifier")
    assert CustodyReceiptV2.model_validate(value).replicas[1].failure_domain == "physical:physicalDeviceIdentifier"


def chunked_receipt():
    value = receipt()
    second = dict(value["captured_artifacts"][0], artifact_id="capturedArtifact02", ciphertext_digest="9" * 64)
    value["captured_artifacts"].append(second)
    for number, replica in enumerate(value["replicas"]):
        replica["artifacts"].append(
            dict(
                second,
                object_id=f"secondObject{number}",
                revision="revision1",
                readback_digest="9" * 64,
                readback_evidence_digest="e" * 64,
            )
        )
    return value


def test_multiple_chunks_in_one_manifest_are_supported():
    assert len(CustodyReceiptV2.model_validate(chunked_receipt()).captured_artifacts) == 2


def test_missing_chunk_is_not_hidden_by_manifest_coverage():
    value = chunked_receipt()
    value["replicas"][1]["artifacts"].pop()
    with pytest.raises(ValidationError, match="full ciphertext denominator"):
        CustodyReceiptV2.model_validate(value)


def test_two_replicas_cannot_agree_on_a_wrong_capture():
    value = receipt()
    for replica in value["replicas"]:
        replica["artifacts"][0].update(ciphertext_digest="9" * 64, readback_digest="9" * 64)
    with pytest.raises(ValidationError, match="immutable captured ciphertext"):
        CustodyReceiptV2.model_validate(value)
