"""Retention planning and lossless atomization for session file trees."""

from __future__ import annotations

import base64
import hashlib
import sqlite3
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .atomize import AtomEmitter, LogicalEmitter, canonical_bytes
from .models import MetabolismReceipt, SourceProof

# Darwin's UF_DATALESS is intentionally absent from Python's stat module.
# File Provider placeholders retain their logical size but set this flag and
# consume no local data blocks.
UF_DATALESS = 0x40000000
NON_EVICTABLE_CLOUD_NAMES = frozenset({".DS_Store"})


@dataclass(frozen=True)
class RetentionPlan:
    root: Path
    cold_paths: tuple[str, ...]
    cold_bytes: int
    hot_paths: tuple[str, ...]
    hot_bytes: int
    cutoff_epoch: float
    maximum_hot_bytes: int


@dataclass(frozen=True)
class FileTreeResult:
    source: SourceProof
    atom_count: int
    logical_sha256: str
    duplicate_chunks: int
    file_count: int


@dataclass(frozen=True)
class EvictionResult:
    selected_files: int
    evicted_files: int
    already_reclaimed_files: int
    allocated_before: int
    allocated_after: int
    retained_non_evictable_files: int = 0
    retained_non_evictable_bytes: int = 0


def plan_retention(
    root: Path,
    *,
    now: float | None = None,
    hot_days: int = 7,
    maximum_hot_bytes: int = 2 * 1024 * 1024 * 1024,
) -> RetentionPlan:
    """Keep the newest seven-day window, bounded by a byte ceiling."""

    root = root.expanduser().resolve()
    now = time.time() if now is None else now
    cutoff = now - hot_days * 86400
    files: list[tuple[str, int, int]] = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        stat = path.stat()
        files.append((path.relative_to(root).as_posix(), stat.st_size, stat.st_mtime_ns))
    files.sort(key=lambda item: (-item[2], item[0]))
    hot: list[str] = []
    cold: list[str] = []
    hot_bytes = 0
    cold_bytes = 0
    cutoff_ns = int(cutoff * 1_000_000_000)
    for relative, size, mtime_ns in files:
        keep = mtime_ns >= cutoff_ns and hot_bytes + size <= maximum_hot_bytes
        if keep:
            hot.append(relative)
            hot_bytes += size
        else:
            cold.append(relative)
            cold_bytes += size
    return RetentionPlan(
        root=root,
        cold_paths=tuple(sorted(cold)),
        cold_bytes=cold_bytes,
        hot_paths=tuple(sorted(hot)),
        hot_bytes=hot_bytes,
        cutoff_epoch=cutoff,
        maximum_hot_bytes=maximum_hot_bytes,
    )


def plan_exact_retention(root: Path, *, retain_paths: tuple[str, ...]) -> RetentionPlan:
    """Capture every regular file except an exact, explicitly retained set."""

    root = root.expanduser().resolve()
    retained: set[str] = set()
    for raw in retain_paths:
        relative_path = Path(raw)
        if (
            relative_path.is_absolute()
            or not relative_path.parts
            or any(part in {".", ".."} for part in relative_path.parts)
        ):
            raise ValueError(f"retained path must be a normalized relative file: {raw}")
        normalized = relative_path.as_posix()
        if normalized in retained:
            raise ValueError(f"retained path is duplicated: {normalized}")
        candidate = root / relative_path
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"retained file is missing: {normalized}") from exc
        if (
            not resolved.is_relative_to(root)
            or candidate.is_symlink()
            or any(
                (root.joinpath(*relative_path.parts[:index])).is_symlink()
                for index in range(1, len(relative_path.parts))
            )
            or not candidate.is_file()
        ):
            raise ValueError(f"retained path must identify a regular file within the root: {normalized}")
        retained.add(normalized)

    files: dict[str, int] = {}
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        relative_name = path.relative_to(root).as_posix()
        files[relative_name] = path.stat().st_size
    missing = retained.difference(files)
    if missing:
        raise FileNotFoundError(f"retained file disappeared during planning: {min(missing)}")

    hot_paths = tuple(sorted(retained))
    cold_paths = tuple(sorted(set(files).difference(retained)))
    return RetentionPlan(
        root=root,
        cold_paths=cold_paths,
        cold_bytes=sum(files[path] for path in cold_paths),
        hot_paths=hot_paths,
        hot_bytes=sum(files[path] for path in hot_paths),
        cutoff_epoch=0.0,
        maximum_hot_bytes=0,
    )


def is_materialized_cloud_path(path: Path) -> bool:
    """Return whether a File Provider path still consumes local data blocks."""

    value = path.stat()
    return not bool(getattr(value, "st_flags", 0) & UF_DATALESS) and value.st_blocks > 0


