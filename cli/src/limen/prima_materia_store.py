"""Encrypted content-addressed custody and dynamic source registration.

The store writes ciphertext first and never stages plaintext on disk.  Object
identities are keyed HMACs rather than public plaintext hashes.  Deterministic
per-object keys and nonces make repeated storage idempotent without reusing an
AES-GCM key/nonce pair across different plaintext objects.
"""

from __future__ import annotations

import base64
import ctypes
import ctypes.util
import hashlib
import hmac
import json
import os
import platform
import secrets
import shutil
import stat
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import rfc8785

from limen.prima_materia import (
    EncryptedPayloadRefV1,
    SourceAdapterV1,
    SourceCoverageV1,
)

STORE_SCHEMA = "limen.encrypted_object_manifest.v1"
REGISTRY_SCHEMA = "limen.source_registry.v1"
DEFAULT_CHUNK_BYTES = 4 * 1024 * 1024
MIN_CHUNK_BYTES = 64 * 1024
MAX_CHUNK_BYTES = 64 * 1024 * 1024
AES_GCM_TAG_BYTES = 16
EVP_CTRL_AEAD_SET_IVLEN = 0x9
EVP_CTRL_AEAD_GET_TAG = 0x10
EVP_CTRL_AEAD_SET_TAG = 0x11


class PrimaMateriaStoreError(RuntimeError):
    """Encrypted custody or registry validation failed closed."""


class _AuthenticationError(RuntimeError):
    """Authenticated decryption rejected the ciphertext."""


@lru_cache(maxsize=1)
def _libcrypto() -> ctypes.CDLL:
    """Load a system OpenSSL/LibreSSL EVP implementation without Python wheels."""

    candidates: list[str] = []
    if platform.system() == "Darwin":
        candidates.extend(
            [
                "/opt/homebrew/opt/openssl@3/lib/libcrypto.dylib",
                "/usr/local/opt/openssl@3/lib/libcrypto.dylib",
            ]
        )
    discovered = ctypes.util.find_library("crypto")
    if discovered and not (platform.system() == "Darwin" and discovered.startswith("/usr/lib/")):
        candidates.append(discovered)
    for candidate in candidates:
        try:
            library = ctypes.CDLL(candidate)
        except OSError:
            continue
        required = (
            "EVP_CIPHER_CTX_new",
            "EVP_CIPHER_CTX_free",
            "EVP_aes_256_gcm",
            "EVP_EncryptInit_ex",
            "EVP_EncryptUpdate",
            "EVP_EncryptFinal_ex",
            "EVP_DecryptInit_ex",
            "EVP_DecryptUpdate",
            "EVP_DecryptFinal_ex",
            "EVP_CIPHER_CTX_ctrl",
        )
        if not all(hasattr(library, symbol) for symbol in required):
            continue
        library.EVP_CIPHER_CTX_new.restype = ctypes.c_void_p
        library.EVP_CIPHER_CTX_free.argtypes = [ctypes.c_void_p]
        library.EVP_aes_256_gcm.restype = ctypes.c_void_p
        for name in ("EVP_EncryptInit_ex", "EVP_DecryptInit_ex"):
            function = getattr(library, name)
            function.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_void_p,
            ]
            function.restype = ctypes.c_int
        for name in ("EVP_EncryptUpdate", "EVP_DecryptUpdate"):
            function = getattr(library, name)
            function.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_int),
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            function.restype = ctypes.c_int
        for name in ("EVP_EncryptFinal_ex", "EVP_DecryptFinal_ex"):
            function = getattr(library, name)
            function.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_int),
            ]
            function.restype = ctypes.c_int
        library.EVP_CIPHER_CTX_ctrl.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        library.EVP_CIPHER_CTX_ctrl.restype = ctypes.c_int
        return library
    raise PrimaMateriaStoreError("authenticated-encryption-unavailable")


