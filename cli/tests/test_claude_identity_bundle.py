"""Executable contracts for the `<store>/ClaudeCode.app` identity bundle.

TCC names a client by the bundle enclosing the path it was exec'd from -- never by
the bytes. `<store>/ClaudeCode.app/Contents/MacOS/claude` and
`<store>/versions/<version>` are the *same inode*, yet the first resolves to
`com.anthropic.claude-code` (stable across every update) and the second, having no
enclosing bundle, is named by its own filename -- a fresh consent client per version.

Scope, stated honestly (verified 2026-08-05 against a live process tree): keeping this
bundle present and inode-correct does NOT by itself stop per-version consent prompts.
Claude Code's daemon runs its pty host from the bundle but hands the *session* process
its `versions/<version>` path as literal argv, and that session is what disclaims into
its own TCC identity. That argv is vendor-internal. What these contracts hold is the
bundle's own correctness -- the precondition, not the whole cure.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/claude-identity-bundle.py"
SPEC = importlib.util.spec_from_file_location("claude_identity_bundle", SCRIPT)
assert SPEC and SPEC.loader
KEEPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(KEEPER)


@pytest.fixture(autouse=True)
def _force_darwin(monkeypatch):
    """Hold the keeper's real logic on every platform, not just the author's laptop.

    Only the *gate* is platform-specific -- the bundle work underneath is ordinary
    filesystem work that runs anywhere. Without this, CI (Linux) short-circuits to
    `not-applicable` and every contract below silently asserts against the gate
    instead of the behavior it exists to hold. The non-darwin test re-patches this
    to Linux, which wins because a test's own monkeypatch runs after the autouse one.
    """
    monkeypatch.setattr(KEEPER.platform, "system", lambda: "Darwin")

    # Cut the two HOST probes the class enumeration would otherwise shell out to. `lsregister -dump`
    # alone costs ~2.85s per call, which turned this suite into a 78s host-dependent integration
    # run; and a contract that consults the author's real LaunchServices is not a contract. Both
    # degrade to the third verdict (`None` = unknown), which the tests below assert is never green.
    # A test that needs a definite answer injects one: LIMEN_CLAUDE_LSREGISTER_DUMP for registration
    # (the env branch is read first, so it still wins here), or monkeypatching `_assessable`.
    monkeypatch.setattr(KEEPER, "LSREGISTER", "/nonexistent/lsregister")
    monkeypatch.setattr(KEEPER.shutil, "which", lambda name: None)


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


# --------------------------------------------------------------------------------------
# IF-GATEKEEPER-INERT: the class enumeration.
#
# The same bundle that carries the TCC identity is what macOS renders as "damaged", because a
# bare-Mach-O signature seals no resources while bundle-form `codesign --strict` demands a
# CodeResources it never sealed. Presence is therefore NOT the defect -- registration is. These
# contracts hold the split: what the keeper repairs (the store bundle) vs what it only measures
# (a bundle in the LaunchServices-scanned ~/Applications domain, homed on a lever).
# --------------------------------------------------------------------------------------


def _dump(tmp_path: Path, *paths: str) -> str:
    """A canned `lsregister -dump`, so registration state is asserted without LaunchServices."""
    capture = tmp_path / "lsregister.txt"
    capture.write_text("\n".join(f"path:  {p}" for p in paths) + "\n", encoding="utf-8")
    return str(capture)


def test_instances_enumerate_the_whole_vendor_class_not_just_the_store(tmp_path, monkeypatch):
    """A lens that judges one domain scores the sprawl green (IF-AGENT-IDENTITY's own rule)."""
    env = _store(tmp_path)
    env["LIMEN_CLAUDE_LSREGISTER_DUMP"] = _dump(tmp_path)
    monkeypatch.setattr(KEEPER, "_assessable", lambda path: False)

    paths = [record["path"] for record in KEEPER.inspect(env)["instances"]]
    assert str(tmp_path / "store" / KEEPER.BUNDLE_NAME) in paths
    assert str(tmp_path / "Applications" / KEEPER.URL_HANDLER_NAME) in paths


def test_registered_and_unassessable_is_class_distance_but_not_repairable_distance(tmp_path, monkeypatch):
    """The finding must surface under --strict without making the beat step escalate forever."""
    env = _store(tmp_path)
    handler = tmp_path / "Applications" / KEEPER.URL_HANDLER_NAME
    (handler / "Contents/MacOS").mkdir(parents=True)
    env["LIMEN_CLAUDE_LSREGISTER_DUMP"] = _dump(tmp_path, str(handler))
    monkeypatch.setattr(KEEPER, "_assessable", lambda path: False)

    KEEPER.repair(env)
    payload = KEEPER.inspect(env)

    assert payload["findings"] == []
    assert payload["ok"] is True
    assert payload["status"] == "at-ideal"
    assert "registered_unassessable_bundle" in payload["class_findings"]
    assert payload["strict_ok"] is False


def test_repair_never_touches_a_bundle_outside_the_store(tmp_path, monkeypatch):
    """Measured, never mutated: re-linking or re-signing a vendor bundle is not this authority."""
    env = _store(tmp_path)
    handler = tmp_path / "Applications" / KEEPER.URL_HANDLER_NAME
    (handler / "Contents/MacOS").mkdir(parents=True)
    (handler / "Contents/Info.plist").write_text("sentinel", encoding="utf-8")
    env["LIMEN_CLAUDE_LSREGISTER_DUMP"] = _dump(tmp_path, str(handler))
    monkeypatch.setattr(KEEPER, "_assessable", lambda path: False)

    KEEPER.repair(env)

    assert (handler / "Contents/Info.plist").read_text(encoding="utf-8") == "sentinel"
    assert not (handler / "Contents/MacOS/claude").exists()


def test_unreadable_launchservices_is_never_reported_as_inert(tmp_path, monkeypatch):
    """A blind read may not register as at-ideal -- absence of a dialog is not evidence.

    This is the defect IF-AGENT-IDENTITY was rewritten to forbid, one domain over: without this,
    a host where lsregister cannot be run reports zero registrations and the probe goes green.
    """
    env = _store(tmp_path)
    monkeypatch.setattr(KEEPER, "_registered_paths", lambda values: None)
    monkeypatch.setattr(KEEPER, "_assessable", lambda path: False)

    KEEPER.repair(env)
    payload = KEEPER.inspect(env)

    assert all(record["ls_registered"] is None for record in payload["instances"])
    assert "registration_unmeasured" in payload["class_findings"]
    assert payload["strict_ok"] is False
    assert payload["ok"] is True  # the repairable half is still honestly green


def test_strict_flag_is_what_separates_the_two_exit_codes(tmp_path, monkeypatch):
    """`--repair` keeps the beat quiet; `--strict` is the ideal-form probe."""
    env = _store(tmp_path)
    handler = tmp_path / "Applications" / KEEPER.URL_HANDLER_NAME
    (handler / "Contents/MacOS").mkdir(parents=True)
    env["LIMEN_CLAUDE_LSREGISTER_DUMP"] = _dump(tmp_path, str(handler))
    monkeypatch.setattr(KEEPER, "_assessable", lambda path: False)
    monkeypatch.setattr(os, "environ", {**os.environ, **env})

    assert KEEPER.main(["--repair"]) == 0
    assert KEEPER.main([]) == 0
    assert KEEPER.main(["--strict"]) == 1
