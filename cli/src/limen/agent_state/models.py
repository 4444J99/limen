"""Machine-readable contracts for agent-state capture and retirement."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class ReceiptError(RuntimeError):
    """A custody or restoration predicate is unsatisfied."""


def _stat_identity(value: object) -> tuple[int, int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in value)
    ):
        raise ReceiptError("agent-state receipt contains an invalid source identity")
    return value[0], value[1], value[2]


def _is_lower_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str) and len(value) == length and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True)
class CipherChunk:
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class AtomPack:
    ordinal: int
    atom_count: int
    plaintext_bytes: int
    plaintext_sha256: str
    chunks: tuple[CipherChunk, ...]


@dataclass(frozen=True)
class SourceProof:
    path: str
    kind: str
    bytes: int
    sha256: str
    stat_before: tuple[int, int, int]
    stat_after: tuple[int, int, int]
    inventory_before_sha256: str | None = None
    inventory_after_sha256: str | None = None

    @property
    def stable(self) -> bool:
        inventory_stable = (
            self.inventory_before_sha256 is None or self.inventory_before_sha256 == self.inventory_after_sha256
        )
        return self.stat_before == self.stat_after and inventory_stable


@dataclass(frozen=True)
class RestoreProof:
    scope: str
    passed: bool
    atoms_verified: int = 0
    logical_sha256: str | None = None
    source_sha256: str | None = None
    detail: str = ""


@dataclass
class MetabolismReceipt:
    schema: str
    run_id: str
    source: SourceProof
    atom_count: int
    logical_sha256: str
    packs: list[AtomPack] = field(default_factory=list)
    duplicate_payloads: int = 0
    git_remote: str | None = None
    git_commit: str | None = None
    git_receipt_commit: str | None = None
    external_chunks: list[CipherChunk] = field(default_factory=list)
    restorations: list[RestoreProof] = field(default_factory=list)
    retained_hot_bytes: int | None = None
    source_retired: bool = False
    retirement_proof: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> MetabolismReceipt:
        """Reconstruct a receipt only when its complete JSON shape is canonical."""

        try:
            source_value = value["source"]
            source = SourceProof(
                path=source_value["path"],
                kind=source_value["kind"],
                bytes=source_value["bytes"],
                sha256=source_value["sha256"],
                stat_before=_stat_identity(source_value["stat_before"]),
                stat_after=_stat_identity(source_value["stat_after"]),
                inventory_before_sha256=source_value["inventory_before_sha256"],
                inventory_after_sha256=source_value["inventory_after_sha256"],
            )
            packs = [
                AtomPack(
                    ordinal=pack["ordinal"],
                    atom_count=pack["atom_count"],
                    plaintext_bytes=pack["plaintext_bytes"],
                    plaintext_sha256=pack["plaintext_sha256"],
                    chunks=tuple(CipherChunk(**chunk) for chunk in pack["chunks"]),
                )
                for pack in value["packs"]
            ]
            receipt = cls(
                schema=value["schema"],
                run_id=value["run_id"],
                source=source,
                atom_count=value["atom_count"],
                logical_sha256=value["logical_sha256"],
                packs=packs,
                duplicate_payloads=value["duplicate_payloads"],
                git_remote=value["git_remote"],
                git_commit=value["git_commit"],
                git_receipt_commit=value["git_receipt_commit"],
                external_chunks=[CipherChunk(**chunk) for chunk in value["external_chunks"]],
                restorations=[RestoreProof(**proof) for proof in value["restorations"]],
                retained_hot_bytes=value["retained_hot_bytes"],
                source_retired=value["source_retired"],
                retirement_proof=value["retirement_proof"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReceiptError("agent-state receipt is missing or malformed") from exc
        normalized = json.loads(json.dumps(receipt.as_dict(), sort_keys=True))
        if normalized != value:
            raise ReceiptError("agent-state receipt has a non-canonical shape")
        numbers = [
            receipt.source.bytes,
            receipt.atom_count,
            receipt.duplicate_payloads,
            *receipt.source.stat_before,
            *receipt.source.stat_after,
            *(pack.ordinal for pack in receipt.packs),
            *(pack.atom_count for pack in receipt.packs),
            *(pack.plaintext_bytes for pack in receipt.packs),
            *(chunk.bytes for pack in receipt.packs for chunk in pack.chunks),
            *(chunk.bytes for chunk in receipt.external_chunks),
            *(proof.atoms_verified for proof in receipt.restorations),
        ]
        hashes = [
            receipt.source.sha256,
            receipt.logical_sha256,
            *(pack.plaintext_sha256 for pack in receipt.packs),
            *(chunk.sha256 for pack in receipt.packs for chunk in pack.chunks),
            *(chunk.sha256 for chunk in receipt.external_chunks),
            *(
                digest
                for digest in (
                    receipt.source.inventory_before_sha256,
                    receipt.source.inventory_after_sha256,
                    *(proof.logical_sha256 for proof in receipt.restorations),
                    *(proof.source_sha256 for proof in receipt.restorations),
                )
                if digest is not None
            ),
        ]
        chunks = [*(chunk for pack in receipt.packs for chunk in pack.chunks), *receipt.external_chunks]
        commits = (receipt.git_commit, receipt.git_receipt_commit)
        if (
            receipt.schema != "limen.agent_state_metabolism.v1"
            or not isinstance(receipt.run_id, str)
            or not receipt.run_id
            or not isinstance(receipt.source.path, str)
            or not isinstance(receipt.source.kind, str)
            or not receipt.source.stable
            or not receipt.packs
            or [pack.ordinal for pack in receipt.packs] != list(range(len(receipt.packs)))
            or sum(pack.atom_count for pack in receipt.packs) != receipt.atom_count
            or any(isinstance(number, bool) or not isinstance(number, int) or number < 0 for number in numbers)
            or any(not _is_lower_hex(digest, 64) for digest in hashes)
            or any(
                Path(chunk.path).is_absolute()
                or len(Path(chunk.path).parts) != 1
                or Path(chunk.path).name != chunk.path
                for chunk in chunks
            )
            or any(commit is not None and not _is_lower_hex(commit, 40) for commit in commits)
            or (receipt.git_remote is not None and not isinstance(receipt.git_remote, str))
            or (
                receipt.retained_hot_bytes is not None
                and (
                    isinstance(receipt.retained_hot_bytes, bool)
                    or not isinstance(receipt.retained_hot_bytes, int)
                    or receipt.retained_hot_bytes < 0
                )
            )
            or not isinstance(receipt.source_retired, bool)
            or (receipt.retirement_proof is not None and not isinstance(receipt.retirement_proof, str))
        ):
            raise ReceiptError("agent-state receipt failed consistency checks")
        return receipt

    @classmethod
    def read(cls, path: Path) -> MetabolismReceipt:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReceiptError("agent-state receipt is missing or invalid") from exc
        if not isinstance(value, dict):
            raise ReceiptError("agent-state receipt must be a JSON object")
        return cls.from_dict(value)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n"
        path.write_text(payload, encoding="utf-8")

    def require_capture_stable(self) -> None:
        if not self.source.stable:
            raise ReceiptError("source mutated during capture")

    def require_retirement_gate(self) -> None:
        self.require_capture_stable()
        if not self.git_remote or not self.git_commit or not self.git_receipt_commit:
            raise ReceiptError("encrypted Git custody is not remote-reachable")
        scopes = {proof.scope for proof in self.restorations if proof.passed}
        required = {"git-sample", "git-full-manifest", "external-full"}
        missing = sorted(required - scopes)
        if missing:
            raise ReceiptError(f"restoration gates missing: {', '.join(missing)}")
        if not self.external_chunks:
            raise ReceiptError("external ciphertext custody is missing")