def _buffer(value: bytes) -> ctypes.Array[ctypes.c_ubyte]:
    return (ctypes.c_ubyte * len(value)).from_buffer_copy(value)


class _AesGcm:
    """Small EVP-backed AES-256-GCM wrapper with no secret-bearing argv."""

    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise PrimaMateriaStoreError("key-must-be-256-bit")
        self.key = key
        self.library = _libcrypto()

    def _context(self) -> ctypes.c_void_p:
        context = self.library.EVP_CIPHER_CTX_new()
        if not context:
            raise PrimaMateriaStoreError("authenticated-encryption-context-failed")
        return ctypes.c_void_p(context)

    def encrypt(self, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
        if len(nonce) != 12:
            raise PrimaMateriaStoreError("aes-gcm-nonce-must-be-96-bit")
        context = self._context()
        output = (ctypes.c_ubyte * max(1, len(plaintext) + AES_GCM_TAG_BYTES))()
        tag = (ctypes.c_ubyte * AES_GCM_TAG_BYTES)()
        written = ctypes.c_int()
        final_written = ctypes.c_int()
        key_buffer = _buffer(self.key)
        nonce_buffer = _buffer(nonce)
        aad_buffer = _buffer(aad)
        plaintext_buffer = _buffer(plaintext)
        try:
            cipher = self.library.EVP_aes_256_gcm()
            checks = (
                self.library.EVP_EncryptInit_ex(
                    context,
                    cipher,
                    None,
                    None,
                    None,
                ),
                self.library.EVP_CIPHER_CTX_ctrl(
                    context,
                    EVP_CTRL_AEAD_SET_IVLEN,
                    len(nonce),
                    None,
                ),
                self.library.EVP_EncryptInit_ex(
                    context,
                    None,
                    None,
                    key_buffer,
                    nonce_buffer,
                ),
                self.library.EVP_EncryptUpdate(
                    context,
                    None,
                    ctypes.byref(written),
                    aad_buffer,
                    len(aad),
                ),
                self.library.EVP_EncryptUpdate(
                    context,
                    output,
                    ctypes.byref(written),
                    plaintext_buffer,
                    len(plaintext),
                ),
                self.library.EVP_EncryptFinal_ex(
                    context,
                    ctypes.byref(output, written.value),
                    ctypes.byref(final_written),
                ),
                self.library.EVP_CIPHER_CTX_ctrl(
                    context,
                    EVP_CTRL_AEAD_GET_TAG,
                    AES_GCM_TAG_BYTES,
                    tag,
                ),
            )
            if any(result != 1 for result in checks):
                raise PrimaMateriaStoreError("authenticated-encryption-failed")
            length = written.value + final_written.value
            return bytes(output[:length]) + bytes(tag)
        finally:
            self.library.EVP_CIPHER_CTX_free(context)

    def decrypt(self, nonce: bytes, ciphertext_and_tag: bytes, aad: bytes) -> bytes:
        if len(nonce) != 12 or len(ciphertext_and_tag) < AES_GCM_TAG_BYTES:
            raise _AuthenticationError("ciphertext-authentication-failed")
        ciphertext = ciphertext_and_tag[:-AES_GCM_TAG_BYTES]
        tag = ciphertext_and_tag[-AES_GCM_TAG_BYTES:]
        context = self._context()
        output = (ctypes.c_ubyte * max(1, len(ciphertext)))()
        written = ctypes.c_int()
        final_written = ctypes.c_int()
        key_buffer = _buffer(self.key)
        nonce_buffer = _buffer(nonce)
        aad_buffer = _buffer(aad)
        ciphertext_buffer = _buffer(ciphertext)
        tag_buffer = _buffer(tag)
        try:
            cipher = self.library.EVP_aes_256_gcm()
            checks = (
                self.library.EVP_DecryptInit_ex(
                    context,
                    cipher,
                    None,
                    None,
                    None,
                ),
                self.library.EVP_CIPHER_CTX_ctrl(
                    context,
                    EVP_CTRL_AEAD_SET_IVLEN,
                    len(nonce),
                    None,
                ),
                self.library.EVP_DecryptInit_ex(
                    context,
                    None,
                    None,
                    key_buffer,
                    nonce_buffer,
                ),
                self.library.EVP_DecryptUpdate(
                    context,
                    None,
                    ctypes.byref(written),
                    aad_buffer,
                    len(aad),
                ),
                self.library.EVP_DecryptUpdate(
                    context,
                    output,
                    ctypes.byref(written),
                    ciphertext_buffer,
                    len(ciphertext),
                ),
                self.library.EVP_CIPHER_CTX_ctrl(
                    context,
                    EVP_CTRL_AEAD_SET_TAG,
                    AES_GCM_TAG_BYTES,
                    tag_buffer,
                ),
            )
            if any(result != 1 for result in checks):
                raise _AuthenticationError("ciphertext-authentication-failed")
            if (
                self.library.EVP_DecryptFinal_ex(
                    context,
                    ctypes.byref(output, written.value),
                    ctypes.byref(final_written),
                )
                != 1
            ):
                raise _AuthenticationError("ciphertext-authentication-failed")
            length = written.value + final_written.value
            return bytes(output[:length])
        finally:
            self.library.EVP_CIPHER_CTX_free(context)


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise PrimaMateriaStoreError("invalid-base64url") from exc


def load_key(path: Path) -> bytes:
    """Load a private 256-bit key from a mode-private raw/base64url file."""

    try:
        info = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise PrimaMateriaStoreError("key-file-not-regular")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise PrimaMateriaStoreError("key-file-not-private")
        raw = path.read_bytes()
    except OSError as exc:
        raise PrimaMateriaStoreError("key-file-unavailable") from exc
    if len(raw) == 32:
        return raw
    try:
        decoded = _decode_b64url(raw.decode("ascii").strip())
    except UnicodeDecodeError as exc:
        raise PrimaMateriaStoreError("key-file-invalid") from exc
    if len(decoded) != 32:
        raise PrimaMateriaStoreError("key-must-be-256-bit")
    return decoded


def _atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            mode,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, mode)
    finally:
        temporary.unlink(missing_ok=True)


