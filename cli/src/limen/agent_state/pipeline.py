"""Fail-closed OpenCode custody, restoration, and source retirement."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict
from pathlib import Path

from limen.host_admission import hold_lease

from .atomize import atomize_opencode, sha256_file, stat_identity
from .crypto import (
    EncryptedAtomPacker,
    encrypt_file,
    encryption_profile_digest,
    keychain_key,
    verify_atom_packs,
    verify_encrypted_file,
)
from .models import MetabolismReceipt


class PipelineError(RuntimeError):
    """The custody pipeline failed before its destructive gate."""


ARCA_REMOTE_EXACT_ERROR = "ARCA completed receipt is not exact on the remote"
RETIREMENT_AUTHORIZATION_REQUIRED = (
    "source retirement requires canonical custody and a separately authorized retirement workflow"
)
GITHUB_PUSH_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_GIT_BATCH_LIMIT_BYTES = 1024 * 1024 * 1024


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


def _run_bytes(arguments: list[str], *, cwd: Path | None = None) -> bytes:
    result = subprocess.run(arguments, cwd=cwd, check=False, capture_output=True)
    if result.returncode:
        detail = result.stderr.decode(errors="replace").strip() or f"exit {result.returncode}"
        raise PipelineError(f"command failed: {arguments[0]}: {detail}")
    return result.stdout


def partition_git_paths(
    paths: Iterable[Path],
    *,
    byte_limit: int = DEFAULT_GIT_BATCH_LIMIT_BYTES,
) -> list[list[Path]]:
    """Partition ciphertext files into deterministic, sub-2 GiB push batches."""
    if byte_limit <= 0 or byte_limit >= GITHUB_PUSH_LIMIT_BYTES:
        raise PipelineError("Git custody batch limit must be positive and below 2 GiB")
    batches: list[list[Path]] = []
    batch: list[Path] = []
    batch_bytes = 0
    for path in sorted(paths, key=lambda candidate: candidate.as_posix()):
        size = path.stat().st_size
        if size > byte_limit:
            raise PipelineError(f"single Git custody file exceeds bounded push batch: {path.name}")
        if batch and batch_bytes + size > byte_limit:
            batches.append(batch)
            batch = []
            batch_bytes = 0
        batch.append(path)
        batch_bytes += size
    if batch:
        batches.append(batch)
    return batches


def _batch_message(message: str, index: int, total: int) -> str:
    return message if total == 1 else f"{message} ({index}/{total})"


class GitVault:
    """Surgical writer for the existing private ARCA ciphertext repository."""

    def __init__(self, root: Path, *, repository: str = "organvm/arca"):
        self.root = root.expanduser().resolve()
        self.repository = repository

    @property
    def remote_url(self) -> str:
        return f"https://github.com/{self.repository}.git"

    def verify_identity(self) -> None:
        if not (self.root / ".git").exists():
            raise PipelineError("ARCA vault is not a Git clone")
        origin = _run(["git", "remote", "get-url", "origin"], cwd=self.root).removesuffix(".git")
        if origin not in {f"https://github.com/{self.repository}", f"git@github.com:{self.repository}"}:
            raise PipelineError("ARCA vault origin does not match the declared private repository")
        visibility = _run(["gh", "repo", "view", self.repository, "--json", "visibility", "-q", ".visibility"])
        if visibility != "PRIVATE":
            raise PipelineError("ARCA remote is not private")

    def verify(self) -> None:
        self.verify_identity()
        if _run(["git", "status", "--porcelain=v1"], cwd=self.root):
            raise PipelineError("ARCA vault is dirty")

    def require_exact_remote_head(self) -> str:
        """Return HEAD only when the private remote has accepted that exact commit."""

        head = _run(["git", "rev-parse", "HEAD"], cwd=self.root)
        remote = _run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=self.root).split()[0]
        if remote != head:
            raise PipelineError("ARCA remote head does not match local custody head")
        return head

    def commit_and_push(self, relative: Path, message: str) -> str:
        changed = _run(
            [
                "git",
                "ls-files",
                "--others",
                "--modified",
                "--exclude-standard",
                "--",
                str(relative),
            ],
            cwd=self.root,
        )
        paths = [self.root / value for value in changed.splitlines() if value]
        batches = partition_git_paths(paths)
        if not batches:
            raise PipelineError("ARCA payload produced no Git change")
        heads: list[str] = []
        for index, batch in enumerate(batches, start=1):
            relative_batch = [str(path.relative_to(self.root)) for path in batch]
            _run(["git", "add", "--", *relative_batch], cwd=self.root)
            _run(
                [
                    "git",
                    "-c",
                    "gc.auto=0",
                    "-c",
                    "maintenance.auto=false",
                    "commit",
                    "-m",
                    _batch_message(message, index, len(batches)),
                    "--",
                    *relative_batch,
                ],
                cwd=self.root,
            )
            head = _run(["git", "rev-parse", "HEAD"], cwd=self.root)
            _run(["git", "push", "origin", "HEAD:main"], cwd=self.root)
            if self.require_exact_remote_head() != head:
                raise AssertionError("remote head changed during exact-head verification")
            heads.append(head)
        return heads[-1]

    def completed_receipt_commits(
        self,
        relative: Path,
        message: str,
    ) -> tuple[str, str] | None:
        """Return the payload and receipt commits for an exact completed run."""

        self.verify_identity()
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("ARCA completed receipt path is unsafe")
        head = _run(["git", "rev-parse", "HEAD"], cwd=self.root)
        subject = _run(["git", "show", "-s", "--format=%s", head], cwd=self.root)
        if subject != message:
            return None
        if _run(["git", "status", "--porcelain=v1"], cwd=self.root):
            raise PipelineError("ARCA completed receipt has dirty state")
        changed = set(
            _run(
                ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", head],
                cwd=self.root,
            ).splitlines()
        )
        if changed != {(relative / "receipt.json").as_posix()}:
            raise PipelineError("ARCA completed receipt commit has unexpected files")
        history = _run(["git", "rev-list", "--parents", "-n", "1", head], cwd=self.root).split()
        if len(history) != 2:
            raise PipelineError("ARCA completed receipt commit has invalid history")
        remote = _run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=self.root).split()[0]
        if remote != head:
            raise PipelineError(ARCA_REMOTE_EXACT_ERROR)
        return history[1], head

    def completed_receipt_at_remote(
        self,
        relative: Path,
        message: str,
    ) -> tuple[str, str, str]:
        """Read one completed receipt from remote-reachable history without mutating the checkout."""

        self.verify_identity()
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("ARCA completed receipt path is unsafe")
        remote_output = _run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=self.root).split()
        if len(remote_output) != 2 or remote_output[1] != "refs/heads/main":
            raise PipelineError("ARCA remote main ref is unavailable")
        head = remote_output[0]
        receipt_path = relative / "receipt.json"
        origin = _run(["git", "config", "--get", "remote.origin.url"], cwd=self.root)
        common_dir = Path(_run(["git", "rev-parse", "--git-common-dir"], cwd=self.root))
        if not common_dir.is_absolute():
            common_dir = (self.root / common_dir).resolve()

        # Borrow the checkout's already-present objects through an alternate, but fetch the
        # advertised remote ref into an isolated bare repository. This makes a newer remote head
        # available to git-show/rev-list without touching a dirty shared checkout or relying on
        # servers accepting an unadvertised fetch-by-SHA request.
        with tempfile.TemporaryDirectory(prefix="limen-arca-remote-") as temporary:
            snapshot = Path(temporary) / "snapshot.git"
            _run(["git", "init", "--bare", "--quiet", str(snapshot)], cwd=self.root)
            alternates = snapshot / "objects" / "info" / "alternates"
            alternates.parent.mkdir(parents=True, exist_ok=True)
            alternates.write_text(f"{(common_dir / 'objects').resolve()}\n", encoding="utf-8")
            remote_ref = "refs/limen/remote-main"
            _run(
                [
                    "git",
                    "fetch",
                    "--quiet",
                    "--no-tags",
                    "--no-write-fetch-head",
                    origin,
                    f"+refs/heads/main:{remote_ref}",
                ],
                cwd=snapshot,
            )
            if _run(["git", "rev-parse", remote_ref], cwd=snapshot) != head:
                raise PipelineError("ARCA remote main changed during completed-receipt verification")

            candidates = _run(
                ["git", "rev-list", remote_ref, "--", receipt_path.as_posix()],
                cwd=snapshot,
            ).splitlines()
            matches = [
                commit
                for commit in candidates
                if _run(["git", "show", "-s", "--format=%s", commit], cwd=snapshot) == message
            ]
            if len(matches) != 1:
                raise PipelineError("ARCA remote history does not contain one exact completed receipt")
            receipt_commit = matches[0]
            changed = set(
                _run(
                    ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", receipt_commit],
                    cwd=snapshot,
                ).splitlines()
            )
            if changed != {receipt_path.as_posix()}:
                raise PipelineError("ARCA remote receipt commit has unexpected files")
            history = _run(
                ["git", "rev-list", "--parents", "-n", "1", receipt_commit],
                cwd=snapshot,
            ).split()
            if len(history) != 2:
                raise PipelineError("ARCA remote receipt commit has invalid history")
            receipt = _run(
                ["git", "show", f"{receipt_commit}:{receipt_path.as_posix()}"],
                cwd=snapshot,
            )
            return history[1], receipt_commit, receipt

    def materialize_remote_payload(
        self,
        relative: Path,
        payload_commit: str,
        expected_paths: Iterable[Path],
        destination: Path,
    ) -> Path:
        """Materialize every expected ciphertext blob from one remote-reachable commit."""

        self.verify_identity()
        relative = Path(relative)
        requested = [Path(path) for path in expected_paths]
        normalized = sorted(set(requested), key=Path.as_posix)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not normalized
            or any(path.is_absolute() or ".." in path.parts or len(path.parts) != 1 for path in normalized)
            or len(normalized) != len(requested)
        ):
            raise PipelineError("ARCA remote payload manifest is unsafe")
        if not re.fullmatch(r"[0-9a-f]{40}", payload_commit):
            raise PipelineError("ARCA remote payload commit is invalid")
        if destination.exists():
            raise PipelineError("ARCA remote restoration target already exists")

        remote_output = _run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=self.root).split()
        if len(remote_output) != 2 or remote_output[1] != "refs/heads/main":
            raise PipelineError("ARCA remote main ref is unavailable")
        origin = _run(["git", "config", "--get", "remote.origin.url"], cwd=self.root)
        common_dir = Path(_run(["git", "rev-parse", "--git-common-dir"], cwd=self.root))
        if not common_dir.is_absolute():
            common_dir = (self.root / common_dir).resolve()

        with tempfile.TemporaryDirectory(prefix="limen-arca-remote-") as temporary:
            snapshot = Path(temporary) / "snapshot.git"
            _run(["git", "init", "--bare", "--quiet", str(snapshot)], cwd=self.root)
            alternates = snapshot / "objects" / "info" / "alternates"
            alternates.parent.mkdir(parents=True, exist_ok=True)
            alternates.write_text(f"{(common_dir / 'objects').resolve()}\n", encoding="utf-8")
            remote_ref = "refs/limen/remote-main"
            _run(
                [
                    "git",
                    "fetch",
                    "--quiet",
                    "--no-tags",
                    "--no-write-fetch-head",
                    origin,
                    f"+refs/heads/main:{remote_ref}",
                ],
                cwd=snapshot,
            )
            if _run(["git", "rev-parse", remote_ref], cwd=snapshot) != remote_output[0]:
                raise PipelineError("ARCA remote main changed during payload restoration")
            _run(["git", "merge-base", "--is-ancestor", payload_commit, remote_ref], cwd=snapshot)

            destination.mkdir(parents=True)
            try:
                for path in normalized:
                    git_path = (relative / path).as_posix()
                    restored = destination / path
                    restored.write_bytes(
                        _run_bytes(
                            ["git", "show", f"{payload_commit}:{git_path}"],
                            cwd=snapshot,
                        )
                    )
                    restored.chmod(0o600)
            except BaseException:
                shutil.rmtree(destination, ignore_errors=True)
                raise
        return destination

    def resume_and_push_payload(
        self,
        relative: Path,
        expected_paths: Iterable[Path],
        message: str,
        *,
        byte_limit: int = DEFAULT_GIT_BATCH_LIMIT_BYTES,
    ) -> str:
        """Resume an interrupted deterministic payload push without re-encryption."""

        self.verify_identity()
        relative = Path(relative)
        if relative.is_absolute() or ".." in relative.parts:
            raise PipelineError("ARCA resume path is unsafe")
        normalized = sorted({Path(path) for path in expected_paths}, key=Path.as_posix)
        if not normalized:
            raise PipelineError("ARCA interrupted payload has no expected files")
        if any(path.is_absolute() or ".." in path.parts for path in normalized):
            raise PipelineError("ARCA interrupted payload contains an unsafe path")
        absolute = [self.root / path for path in normalized]
        if any(not path.is_file() for path in absolute):
            raise PipelineError("ARCA interrupted payload is missing an expected file")
        batches = partition_git_paths(absolute, byte_limit=byte_limit)
        expected_batches = [{path.relative_to(self.root).as_posix() for path in batch} for batch in batches]
        total = len(expected_batches)
        head = _run(["git", "rev-parse", "HEAD"], cwd=self.root)
        subject = _run(["git", "show", "-s", "--format=%s", head], cwd=self.root)
        matching = [index for index in range(1, total + 1) if subject == _batch_message(message, index, total)]
        if not matching:
            raise PipelineError("ARCA local HEAD is not an interrupted payload batch")
        committed_count = matching[0]
        history = _run(
            [
                "git",
                "rev-list",
                "--first-parent",
                f"--max-count={committed_count + 1}",
                "HEAD",
            ],
            cwd=self.root,
        ).splitlines()
        if len(history) != committed_count + 1:
            raise PipelineError("ARCA interrupted payload history is incomplete")
        committed = list(reversed(history[:committed_count]))
        base = history[committed_count]
        for index, commit in enumerate(committed, start=1):
            if _run(["git", "show", "-s", "--format=%s", commit], cwd=self.root) != _batch_message(
                message, index, total
            ):
                raise PipelineError("ARCA interrupted payload messages are not a valid prefix")
            changed = set(
                _run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit], cwd=self.root).splitlines()
            )
            if changed != expected_batches[index - 1]:
                raise PipelineError("ARCA interrupted payload commits are not a valid prefix")

        status = _run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=self.root,
        )
        dirty: set[str] = set()
        for entry in status.split("\0"):
            if not entry:
                continue
            code, path = entry[:2], entry[3:]
            if code != "??":
                raise PipelineError("ARCA interrupted payload has modified tracked state")
            dirty.add(path)
        remaining = set().union(*expected_batches[committed_count:]) if committed_count < total else set()
        if dirty != remaining:
            raise PipelineError("ARCA interrupted payload has unrelated or missing dirty state")

        remote = _run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=self.root).split()[0]
        valid_remote_heads = {base, *committed}
        if remote not in valid_remote_heads:
            raise PipelineError("ARCA remote is not aligned with the interrupted payload prefix")
        if remote != head:
            _run(["git", "push", "origin", "HEAD:main"], cwd=self.root)
            if self.require_exact_remote_head() != head:
                raise AssertionError("remote head changed during interrupted payload recovery")

        for index, batch in enumerate(batches[committed_count:], start=committed_count + 1):
            relative_batch = [str(path.relative_to(self.root)) for path in batch]
            _run(["git", "add", "--", *relative_batch], cwd=self.root)
            _run(
                [
                    "git",
                    "-c",
                    "gc.auto=0",
                    "-c",
                    "maintenance.auto=false",
                    "commit",
                    "-m",
                    _batch_message(message, index, total),
                    "--",
                    *relative_batch,
                ],
                cwd=self.root,
            )
            head = _run(["git", "rev-parse", "HEAD"], cwd=self.root)
            _run(["git", "push", "origin", "HEAD:main"], cwd=self.root)
            if self.require_exact_remote_head() != head:
                raise AssertionError("remote head changed during resumed exact-head verification")
        return self.require_exact_remote_head()


def _capture_manifest(receipt: MetabolismReceipt, table_counts: dict[str, int]) -> dict[str, object]:
    return {
        "schema": receipt.schema,
        "run_id": receipt.run_id,
        "source": asdict(receipt.source),
        "atom_count": receipt.atom_count,
        "duplicate_payloads": receipt.duplicate_payloads,
        "logical_sha256": receipt.logical_sha256,
        "encryption_profile_digest": receipt.encryption_profile_digest,
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
            encryption_profile_digest=encryption_profile_digest("opencode-sqlite"),
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
    """Hold the sole heavy lease across a preservation-only capture."""

    if retire:
        raise PipelineError(RETIREMENT_AUTHORIZATION_REQUIRED)
    owner = f"agent-state-metabolism-{os.getpid()}"
    with hold_lease("heavy", owner=owner, surface="opencode-agent-state-custody"):
        receipt = capture_opencode(
            source,
            vault_root,
            external_root,
            private_receipt,
            run_id=run_id,
        )
        return receipt
