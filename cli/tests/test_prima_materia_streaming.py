from __future__ import annotations

import hashlib
import json
import tracemalloc

import pytest

from limen.prima_materia_store import EncryptedObjectStore, PrimaMateriaStoreError, _AesGcm
from limen.prima_materia_streaming import StreamingEncryptedObjectStore


@pytest.fixture
def store(tmp_path):
    return StreamingEncryptedObjectStore(tmp_path / "store", b"k" * 32, chunk_bytes=65536)


@pytest.mark.parametrize("size", [0, 1, 65536, 65537, 196777])
def test_existing_format_and_idempotence(store, tmp_path, size):
    source = tmp_path / "source"
    plaintext = (b"private original material\x00" * (size // 26 + 1))[:size]
    source.write_bytes(plaintext)
    ref = store.put_file(source, max_bytes=size, timeout_seconds=10)
    legacy = EncryptedObjectStore(store.root, store.key, chunk_bytes=store.chunk_bytes)
    assert legacy.restore(ref) == plaintext
    assert legacy.put(plaintext) == ref
    assert store.put_file(source, max_bytes=size, timeout_seconds=10) == ref
    target = tmp_path / "restored"
    expected = {"plaintext_bytes": size, "plaintext_sha256": hashlib.sha256(plaintext).hexdigest()}
    assert store.verify_file(ref, max_bytes=size, timeout_seconds=10) == expected
    assert store.restore_file(ref, target, max_bytes=size, timeout_seconds=10) == expected
    assert target.read_bytes() == plaintext
    assert target.stat().st_mode & 0o777 == 0o600


def test_reads_legacy_written_payload(store, tmp_path):
    ref = EncryptedObjectStore(store.root, store.key, chunk_bytes=store.chunk_bytes).put(b"legacy")
    target = tmp_path / "restored"
    store.restore_file(ref, target, max_bytes=6, timeout_seconds=10)
    assert target.read_bytes() == b"legacy"


@pytest.mark.parametrize("limit,deadline", [(-1, 10), (True, 10), (1, 0), (1, float("inf")), (1, True)])
def test_requires_explicit_finite_bounds(store, tmp_path, limit, deadline):
    with pytest.raises(PrimaMateriaStoreError):
        store.put_file(tmp_path / "absent", max_bytes=limit, timeout_seconds=deadline)


def test_source_and_restore_byte_limits(store, tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"12345")
    with pytest.raises(PrimaMateriaStoreError, match="byte-bound"):
        store.put_file(source, max_bytes=4, timeout_seconds=10)
    ref = store.put_file(source, max_bytes=5, timeout_seconds=10)
    target = tmp_path / "restore"
    with pytest.raises(PrimaMateriaStoreError, match="byte-bound"):
        store.restore_file(ref, target, max_bytes=4, timeout_seconds=10)
    assert not target.exists()
    assert not list(tmp_path.glob("*.partial"))


def test_tampered_last_chunk_never_publishes_partial_plaintext(store, tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"x" * 140000)
    ref = store.put_file(source, max_bytes=source.stat().st_size, timeout_seconds=10)
    chunk = sorted((store.root / "objects" / ref.object_id).glob("*.bin"))[-1]
    value = bytearray(chunk.read_bytes())
    value[-1] ^= 1
    chunk.write_bytes(value)
    target = tmp_path / "restore"
    with pytest.raises(PrimaMateriaStoreError, match="ciphertext-chunk-drift"):
        store.restore_file(ref, target, max_bytes=140000, timeout_seconds=10)
    assert not target.exists()
    assert not list(tmp_path.glob("*.partial"))


def test_source_change_between_hash_and_encryption_fails(store, tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_bytes(b"x" * 140000)
    original = _AesGcm.encrypt
    changed = False

    def encrypt(self, nonce, plaintext, aad):
        nonlocal changed
        if not changed:
            changed = True
            with source.open("r+b") as handle:
                handle.seek(130000)
                handle.write(b"changed")
        return original(self, nonce, plaintext, aad)

    monkeypatch.setattr(_AesGcm, "encrypt", encrypt)
    with pytest.raises(PrimaMateriaStoreError, match="source-changed"):
        store.put_file(source, max_bytes=140000, timeout_seconds=10)
    assert not (store.root / "objects").exists()
    assert not list((store.root / ".staging").iterdir())


def test_existing_destination_and_links_are_never_overwritten(store, tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"payload")
    ref = store.put_file(source, max_bytes=7, timeout_seconds=10)
    target = tmp_path / "target"
    target.write_bytes(b"keep")
    with pytest.raises(PrimaMateriaStoreError, match="not-new"):
        store.restore_file(ref, target, max_bytes=7, timeout_seconds=10)
    assert target.read_bytes() == b"keep"
    link = tmp_path / "link"
    link.symlink_to(source)
    with pytest.raises(OSError):
        store.put_file(link, max_bytes=7, timeout_seconds=10)
    with pytest.raises(PrimaMateriaStoreError, match="not-new"):
        store.restore_file(ref, link, max_bytes=7, timeout_seconds=10)
    assert source.read_bytes() == b"payload"


def test_symlinked_store_parent_is_rejected(store, tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"payload")
    ref = store.put_file(source, max_bytes=7, timeout_seconds=10)
    original = store.root / "objects"
    relocated = tmp_path / "moved-objects"
    original.rename(relocated)
    original.symlink_to(relocated, target_is_directory=True)
    with pytest.raises(PrimaMateriaStoreError, match="manifest-unavailable"):
        store.verify_file(ref, max_bytes=7, timeout_seconds=10)


def test_wrong_key_cannot_restore(store, tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"payload")
    ref = store.put_file(source, max_bytes=7, timeout_seconds=10)
    wrong = StreamingEncryptedObjectStore(store.root, b"z" * 32, chunk_bytes=65536)
    target = tmp_path / "restore"
    with pytest.raises(PrimaMateriaStoreError, match="key-capsule-invalid"):
        wrong.restore_file(ref, target, max_bytes=7, timeout_seconds=10)
    assert not target.exists()


def test_large_file_memory_does_not_scale_with_payload(store, tmp_path):
    source = tmp_path / "large"
    with source.open("wb") as handle:
        for _ in range(192):
            handle.write(b"x" * 65536)
    tracemalloc.start()
    try:
        ref = store.put_file(source, max_bytes=12 * 1024**2, timeout_seconds=30)
        store.restore_file(ref, tmp_path / "restore", max_bytes=12 * 1024**2, timeout_seconds=30)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 3 * 1024**2


def test_manifest_and_chunk_type_bounds(store, tmp_path):
    source = tmp_path / "source"
    source.write_bytes(b"payload")
    ref = store.put_file(source, max_bytes=7, timeout_seconds=10)
    path = store.root / "objects" / ref.object_id / "manifest.json"
    path.write_bytes(b"not JSON")
    with pytest.raises(PrimaMateriaStoreError, match="manifest-invalid"):
        store.verify_file(ref, max_bytes=7, timeout_seconds=10)
    path.write_text(json.dumps({}))
    with pytest.raises(PrimaMateriaStoreError, match="manifest-digest-mismatch"):
        store.verify_file(ref, max_bytes=7, timeout_seconds=10)
