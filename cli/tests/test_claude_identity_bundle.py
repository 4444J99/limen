"""Executable contracts for Claude Code's stable disclaimed TCC identity.

Claude Code disclaims its inherited TCC responsibility at startup, so the identity
it lands on is decided entirely by whether `<store>/ClaudeCode.app` is present and
inode-correct. Present -> `com.anthropic.claude-code`, stable across every version.
Absent or stale -> `<store>/versions/<version>`, a new consent client per update.
These tests hold that distinction, including the failure mode that produced it.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/claude-identity-bundle.py"
SPEC = importlib.util.spec_from_file_location("claude_identity_bundle", SCRIPT)
assert SPEC and SPEC.loader
KEEPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(KEEPER)


def _store(tmp_path: Path, version: str = "2.1.222", *, size: int = 64) -> dict[str, str]:
    """A miniature Claude Code store: one runnable version and a launcher symlink."""
    versions = tmp_path / "store/versions"
    versions.mkdir(parents=True)
    binary = versions / version
    binary.write_bytes(b"\x00" * size)
    binary.chmod(0o755)

    launcher = tmp_path / "bin/claude"
    launcher.parent.mkdir(parents=True)
    launcher.symlink_to(binary)

    return {
        "HOME": str(tmp_path),
        "LIMEN_CLAUDE_STORE": str(tmp_path / "store"),
        "LIMEN_CLAUDE_LAUNCHER": str(launcher),
    }


def test_absent_bundle_is_distance_not_silence(tmp_path: Path):
    """The whole defect is silent fallback, so absence must be loud and enumerated."""
    payload = KEEPER.inspect(_store(tmp_path))

    assert payload["ok"] is False
    assert payload["status"] == "distance-remains"
    assert set(payload["findings"]) == {
        "bundle_absent",
        "info_plist_missing_or_divergent",
        "hardlink_absent_or_stale",
    }


def test_repair_reaches_the_ideal_and_is_idempotent(tmp_path: Path):
    env = _store(tmp_path)

    first = KEEPER.repair(env)
    assert first["ok"] is True
    assert first["status"] == "at-ideal"
    assert first["repaired"] is True

    second = KEEPER.repair(env)
    assert second["ok"] is True
    assert second["actions"] == []
    assert second["repaired"] is False


def test_repaired_hardlink_shares_the_running_binary_inode(tmp_path: Path):
    """Inode identity is the ENTIRE predicate: the vendor's early return is
    `if ((await stat(r)).ino === n) return r`. A same-content copy would still
    take the unlink/link path this organ exists to keep closed."""
    env = _store(tmp_path)
    KEEPER.repair(env)

    link = Path(env["LIMEN_CLAUDE_STORE"]) / "ClaudeCode.app/Contents/MacOS/claude"
    binary = Path(env["LIMEN_CLAUDE_STORE"]) / "versions/2.1.222"

    assert link.stat().st_ino == binary.stat().st_ino


def test_hardlink_to_a_superseded_version_is_stale_not_ok(tmp_path: Path):
    """The post-update state: the bundle exists, but points at yesterday's binary.

    This reads as "present" to any existence check, and it is exactly the state in
    which the vendor unlinks and re-links -- reopening the race window.
    """
    env = _store(tmp_path)
    KEEPER.repair(env)

    versions = Path(env["LIMEN_CLAUDE_STORE"]) / "versions"
    updated = versions / "2.1.223"
    updated.write_bytes(b"\x01" * 64)
    updated.chmod(0o755)
    launcher = Path(env["LIMEN_CLAUDE_LAUNCHER"])
    launcher.unlink()
    launcher.symlink_to(updated)

    stale = KEEPER.inspect(env)
    assert stale["ok"] is False
    assert stale["findings"] == ["hardlink_absent_or_stale"]

    healed = KEEPER.repair(env)
    assert healed["ok"] is True
    assert "removed_stale_hardlink" in healed["actions"]
    assert "linked_current_binary" in healed["actions"]


def test_divergent_info_plist_is_rewritten_to_the_vendor_bytes(tmp_path: Path):
    """A plist that differs would be overwritten by the vendor on every start; the
    keeper writing anything else would be permanent churn, not a fixed point."""
    env = _store(tmp_path)
    KEEPER.repair(env)
    plist = Path(env["LIMEN_CLAUDE_STORE"]) / "ClaudeCode.app/Contents/Info.plist"
    plist.write_text("<plist>tampered</plist>", encoding="utf-8")

    assert KEEPER.inspect(env)["findings"] == ["info_plist_missing_or_divergent"]

    KEEPER.repair(env)
    assert plist.read_text(encoding="utf-8") == KEEPER.INFO_PLIST
    assert KEEPER.inspect(env)["ok"] is True


def test_launcher_outside_the_versions_tree_is_unmeasured_never_repaired(tmp_path: Path):
    """The vendor creates no bundle unless execPath is under `versions/`. Repairing
    into that state would fabricate an identity for a binary that will never adopt
    it -- so this reports `unmeasured` and touches nothing (the same third-verdict
    discipline the TCC audit carries)."""
    env = _store(tmp_path)
    elsewhere = tmp_path / "elsewhere/claude"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_bytes(b"\x00" * 64)
    elsewhere.chmod(0o755)
    launcher = Path(env["LIMEN_CLAUDE_LAUNCHER"])
    launcher.unlink()
    launcher.symlink_to(elsewhere)

    payload = KEEPER.inspect(env)
    assert payload["status"] == "unmeasured"
    assert payload["ok"] is False
    assert payload["findings"] == ["launcher_unresolvable"]

    outcome = KEEPER.repair(env)
    assert outcome["actions"] == []
    assert not (Path(env["LIMEN_CLAUDE_STORE"]) / "ClaudeCode.app").exists()


def test_two_runnable_versions_are_reported_as_a_standing_race_risk(tmp_path: Path):
    """Concurrent starts of DIFFERENT versions have different inodes, so each one
    unlinks the other's link. The keeper cannot fix that -- deleting a vendor
    version is not its authority -- so it must surface it rather than imply green."""
    env = _store(tmp_path)
    older = Path(env["LIMEN_CLAUDE_STORE"]) / "versions/2.1.220"
    older.write_bytes(b"\x02" * 64)
    older.chmod(0o755)

    payload = KEEPER.repair(env)
    assert payload["ok"] is True
    assert payload["concurrent_version_race_risk"] is True

    empty = Path(env["LIMEN_CLAUDE_STORE"]) / "versions/2.1.221"
    empty.write_bytes(b"")
    runnable = [item["version"] for item in KEEPER.inspect(env)["versions"] if item["runnable"]]
    assert "2.1.221" not in runnable, "a zero-byte install artifact is not a runnable version"


def test_non_darwin_is_not_applicable_rather_than_a_failure(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(KEEPER.platform, "system", lambda: "Linux")

    payload = KEEPER.inspect(_store(tmp_path))
    assert payload["ok"] is True
    assert payload["status"] == "not-applicable"


def test_cli_exit_code_tracks_the_predicate(tmp_path: Path, monkeypatch, capsys):
    env = _store(tmp_path)
    monkeypatch.setattr(os, "environ", {**os.environ, **env})

    assert KEEPER.main([]) == 1
    assert KEEPER.main(["--repair"]) == 0
    assert KEEPER.main([]) == 0
    capsys.readouterr()