def _hmac(key: bytes, label: bytes, payload: bytes) -> bytes:
    return hmac.new(key, label + b"\0" + payload, hashlib.sha256).digest()


class EncryptedObjectStore:
    def __init__(
        self,
        root: Path,
        key: bytes,
        *,
        chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    ) -> None:
        if len(key) != 32:
            raise PrimaMateriaStoreError("key-must-be-256-bit")
        if not MIN_CHUNK_BYTES <= chunk_bytes <= MAX_CHUNK_BYTES:
            raise PrimaMateriaStoreError("chunk-size-out-of-range")
        candidate = root.expanduser().absolute()
        try:
            candidate.mkdir(parents=True, exist_ok=True, mode=0o700)
            info = candidate.lstat()
        except OSError as exc:
            raise PrimaMateriaStoreError("store-root-unavailable") from exc
        if candidate.is_symlink() or not stat.S_ISDIR(info.st_mode):
            raise PrimaMateriaStoreError("store-root-not-directory")
        if stat.S_IMODE(info.st_mode) & 0o077:
            raise PrimaMateriaStoreError("store-root-not-private")
        self.root = candidate.resolve(strict=True)
        self.key = key
        self.chunk_bytes = chunk_bytes
        self.profile = {
            "schema": "limen.encryption_profile.v1",
            "algorithm": "AES-256-GCM",
            "implementation_contract": "system-libcrypto-EVP",
            "object_key_derivation": "HMAC-SHA256-object-v1",
            "nonce_derivation": "HMAC-SHA256-index-v1",
            "object_identity": "keyed-plaintext-digest-v1",
            "chunk_bytes": chunk_bytes,
        }
        self.profile_digest = _canonical_digest(self.profile)

    def _identities(self, plaintext: bytes) -> tuple[str, bytes, bytes]:
        digest = hashlib.sha256(plaintext).digest()
        object_id = _b64url(_hmac(self.key, b"object-id", digest))
        object_key = _hmac(self.key, b"object-key", digest)
        content_auth = _b64url(_hmac(self.key, b"content-auth", digest))
        return object_id, object_key, content_auth.encode("ascii")

    def _object_dir(self, object_id: str) -> Path:
        if not object_id or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
            for character in object_id
        ):
            raise PrimaMateriaStoreError("object-id-invalid")
        return self.root / "objects" / object_id

    def put(self, plaintext: bytes) -> EncryptedPayloadRefV1:
        if not isinstance(plaintext, bytes):
            raise PrimaMateriaStoreError("plaintext-must-be-bytes")
        object_id, object_key, content_auth = self._identities(plaintext)
        chunks: list[tuple[dict[str, Any], bytes]] = []
        ciphertext_digest = hashlib.sha256()
        aes = _AesGcm(object_key)
        total = max(1, (len(plaintext) + self.chunk_bytes - 1) // self.chunk_bytes)
        for index in range(total):
            chunk = plaintext[index * self.chunk_bytes : (index + 1) * self.chunk_bytes]
            nonce = _hmac(
                object_key,
                b"nonce",
                index.to_bytes(8, "big"),
            )[:12]
            aad = rfc8785.dumps(
                {
                    "schema": STORE_SCHEMA,
                    "object_id": object_id,
                    "index": index,
                    "total": total,
                    "profile": self.profile_digest,
                }
            )
            ciphertext = aes.encrypt(nonce, chunk, aad)
            ciphertext_sha256 = hashlib.sha256(ciphertext).hexdigest()
            ciphertext_digest.update(ciphertext)
            chunks.append(
                (
                    {
                        "index": index,
                        "ciphertext_sha256": ciphertext_sha256,
                        "ciphertext_bytes": len(ciphertext),
                        "plaintext_bytes": len(chunk),
                        "nonce": _b64url(nonce),
                    },
                    ciphertext,
                )
            )
        key_nonce = _hmac(
            self.key,
            b"key-capsule-nonce",
            object_id.encode(),
        )[:12]
        object_key_capsule = _AesGcm(self.key).encrypt(
            key_nonce,
            object_key,
            object_id.encode(),
        )
        manifest_payload = {
            "schema": STORE_SCHEMA,
            "object_id": object_id,
            "encryption_profile": self.profile,
            "encryption_profile_digest": self.profile_digest,
            "content_auth": content_auth.decode("ascii"),
            "object_key_capsule": _b64url(object_key_capsule),
            "plaintext_bytes": len(plaintext),
            "chunks": [metadata for metadata, _ciphertext in chunks],
        }
        manifest_digest = _canonical_digest(manifest_payload)
        ref = EncryptedPayloadRefV1(
            object_id=object_id,
            ciphertext_sha256=ciphertext_digest.hexdigest(),
            encryption_profile_digest=self.profile_digest,
            chunk_manifest_digest=manifest_digest,
            ciphertext_bytes=sum(len(ciphertext) for _metadata, ciphertext in chunks),
        )
        final = self._object_dir(object_id)
        if final.exists():
            if self.restore(ref) != plaintext:
                raise PrimaMateriaStoreError("existing-object-mismatch")
            return ref

        staging_root = self.root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging = staging_root / f"{object_id}.{os.getpid()}.{secrets.token_hex(8)}"
        staging.mkdir(mode=0o700)
        try:
            for metadata, ciphertext in chunks:
                name = f"{metadata['index']:08d}-{metadata['ciphertext_sha256']}.bin"
                _atomic_bytes(staging / name, ciphertext)
            _atomic_bytes(
                staging / "manifest.json",
                json.dumps(
                    manifest_payload,
                    indent=2,
                    sort_keys=True,
                ).encode("utf-8")
                + b"\n",
            )
            final.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                os.rename(staging, final)
            except OSError:
                if not final.exists():
                    raise
                if self.restore(ref) != plaintext:
                    raise PrimaMateriaStoreError("concurrent-object-mismatch") from None
            parent_descriptor = os.open(final.parent, os.O_RDONLY)
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        if self.restore(ref) != plaintext:
            raise PrimaMateriaStoreError("post-write-restore-failed")
        return ref

    def restore(self, ref: EncryptedPayloadRefV1) -> bytes:
        object_root = self._object_dir(ref.object_id)
        try:
            manifest_path = object_root / "manifest.json"
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise PrimaMateriaStoreError("manifest-unavailable")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PrimaMateriaStoreError("manifest-unavailable") from exc
        if not isinstance(manifest, dict) or _canonical_digest(manifest) != ref.chunk_manifest_digest:
            raise PrimaMateriaStoreError("manifest-digest-mismatch")
        if (
            manifest.get("schema") != STORE_SCHEMA
            or manifest.get("object_id") != ref.object_id
            or manifest.get("encryption_profile") != self.profile
            or manifest.get("encryption_profile_digest") != ref.encryption_profile_digest
        ):
            raise PrimaMateriaStoreError("manifest-identity-mismatch")
        chunks = manifest.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            raise PrimaMateriaStoreError("manifest-chunks-invalid")
        content_auth = manifest.get("content_auth")
        if not isinstance(content_auth, str):
            raise PrimaMateriaStoreError("manifest-content-auth-invalid")
        expected_object_id = ref.object_id
        plaintext_parts: list[bytes] = []
        ciphertext_digest = hashlib.sha256()
        # The private manifest carries an authenticated AES-GCM key capsule;
        # no plaintext digest or unwrapped object key is persisted.
        key_nonce = _hmac(self.key, b"key-capsule-nonce", ref.object_id.encode())[:12]
        capsule = manifest.get("object_key_capsule")
        if not isinstance(capsule, str):
            raise PrimaMateriaStoreError("manifest-key-capsule-missing")
        try:
            object_key = _AesGcm(self.key).decrypt(
                key_nonce,
                _decode_b64url(capsule),
                ref.object_id.encode(),
            )
        except (_AuthenticationError, ValueError) as exc:
            raise PrimaMateriaStoreError("manifest-key-capsule-invalid") from exc
        aes = _AesGcm(object_key)
        total = len(chunks)
        for expected_index, metadata in enumerate(chunks):
            if not isinstance(metadata, dict) or metadata.get("index") != expected_index:
                raise PrimaMateriaStoreError("manifest-chunk-order-invalid")
            ciphertext_sha256 = metadata.get("ciphertext_sha256")
            if not isinstance(ciphertext_sha256, str):
                raise PrimaMateriaStoreError("manifest-chunk-digest-invalid")
            path = object_root / f"{expected_index:08d}-{ciphertext_sha256}.bin"
            try:
                if path.is_symlink() or not path.is_file():
                    raise PrimaMateriaStoreError("ciphertext-chunk-unavailable")
                ciphertext = path.read_bytes()
            except OSError as exc:
                raise PrimaMateriaStoreError("ciphertext-chunk-unavailable") from exc
            if hashlib.sha256(ciphertext).hexdigest() != ciphertext_sha256 or len(ciphertext) != metadata.get(
                "ciphertext_bytes"
            ):
                raise PrimaMateriaStoreError("ciphertext-chunk-drift")
            nonce = _decode_b64url(str(metadata.get("nonce", "")))
            aad = rfc8785.dumps(
                {
                    "schema": STORE_SCHEMA,
                    "object_id": ref.object_id,
                    "index": expected_index,
                    "total": total,
                    "profile": self.profile_digest,
                }
            )
            try:
                plaintext = aes.decrypt(nonce, ciphertext, aad)
            except _AuthenticationError as exc:
                raise PrimaMateriaStoreError("ciphertext-authentication-failed") from exc
            if len(plaintext) != metadata.get("plaintext_bytes"):
                raise PrimaMateriaStoreError("plaintext-chunk-size-mismatch")
            plaintext_parts.append(plaintext)
            ciphertext_digest.update(ciphertext)
        plaintext = b"".join(plaintext_parts)
        object_id, _derived_key, observed_auth = self._identities(plaintext)
        if (
            object_id != expected_object_id
            or not hmac.compare_digest(observed_auth, content_auth.encode())
            or len(plaintext) != manifest.get("plaintext_bytes")
            or ciphertext_digest.hexdigest() != ref.ciphertext_sha256
            or sum(int(item["ciphertext_bytes"]) for item in chunks) != ref.ciphertext_bytes
        ):
            raise PrimaMateriaStoreError("restored-object-mismatch")
        return plaintext


@dataclass(frozen=True)
class SourceRegistry:
    adapters: tuple[SourceAdapterV1, ...]
    registry_digest: str

    @classmethod
    def load(cls, path: Path) -> SourceRegistry:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PrimaMateriaStoreError("source-registry-unavailable") from exc
        if not isinstance(payload, dict) or set(payload) != {"schema", "adapters"}:
            raise PrimaMateriaStoreError("source-registry-fields-mismatch")
        if payload["schema"] != REGISTRY_SCHEMA or not isinstance(payload["adapters"], list):
            raise PrimaMateriaStoreError("source-registry-schema-mismatch")
        try:
            adapters = tuple(SourceAdapterV1.model_validate(item) for item in payload["adapters"])
        except ValueError as exc:
            raise PrimaMateriaStoreError("source-adapter-invalid") from exc
        return cls.from_adapters(adapters)

    @classmethod
    def from_adapters(cls, adapters: Iterable[SourceAdapterV1]) -> SourceRegistry:
        ordered = tuple(sorted(adapters, key=lambda item: item.adapter_id))
        adapter_ids = [item.adapter_id for item in ordered]
        source_ids = [item.source_id for item in ordered]
        if len(adapter_ids) != len(set(adapter_ids)):
            raise PrimaMateriaStoreError("duplicate-adapter-id")
        if len(source_ids) != len(set(source_ids)):
            raise PrimaMateriaStoreError("duplicate-source-id")
        normalized = {
            "schema": REGISTRY_SCHEMA,
            "adapters": [item.model_dump(mode="json") for item in ordered],
        }
        return cls(ordered, _canonical_digest(normalized))

    def coverage(self, observed_source_ids: Iterable[str]) -> SourceCoverageV1:
        return SourceCoverageV1.reconcile(
            registry_digest=self.registry_digest,
            observed_source_ids=tuple(observed_source_ids),
            adapters=self.adapters,
        )

    def public_projection(self, observed_source_ids: Iterable[str]) -> dict[str, Any]:
        coverage = self.coverage(observed_source_ids)
        payload: dict[str, Any] = {
            "schema": "limen.source_registry_projection.v1",
            "registry_digest": self.registry_digest,
            "adapter_count": len(self.adapters),
            "observed_source_count": len(coverage.observed_source_ids),
            "missing_adapter_count": len(coverage.missing_adapter_source_ids),
            "registered_source_digests": [
                hashlib.sha256(value.encode()).hexdigest() for value in coverage.registered_source_ids
            ],
            "missing_adapter_source_digests": [
                hashlib.sha256(value.encode()).hexdigest() for value in coverage.missing_adapter_source_ids
            ],
        }
        return {**payload, "projection_sha256": _canonical_digest(payload)}
