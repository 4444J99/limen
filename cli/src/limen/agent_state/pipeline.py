"""Fail-closed OpenCode custody, restoration, and source retirement."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from limen.host_admission import hold_lease

from .atomize import atomize_opencode, sha256_file, stat_identity
from .crypto import (
    EncryptedAtomPacker,
    encrypt_file,
    keychain_key,
    verify_atom_packs,
    verify_encrypted_file,
)
from .models import MetabolismReceipt


class PipelineError(RuntimeError):
    """The custody pipeline failed before its destructive gate."""


def run_id_now() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def vendor_active(executable: str = "opencode") -> bool:
    result = subprocess.run(
        ["pgrep", "-x", executable], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return result.returncode == 0


def require_mounted_external(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        volume = Path("/Volumes") / resolved.relative_to("/Volumes").parts[0]
    except (ValueError, IndexError) as exc:
        raise PipelineError("external custody must be rooted on a mounted /Volumes device") from exc
    if not volume.is_mount() or not os.access(volume, os.W_OK):
        raise PipelineError(f"external custody volume unavailable: {volume}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _run(arguments: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(arguments, cwd=cwd, check=False, capture_output=True, text=True)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        raise PipelineError(f"command failed: {arguments[0]}: {detail}")
    return result.stdout.strip()


class GitVault:
    """Surgical writer for the existing private ARCA ciphertext repository."""

    def __init__(self, root: Path, *, repository: str = "organvm/arca"):
        self.root = root.expanduser().resolve()
        self.repository = repository

    @property
    def remote_url(self) -> str:
        return f"https://github.com/{self.repository}.git"

    def verify(self) -> None:
        if not (self.root / ".git").is_dir():
            raise PipelineError("ARCA vault is not a Git clone")
        if _run(["git", "status", "--porcelain=v1"], cwd=self.root):
            raise PipelineError("ARCA vault is dirty")
        origin = _run(["git", "remote", "get-url", "origin"], cwd=self.root).removesuffix(".git")
        if origin not in {f"https://github.com/{self.repository}", f"git@github.com:{self.repository}"}:
            raise PipelineError("ARCA vault origin does not match the declared private repository")
        visibility = _run(["gh", "repo", "view", self.repository, "--json", "visibility", "-q", ".visibility"])
        if visibility != "PRIVATE":
            raise PipelineError("ARCA remote is not private")

    def commit_and_push(self, relative: Path, message: str) -> str:
        _run(["git", "add", "-A", "--", str(relative)], cwd=self.root)
        if not _run(["git", "status", "--porcelain=v1", "--", str(relative)], cwd=self.root):
            raise PipelineError("ARCA payload produced no Git change")
        _run(["git", "commit", "-m", message, "--", str(relative)], cwd=self.root)
        head = _run(["git", "rev-parse", "HEAD"], cwd=self.root)
        _run(["git", "push", "origin", "HEAD:main"], cwd=self.root)
        remote = _run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=self.root).split()[0]
        if remote != head:
            raise PipelineError("ARCA remote did not accept the exact custody commit")
        return head


def _capture_manifest(receipt: MetabolismReceipt, table_counts: dict[str, int]) -> dict[str, object]:
    return {
        "schema": receipt.schema,
        "run_id": receipt.run_id,
        "source": asdict(receipt.source),
        "atom_count": receipt.atom_count,
        "duplicate_payloads": receipt.duplicate_payloads,
        "logical_sha256": receipt.logical_sha256,
        "table_counts": table_counts,
        "packs": [asdict(pack) for pack in receipt.packs],
        "external_chunks": [asdict(chunk) for chunk in receipt.external_chunks],
        "restorations": [asdict(proof) for proof in receipt.restorations],
    }


def capture_opencode(
    source: Path,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    *,
    run_id: str | None = None,
    repository: str = "organvm/arca",
    key_service: str = "limen-arca-vault",
    process_probe: Callable[[], bool] = vendor_active,
    require_external_mount: bool = True,
    pack_plaintext_limit: int = 32 * 1024 * 1024,
    chunk_limit: int = 90 * 1024 * 1024,
) -> MetabolismReceipt:
    """Create encrypted Git atoms plus an exact encrypted external source copy."""

    source = source.expanduser().resolve()
    if process_probe():
        raise PipelineError("OpenCode is active; capture denied")
    if not source.is_file():
        raise PipelineError(f"OpenCode database missing: {source}")
    wal = Path(str(source) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise PipelineError("OpenCode WAL is non-empty; quiesce and checkpoint before capture")
    external_base = require_mounted_external(external_root) if require_external_mount else external_root.resolve()
    external_base.mkdir(parents=True, exist_ok=True)
    run_id = run_id or run_id_now()
    vault = GitVault(vault_root, repository=repository)
    vault.verify()
    relative = Path("agent-state") / "opencode" / run_id
    payload_root = vault.root / relative
    exact_root = external_base / "opencode" / run_id
    if payload_root.exists() or exact_root.exists():
        raise PipelineError(f"custody run already exists: {run_id}")
    payload_root.mkdir(parents=True, mode=0o700)
    exact_root.mkdir(parents=True, mode=0o700)
    key = keychain_key(key_service)
    packer = EncryptedAtomPacker(
        payload_root,
        key,
        pack_plaintext_limit=pack_plaintext_limit,
        chunk_limit=chunk_limit,
    )
    try:
        result = atomize_opencode(source, packer, spill_dir=None)
        packs = list(packer.close())
        if not result.source.stable:
            raise PipelineError("OpenCode database mutated during capture")
        sample = verify_atom_packs(packs, payload_root, key, logical_sha256=result.logical_sha256, sample=True)
        full = verify_atom_packs(packs, payload_root, key, logical_sha256=result.logical_sha256)
        if not sample.passed or not full.passed:
            raise PipelineError("encrypted Git atom restoration failed")
        external_chunks = list(encrypt_file(source, exact_root, "opencode.db", key, chunk_limit=chunk_limit))
        external = verify_encrypted_file(
            external_chunks,
            exact_root,
            key,
            source_sha256=result.source.sha256,
        )
        if not external.passed:
            raise PipelineError("exact external restoration failed")
        if stat_identity(source) != result.source.stat_after:
            raise PipelineError("OpenCode database mutated after external capture")
        receipt = MetabolismReceipt(
            schema="limen.agent_state_metabolism.v1",
            run_id=run_id,
            source=result.source,
            atom_count=result.atom_count,
            logical_sha256=result.logical_sha256,
            packs=packs,
            duplicate_payloads=result.duplicate_payloads,
            external_chunks=external_chunks,
            restorations=[sample, full, external],
        )
        manifest = _capture_manifest(receipt, result.table_counts)
        (payload_root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        data_commit = vault.commit_and_push(relative, f"agent-state: seal OpenCode {run_id}")
        receipt.git_remote = repository
        receipt.git_commit = data_commit
        (payload_root / "receipt.json").write_text(
            json.dumps(receipt.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        receipt.git_receipt_commit = vault.commit_and_push(relative, f"agent-state: receipt OpenCode {run_id}")
        receipt.write(private_receipt)
        receipt.require_retirement_gate()
        return receipt
    except BaseException:
        packer.abort()
        if not (payload_root / ".git-preserved").exists():
            shutil.rmtree(payload_root, ignore_errors=True)
        shutil.rmtree(exact_root, ignore_errors=True)
        raise


def _schema_sql(source: Path) -> tuple[list[str], int]:
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT type, sql FROM sqlite_schema "
            "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL "
            "ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 "
            "WHEN 'trigger' THEN 2 ELSE 3 END, name"
        ).fetchall()
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    return [str(sql) for _kind, sql in rows], user_version


def _clean_database(source: Path, destination: Path) -> None:
    statements, user_version = _schema_sql(source)
    with sqlite3.connect(destination) as connection:
        for statement in statements:
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version={user_version}")
        check = connection.execute("PRAGMA integrity_check").fetchone()
        if not check or check[0] != "ok":
            raise PipelineError("clean OpenCode database failed integrity check")
    os.chmod(destination, source.stat().st_mode & 0o777)


def retire_opencode(
    receipt: MetabolismReceipt,
    *,
    process_probe: Callable[[], bool] = vendor_active,
) -> MetabolismReceipt:
    """Atomically replace the preserved database with its empty current schema."""

    receipt.require_retirement_gate()
    source = Path(receipt.source.path)
    if process_probe():
        raise PipelineError("OpenCode became active; retirement denied")
    if stat_identity(source) != receipt.source.stat_after:
        raise PipelineError("OpenCode database changed after custody")
    wal = Path(str(source) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise PipelineError("OpenCode WAL became non-empty; retirement denied")
    clean = source.with_name(f".{source.name}.{receipt.run_id}.clean")
    retiring = source.with_name(f".{source.name}.{receipt.run_id}.retiring")
    if clean.exists() or retiring.exists():
        raise PipelineError("prior OpenCode retirement staging exists")
    _clean_database(source, clean)
    if process_probe() or stat_identity(source) != receipt.source.stat_after:
        clean.unlink(missing_ok=True)
        raise PipelineError("OpenCode changed during retirement preparation")
    source.replace(retiring)
    try:
        clean.replace(source)
    except BaseException:
        retiring.replace(source)
        clean.unlink(missing_ok=True)
        raise
    for sidecar in (Path(str(retiring) + "-wal"), Path(str(retiring) + "-shm"), wal, Path(str(source) + "-shm")):
        sidecar.unlink(missing_ok=True)
    retiring.unlink()
    receipt.source_retired = True
    receipt.retirement_proof = f"deleted-source-sha256:{receipt.source.sha256};clean-db-sha256:{sha256_file(source)}"
    return receipt


def run_opencode_campaign(
    source: Path,
    vault_root: Path,
    external_root: Path,
    private_receipt: Path,
    *,
    retire: bool = False,
    run_id: str | None = None,
) -> MetabolismReceipt:
    """Hold the sole heavy lease across capture, verification, and optional retirement."""

    owner = f"agent-state-metabolism-{os.getpid()}"
    with hold_lease("heavy", owner=owner, surface="opencode-agent-state-custody"):
        receipt = capture_opencode(
            source,
            vault_root,
            external_root,
            private_receipt,
            run_id=run_id,
        )
        if retire:
            retire_opencode(receipt)
            receipt.write(private_receipt)
        return receipt
