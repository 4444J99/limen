from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_module():
    source = ROOT / "scripts" / "worktree-preserve-dirty.py"
    spec = importlib.util.spec_from_file_location("worktree_preserve_dirty", source)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def make_repo(tmp_path: Path, name: str = "owner-repo") -> Path:
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    git(repo, "config", "user.name", "Test User")
    git(repo, "config", "user.email", "test@example.com")
    (repo / "tracked.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "tracked.txt")
    git(repo, "commit", "-m", "base")
    git(repo, "remote", "add", "origin", f"https://github.com/example/{name}.git")
    return repo


def configure_paths(module, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "limen"
    private_root = root / ".limen-private" / "session-corpus" / "lifecycle" / "worktree-preserve"
    monkeypatch.setattr(module, "ROOT", root)
    monkeypatch.setattr(module, "PRIVATE_ROOT", private_root)
    monkeypatch.setattr(module, "PRESERVATION_RECEIPTS", root / "docs" / "worktree-preservation-receipts.json")
    return root


def dirty_item(repo: Path) -> dict[str, object]:
    return {"debt": True, "name": repo.name, "path": str(repo), "reason": "dirty"}


def test_prepare_item_streams_bounded_patch_and_bounds_public_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    configure_paths(module, tmp_path, monkeypatch)
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()

    prepared = module.prepare_item(dirty_item(repo), staging, 1024 * 1024)
    receipt = prepared["receipt"]

    assert prepared["staged_patch"].is_file()
    assert prepared["staged_patch"].stat().st_size == receipt["dirty_patch_bytes"]
    assert module.file_sha256(prepared["staged_patch"]) == receipt["dirty_patch_sha256"]
    assert "worktree_status" not in receipt
    assert receipt["worktree_status_count"] == 2
    assert len(receipt["worktree_status_sample"]) <= module.PUBLIC_SAMPLE_LIMIT
    assert receipt["untracked_paths_count"] == 0


def test_prepare_item_fails_closed_on_untracked_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    root = configure_paths(module, tmp_path, monkeypatch)
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (repo / "untracked.bin").write_bytes(b"not represented by git diff HEAD")
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(module.PreservationError, match="untracked path"):
        module.prepare_item(dirty_item(repo), staging, 1024 * 1024)

    assert list(staging.iterdir()) == []
    assert not (root / "docs" / "worktree-preservation-receipts.json").exists()
    assert not module.PRIVATE_ROOT.exists()


def test_prepare_item_removes_partial_patch_when_byte_ceiling_is_exceeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    configure_paths(module, tmp_path, monkeypatch)
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("x" * 8192, encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(module.PreservationError, match="per-item ceiling"):
        module.prepare_item(dirty_item(repo), staging, 128)

    assert list(staging.iterdir()) == []


def test_prepare_item_fails_closed_when_source_changes_during_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    configure_paths(module, tmp_path, monkeypatch)
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("first state\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    real_capture = module.stream_git_patch

    def capture_then_change(path: Path, destination: Path, max_bytes: int):
        capture = real_capture(path, destination, max_bytes)
        (repo / "tracked.txt").write_text("second state\n", encoding="utf-8")
        return capture

    monkeypatch.setattr(module, "stream_git_patch", capture_then_change)

    with pytest.raises(module.PreservationError, match="changed during capture"):
        module.prepare_item(dirty_item(repo), staging, 1024 * 1024)

    assert list(staging.iterdir()) == []


def test_candidate_receipt_removes_unbounded_legacy_fields_and_preserves_owner_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    configure_paths(module, tmp_path, monkeypatch)
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("changed\n", encoding="utf-8")
    staging = tmp_path / "staging"
    staging.mkdir()
    prepared = module.prepare_item(dirty_item(repo), staging, 1024 * 1024)
    existing = {
        "dirty_paths": ["legacy.py"],
        "evidence_updated_utc": "2026-07-01T00:00:00Z",
        "owner_context": "retain this reviewed field",
        "root": repo.name,
        "untracked_paths": ["legacy.bin"],
        "worktree_status": ["M legacy.py"] * 1000,
    }

    candidate = module.candidate_receipt(existing, prepared)

    assert candidate["owner_context"] == "retain this reviewed field"
    assert candidate["evidence_updated_utc"] == "2026-07-01T00:00:00Z"
    assert "dirty_paths" not in candidate
    assert "untracked_paths" not in candidate
    assert "worktree_status" not in candidate
    assert len(candidate["worktree_status_sample"]) <= module.PUBLIC_SAMPLE_LIMIT


def test_apply_is_content_addressed_and_byte_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    root = configure_paths(module, tmp_path, monkeypatch)
    repo = make_repo(tmp_path)
    (repo / "tracked.txt").write_text("changed once\n", encoding="utf-8")
    monkeypatch.setattr(module, "worktree_debt_report", lambda _root: {"items": [dirty_item(repo)]})
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worktree-preserve-dirty.py",
            "--apply",
            "--json",
            "--max-patch-bytes",
            str(1024 * 1024),
            "--max-total-patch-bytes",
            str(1024 * 1024),
        ],
    )

    assert module.main() == 0
    ledger = root / "docs" / "worktree-preservation-receipts.json"
    first = ledger.read_bytes()
    first_dirs = sorted(path.name for path in module.PRIVATE_ROOT.iterdir())
    receipt = json.loads(first)["receipts"][0]
    assert "worktree_status" not in receipt
    assert Path(root / receipt["private_patch"]).is_file()

    assert module.main() == 0
    assert ledger.read_bytes() == first
    assert sorted(path.name for path in module.PRIVATE_ROOT.iterdir()) == first_dirs


def test_aggregate_ceiling_fails_before_any_durable_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_module()
    root = configure_paths(module, tmp_path, monkeypatch)
    first = make_repo(tmp_path, "first")
    second = make_repo(tmp_path, "second")
    (first / "tracked.txt").write_text("a" * 1024, encoding="utf-8")
    (second / "tracked.txt").write_text("b" * 1024, encoding="utf-8")
    monkeypatch.setattr(
        module,
        "worktree_debt_report",
        lambda _root: {"items": [dirty_item(first), dirty_item(second)]},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "worktree-preserve-dirty.py",
            "--apply",
            "--json",
            "--max-patch-bytes",
            "1500",
            "--max-total-patch-bytes",
            "1500",
        ],
    )

    assert module.main() == 1
    assert not (root / "docs" / "worktree-preservation-receipts.json").exists()
    assert not module.PRIVATE_ROOT.exists()
