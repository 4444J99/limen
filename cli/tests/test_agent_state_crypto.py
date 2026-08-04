from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from limen.agent_state import crypto
from limen.agent_state.atomize import canonical_bytes

KEY = "test-key-that-never-leaves-this-process"


def _line(value: str) -> tuple[dict[str, object], bytes]:
    record = {"kind": "test", "value": value}
    body = canonical_bytes(record)
    envelope = {"atom_sha256": hashlib.sha256(body).hexdigest(), "record": record}
    return envelope, canonical_bytes(envelope) + b"\n"


def test_atom_packs_round_trip_and_stay_bounded(tmp_path: Path) -> None:
    packer = crypto.EncryptedAtomPacker(tmp_path, KEY, pack_plaintext_limit=140, chunk_limit=64)
    logical = hashlib.sha256()
    for value in ("alpha" * 20, "beta" * 20, "gamma" * 20):
        envelope, line = _line(value)
        logical.update(line)
        packer(envelope, line)
    packs = packer.close()

    assert len(packs) == 3
    assert all(chunk.bytes <= 64 for pack in packs for chunk in pack.chunks)
    assert crypto.verify_atom_packs(packs, tmp_path, KEY, logical_sha256=logical.hexdigest(), sample=True).passed
    records: list[dict[str, object]] = []
    full = crypto.verify_atom_packs(
        packs,
        tmp_path,
        KEY,
        logical_sha256=logical.hexdigest(),
        record_consumer=records.append,
    )
    assert full.passed
    assert full.atoms_verified == 3
    assert [record["value"] for record in records] == ["alpha" * 20, "beta" * 20, "gamma" * 20]
    with pytest.raises(ValueError, match="incomplete atom stream"):
        crypto.verify_atom_packs(
            packs,
            tmp_path,
            KEY,
            logical_sha256=logical.hexdigest(),
            sample=True,
            record_consumer=records.append,
        )


def test_corrupt_ciphertext_fails_restore(tmp_path: Path) -> None:
    packer = crypto.EncryptedAtomPacker(tmp_path, KEY, chunk_limit=1024)
    envelope, line = _line("private")
    packer(envelope, line)
    packs = packer.close()
    path = tmp_path / packs[0].chunks[0].path
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    path.write_bytes(data)

    proof = crypto.verify_atom_packs(packs, tmp_path, KEY, logical_sha256=hashlib.sha256(line).hexdigest())
    assert not proof.passed
    assert "hash verification" in proof.detail


def test_exact_file_ciphertext_restores_source_hash(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    source.write_bytes((b"private-state\x00" * 1000) + bytes(range(256)))
    target = tmp_path / "external"
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    chunks = crypto.encrypt_file(source, target, "source.db", KEY, chunk_limit=257)

    assert len(chunks) > 1
    assert all(chunk.bytes <= 257 for chunk in chunks)
    proof = crypto.verify_encrypted_file(chunks, target, KEY, source_sha256=source_hash)
    assert proof.passed
    assert proof.source_sha256 == source_hash


def test_interrupted_encryption_removes_partial_ciphertext(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    source.write_bytes(b"x" * (5 * 1024 * 1024))
    original = crypto._EncryptPipe.write
    writes = 0

    def interrupted(self, value: bytes) -> int:
        nonlocal writes
        writes += 1
        if writes > 1:
            raise OSError("simulated interruption")
        return original(self, value)

    monkeypatch.setattr(crypto._EncryptPipe, "write", interrupted)
    with pytest.raises(OSError, match="simulated interruption"):
        crypto.encrypt_file(source, tmp_path / "out", "source", KEY, chunk_limit=1024)
    assert not list((tmp_path / "out").glob("*.enc.part-*"))


def test_missing_key_fails_without_creating_one(monkeypatch) -> None:
    class Result:
        returncode = 44
        stdout = ""

    monkeypatch.setattr(crypto.subprocess, "run", lambda *args, **kwargs: Result())
    with pytest.raises(crypto.CryptoError, match="Keychain key unavailable"):
        crypto.keychain_key("missing-service")
