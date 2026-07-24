"""Machine-readable contracts for agent-state capture and retirement."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class ReceiptError(RuntimeError):
    """A custody or restoration predicate is unsatisfied."""


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

    @property
    def stable(self) -> bool:
        return self.stat_before == self.stat_after


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