def plan_cloud_materializations(
    root: Path,
    *,
    materialized_probe: Callable[[Path], bool] = is_materialized_cloud_path,
) -> RetentionPlan:
    """Select only locally materialized File Provider files.

    Cloud-only placeholders are never opened, so planning cannot accidentally
    hydrate a corpus merely to preserve the already-remote logical namespace.
    hot_bytes records the allocated bytes retained outside the selected
    materializations; for normal placeholders this is zero.
    """

    root = root.expanduser().resolve()
    materialized: list[str] = []
    placeholders: list[str] = []
    materialized_bytes = 0
    retained_allocated_bytes = 0
    for path in root.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        value = path.stat()
        relative = path.relative_to(root).as_posix()
        if materialized_probe(path):
            materialized.append(relative)
            materialized_bytes += value.st_size
        else:
            placeholders.append(relative)
            retained_allocated_bytes += value.st_blocks * 512
    return RetentionPlan(
        root=root,
        cold_paths=tuple(sorted(materialized)),
        cold_bytes=materialized_bytes,
        hot_paths=tuple(sorted(placeholders)),
        hot_bytes=retained_allocated_bytes,
        cutoff_epoch=0.0,
        maximum_hot_bytes=0,
    )


def _inventory(root: Path, relatives: tuple[str, ...]) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    for relative in relatives:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise FileNotFoundError(f"selected file disappeared: {relative}")
        stat = path.stat()
        total += stat.st_size
        digest.update(
            canonical_bytes(
                {
                    "path": relative,
                    "bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "mode": stat.st_mode & 0o777,
                    "inode": stat.st_ino,
                }
            )
            + b"\n"
        )
    return digest.hexdigest(), total


def require_plan_matches_source(plan: RetentionPlan, source: SourceProof) -> None:
    """Fail closed unless the selected cold inventory still matches capture."""

    digest, total = _inventory(plan.root, plan.cold_paths)
    if (
        source.kind != "file-tree"
        or Path(source.path).resolve() != plan.root
        or total != source.bytes
        or digest != source.inventory_after_sha256
    ):
        raise RuntimeError("cold retention plan does not match captured source")


def atomize_file_tree(
    plan: RetentionPlan,
    sink: AtomEmitter,
    *,
    spill_dir: Path | None = None,
    chunk_size: int = 512 * 1024,
) -> FileTreeResult:
    """Emit content-addressed chunks and exact file metadata for the cold set."""

    if chunk_size <= 0:
        raise ValueError("file chunk size must be positive")
    before_digest, before_bytes = _inventory(plan.root, plan.cold_paths)
    emitter = LogicalEmitter(sink)
    tree_digest = hashlib.sha256()
    duplicate_chunks = 0
    temp_parent = str(spill_dir.expanduser().resolve()) if spill_dir else None
    with tempfile.TemporaryDirectory(prefix="limen-agent-tree-", dir=temp_parent) as temporary:
        seen = sqlite3.connect(str(Path(temporary) / "chunks.sqlite3"))
        seen.execute("PRAGMA journal_mode=OFF")
        seen.execute("PRAGMA synchronous=OFF")
        seen.execute("CREATE TABLE chunk (sha256 TEXT PRIMARY KEY) WITHOUT ROWID")
        for relative in plan.cold_paths:
            path = plan.root / relative
            before = path.stat()
            file_digest = hashlib.sha256()
            chunk_hashes: list[str] = []
            with path.open("rb") as handle:
                for value in iter(lambda: handle.read(chunk_size), b""):
                    file_digest.update(value)
                    chunk_hash = hashlib.sha256(b"file-chunk:v1\0" + value).hexdigest()
                    inserted = seen.execute("INSERT OR IGNORE INTO chunk (sha256) VALUES (?)", (chunk_hash,)).rowcount
                    if inserted:
                        emitter.emit(
                            {
                                "kind": "file_chunk",
                                "chunk_sha256": chunk_hash,
                                "value_b64": base64.b64encode(value).decode("ascii"),
                            }
                        )
                    else:
                        duplicate_chunks += 1
                    chunk_hashes.append(chunk_hash)
            after = path.stat()
            identity_before = (before.st_size, before.st_mtime_ns, before.st_ino)
            identity_after = (after.st_size, after.st_mtime_ns, after.st_ino)
            if identity_before != identity_after:
                raise RuntimeError(f"selected file mutated during capture: {relative}")
            entry = {
                "kind": "file_entry",
                "path": relative,
                "bytes": after.st_size,
                "mtime_ns": after.st_mtime_ns,
                "mode": after.st_mode & 0o777,
                "sha256": file_digest.hexdigest(),
                "chunks": chunk_hashes,
            }
            emitter.emit(entry)
            tree_digest.update(canonical_bytes(entry) + b"\n")
        seen.close()
    after_digest, after_bytes = _inventory(plan.root, plan.cold_paths)
    proof = SourceProof(
        path=str(plan.root),
        kind="file-tree",
        bytes=after_bytes,
        sha256=tree_digest.hexdigest(),
        stat_before=(before_bytes, len(plan.cold_paths), 0),
        stat_after=(after_bytes, len(plan.cold_paths), 0),
        inventory_before_sha256=before_digest,
        inventory_after_sha256=after_digest,
    )
    return FileTreeResult(
        source=proof,
        atom_count=emitter.count,
        logical_sha256=emitter.hexdigest,
        duplicate_chunks=duplicate_chunks,
        file_count=len(plan.cold_paths),
    )


