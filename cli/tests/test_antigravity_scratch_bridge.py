from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "antigravity-scratch-bridge.py"


def _load():
    spec = importlib.util.spec_from_file_location("antigravity_scratch_bridge", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _make_remote_preserved_repo(root: Path, name: str = "clean-root") -> Path:
    remote_parent = root.parent.parent if root.parent != root else root.parent
    remote = remote_parent / f"{name}.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    repo = root / name
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "test@example.invalid"], repo)
    _git(["config", "user.name", "Test User"], repo)
    (repo / "README.md").write_text("preserved\n", encoding="utf-8")
    _git(["add", "README.md"], repo)
    _git(["commit", "-qm", "init"], repo)
    _git(["remote", "add", "origin", str(remote)], repo)
    _git(["push", "-q", "-u", "origin", "main"], repo)
    return repo


def test_clean_remote_preserved_root_is_reap_candidate(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    _make_remote_preserved_repo(scratch)

    report = bridge.build_report(scratch, min_idle_hours=0)
    row = report["roots"][0]

    assert row["name"] == "clean-root"
    assert row["kind"] == "git"
    assert row["disposition"] == "safe_reap_candidate"
    assert row["remote_preserved"] is True
    assert report["summary"]["by_disposition"] == {"safe_reap_candidate": 1}


def test_dirty_root_requires_bridge(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    repo = _make_remote_preserved_repo(scratch, "dirty-root")
    (repo / "new_delta.py").write_text("unbridged work\n", encoding="utf-8")

    report = bridge.build_report(scratch, min_idle_hours=0)
    row = report["roots"][0]

    assert row["disposition"] == "bridge_required"
    assert row["reason"] == "dirty-or-untracked"
    assert row["dirty_entries"] == 1


def test_container_root_requires_nested_review(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    parent = scratch / "container"
    parent.mkdir()
    nested = parent / "nested-repo"
    _make_remote_preserved_repo(parent, "nested-repo")
    assert nested.exists()

    report = bridge.build_report(scratch, min_idle_hours=0)
    row = report["roots"][0]

    assert row["name"] == "container"
    assert row["kind"] == "container"
    assert row["disposition"] == "container_review_required"
    assert row["nested_git_roots"] == 1
    assert row["nested_by_disposition"] == {"safe_reap_candidate": 1}


def test_apply_safe_reap_deletes_only_reclassified_candidates(tmp_path: Path):
    bridge = _load()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    clean = _make_remote_preserved_repo(scratch, "clean-root")
    dirty = _make_remote_preserved_repo(scratch, "dirty-root")
    (dirty / "new_delta.py").write_text("unbridged work\n", encoding="utf-8")

    report = bridge.build_report(scratch, min_idle_hours=0)
    reap = bridge.apply_safe_reap(report, min_idle_hours=0)

    assert reap["summary"]["reaped"] == 1
    assert reap["summary"]["skipped"] == 0
    assert reap["summary"]["failed"] == 0
    assert not clean.exists()
    assert dirty.exists()
