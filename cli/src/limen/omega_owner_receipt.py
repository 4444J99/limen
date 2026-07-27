"""Typed, content-free owner receipts for live strict-Omega predicates."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA = "limen.omega_owner_receipt.v1"
OUTPUT_CEILING_BYTES = 65_536
RECEIPT_CEILING_BYTES = 16_384
MAX_FRESHNESS_SECONDS = 604_800
_DIGEST_LENGTH = 64


class OmegaOwnerReceiptError(ValueError):
    """A live owner receipt is missing, stale, malformed, or bound to another predicate."""


class OmegaOwnerReceiptV1(BaseModel):
    """Content-free evidence from one source-owned live predicate observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_id: Literal["limen.omega_owner_receipt.v1"] = Field(
        default=SCHEMA,
        alias="schema",
        serialization_alias="schema",
    )
    rung_id: str = Field(min_length=1, max_length=256, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    status: Literal["PASS", "FAIL", "SKIP"]
    exit_code: Literal[0, 1, 77]
    observed_at: datetime
    predicate_digest: str
    evidence_digest: str
    evidence_bytes: int = Field(ge=0, le=OUTPUT_CEILING_BYTES)
    evidence_truncated: bool = False

    @field_validator("predicate_digest", "evidence_digest")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if len(value) != _DIGEST_LENGTH or any(character not in "0123456789abcdef" for character in value):
            raise ValueError("receipt digests must be lowercase SHA-256 values")
        return value

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def outcome_matches_exit(self) -> OmegaOwnerReceiptV1:
        expected = {0: "PASS", 1: "FAIL", 77: "SKIP"}[self.exit_code]
        if self.status != expected:
            raise ValueError("owner receipt status does not match its explicit exit code")
        if self.evidence_truncated and self.status != "FAIL":
            raise ValueError("truncated owner evidence must fail closed")
        return self


def predicate_digest(predicate: str) -> str:
    normalized = predicate.strip()
    if not normalized or "\x00" in normalized or len(normalized) > 8192:
        raise OmegaOwnerReceiptError("owner predicate must be non-empty, bounded, and contain no NUL")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _evidence_digest(stdout: bytes, stderr: bytes, exit_code: int, truncated: bool) -> str:
    digest = hashlib.sha256()
    for label, value in ((b"stdout", stdout), (b"stderr", stderr)):
        digest.update(label)
        digest.update(b"\0")
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    digest.update(b"exit\0")
    digest.update(str(exit_code).encode("ascii"))
    digest.update(b"\0truncated\0")
    digest.update(b"1" if truncated else b"0")
    return digest.hexdigest()


def normalize_exit_code(returncode: int, *, truncated: bool = False) -> Literal[0, 1, 77]:
    if truncated:
        return 1
    if returncode == 0:
        return 0
    if returncode == 77:
        return 77
    return 1


def build_owner_receipt(
    *,
    rung_id: str,
    predicate: str,
    returncode: int,
    stdout: bytes = b"",
    stderr: bytes = b"",
    truncated: bool = False,
    observed_at: datetime | None = None,
) -> OmegaOwnerReceiptV1:
    normalized_exit = normalize_exit_code(returncode, truncated=truncated)
    status = {0: "PASS", 1: "FAIL", 77: "SKIP"}[normalized_exit]
    bounded_stdout = stdout[:OUTPUT_CEILING_BYTES]
    remaining = OUTPUT_CEILING_BYTES - len(bounded_stdout)
    bounded_stderr = stderr[:remaining]
    evidence_bytes = len(bounded_stdout) + len(bounded_stderr)
    was_truncated = truncated or len(stdout) + len(stderr) > OUTPUT_CEILING_BYTES
    if was_truncated:
        normalized_exit = 1
        status = "FAIL"
    return OmegaOwnerReceiptV1(
        rung_id=rung_id,
        status=status,
        exit_code=normalized_exit,
        observed_at=(observed_at or datetime.now(UTC)).astimezone(UTC),
        predicate_digest=predicate_digest(predicate),
        evidence_digest=_evidence_digest(
            bounded_stdout,
            bounded_stderr,
            normalized_exit,
            was_truncated,
        ),
        evidence_bytes=evidence_bytes,
        evidence_truncated=was_truncated,
    )


def _canonical_receipt_bytes(receipt: OmegaOwnerReceiptV1) -> bytes:
    payload = receipt.model_dump(mode="json", by_alias=True)
    return (json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n").encode("ascii")


def write_owner_receipt(path: Path, receipt: OmegaOwnerReceiptV1) -> None:
    if path.is_symlink():
        raise OmegaOwnerReceiptError("owner receipt path must not be a symlink")
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _canonical_receipt_bytes(receipt)
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        if temporary is None:  # pragma: no cover - assigned by the successful context above
            raise OmegaOwnerReceiptError("owner receipt temporary file was not created")
        os.replace(temporary, path)
    except OSError as exc:
        raise OmegaOwnerReceiptError(f"owner receipt write failed: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_bounded(handle, remaining: int) -> tuple[bytes, int, bool]:
    handle.seek(0)
    data = handle.read(remaining + 1)
    if len(data) > remaining:
        return data[:remaining], 0, True
    return data, remaining - len(data), False


def run_owner_predicate(
    *,
    root: Path,
    rung_id: str,
    predicate: str,
    receipt_path: Path,
    timeout_seconds: int,
) -> tuple[int, bytes, bytes, OmegaOwnerReceiptV1]:
    """Run one trusted registry predicate with bounded output and a process-group timeout."""

    if not 1 <= timeout_seconds <= 7200:
        raise OmegaOwnerReceiptError("owner predicate timeout must be between 1 and 7200 seconds")
    predicate_digest(predicate)
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                predicate,
                shell=True,
                executable="/bin/bash",
                cwd=root,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
            try:
                returncode = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    process.kill()
                process.wait()
                returncode = 1
                stderr_file.write(b"\nomega owner predicate timed out\n")
        except OSError as exc:
            returncode = 1
            stderr_file.write(f"omega owner predicate could not start: {exc}\n".encode("utf-8", errors="replace"))

        stdout, remaining, stdout_truncated = _read_bounded(stdout_file, OUTPUT_CEILING_BYTES)
        stderr, _remaining, stderr_truncated = _read_bounded(stderr_file, remaining)
        truncated = stdout_truncated or stderr_truncated
        receipt = build_owner_receipt(
            rung_id=rung_id,
            predicate=predicate,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
        )
        write_owner_receipt(receipt_path, receipt)
        return receipt.exit_code, stdout, stderr, receipt


def load_owner_receipt(
    path: Path,
    *,
    rung_id: str,
    predicate: str,
    max_age_seconds: int,
    now: datetime | None = None,
    require_pass: bool = True,
) -> OmegaOwnerReceiptV1:
    if not 1 <= max_age_seconds <= MAX_FRESHNESS_SECONDS:
        raise OmegaOwnerReceiptError("owner receipt max age is out of bounds")
    if path.is_symlink() or not path.is_file():
        raise OmegaOwnerReceiptError(f"{rung_id}: missing source-owned receipt")
    try:
        if path.stat().st_size > RECEIPT_CEILING_BYTES:
            raise OmegaOwnerReceiptError(f"{rung_id}: source-owned receipt exceeds its size bound")
        payload = json.loads(path.read_bytes().decode("utf-8"))
        receipt = OmegaOwnerReceiptV1.model_validate(payload)
    except OmegaOwnerReceiptError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise OmegaOwnerReceiptError(f"{rung_id}: invalid source-owned receipt: {exc}") from exc
    if receipt.rung_id != rung_id:
        raise OmegaOwnerReceiptError(f"{rung_id}: source-owned receipt names another rung")
    if receipt.predicate_digest != predicate_digest(predicate):
        raise OmegaOwnerReceiptError(f"{rung_id}: source-owned receipt belongs to another predicate")
    observed_now = (now or datetime.now(UTC)).astimezone(UTC)
    if receipt.observed_at > observed_now + timedelta(seconds=60):
        raise OmegaOwnerReceiptError(f"{rung_id}: source-owned receipt is future-dated")
    if observed_now - receipt.observed_at > timedelta(seconds=max_age_seconds):
        raise OmegaOwnerReceiptError(f"{rung_id}: source-owned receipt is stale")
    if require_pass and receipt.status != "PASS":
        raise OmegaOwnerReceiptError(f"{rung_id}: source-owned receipt is {receipt.status}")
    return receipt


def normalized_owner_receipt(receipt: OmegaOwnerReceiptV1) -> dict:
    """Return the convergence identity while freshness remains independently validated."""

    return receipt.model_dump(mode="json", by_alias=True, exclude={"observed_at"})