def open_files_under(root: Path) -> set[Path]:
    """Return exact paths with open descriptors; failure is fail-closed."""

    result = subprocess.run(["lsof", "-Fn", "+D", str(root)], check=False, capture_output=True, text=True)
    if result.returncode not in {0, 1}:
        raise RuntimeError("cannot inspect open files under retention root")
    return {
        Path(line[1:]).resolve()
        for line in result.stdout.splitlines()
        if line.startswith("n") and line[1:].startswith("/")
    }


def _active_path_conflicts(selected: Iterable[Path], active: Iterable[Path]) -> set[Path]:
    """Return selected paths that are active or descend from an active directory."""

    active_paths = tuple(path.resolve() for path in active)
    return {
        candidate
        for candidate in selected
        if any(candidate.is_relative_to(active_path) for active_path in active_paths)
    }


def retire_cold_files(
    receipt: MetabolismReceipt,
    plan: RetentionPlan,
    *,
    open_probe=open_files_under,
) -> int:
    """Delete only the captured cold files after the receipt's dual gate passes."""

    receipt.require_retirement_gate()
    require_plan_matches_source(plan, receipt.source)
    opened = open_probe(plan.root)
    selected = {(plan.root / relative).resolve() for relative in plan.cold_paths}
    conflicts = _active_path_conflicts(selected, opened)
    if conflicts:
        raise RuntimeError(f"captured cold file is active: {len(conflicts)} open path(s)")
    deleted = 0
    for path in selected:
        path.unlink()
        deleted += 1
    directories = sorted(
        {path.parent for path in selected if path.parent != plan.root},
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        try:
            directory.rmdir()
        except OSError:
            pass
    return deleted


def brctl_evict(path: Path) -> None:
    """Fail closed until a supported host File Provider adapter is installed."""

    raise RuntimeError(
        f"automatic File Provider eviction is disabled for {path.name}: "
        "the host CLI exposes no supported eviction command, and hidden brctl eviction was non-atomic"
    )


def evict_cloud_materializations(
    receipt: MetabolismReceipt,
    plan: RetentionPlan,
    *,
    open_probe: Callable[[Path], set[Path]] = open_files_under,
    evict_command: Callable[[Path], None] = brctl_evict,
    materialized_probe: Callable[[Path], bool] = is_materialized_cloud_path,
    wait: Callable[[float], None] = time.sleep,
    per_file_timeout: float = 30.0,
) -> EvictionResult:
    """Evict captured files through File Provider after dual restoration.

    Paths remain in iCloud Drive as placeholders. A partial command failure is
    safe and resumable: previously evicted files remain remotely addressable,
    while every selected file is already covered by the same restoration gate.
    """

    if per_file_timeout <= 0:
        raise ValueError("per-file eviction timeout must be positive")
    receipt.require_retirement_gate()
    require_plan_matches_source(plan, receipt.source)
    opened = open_probe(plan.root)
    planned = tuple((plan.root / relative).resolve() for relative in plan.cold_paths)
    retained = tuple(path for path in planned if path.name in NON_EVICTABLE_CLOUD_NAMES)
    selected = tuple(path for path in planned if path.name not in NON_EVICTABLE_CLOUD_NAMES)
    conflicts = _active_path_conflicts(selected, opened)
    if conflicts:
        raise RuntimeError(f"captured CloudKit file is active: {len(conflicts)} open path(s)")
    allocated_before = sum(path.stat().st_blocks * 512 for path in selected)
    evicted = 0
    already_reclaimed = 0
    for path in selected:
        if not materialized_probe(path):
            already_reclaimed += 1
            continue
        evict_command(path)
        deadline = time.monotonic() + per_file_timeout
        while materialized_probe(path):
            if time.monotonic() >= deadline:
                raise RuntimeError(f"File Provider did not evict captured path: {path.name}")
            wait(0.1)
        evicted += 1
    remaining = [path for path in selected if materialized_probe(path)]
    if remaining:
        raise RuntimeError(f"File Provider left {len(remaining)} captured path(s) materialized")
    return EvictionResult(
        selected_files=len(selected),
        evicted_files=evicted,
        already_reclaimed_files=already_reclaimed,
        allocated_before=allocated_before,
        allocated_after=0,
        retained_non_evictable_files=len(retained),
        retained_non_evictable_bytes=sum(path.stat().st_blocks * 512 for path in retained),
    )
