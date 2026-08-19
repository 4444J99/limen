from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
import rfc8785
from limen.prima_materia import SourceAdapterV1
from limen.prima_materia_store import (
    EncryptedObjectStore,
    PrimaMateriaStoreError,
    SourceRegistry,
    load_key,
)

DIGEST = "a" * 64


def _adapter(adapter_id: str, source_id: str) -> SourceAdapterV1:
    return SourceAdapterV1(
        adapter_id=adapter_id,
        source_id=source_id,
        owner_ref=f"owner:{adapter_id}",
        source_native_acquisition="source-owned cursor stream",
        cursor_schema_digest=DIGEST,
        completeness_predicate="cursor exhausted",
        privacy_transform_digest=DIGEST,
        claim_recipe=f"claim-recipe-{source_id}",
        recipe_version="recipe-v1",
        custody_target_refs=("archive", "recovery"),
        restoration_predicate="both copies restore",
    )


def test_store_encrypts_before_disk_and_restores_idempotently(tmp_path: Path) -> None:
    plaintext = b"private prima materia payload that must never be staged"
    store = EncryptedObjectStore(tmp_path / "store", b"k" * 32, chunk_bytes=64 * 1024)

    first = store.put(plaintext)
    second = store.put(plaintext)

    assert second == first
    assert store.restore(first) == plaintext
    stored = [path.read_bytes() for path in (tmp_path / "store").rglob("*") if path.is_file()]
    assert stored
    assert all(plaintext not in payload for payload in stored)
    assert first.object_id not in plaintext.decode()


def test_store_tamper_and_interrupted_staging_fail_safe(tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    interrupted = store_root / ".staging" / "interrupted"
    interrupted.mkdir(parents=True)
    store_root.chmod(0o700)
    store = EncryptedObjectStore(store_root, b"z" * 32, chunk_bytes=64 * 1024)
    ref = store.put(b"payload")

    assert interrupted.exists()
    chunk = next((store_root / "objects" / ref.object_id).glob("*.bin"))
    payload = bytearray(chunk.read_bytes())
    payload[-1] ^= 1
    chunk.write_bytes(bytes(payload))

    with pytest.raises(PrimaMateriaStoreError, match="ciphertext-chunk-drift"):
        store.restore(ref)


def test_store_rejects_rehashed_but_unauthenticated_ciphertext(
    tmp_path: Path,
) -> None:
    store = EncryptedObjectStore(
        tmp_path / "store",
        b"a" * 32,
        chunk_bytes=64 * 1024,
    )
    ref = store.put(b"authenticated payload")
    object_root = store.root / "objects" / ref.object_id
    manifest_path = object_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_chunk = next(object_root.glob("*.bin"))
    ciphertext = bytearray(old_chunk.read_bytes())
    ciphertext[0] ^= 1
    ciphertext_bytes = bytes(ciphertext)
    new_digest = hashlib.sha256(ciphertext_bytes).hexdigest()
    new_chunk = object_root / f"00000000-{new_digest}.bin"
    new_chunk.write_bytes(ciphertext_bytes)
    old_chunk.unlink()
    manifest["chunks"][0]["ciphertext_sha256"] = new_digest
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    forged_ref = ref.model_copy(
        update={
            "ciphertext_sha256": new_digest,
            "chunk_manifest_digest": hashlib.sha256(rfc8785.dumps(manifest)).hexdigest(),
        }
    )

    with pytest.raises(
        PrimaMateriaStoreError,
        match="ciphertext-authentication-failed",
    ):
        store.restore(forged_ref)


def test_key_file_must_be_private_and_256_bit(tmp_path: Path) -> None:
    key = tmp_path / "key"
    key.write_bytes(b"k" * 32)
    key.chmod(0o644)

    with pytest.raises(PrimaMateriaStoreError, match="key-file-not-private"):
        load_key(key)

    key.chmod(0o600)
    assert load_key(key) == b"k" * 32


def test_dynamic_source_registry_is_order_independent_and_keeps_unknown_debt() -> None:
    first = _adapter("adapter-z", "sourceIdentifierB2")
    second = _adapter("adapter-a", "sourceIdentifierA1")
    missing = "sourceIdentifierC3"

    left = SourceRegistry.from_adapters((first, second))
    right = SourceRegistry.from_adapters((second, first))
    projection = left.public_projection((first.source_id, second.source_id, missing))

    assert left.registry_digest == right.registry_digest
    assert projection["adapter_count"] == 2
    assert projection["observed_source_count"] == 3
    assert projection["missing_adapter_count"] == 1
    encoded = json.dumps(projection, sort_keys=True)
    assert missing not in encoded
    assert first.source_id not in encoded


def test_source_registry_load_rejects_duplicate_source(tmp_path: Path) -> None:
    adapter = _adapter("adapter-a", "sourceIdentifierA1")
    duplicate = adapter.model_copy(update={"adapter_id": "adapter-b"})
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "schema": "limen.source_registry.v1",
                "adapters": [
                    adapter.model_dump(mode="json"),
                    duplicate.model_dump(mode="json"),
                ],
            }
        ),
        encoding="utf-8",
    )
    os.chmod(registry, 0o600)

    with pytest.raises(PrimaMateriaStoreError, match="duplicate-source-id"):
        SourceRegistry.load(registry)
