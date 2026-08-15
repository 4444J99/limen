"""Regression tests for scripts/claude-identity-bundle.py.

Guards two install layouts the launcher can resolve through:
  - the legacy npm-style layout, where `versions/<v>` is a raw binary the vendor's
    own `_jb()` still needs to hardlink into the bundle
  - the native-installer layout, where `versions/<v>` is ALREADY a symlink straight
    into the bundle -- verified live 2026-08-15 on `versions/2.1.233`. A strict
    resolve of the launcher then lands on the bundle's own binary, which sits
    outside `versions/`, and the pre-fix `_current_binary()` misread that as
    `launcher_unresolvable` -- an already-healed install reporting itself broken,
    forever, because `repair()` returns early on that same error.
"""

import importlib.util
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "claude-identity-bundle.py"
    spec = importlib.util.spec_from_file_location("claude_identity_bundle", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _env(tmp_path: Path, launcher: Path) -> dict:
    return {
        "HOME": str(tmp_path),
        "LIMEN_CLAUDE_STORE": str(tmp_path / "store"),
        "LIMEN_CLAUDE_LAUNCHER": str(launcher),
        "LIMEN_CLAUDE_LSREGISTER_DUMP": str(tmp_path / "missing-dump"),  # forces ls_registered=None, no subprocess
    }


def test_legacy_raw_version_still_needs_and_gets_repair(tmp_path):
    store = tmp_path / "store"
    (store / "versions").mkdir(parents=True)
    binary = store / "versions" / "9.9.9"
    binary.write_bytes(b"\x00" * 16)
    binary.chmod(0o755)
    launcher = tmp_path / "bin-claude"
    launcher.symlink_to(binary)

    module = _module()
    env = _env(tmp_path, launcher)

    before = module.inspect(env)
    assert before["ok"] is False
    assert "hardlink_absent_or_stale" in before["findings"]

    after = module.repair(env)
    assert after["ok"] is True
    assert after["status"] == "at-ideal"
    assert "linked_current_binary" in after["actions"]

    link = store / module.BUNDLE_NAME / "Contents/MacOS/claude"
    assert link.stat().st_ino == binary.stat().st_ino


def test_native_installer_already_symlinked_reads_at_ideal_without_repair(tmp_path):
    store = tmp_path / "store"
    bundle_macos = store / module_bundle_name(_module()) / "Contents/MacOS"
    bundle_macos.mkdir(parents=True)
    bundle_binary = bundle_macos / "claude"
    bundle_binary.write_bytes(b"\x00" * 16)
    bundle_binary.chmod(0o755)
    (bundle_macos.parent / "Info.plist").write_text(_module().INFO_PLIST, encoding="utf-8")

    (store / "versions").mkdir(parents=True)
    version_link = store / "versions" / "2.1.233"
    version_link.symlink_to(bundle_binary)
    launcher = tmp_path / "bin-claude"
    launcher.symlink_to(version_link)

    module = _module()
    env = _env(tmp_path, launcher)

    result = module.inspect(env)
    assert result.get("error") is None, result.get("error")
    assert result["current_binary"] == str(bundle_binary.resolve())
    assert result["hardlink_inode_matches"] is True
    assert result["status"] == "at-ideal"
    assert result["ok"] is True

    # repair() must be a true no-op here -- nothing to link, nothing to write
    repaired = module.repair(env)
    assert repaired["actions"] == []


def module_bundle_name(module) -> str:
    return module.BUNDLE_NAME
