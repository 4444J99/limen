"""Bounded file IO for the existing authenticated encrypted-object format.

Publication, independent key recovery, native restoration and retirement are
separate predicates. This module never uploads or removes source files.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import shutil
import stat
import time
from collections.abc import Iterator
from pathlib import Path

import rfc8785

from limen.prima_materia import EncryptedPayloadRefV1
from limen.prima_materia_store import (
    STORE_SCHEMA,
    EncryptedObjectStore,
    PrimaMateriaStoreError,
    _AesGcm,
    _AuthenticationError,
    _atomic_bytes,
    _b64url,
    _canonical_digest,
    _decode_b64url,
    _hmac,
)


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_bounded(path: Path, limit: int) -> bytes:
    """Never follow a final link or allocate from an unchecked file size."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise PrimaMateriaStoreError("stored-file-type-or-byte-bound-invalid")
            value = stream.read(before.st_size + 1)
            if len(value) != before.st_size or _identity(before) != _identity(os.fstat(stream.fileno())):
                raise PrimaMateriaStoreError("stored-file-changed-or-byte-bound-exceeded")
            return value
    except OSError as exc:
        raise PrimaMateriaStoreError("stored-file-unavailable") from exc


class StreamingEncryptedObjectStore(EncryptedObjectStore):
    """Same object identities and manifests; at most one plaintext chunk in IO."""

    def _limits(self, max_bytes: int, timeout_seconds: float) -> float:
        if type(max_bytes) is not int or max_bytes < 0:
            raise PrimaMateriaStoreError("explicit-byte-bound-required")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise PrimaMateriaStoreError("finite-deadline-required")
        return time.monotonic() + timeout_seconds

    @staticmethod
    def _check(deadline: float) -> None:
        if time.monotonic() >= deadline:
            raise PrimaMateriaStoreError("streaming-deadline-exceeded")

    def _plaintext(self, ref: EncryptedPayloadRefV1, *, max_bytes: int, deadline: float) -> Iterator[bytes]:
        root = self._object_dir(ref.object_id)
        path = root / "manifest.json"
        if root.is_symlink() or root.parent.is_symlink() or root.resolve() != root:
            raise PrimaMateriaStoreError("manifest-unavailable")
        self._check(deadline)
        try:
            manifest = json.loads(_read_bounded(path, 32 * 1024**2))
        except (ValueError, UnicodeError) as exc:
            raise PrimaMateriaStoreError("manifest-invalid") from exc
        if not isinstance(manifest, dict) or _canonical_digest(manifest) != ref.chunk_manifest_digest:
            raise PrimaMateriaStoreError("manifest-digest-mismatch")
        if (
            manifest.get("schema") != STORE_SCHEMA
            or manifest.get("object_id") != ref.object_id
            or manifest.get("encryption_profile") != self.profile
            or manifest.get("encryption_profile_digest") != ref.encryption_profile_digest
            or ref.encryption_profile_digest != self.profile_digest
        ):
            raise PrimaMateriaStoreError("manifest-identity-mismatch")
        size = manifest.get("plaintext_bytes")
        chunks = manifest.get("chunks")
        if type(size) is not int or not 0 <= size <= max_bytes:
            raise PrimaMateriaStoreError("plaintext-byte-bound-exceeded")
        if not isinstance(chunks, list) or len(chunks) != max(1, (size + self.chunk_bytes - 1) // self.chunk_bytes):
            raise PrimaMateriaStoreError("manifest-chunks-invalid")
        if len(chunks) > 65536:
            raise PrimaMateriaStoreError("manifest-chunk-bound-exceeded")
        try:
            nonce = _hmac(self.key, b"key-capsule-nonce", ref.object_id.encode())[:12]
            key = _AesGcm(self.key).decrypt(
                nonce, _decode_b64url(manifest["object_key_capsule"]), ref.object_id.encode()
            )
        except (_AuthenticationError, ValueError, KeyError, TypeError) as exc:
            raise PrimaMateriaStoreError("manifest-key-capsule-invalid") from exc
        aes = _AesGcm(key)
        plain_hash, cipher_hash = hashlib.sha256(), hashlib.sha256()
        plain_size = cipher_size = 0
        for index, metadata in enumerate(chunks):
            self._check(deadline)
            if not isinstance(metadata, dict) or type(metadata.get("index")) is not int or metadata["index"] != index:
                raise PrimaMateriaStoreError("manifest-chunk-order-invalid")
            digest = metadata.get("ciphertext_sha256")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise PrimaMateriaStoreError("manifest-chunk-digest-invalid")
            chunk_path = root / f"{index:08d}-{digest}.bin"
            ciphertext = _read_bounded(chunk_path, self.chunk_bytes + 16)
            if len(ciphertext) != metadata.get("ciphertext_bytes") or hashlib.sha256(ciphertext).hexdigest() != digest:
                raise PrimaMateriaStoreError("ciphertext-chunk-drift")
            aad = rfc8785.dumps(
                {
                    "schema": STORE_SCHEMA,
                    "object_id": ref.object_id,
                    "index": index,
                    "total": len(chunks),
                    "profile": self.profile_digest,
                }
            )
            try:
                plaintext = aes.decrypt(_decode_b64url(metadata["nonce"]), ciphertext, aad)
            except (_AuthenticationError, ValueError, KeyError, TypeError) as exc:
                raise PrimaMateriaStoreError("ciphertext-authentication-failed") from exc
            expected_size = min(self.chunk_bytes, size - plain_size)
            if len(plaintext) != expected_size or len(plaintext) != metadata.get("plaintext_bytes"):
                raise PrimaMateriaStoreError("plaintext-chunk-size-invalid")
            plain_hash.update(plaintext)
            cipher_hash.update(ciphertext)
            plain_size += len(plaintext)
            cipher_size += len(ciphertext)
            yield plaintext
        digest = plain_hash.digest()
        if (
            plain_size != size
            or cipher_size != ref.ciphertext_bytes
            or cipher_hash.hexdigest() != ref.ciphertext_sha256
            or _b64url(_hmac(self.key, b"object-id", digest)) != ref.object_id
            or _b64url(_hmac(self.key, b"content-auth", digest)) != manifest.get("content_auth")
        ):
            raise PrimaMateriaStoreError("streaming-content-identity-mismatch")
        self._check(deadline)

    def verify_file(self, ref: EncryptedPayloadRefV1, *, max_bytes: int, timeout_seconds: float) -> dict[str, int | str]:
        deadline = self._limits(max_bytes, timeout_seconds)
        digest, size = hashlib.sha256(), 0
        for plaintext in self._plaintext(ref, max_bytes=max_bytes, deadline=deadline):
            digest.update(plaintext)
            size += len(plaintext)
        return {"plaintext_bytes": size, "plaintext_sha256": digest.hexdigest()}

    def put_file(self, source: Path, *, max_bytes: int, timeout_seconds: float) -> EncryptedPayloadRefV1:
        deadline = self._limits(max_bytes, timeout_seconds)
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            initial = os.fstat(stream.fileno())
            if not stat.S_ISREG(initial.st_mode) or initial.st_size > max_bytes:
                raise PrimaMateriaStoreError("source-type-or-byte-bound-invalid")
            total = max(1, (initial.st_size + self.chunk_bytes - 1) // self.chunk_bytes)
            if total > 65536:
                raise PrimaMateriaStoreError("manifest-chunk-bound-exceeded")
            plain_hash = hashlib.sha256()
            for _ in range(total):
                self._check(deadline)
                plain_hash.update(stream.read(self.chunk_bytes))
            if stream.read(1) or _identity(initial) != _identity(os.fstat(stream.fileno())):
                raise PrimaMateriaStoreError("source-changed-during-capture")
            digest = plain_hash.digest()
            object_id = _b64url(_hmac(self.key, b"object-id", digest))
            key = _hmac(self.key, b"object-key", digest)
            final = self._object_dir(object_id)
            staging_root = self.root / ".staging"
            if staging_root.is_symlink() or (self.root / "objects").is_symlink():
                raise PrimaMateriaStoreError("store-parent-indirection")
            staging_root.mkdir(mode=0o700, exist_ok=True)
            staging = staging_root / f"{object_id}.{os.getpid()}.{secrets.token_hex(8)}"
            staging.mkdir(mode=0o700)
            metadata, cipher_hash, cipher_bytes = [], hashlib.sha256(), 0
            stream.seek(0)
            aes = _AesGcm(key)
            try:
                second_hash = hashlib.sha256()
                for index in range(total):
                    self._check(deadline)
                    plaintext = stream.read(self.chunk_bytes)
                    second_hash.update(plaintext)
                    nonce = _hmac(key, b"nonce", index.to_bytes(8, "big"))[:12]
                    aad = rfc8785.dumps(
                        {
                            "schema": STORE_SCHEMA,
                            "object_id": object_id,
                            "index": index,
                            "total": total,
                            "profile": self.profile_digest,
                        }
                    )
                    ciphertext = aes.encrypt(nonce, plaintext, aad)
                    hashed = hashlib.sha256(ciphertext).hexdigest()
                    cipher_hash.update(ciphertext)
                    cipher_bytes += len(ciphertext)
                    metadata.append(
                        {
                            "index": index,
                            "ciphertext_sha256": hashed,
                            "ciphertext_bytes": len(ciphertext),
                            "plaintext_bytes": len(plaintext),
                            "nonce": _b64url(nonce),
                        }
                    )
                    _atomic_bytes(staging / f"{index:08d}-{hashed}.bin", ciphertext)
                if (
                    stream.read(1)
                    or second_hash.digest() != digest
                    or _identity(initial) != _identity(os.fstat(stream.fileno()))
                ):
                    raise PrimaMateriaStoreError("source-changed-during-capture")
                if _identity(initial) != _identity(source.lstat()):
                    raise PrimaMateriaStoreError("source-path-changed-during-capture")
                key_nonce = _hmac(self.key, b"key-capsule-nonce", object_id.encode())[:12]
                capsule = _AesGcm(self.key).encrypt(key_nonce, key, object_id.encode())
                manifest = {
                    "schema": STORE_SCHEMA,
                    "object_id": object_id,
                    "encryption_profile": self.profile,
                    "encryption_profile_digest": self.profile_digest,
                    "content_auth": _b64url(_hmac(self.key, b"content-auth", digest)),
                    "object_key_capsule": _b64url(capsule),
                    "plaintext_bytes": initial.st_size,
                    "chunks": metadata,
                }
                _atomic_bytes(
                    staging / "manifest.json", json.dumps(manifest, sort_keys=True, indent=2).encode() + b"\n"
                )
                ref = EncryptedPayloadRefV1(
                    object_id=object_id,
                    ciphertext_sha256=cipher_hash.hexdigest(),
                    encryption_profile_digest=self.profile_digest,
                    chunk_manifest_digest=_canonical_digest(manifest),
                    ciphertext_bytes=cipher_bytes,
                )
                final.parent.mkdir(mode=0o700, exist_ok=True)
                if not final.exists():
                    try:
                        os.rename(staging, final)
                    except OSError:
                        if not final.exists():
                            raise
                directory = os.open(final.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                verified_hash = hashlib.sha256()
                for part in self._plaintext(ref, max_bytes=max_bytes, deadline=deadline):
                    verified_hash.update(part)
                if verified_hash.digest() != digest:
                    raise PrimaMateriaStoreError("post-write-restore-failed")
                return ref
            finally:
                if staging.exists():
                    shutil.rmtree(staging)

    def restore_file(
        self, ref: EncryptedPayloadRefV1, destination: Path, *, max_bytes: int, timeout_seconds: float
    ) -> dict[str, int | str]:
        deadline = self._limits(max_bytes, timeout_seconds)
        destination = destination.absolute()
        if destination.exists() or destination.is_symlink() or destination.parent.resolve() != destination.parent:
            raise PrimaMateriaStoreError("restore-destination-not-new-canonical-path")
        staging = destination.with_name(f".{destination.name}.{secrets.token_hex(8)}.partial")
        size, digest = 0, hashlib.sha256()
        try:
            descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                for plaintext in self._plaintext(ref, max_bytes=max_bytes, deadline=deadline):
                    output.write(plaintext)
                    size += len(plaintext)
                    digest.update(plaintext)
                output.flush()
                os.fsync(output.fileno())
            # link is exclusive: a concurrent destination is never overwritten.
            os.link(staging, destination, follow_symlinks=False)
            return {"plaintext_bytes": size, "plaintext_sha256": digest.hexdigest()}
        finally:
            if staging.exists():
                staging.unlink()
