"""Bounded, read-only growth admission for linked worktree writes."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

GROWTH_ADMISSION_SCHEMA = "limen.growth_admission.v1"
MAX_NEW_TEXT_FILE_BYTES = 8 * 1024**2
MAX_UNTRACKED_TEXT_BYTES = 64 * 1024**2
MAX_SCANNED_PATHS = 10_000
_TEXT_SAMPLE_BYTES = 8 * 1024


@dataclass(frozen=True)
class GrowthAdmission:
    schema: str
    allowed: bool
    reason: str
    scanned_paths: int
    untracked_text_bytes: int
    oversized_text_paths: tuple[str, ...]
    nested_repository_paths: tuple[str, ...]
    scan_exhausted: bool


class GrowthScanError(RuntimeError):
    """The worktree cannot be bounded or classified safely."""


def _relative_git_paths(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard", "-z"],
            capture_output=True,
            text=False,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GrowthScanError("untracked-path-scan-unavailable") from exc
    if result.returncode != 0:
        raise GrowthScanError("untracked-path-scan-unavailable")
    paths: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            value = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GrowthScanError("untracked-path-is-not-utf8") from exc
        pure = PurePosixPath(value)
        if pure.is_absolute() or not pure.parts or ".." in pure.parts:
            raise GrowthScanError("untracked-path-escapes-worktree")
        paths.append(value)
    return paths


def _walk_bounded(root: Path, max_scanned_paths: int) -> tuple[int, tuple[str, ...], bool]:
    scanned = 0
    nested: list[str] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as exc:
            raise GrowthScanError("worktree-path-scan-unavailable") from exc
        for entry in entries:
            scanned += 1
            if scanned > max_scanned_paths:
                return max_scanned_paths, tuple(nested), True
            path = Path(entry.path)
            if entry.name == ".git":
                if directory != root:
                    nested.append(path.relative_to(root).as_posix())
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
            except OSError as exc:
                raise GrowthScanError("worktree-path-scan-unavailable") from exc
    return scanned, tuple(nested), False


def _looks_like_text(path: Path, size: int) -> bool:
    if size == 0:
        return True
    try:
        with path.open("rb") as handle:
            start = handle.read(_TEXT_SAMPLE_BYTES)
            end = b""
            if size > _TEXT_SAMPLE_BYTES:
                handle.seek(max(0, size - _TEXT_SAMPLE_BYTES))
                end = handle.read(_TEXT_SAMPLE_BYTES)
    except OSError as exc:
        raise GrowthScanError("untracked-text-sample-unavailable") from exc
    sample = start + end
    if b"\0" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _projected_new_text(
    root: Path,
    target_paths: Sequence[Path],
    tool_input: Mapping[str, Any] | None,
) -> tuple[int, int]:
    if not tool_input:
        return 0, 0
    content = tool_input.get("content")
    if not isinstance(content, str):
        return 0, 0
    encoded_size = len(content.encode("utf-8"))
    new_targets = 0
    for target in target_paths:
        try:
            target.relative_to(root)
        except ValueError:
            continue
        if not target.exists():
            new_targets += 1
    return new_targets, encoded_size


def inspect_growth(
    root: Path,
    *,
    target_paths: Sequence[Path] = (),
    tool_input: Mapping[str, Any] | None = None,
    max_new_text_file_bytes: int = MAX_NEW_TEXT_FILE_BYTES,
    max_untracked_text_bytes: int = MAX_UNTRACKED_TEXT_BYTES,
    max_scanned_paths: int = MAX_SCANNED_PATHS,
) -> GrowthAdmission:
    """Inspect one worktree without modifying or deleting any path."""

    root = root.resolve(strict=True)
    if not root.is_dir():
        raise GrowthScanError("worktree-root-not-directory")
    if min(max_new_text_file_bytes, max_untracked_text_bytes, max_scanned_paths) <= 0:
        raise ValueError("growth admission limits must be positive")

    scanned, nested, exhausted = _walk_bounded(root, max_scanned_paths)
    if exhausted:
        return GrowthAdmission(
            GROWTH_ADMISSION_SCHEMA,
            False,
            "growth-scan-exhausted",
            scanned,
            0,
            (),
            nested,
            True,
        )
    if nested:
        return GrowthAdmission(
            GROWTH_ADMISSION_SCHEMA,
            False,
            "nested-repository",
            scanned,
            0,
            (),
            nested,
            False,
        )

    aggregate = 0
    oversized: list[str] = []
    for relative in _relative_git_paths(root):
        path = root / relative
        try:
            stat = path.lstat()
        except OSError as exc:
            raise GrowthScanError("untracked-path-stat-unavailable") from exc
        if not path.is_file() or path.is_symlink():
            continue
        size = stat.st_size
        if not _looks_like_text(path, size):
            continue
        aggregate += size
        if size > max_new_text_file_bytes:
            oversized.append(relative)

    new_target_count, projected_size = _projected_new_text(root, target_paths, tool_input)
    if new_target_count and projected_size > max_new_text_file_bytes:
        oversized.extend(
            path.relative_to(root).as_posix()
            for path in target_paths
            if not path.exists() and path.is_relative_to(root)
        )
    projected_aggregate = aggregate + (new_target_count * projected_size)
    if oversized:
        return GrowthAdmission(
            GROWTH_ADMISSION_SCHEMA,
            False,
            "new-text-file-exceeds-8-mib",
            scanned,
            aggregate,
            tuple(sorted(set(oversized))),
            (),
            False,
        )
    if projected_aggregate > max_untracked_text_bytes:
        return GrowthAdmission(
            GROWTH_ADMISSION_SCHEMA,
            False,
            "untracked-text-exceeds-64-mib",
            scanned,
            aggregate,
            (),
            (),
            False,
        )
    return GrowthAdmission(
        GROWTH_ADMISSION_SCHEMA,
        True,
        "",
        scanned,
        aggregate,
        (),
        (),
        False,
    )


__all__ = [
    "GROWTH_ADMISSION_SCHEMA",
    "MAX_NEW_TEXT_FILE_BYTES",
    "MAX_SCANNED_PATHS",
    "MAX_UNTRACKED_TEXT_BYTES",
    "GrowthAdmission",
    "GrowthScanError",
    "inspect_growth",
]
