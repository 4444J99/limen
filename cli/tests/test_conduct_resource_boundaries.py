"""Root-path parity and resource isolation at the real conduct boundary."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from limen.conduct import AuthorityEnvelopeV1, ConductConflict, ResourceClaimV1
from limen.conduct.resources import conflicting_keys, normalize_key, parse_resource, resources_overlap, sorted_claims
from test_conduct_protocol import NOW, broker_with, identity, packet, session


VECTORS = json.loads(
    (Path(__file__).resolve().parents[2] / "spec/contracts/conduct/resource-overlap-vectors.json").read_text()
)
ROOT_KEYS = [
    "path/Example/Repo/main",
    "path/Example/Repo/main/",
    "path/Example/Repo/main/.",
    "path/Example/Repo/main/src/..",
    "path/Example/Repo/main/././",
    "path/Example/Repo/main//",
]


@pytest.mark.parametrize("vector", VECTORS, ids=lambda vector: vector["id"])
def test_shared_cross_runtime_vectors(vector):
    left = ResourceClaimV1(**vector["left"])
    right = ResourceClaimV1(**vector["right"])
    assert resources_overlap(left, right) is vector["overlap"]
    assert resources_overlap(right, left) is vector["overlap"]
    assert bool(conflicting_keys([left], [right])) is vector["overlap"]


@pytest.mark.parametrize("key", ROOT_KEYS)
def test_root_remains_typed_after_model_validation_and_canonicalization(key):
    claim = ResourceClaimV1(key=key)
    normalized = normalize_key(claim.key)
    assert normalized == "path/example/repo/main"
    assert normalize_key(normalized) == normalized
    parsed = parse_resource(normalized)
    assert parsed.kind == "path"
    assert parsed.repo == "example/repo"
    assert parsed.identity == ("example/repo", "main")
    assert parsed.prefix == "/"


def test_root_aliases_share_one_claim_with_strongest_mode():
    claims = [ResourceClaimV1(key=key, mode="shared") for key in ROOT_KEYS]
    claims.append(ResourceClaimV1(key=ROOT_KEYS[0], mode="exclusive"))
    canonical = sorted_claims(claims)
    assert len(canonical) == 1
    assert canonical[0].key == "path/example/repo/main"
    assert canonical[0].mode == "exclusive"


def test_root_claim_cannot_escape_scoped_path_authority():
    broker = broker_with(session("jules"))
    request = packet(
        work_id="root-authority-rejection",
        conductor=identity("jules"),
        resource="path/example/repo/main",
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"code"}),
            repositories=frozenset({"example/repo"}),
            path_prefixes=frozenset({"src"}),
        ),
    )
    before = broker.store.snapshot()
    with pytest.raises(ConductConflict, match="path resource exceeds packet path authority"):
        broker.submit(request, now=NOW)
    assert broker.store.snapshot() == before


def test_root_reader_blocks_same_base_writer_but_not_another_repository():
    broker = broker_with(session("jules", concurrency=3))
    authority = AuthorityEnvelopeV1(
        actions=frozenset({"code"}),
        repositories=frozenset({"example/repo", "example/other"}),
        path_prefixes=frozenset({"."}),
    )
    reader = packet(
        work_id="root-reader",
        conductor=identity("jules"),
        resource="path/example/repo/main",
        effect="read",
        authority=authority,
        claims=(ResourceClaimV1(key="path/example/repo/main", mode="shared"),),
    )
    assert broker.submit(reader, now=NOW)["status"] == "reserved"
    same = packet(
        work_id="root-writer",
        conductor=identity("jules"),
        resource="path/example/repo/main/src/service.py",
        authority=authority,
    )
    assert broker.submit(same, now=NOW)["status"] == "busy"
    independent = packet(
        work_id="other-writer",
        conductor=identity("jules"),
        resource="path/example/other/main/src/service.py",
        authority=authority,
    )
    assert broker.submit(independent, now=NOW)["status"] == "reserved"


def test_large_repository_partition_has_only_one_real_conflict():
    held = [ResourceClaimV1(key=f"path/example/repo-{index}/main") for index in range(1000)]
    requested = [ResourceClaimV1(key="path/example/repo-499/main/src/service.py")]
    assert conflicting_keys(requested, held) == [
        ("path/example/repo-499/main/src/service.py", "path/example/repo-499/main")
    ]
