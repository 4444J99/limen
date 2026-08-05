from __future__ import annotations

import subprocess
from pathlib import Path

from limen.growth_admission import GROWTH_ADMISSION_SCHEMA, inspect_growth


def _repo(root: Path) -> Path:
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    return root


def test_small_untracked_text_is_admitted_with_versioned_receipt(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    (root / "notes.txt").write_text("bounded\n", encoding="utf-8")

    result = inspect_growth(root, max_new_text_file_bytes=64, max_untracked_text_bytes=128)

    assert result.schema == GROWTH_ADMISSION_SCHEMA
    assert result.allowed is True
    assert result.untracked_text_bytes == len("bounded\n")


def test_oversized_new_text_blocks_without_deleting_it(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    payload = root / "large.txt"
    payload.write_text("x" * 65, encoding="utf-8")

    result = inspect_growth(root, max_new_text_file_bytes=64, max_untracked_text_bytes=256)

    assert result.allowed is False
    assert result.reason == "new-text-file-exceeds-8-mib"
    assert result.oversized_text_paths == ("large.txt",)
    assert payload.read_text(encoding="utf-8") == "x" * 65


def test_aggregate_untracked_text_limit_blocks_without_deleting_files(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    first = root / "first.txt"
    second = root / "second.txt"
    first.write_text("a" * 40, encoding="utf-8")
    second.write_text("b" * 40, encoding="utf-8")

    result = inspect_growth(root, max_new_text_file_bytes=64, max_untracked_text_bytes=79)

    assert result.allowed is False
    assert result.reason == "untracked-text-exceeds-64-mib"
    assert first.exists() and second.exists()


def test_binary_files_do_not_count_as_untracked_text(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    (root / "blob.bin").write_bytes(b"\0" + b"x" * 100)

    result = inspect_growth(root, max_new_text_file_bytes=16, max_untracked_text_bytes=16)

    assert result.allowed is True
    assert result.untracked_text_bytes == 0


def test_nested_repository_blocks_without_removing_nested_state(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    nested = root / "vendor"
    subprocess.run(["git", "init", "-q", str(nested)], check=True)

    result = inspect_growth(root)

    assert result.allowed is False
    assert result.reason == "nested-repository"
    assert result.nested_repository_paths == ("vendor/.git",)
    assert (nested / ".git").exists()


def test_scan_exhaustion_fails_closed_at_exact_bound(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    for index in range(5):
        (root / f"path-{index}.txt").write_text("x", encoding="utf-8")

    result = inspect_growth(root, max_scanned_paths=3)

    assert result.allowed is False
    assert result.reason == "growth-scan-exhausted"
    assert result.scanned_paths == 3
    assert result.scan_exhausted is True


def test_projected_new_write_is_denied_before_crossing_file_limit(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    target = root / "future.txt"

    result = inspect_growth(
        root,
        target_paths=[target],
        tool_input={"content": "x" * 65},
        max_new_text_file_bytes=64,
        max_untracked_text_bytes=256,
    )

    assert result.allowed is False
    assert result.reason == "new-text-file-exceeds-8-mib"
    assert not target.exists()


def test_projected_new_write_is_denied_before_crossing_aggregate_limit(tmp_path: Path) -> None:
    root = _repo(tmp_path / "repo")
    (root / "existing.txt").write_text("x" * 60, encoding="utf-8")
    target = root / "future.txt"

    result = inspect_growth(
        root,
        target_paths=[target],
        tool_input={"content": "12345"},
        max_new_text_file_bytes=64,
        max_untracked_text_bytes=64,
    )

    assert result.allowed is False
    assert result.reason == "untracked-text-exceeds-64-mib"
    assert not target.exists()
