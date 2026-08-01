"""Streaming ARCA-compatible encryption and restoration predicates."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
import threading
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, BinaryIO, TypeVar, cast

import rfc8785

from .models import AtomPack, CipherChunk, RestoreProof

T = TypeVar("T")
_OPENSSL_ENCRYPT = (
    "openssl",
    "enc",
    "-aes-256-cbc",
    "-pbkdf2",
    "-iter",
    "200000",
    "-salt",
    "-pass",
    "env:ARCA_KEY",
)
_OPENSSL_DECRYPT = (
    "openssl",
    "enc",
    "-d",
    "-aes-256-cbc",
    "-pbkdf2",
    "-iter",
    "200000",
    "-pass",
    "env:ARCA_KEY",
)
ARCA_ENCRYPTION_PROFILE: dict[str, Any] = {
    "cipher_command": list(_OPENSSL_ENCRYPT),
    "compression": {
        "format": "gzip",
        "filename": "",
        "mtime": 0,
    },
    "record_format": "canonical-jsonl-atoms",
}
ARCA_RAW_FILE_ENCRYPTION_PROFILE: dict[str, Any] = {
    "cipher_command": list(_OPENSSL_ENCRYPT),
    "compression": {
        "format": "none",
    },
    "record_format": "raw-file-bytes",
}


class CryptoError(RuntimeError):
    """Ciphertext could not be created or restored safely."""


def encryption_profile_digest(source_kind: str = "file-tree") -> str:
    """Return the run-level digest for every encrypted payload form."""

    if source_kind == "file-tree":
        external: dict[str, Any] = {
            "form": "replicated-git-ciphertext",
            "profile_ref": "git-atom-packs",
        }
    elif source_kind == "opencode-sqlite":
        external = {
            "form": "raw-source-copy",
            "profile": ARCA_RAW_FILE_ENCRYPTION_PROFILE,
        }
    else:
        raise ValueError(f"unsupported agent-state source kind: {source_kind}")
    profile: dict[str, Any] = {
        "schema": "limen.agent_state_encryption_profile.v2",
        "git-atom-packs": ARCA_ENCRYPTION_PROFILE,
        "external": external,
    }
    return hashlib.sha256(rfc8785.dumps(profile)).hexdigest()


def keychain_key(service: str = "limen-arca-vault") -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-w"],
        check=False,
        capture_output=True,
        text=True,
    )
    key = result.stdout.strip()
    if result.returncode or not key:
        raise CryptoError(f"Keychain key unavailable for service {service}")
    return key


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class _ChunkOutput:
    def __init__(self, root: Path, stem: str, limit: int):
        if limit <= 0:
            raise ValueError("cipher chunk limit must be positive")
        self.root = root
        self.stem = stem
        self.limit = limit
        self.root.mkdir(parents=True, exist_ok=True)
        self._handle: BinaryIO | None = None
        self._path: Path | None = None
        self._size = 0
        self._digest = hashlib.sha256()
        self._receipts: list[CipherChunk] = []

    def _open(self) -> None:
        ordinal = len(self._receipts)
        self._path = self.root / f"{self.stem}.enc.part-{ordinal:05d}"
        self._handle = self._path.open("xb")
        os.chmod(self._path, 0o600)
        self._size = 0
        self._digest = hashlib.sha256()

    def write(self, value: bytes) -> None:
        view = memoryview(value)
        while view:
            if self._handle is None:
                self._open()
            available = self.limit - self._size
            piece = view[:available]
            assert self._handle is not None
            self._handle.write(piece)
            self._digest.update(piece)
            self._size += len(piece)
            view = view[len(piece) :]
            if self._size == self.limit:
                self._finish_chunk()

    def _finish_chunk(self) -> None:
        if self._handle is None or self._path is None:
            return
        self._handle.flush()
        os.fsync(self._handle.fileno())
        self._handle.close()
        self._receipts.append(CipherChunk(path=self._path.name, bytes=self._size, sha256=self._digest.hexdigest()))
        self._handle = None
        self._path = None

    def close(self) -> tuple[CipherChunk, ...]:
        self._finish_chunk()
        if not self._receipts:
            raise CryptoError("cipher produced no output")
        return tuple(self._receipts)

    def abort(self) -> None:
        if self._handle is not None:
            self._handle.close()
        candidates = [self.root / receipt.path for receipt in self._receipts]
        if self._path is not None:
            candidates.append(self._path)
        for path in candidates:
            path.unlink(missing_ok=True)


class _EncryptPipe:
    def __init__(self, root: Path, stem: str, key: str, chunk_limit: int):
        environment = dict(os.environ)
        environment["ARCA_KEY"] = key
        self.output = _ChunkOutput(root, stem, chunk_limit)
        self.process = subprocess.Popen(
            _OPENSSL_ENCRYPT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        self._stderr = bytearray()
        self._error: BaseException | None = None
        self._stdout_thread = threading.Thread(target=self._drain_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _drain_stdout(self) -> None:
        try:
            stdout = cast(BinaryIO, self.process.stdout)
            for block in iter(lambda: stdout.read(1024 * 1024), b""):
                self.output.write(block)
        except BaseException as exc:  # noqa: BLE001  # pragma: no cover - hardware/filesystem failures
            self._error = exc

    def _drain_stderr(self) -> None:
        stderr = cast(BinaryIO, self.process.stderr)
        for block in iter(lambda: stderr.read(4096), b""):
            if len(self._stderr) < 65536:
                self._stderr.extend(block[: 65536 - len(self._stderr)])

    def write(self, value: bytes) -> int:
        if self._error:
            raise CryptoError("cipher output failed") from self._error
        assert self.process.stdin is not None
        return self.process.stdin.write(value)

    def flush(self) -> None:
        assert self.process.stdin is not None
        self.process.stdin.flush()

    def close(self) -> tuple[CipherChunk, ...]:
        assert self.process.stdin is not None
        self.process.stdin.close()
        return_code = self.process.wait()
        self._stdout_thread.join()
        self._stderr_thread.join()
        if return_code or self._error:
            self.output.abort()
            detail = bytes(self._stderr).decode("utf-8", errors="replace").strip()
            raise CryptoError(f"encryption failed: {detail or 'cipher output error'}") from self._error
        return self.output.close()

    def abort(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait()
        self._stdout_thread.join()
        self._stderr_thread.join()
        self.output.abort()


class EncryptedAtomPacker:
    """Atom sink that gzip-compresses directly into bounded ciphertext parts."""

    def __init__(
        self,
        root: Path,
        key: str,
        *,
        pack_plaintext_limit: int = 32 * 1024 * 1024,
        chunk_limit: int = 90 * 1024 * 1024,
    ):
        self.root = root
        self.key = key
        self.pack_plaintext_limit = pack_plaintext_limit
        self.chunk_limit = chunk_limit
        self._pipe: _EncryptPipe | None = None
        self._gzip: gzip.GzipFile | None = None
        self._count = 0
        self._bytes = 0
        self._digest = hashlib.sha256()
        self.packs: list[AtomPack] = []

    def _start(self) -> None:
        ordinal = len(self.packs)
        self._pipe = _EncryptPipe(self.root, f"atoms-{ordinal:05d}.jsonl.gz", self.key, self.chunk_limit)
        self._gzip = gzip.GzipFile(fileobj=self._pipe, mode="wb", filename="", mtime=0)
        self._count = 0
        self._bytes = 0
        self._digest = hashlib.sha256()

    def __call__(self, _envelope: dict[str, object], line: bytes) -> None:
        if self._pipe is not None and self._bytes and self._bytes + len(line) > self.pack_plaintext_limit:
            self._finish()
        if self._pipe is None:
            self._start()
        assert self._gzip is not None
        try:
            self._gzip.write(line)
        except BaseException:
            assert self._pipe is not None
            self._pipe.abort()
            raise
        self._digest.update(line)
        self._bytes += len(line)
        self._count += 1

    def _finish(self) -> None:
        if self._pipe is None or self._gzip is None:
            return
        pipe = self._pipe
        try:
            self._gzip.close()
            chunks = pipe.close()
        except BaseException:
            pipe.abort()
            raise
        self.packs.append(
            AtomPack(
                ordinal=len(self.packs),
                atom_count=self._count,
                plaintext_bytes=self._bytes,
                plaintext_sha256=self._digest.hexdigest(),
                chunks=chunks,
            )
        )
        self._pipe = None
        self._gzip = None

    def close(self) -> tuple[AtomPack, ...]:
        self._finish()
        return tuple(self.packs)

    def abort(self) -> None:
        if self._pipe is not None:
            self._pipe.abort()
            self._pipe = None
            self._gzip = None


def _decrypt(chunks: Iterable[Path], key: str, consumer: Callable[[BinaryIO], T]) -> T:
    paths = tuple(chunks)
    environment = dict(os.environ)
    environment["ARCA_KEY"] = key
    process = subprocess.Popen(
        _OPENSSL_DECRYPT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    stdin = cast(BinaryIO, process.stdin)
    stdout = cast(BinaryIO, process.stdout)
    feeder_error: list[BaseException] = []

    def feed() -> None:
        try:
            for path in paths:
                with path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b""):
                        stdin.write(block)
            stdin.close()
        except BaseException as exc:  # noqa: BLE001  # pragma: no cover - hardware/filesystem failures
            feeder_error.append(exc)
            stdin.close()

    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()
    try:
        result = consumer(stdout)
    except BaseException:
        process.kill()
        feeder.join()
        process.wait()
        raise
    stdout.close()
    feeder.join()
    stderr = process.stderr.read(65536) if process.stderr is not None else b""
    return_code = process.wait()
    if feeder_error or return_code:
        detail = stderr.decode("utf-8", errors="replace").strip()
        raise CryptoError(f"decryption failed: {detail or 'ciphertext unreadable'}") from (
            feeder_error[0] if feeder_error else None
        )
    return result


def _chunk_paths(pack: AtomPack, root: Path) -> tuple[Path, ...]:
    paths: list[Path] = []
    for chunk in pack.chunks:
        path = root / chunk.path
        if not path.is_file() or path.stat().st_size != chunk.bytes or _sha256(path) != chunk.sha256:
            raise CryptoError(f"ciphertext chunk failed hash verification: {chunk.path}")
        paths.append(path)
    return tuple(paths)


def _verify_pack(
    pack: AtomPack,
    root: Path,
    key: str,
    *,
    logical_digest: hashlib._Hash | None = None,
    record_consumer: Callable[[dict[str, Any]], None] | None = None,
) -> int:
    def consume(stream: BinaryIO) -> int:
        count = 0
        digest = hashlib.sha256()
        with gzip.GzipFile(fileobj=stream, mode="rb") as payload:
            for line in payload:
                envelope = json.loads(line)
                body = json.dumps(envelope["record"], ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
                    "utf-8"
                )
                if hashlib.sha256(body).hexdigest() != envelope["atom_sha256"]:
                    raise CryptoError("atom content hash mismatch")
                digest.update(line)
                if logical_digest is not None:
                    logical_digest.update(line)
                if record_consumer is not None:
                    record_consumer(envelope["record"])
                count += 1
        if count != pack.atom_count or digest.hexdigest() != pack.plaintext_sha256:
            raise CryptoError("atom pack manifest mismatch")
        return count

    return _decrypt(_chunk_paths(pack, root), key, consume)


def verify_atom_packs(
    packs: Iterable[AtomPack],
    root: Path,
    key: str,
    *,
    logical_sha256: str,
    sample: bool = False,
    record_consumer: Callable[[dict[str, Any]], None] | None = None,
) -> RestoreProof:
    if sample and record_consumer is not None:
        raise ValueError("sample restoration cannot emit an incomplete atom stream")
    selected = tuple(packs)
    if sample and len(selected) > 1:
        selected = (selected[0], selected[-1])
    atoms = 0
    logical = hashlib.sha256()
    try:
        for pack in selected:
            atoms += _verify_pack(
                pack,
                root,
                key,
                logical_digest=None if sample else logical,
                record_consumer=record_consumer,
            )
        if not sample and logical.hexdigest() != logical_sha256:
            raise CryptoError("full logical manifest digest mismatch")
    except (CryptoError, OSError, EOFError, gzip.BadGzipFile, json.JSONDecodeError) as exc:
        return RestoreProof(
            scope="git-sample" if sample else "git-full-manifest",
            passed=False,
            atoms_verified=atoms,
            detail=str(exc),
        )
    return RestoreProof(
        scope="git-sample" if sample else "git-full-manifest",
        passed=True,
        atoms_verified=atoms,
        logical_sha256=None if sample else logical.hexdigest(),
    )


def encrypt_file(source: Path, root: Path, stem: str, key: str, *, chunk_limit: int) -> tuple[CipherChunk, ...]:
    pipe = _EncryptPipe(root, stem, key, chunk_limit)
    try:
        with source.open("rb") as handle:
            for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
                pipe.write(block)
        return pipe.close()
    except BaseException:
        pipe.abort()
        raise


def verify_encrypted_file(chunks: Iterable[CipherChunk], root: Path, key: str, *, source_sha256: str) -> RestoreProof:
    chunk_receipts = tuple(chunks)
    try:
        paths = []
        for chunk in chunk_receipts:
            path = root / chunk.path
            if not path.is_file() or path.stat().st_size != chunk.bytes or _sha256(path) != chunk.sha256:
                raise CryptoError(f"ciphertext chunk failed hash verification: {chunk.path}")
            paths.append(path)

        def consume(stream: BinaryIO) -> str:
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                digest.update(block)
            return digest.hexdigest()

        restored = _decrypt(paths, key, consume)
        if restored != source_sha256:
            raise CryptoError("restored source hash mismatch")
    except (CryptoError, OSError) as exc:
        return RestoreProof(scope="external-full", passed=False, detail=str(exc))
    return RestoreProof(scope="external-full", passed=True, source_sha256=restored)
