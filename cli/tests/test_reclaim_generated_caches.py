from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "reclaim-generated-caches.py"


def load_module():
    spec = importlib.util.spec_from_file_location("reclaim_generated_caches", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repository(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Test"], check=True)
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
    (root / "package-lock.json").write_text("{}\n", encoding="utf-8")
    cache = root / "node_modules"
    cache.mkdir()
    (cache / "dependency.js").write_bytes(b"x" * 4096)
    subprocess.run(["git", "-C", str(root), "add", ".gitignore", "package-lock.json"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
    return root, cache


def test_scan_selects_only_inactive_ignored_locked_dependency_cache(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    root, cache = repository(tmp_path)
    monkeypatch.setattr(module, "active_cwds", lambda: set())
    monkeypatch.setattr(module, "directory_size", lambda _path: 4096)

    candidates = module.scan(tmp_path, minimum_bytes=1)

    assert candidates == [
        {
            "path": str(cache.resolve()),
            "repo_root": str(root.resolve()),
            "size_bytes": 4096,
            "recovery": "reinstall from repository lockfile",
        }
    ]


def test_scan_excludes_active_repo_and_unignored_cache(tmp_path: Path, monkeypatch) -> None:
    module = load_module()
    root, _cache = repository(tmp_path)
    monkeypatch.setattr(module, "active_cwds", lambda: {root})
    assert module.scan(tmp_path, minimum_bytes=1) == []

    monkeypatch.setattr(module, "active_cwds", lambda: set())
    (root / ".gitignore").write_text("", encoding="utf-8")
    assert module.scan(tmp_path, minimum_bytes=1) == []


def test_check_apply_digest_fails_closed_on_candidate_drift(tmp_path: Path) -> None:
    _root, cache = repository(tmp_path)
    check = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--check",
            "--json",
            "--workspace-root",
            str(tmp_path),
            "--minimum-mib",
            "0",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    plan = json.loads(check.stdout)
    (cache / "drift.js").write_text("changed\n", encoding="utf-8")

    apply = subprocess.run(
        [
            "python3",
            str(SCRIPT),
            "--apply",
            "--json",
            "--workspace-root",
            str(tmp_path),
            "--minimum-mib",
            "0",
            "--expected-plan-sha",
            plan["plan_sha256"],
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert apply.returncode == 3
    assert cache.is_dir()
